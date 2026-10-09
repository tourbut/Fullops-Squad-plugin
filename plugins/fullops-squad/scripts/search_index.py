"""Git 원문에서 추출한 메타데이터를 작업 트리별 JSON에 재사용한다. 본문은 저장하지 않는다."""
import ast
import codecs
from fnmatch import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import time

from deliverables import split
from jev_observe import digest, git_env, local_file, safe_text
from lint import CONFIG, DEFAULT, header_summary
from storage import write_json

SCHEMA_VERSION = 1
PARSER_VERSION = 'search-map-v1'
MAX_BLOB = 65536
# 하네스 폴더는 코드 지도에서 뺀다. 지시서가 이 경로를 많이 적어 디렉터리 선택이 매번 여기로 끌려가고(erden recall 0~0.14),
# 규칙·설계 문서는 필수 문서와 지시서 참조로 이미 들어간다. Unity .meta는 짝 파일과 같은 내용이라 뺀다
HARNESS = '.fullops-squad/'
HARNESS_FILES = ('AGENTS.md', 'CLAUDE.md', 'GEMINI.md')  # 하네스 진입 파일


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], env=git_env(),
                                   encoding='utf-8', errors='strict', stderr=subprocess.DEVNULL).strip()


def prefix_blob(repo, sha, size):
    """큰 Git blob도 처음 MAX_BLOB 바이트만 읽는다. 불완전한 마지막 UTF-8 문자만 제외한다."""
    with subprocess.Popen(['git', '-C', str(repo), 'cat-file', 'blob', sha], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env=git_env()) as process:
        data = process.stdout.read(min(size, MAX_BLOB))
        process.stdout.close()
        if size > MAX_BLOB:
            process.terminate()
        code = process.wait()
    if code and size <= MAX_BLOB:
        raise OSError('Git blob unavailable locally')
    if b'\0' in data[:8000]:
        return ''
    return codecs.getincrementaldecoder('utf-8')().decode(data, final=size <= MAX_BLOB)


def configuration(repo, head, scope):
    try:
        exclude = json.loads(git(repo, 'show', f'{head}:{CONFIG}')).get('exclude', DEFAULT['exclude'])
        if not isinstance(exclude, list) or any(not isinstance(x, str) for x in exclude):
            raise ValueError('invalid excludes')
    except (subprocess.CalledProcessError, ValueError, AttributeError):
        exclude = DEFAULT['exclude']
    return {'scope': scope, 'exclude': exclude, 'max_blob': MAX_BLOB}


def blobs(repo, head, config):
    rows = git(repo, 'ls-tree', '-r', '-z', head).split('\0')
    result = []
    for row in rows:
        meta, _, path = row.partition('\t')
        mode, kind, sha = (meta.split() + ['', '', ''])[:3]
        eligible = path.endswith('.md') if config['scope'] == 'documents' else not path.startswith(HARNESS) and path not in HARNESS_FILES
        # 하네스 문서는 코드 lint 제외와 무관하다. 나머지 경로의 의존성·빌드 제외는 유지한다.
        excluded = any(fnmatch(path, x) or (x.startswith('**/') and fnmatch(path, x[3:])) for x in config['exclude'])
        if kind == 'blob' and mode in ('100644', '100755') and eligible and not path.endswith('.meta') and (
                config['scope'] == 'documents' and path.startswith(HARNESS) or not excluded):
            try:
                local_file(repo, path, historical=True)
                safe_text(path, MAX_BLOB)
            except ValueError:
                continue
            result.append((path, sha))
    return result


