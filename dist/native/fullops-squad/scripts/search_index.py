"""Git 원문에서 추출한 메타데이터를 작업 트리별 JSON에 재사용한다. 본문은 저장하지 않는다."""
import ast
import codecs
import json
import os
from pathlib import Path
import re
import subprocess
import time

from deliverables import split
from jev_observe import digest, git_env, local_file, safe_text
from lint import CONFIG, DEFAULT, header_summary, matches, stale
from storage import write_json

SCHEMA_VERSION = 2
PARSER_VERSION = 'search-map-v1'
MAX_BLOB = 65536
# 하네스 폴더는 코드 지도에서 뺀다. 지시서가 이 경로를 많이 적어 디렉터리 선택이 매번 여기로 끌려가고(erden recall 0~0.14),
# 규칙·설계 문서는 필수 문서와 지시서 참조로 이미 들어간다. Unity .meta는 짝 파일과 같은 내용이라 뺀다
HARNESS = '.fullops-squad/'
HARNESS_FILES = ('AGENTS.md', 'CLAUDE.md', 'GEMINI.md')  # 하네스 진입 파일


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], env=git_env(),
                                   encoding='utf-8', errors='strict', stderr=subprocess.DEVNULL).strip()


def blob_reader(repo):
    return subprocess.Popen(['git', '-C', str(repo), 'cat-file', '--batch'], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=git_env())


def close_reader(process):
    try:
        with process:
            pass
    except OSError:  # 이미 죽은 git의 stdin을 닫으면 Windows는 EINVAL을 낸다
        pass


def prefix_blob(process, sha):
    """열린 `cat-file --batch`에서 (크기, 앞 MAX_BLOB 바이트의 텍스트)를 얻는다. 불완전한 마지막 UTF-8 문자만 제외한다.

    한 번에 하나만 요청하고 응답을 끝까지 읽으므로 stdin과 stdout이 서로 막히지 않는다.
    없는 객체는 ValueError이고 스트림은 유효하다. git이 죽으면 OSError이고 새 프로세스가 필요하다."""
    process.stdin.write(f'{sha}\n'.encode())
    process.stdin.flush()
    fields = process.stdout.readline().split()
    if not fields:
        raise OSError('git cat-file exited')
    if len(fields) != 3:
        raise ValueError('Git blob unavailable locally')
    size = int(fields[2])
    data = process.stdout.read(min(size, MAX_BLOB))
    # shortcut: 초대형 blob도 git이 끝까지 풀어 보내는 시간을 쓴다(메모리는 쓰지 않는다), 실측으로 느려지면 끊고 새 프로세스를 띄운다
    rest = size - len(data) + 1  # 내용 뒤의 LF까지 읽어야 다음 응답과 맞는다
    while rest:
        chunk = process.stdout.read(min(rest, MAX_BLOB))
        if not chunk:
            raise OSError('git cat-file exited')
        rest -= len(chunk)
    if b'\0' in data[:8000]:
        return size, ''
    return size, codecs.getincrementaldecoder('utf-8')().decode(data, final=size <= MAX_BLOB)


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
        excluded = matches(path, config['exclude'])
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
    entry = {'path': path, 'blob_oid': sha, 'summary': '', 'definitions': [], 'headings': [], 'searchable': False}
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
        meta, body = None, text
    entry['summary'] = ((' — '.join(str(meta.get(k, '')) for k in ('title', 'summary') if meta.get(k)) if meta else '')
                        or header_summary(body, Path(path).suffix.lower()))[:240]
    if path.endswith('.md'):
        entry['headings'] = [v[:160] for v in re.findall(r'(?m)^#{1,6}\s+(.+)', body)[:24]]
        # 승인 상태와 다중 D번호별 상태는 원문 그대로 보존한다.
        entry['status'] = (meta or {}).get('status')
        entry['statuses'] = (meta or {}).get('statuses')
    elif path.endswith('.py') and size <= MAX_BLOB:
        try:
            nodes = [n for n in ast.walk(ast.parse(text)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            for node in nodes[:24]:
                signature = node.name if isinstance(node, ast.ClassDef) else f'{node.name}({ast.unparse(node.args)})'
                entry['definitions'].append({'signature': signature[:240], 'docstring': (ast.get_docstring(node) or '')[:160]})
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
                if not isinstance(definition, dict) or any(not isinstance(definition.get(k), str) for k in ('signature', 'docstring')):
                    return {}
            if not re.fullmatch(r'[0-9a-f]{40,64}', item.get('blob_oid', '')):
                return {}
            safe_text(json.dumps(item, ensure_ascii=False), MAX_BLOB)
        return value
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return {}


def build(repo, rows, previous):
    entries, reader = [], None
    try:
        for path, sha in rows:
            old = previous.get(path)
            if old and old['blob_oid'] == sha and not old.get('read_error'):
                entries.append(old)
                continue
            try:
                reader = reader or blob_reader(repo)
                size, text = prefix_blob(reader, sha)
                entries.append(parse(path, sha, text, size))
            except (OSError, ValueError, UnicodeError) as error:
                entries.append({**parse(path, sha, '', 0), 'read_error': 'blob unavailable or invalid; inspect locally'})
                if isinstance(error, OSError) and reader:  # 손상 blob에서 git이 죽는다. 나머지 파일이 함께 실패하지 않게 새로 띄운다
                    close_reader(reader)
                    reader = None
    finally:
        if reader:
            close_reader(reader)
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
        if stale(lock_path):  # 강제 종료된 writer의 잠금은 lint와 같은 PID 규칙으로 회수한다
            lock_path.unlink(missing_ok=True)
        lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(lock, str(os.getpid()).encode())
        previous = load(path, config_hash)
        entries = build(repo, rows, {item['path']: item for item in previous.get('files', [])})
        value = {'schema_version': SCHEMA_VERSION, 'parser_version': PARSER_VERSION,
                 'config_hash': config_hash, 'files': entries,
                 'files_sha256': digest(json.dumps(entries, sort_keys=True, ensure_ascii=False).encode())}
        if value == previous:
            return entries
        for attempt in range(3):
            try:
                write_json(path, value)
                break
            except OSError:  # 캐시를 못 써도 이미 만든 entries는 정확하다
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