def parse(path, sha, text, size):
    """지원하지 않는 언어·불완전한 Python은 헤더로 돌아간다. 정의는 최대 24개만 저장한다."""
    entry = {'path': path, 'blob_oid': sha, 'kind': 'document' if path.endswith('.md') else 'code',
             'title': '', 'summary': '', 'definitions': [], 'headings': [], 'links': [],
             'parser': 'header', 'partial': size > MAX_BLOB, 'searchable': False}
    if not text.strip():
        return entry
    try:
        safe_text(text, MAX_BLOB)
    except ValueError:
        return entry
    try:
        meta, body = split(text) if path.endswith('.md') else (None, text)
        json.dumps(meta, allow_nan=False)
    except (ValueError, RecursionError):
        meta, body, entry['partial'] = None, text, True
    entry['title'] = str((meta or {}).get('title', ''))[:240]
    entry['summary'] = ((' — '.join(str(meta.get(k, '')) for k in ('title', 'summary') if meta.get(k)) if meta else '')
                        or header_summary(body, Path(path).suffix.lower()))[:240]
    if path.endswith('.md'):
        entry['headings'] = re.findall(r'(?m)^#{1,6}\s+(.+)', body)[:24]
        entry['links'] = re.findall(r'\]\(([^)\s]+)\)', body)[:24]
        entry['headings'] = [v[:160] for v in entry['headings']]
        entry['links'] = [v[:240] for v in entry['links'] if not re.match(r'[a-z]+:|#', v)]
        # 승인 상태와 다중 D번호별 상태는 원문 그대로 보존한다.
        entry['status'] = (meta or {}).get('status')
        entry['statuses'] = (meta or {}).get('statuses')
        entry['id'] = (meta or {}).get('id')
        entry['parser'] = 'markdown'
    elif path.endswith('.py') and not entry['partial']:
        try:
            nodes = [n for n in ast.walk(ast.parse(text)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            entry['partial'] = len(nodes) > 24
            for node in nodes[:24]:
                signature = node.name if isinstance(node, ast.ClassDef) else f'{node.name}({ast.unparse(node.args)})'
                entry['definitions'].append({'name': node.name, 'kind': 'class' if isinstance(node, ast.ClassDef) else 'function',
                    'line_start': node.lineno, 'signature': signature[:240], 'docstring': (ast.get_docstring(node) or '')[:160]})
            entry['parser'] = 'python-ast'
        except (SyntaxError, ValueError, RecursionError):
            pass
    entry['searchable'] = True
    return entry


def cache_path(repo, scope):
    return Path(git(repo, 'rev-parse', '--absolute-git-dir')) / 'fullops-search' / f'{scope}.json'


def load(path, config_hash):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if value['schema_version'] != SCHEMA_VERSION or value['parser_version'] != PARSER_VERSION or value['config_hash'] != config_hash:
            return {}
        files = value['files']
        if value['files_sha256'] != digest(json.dumps(files, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()):
            return {}
        if not isinstance(files, list) or len({x['path'] for x in files}) != len(files):
            return {}
        for item in files:
            if not isinstance(item, dict) or not isinstance(item.get('summary'), str) or type(item.get('searchable')) is not bool:
                return {}
            if not isinstance(item.get('definitions'), list) or not isinstance(item.get('headings'), list):
                return {}
            if any(not isinstance(heading, str) for heading in item['headings']):
                return {}
            for definition in item['definitions']:
                if not isinstance(definition, dict) or any(not isinstance(definition.get(k), str) for k in ('name', 'kind', 'signature', 'docstring')) or type(definition.get('line_start')) is not int:
                    return {}
            if not re.fullmatch(r'[0-9a-f]{40,64}', item.get('blob_oid', '')):
                return {}
            safe_text(json.dumps(item, ensure_ascii=False), MAX_BLOB)
        return value
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return {}


def build(repo, rows, previous):
    sizes = subprocess.check_output(['git', '-C', str(repo), 'cat-file', '--batch-check=%(objectsize)'],
        input=''.join(f'{sha}\n' for _, sha in rows).encode(), env=git_env()).splitlines()
    entries = []
    for (path, sha), size in zip(rows, sizes):
        old = previous.get(path)
        if old and old['blob_oid'] == sha and not old.get('read_error'):
            entries.append(old)
            continue
        try:
            size = int(size)
            entries.append(parse(path, sha, prefix_blob(repo, sha, size), size))
        except (OSError, ValueError, UnicodeError):
            entries.append({**parse(path, sha, '', 0), 'read_error': 'blob unavailable or invalid; inspect locally'})
    return entries


def metadata(repo, head, scope='code', use_cache=True):
    if scope not in ('code', 'documents'):
        raise ValueError('invalid search scope')
    # HEAD를 먼저 확정한다. writer 잠금 안에서도 이 커밋만 읽어 실행 중 HEAD 이동과 독립적이다.
    head = git(repo, 'rev-parse', '--verify', head + '^{commit}')
    config = configuration(repo, head, scope)
    config_hash = digest(json.dumps(config, sort_keys=True).encode())
    rows = blobs(repo, head, config)
    if not use_cache:
        return build(repo, rows, {})
    lock = None
    try:
        path = cache_path(repo, scope)
        if path.parent.is_symlink() or path.is_symlink():
            raise OSError('symlink cache')
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = path.parent / 'writer.lock'
        lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        previous = load(path, config_hash)
        entries = build(repo, rows, {item['path']: item for item in previous.get('files', [])})
        value = {'schema_version': SCHEMA_VERSION, 'parser_version': PARSER_VERSION,
                 'config_hash': config_hash, 'head': head, 'files': entries,
                 'files_sha256': digest(json.dumps(entries, sort_keys=True, ensure_ascii=False).encode())}
        if value == previous:
            return entries
        for attempt in range(3):
            try:
                write_json(path, value)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.02 * (attempt + 1))
        return entries
    except OSError:
        return build(repo, rows, {})
    finally:
        if lock is not None:
            os.close(lock)
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass  # 잠금 잔여 파일은 다음 실행에서 직접 읽기로 돌아가게 한다.


def code_map(repo, head, scope='code'):
    return [(item['path'], item['summary']) for item in metadata(repo, head, scope) if item['searchable']]


def description(item):
    parts = [item['summary'], *item['headings'][:4],
             *(d['signature'] + ' ' + d['docstring'] for d in item['definitions'][:8])]
    return ' | '.join(p for p in parts if p)[:800]
