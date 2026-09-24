#!/usr/bin/env python3
"""변경 파일에 프로젝트 lint 명령과 스택 무관 기본 검사를 실행한다. 기존 위반은 소급하지 않는다."""
import argparse
import difflib
from fnmatch import fnmatch
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tokenize

from work import active_repo, safe_file

CONFIG = '.fullops-squad/lint/lint.json'
DEFAULT = json.loads((Path(__file__).resolve().parents[1] / 'assets/repository' / CONFIG).read_text())
PY = {'.py'}
HASH = {'.sh', '.bash', '.rb', '.gd', '.pl', '.r'}
C_STYLE = {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.svelte', '.vue', '.go', '.rs', '.java',
           '.kt', '.kts', '.scala', '.c', '.h', '.cc', '.cpp', '.hpp', '.cs', '.swift', '.php',
           '.dart', '.css', '.scss', '.less', '.html', '.gdshader', '.shader'}
EVAL_TARGETS = PY | {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.svelte', '.vue'}
BLOCK_COMMENTS = (('/*', '*/'), ('<!--', '-->'))
SUPPRESSIONS = [
    (re.compile(r'#\s*type:\s*ignore(?!\s*\[)'), '# type: ignore[<code>]'),
    (re.compile(r'#\s*pyright:\s*ignore(?!\s*\[)'), '# pyright: ignore[<rule>]'),
    (re.compile(r'#\s*noqa(?!\s*:)', re.IGNORECASE), '# noqa: <code>'),
    (re.compile(r'@ts-ignore|@ts-nocheck'), '정확한 타입 또는 @ts-expect-error <사유>'),
    (re.compile(r'eslint-disable(?:-next-line|-line)?\s*(?:\*/|-->)?\s*$'), 'eslint-disable-next-line <rule>'),
]
# Canny(qkal/canny)의 테스트 케이스·skip 패턴을 따른다.
CASE = re.compile(r'\b[xf]?(?:it|test|describe)(?:\.\w+)?\s*\(|\bdef test_\w+|\bfunc Test\w+|#\[test\]|@Test\b|'
                  r'\bfunc test\w+\s*\(|\b(?:it|test)\s+"[^"]*"\s+do\b')
SKIP = re.compile(r'\.(?:skip|todo|only)\s*\(|\b[xf](?:it|test|describe)\s*\(|@pytest\.mark\.(?:skip|xfail)|'
                  r'\bpytest\.(?:skip|xfail)\(|@unittest\.skip|\bt\.Skip(?:f|Now)?\(|#\[ignore\]|@Ignore\b|'
                  r'@Disabled\b|XCTSkip|\bpending\s*\(')
EVAL = re.compile(r'(?<![\w.$])(?:eval|exec)\s*\(')
SECRET = re.compile(r"""(?:password|passwd|pwd|api[_-]?key|apikey|secret(?:_key)?|(?:access_|auth_)?token|"""
                    r"""db_password|database_password)\s*[:=]\s*["'][^"']+["']""", re.IGNORECASE)
SECRET_OK = re.compile(r"""[:=]\s*["'](?:test|example|dummy|placeholder|changeme|xxx|your_|<)|"""
                       r"""os\.environ|process\.env|import\.meta\.env|settings\.""", re.IGNORECASE)


def git(repo, *args, data=False):
    output = subprocess.check_output(['git', '-C', str(repo), *args])
    return output if data else output.decode().strip()


def config_blob(repo, ref):
    """ref 시점의 설정 원문. 없으면 None."""
    done = subprocess.run(['git', '-C', str(repo), 'cat-file', 'blob', f'{ref}:{CONFIG}'], capture_output=True)
    return done.stdout if done.returncode == 0 else None


def load_config(repo, ref):
    """검사 대상 브랜치가 스스로 규칙을 느슨하게 하지 못하도록 기준 시점(merge-base)의 설정을 쓴다."""
    raw = config_blob(repo, ref)
    if raw is None:
        return DEFAULT, None
    config = {**DEFAULT, **json.loads(raw)}
    if config.get('schema_version') != 1:
        raise ValueError('지원하지 않는 lint 설정 버전')
    for command in config['commands']:
        run = command.get('run')
        if not command.get('name') or not isinstance(run, list) or not run or not all(isinstance(a, str) for a in run):
            raise ValueError('lint 명령은 name과 문자열 배열 run이 필요합니다')
        cwd = (repo / command.get('cwd', '.')).resolve()
        if cwd != repo and repo not in cwd.parents:
            raise ValueError(f'레포 밖 cwd: {command["name"]}')
    return config, hashlib.sha256(raw).hexdigest()


def code_lines(text, ext):
    if ext == '.md':
        return len(text.splitlines())
    if ext in PY:
        try:
            code, logical = set(), []
            skip = {tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER}
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type in skip:
                    continue
                if tok.type == tokenize.NEWLINE:
                    if not (len(logical) == 1 and logical[0].type == tokenize.STRING):  # docstring
                        for t in logical:
                            code.update(range(t.start[0], t.end[0] + 1))
                    logical = []
                else:
                    logical.append(tok)
            return len(code)
        except (tokenize.TokenError, SyntaxError):
            pass
    if ext in HASH:
        return sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith('#'))
    # ponytail: 문자열 안의 주석 마커를 구분하지 않는다. 상한 검사라 적게 세는 쪽이 안전하다.
    count, closer = 0, None
    for raw in text.splitlines():
        s = raw.strip()
        while s:
            if closer:
                s, closer = (s.split(closer, 1)[1].strip(), None) if closer in s else ('', closer)
                continue
            opener = next((pair for pair in BLOCK_COMMENTS if s.startswith(pair[0])), None)
            if not opener:
                break
            s, closer = s[len(opener[0]):], opener[1]
        if s and not s.startswith('//'):
            count += 1
    return count


def header_summary(text, ext):
    """파일 머리의 설명 한 줄(docstring·주석·제목). 없으면 ''. jev_find의 코드 지도가 이 값을 쓴다."""
    lines = [line.strip() for line in text.splitlines()[:40]]
    lines = [line for line in lines if line and not line.startswith(('#!', '# -*-', '// @ts-', "'use ", '"use '))]
    if not lines:
        return ''
    first = lines[0]
    if ext == '.md':
        return first.lstrip('#').strip() if first.startswith('#') else ''
    if ext in PY:
        for quote in ('"""', "'''"):
            if first.startswith(quote):
                body = first[3:].split(quote)[0].strip()
                return body or next((line for line in lines[1:] if line and not line.startswith(quote)), '')
    if ext in PY | HASH and first.startswith('#'):
        return first.lstrip('#').strip()
    if ext in C_STYLE:
        for marker in ('//', '/**', '/*', '<!--'):
            if first.startswith(marker):
                body = first[len(marker):].replace('*/', '').replace('-->', '').strip(' *')
                return body or next((line.strip('/* ') for line in lines[1:] if line.strip('/* ')), '')
    return ''


def is_test(path):
    name, parts = Path(path).name, Path(path).parts
    return (name.startswith('test_') or re.search(r'[._](test|spec)\.[^.]+$', name) is not None
            or re.search(r'Tests?\.(swift|kt|java|cs)$|_spec\.rb$', name) is not None
            or bool({'test', 'tests', 'spec', 'specs', '__tests__'} & set(parts[:-1])))


def changed(repo, base, head):
    fields = git(repo, 'diff', '--name-status', '-z', '-M', '--no-ext-diff', base, head, data=True).decode().split('\0')
    items, i = [], 0
    while i < len(fields) - 1:
        status = fields[i]
        if status[0] in 'RC':
            items.append((fields[i + 1], fields[i + 2]))
            i += 3
        else:
            path = fields[i + 1]
            items.append((None if status[0] == 'A' else path, None if status[0] == 'D' else path))
            i += 2
    return items


def blob(repo, ref, path):
    if path is None:
        return ''  # 추가·삭제된 쪽은 빈 내용으로 비교한다
    data = git(repo, 'cat-file', 'blob', f'{ref}:{path}', data=True)
    return None if b'\0' in data else data.decode('utf-8', errors='replace')


def added_lines(old, new):
    lines = new.splitlines()
    matcher = difflib.SequenceMatcher(None, old.splitlines(), lines, autojunk=False)
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag in ('replace', 'insert'):
            yield from ((j + 1, lines[j]) for j in range(j1, j2))


def check_file(path, old, new, config):
    ext = Path(path).suffix.lower()
    size = config['size']
    limit = size['max_doc_lines'] if ext == '.md' else size['max_code_lines']
    if limit and (ext == '.md' or ext in PY | HASH | C_STYLE):
        after = code_lines(new, ext)
        before = code_lines(old, ext) if old else 0
        if after > limit and after > before:
            yield ('SIZE-001', size['severity'], None,
                   f'{after}줄(이전 {before}, 상한 {limit}). ① 삭제 → ② 압축 → ③ 분할 순으로 처리하고 docstring·헤더를 깎지 않는다')
    test = is_test(path)
    soft = test or ext == '.md'
    if not old and ext in PY | HASH | C_STYLE and not header_summary(new, ext):
        yield ('DOC-001', 'WARNING', None, '새 코드 파일에 무엇을 하는지 적은 헤더 설명(docstring·주석 1~3줄)이 없다')
    if test and old and len(CASE.findall(new)) < len(CASE.findall(old)):
        yield ('ANTI-005', 'WARNING', None,
               f'테스트 케이스 {len(CASE.findall(old)) - len(CASE.findall(new))}개 감소. 대체 테스트나 삭제 이유를 확인한다')
    rules = [r for r in config['rules'] if r.get('enabled', True)
             and (not r.get('file_extensions') or ext in r['file_extensions'])]
    for number, line in added_lines(old or '', new):
        if ext in PY | HASH | C_STYLE:
            for pattern, hint in SUPPRESSIONS:
                if pattern.search(line):
                    yield 'ANTI-003', 'ERROR', number, f'범위 없는 억제 금지. {hint}로 좁힌다'
        if test and SKIP.search(line):
            yield 'ANTI-004', 'ERROR', number, '테스트 skip·only 표식 추가 금지. 실패 원인을 고치거나 테스트를 정당하게 바꾼다'
        if ext in EVAL_TARGETS and EVAL.search(line):
            yield 'ANTI-002', 'ERROR', number, 'eval()/exec() 금지'
        if SECRET.search(line) and not SECRET_OK.search(line):
            yield 'SEC-001', 'WARNING' if soft else 'ERROR', number, '하드코딩 비밀값 의심. 환경변수·설정으로 옮긴다'
        for rule in rules:
            if re.search(rule['pattern'], line) and not any(re.search(p, line) for p in rule.get('exclude_patterns', [])):
                yield rule['code'], rule.get('severity', 'WARNING'), number, f"{rule['description']}. {rule.get('suggestion', '')}".strip()


def run_command(repo, command, timeout):
    entry = {'name': command['name'], 'run': command['run'], 'cwd': command.get('cwd', '.'), 'reason': ''}
    try:
        run = [shutil.which(command['run'][0]) or command['run'][0], *command['run'][1:]]  # Windows의 npx.cmd 등
        done = subprocess.run(run, cwd=repo / entry['cwd'], capture_output=True, text=True,
                              timeout=timeout, errors='replace')
    except FileNotFoundError:
        return {**entry, 'status': 'unavailable', 'exit_code': None, 'output_tail': ''}
    except subprocess.TimeoutExpired:
        return {**entry, 'status': 'timeout', 'exit_code': None, 'output_tail': ''}
    tail = '\n'.join((done.stdout + done.stderr).splitlines()[-40:])
    return {**entry, 'status': 'passed' if done.returncode == 0 else 'failed',
            'exit_code': done.returncode, 'output_tail': tail}


def lint(repo, base_ref):
    if git(repo, 'status', '--porcelain'):
        raise ValueError('작업 트리가 깨끗하지 않습니다. 커밋 후 실행하세요')
    head = git(repo, 'rev-parse', 'HEAD')
    base = git(repo, 'rev-parse', '--verify', base_ref + '^{commit}')
    merge_base = git(repo, 'merge-base', base, head)
    config, digest = load_config(repo, merge_base)
    violations, files = [], 0
    if config_blob(repo, head) != config_blob(repo, merge_base):
        violations.append({'code': 'LINT-001', 'severity': 'WARNING', 'line': None, 'path': CONFIG,
                           'message': '이 브랜치의 lint 설정 변경은 적용하지 않았습니다. 병합 후 적용되니 변경 이유를 검토하세요'})
    for old_path, path in changed(repo, merge_base, head):
        target = path or old_path
        if any(fnmatch(target, p) or (p.startswith('**/') and fnmatch(target, p[3:])) for p in config['exclude']):
            continue
        if path is None:
            if is_test(old_path):
                violations.append({'code': 'ANTI-005', 'severity': 'WARNING', 'line': None, 'path': old_path,
                                   'message': '테스트 파일 삭제. 대체 테스트나 삭제 이유를 확인한다'})
            continue
        new = blob(repo, head, path)
        old = blob(repo, merge_base, old_path)
        if new is None or old is None:
            continue
        files += 1
        violations += [dict(zip(('code', 'severity', 'line', 'message'), v), path=path)
                       for v in check_file(path, old, new, config)]
    commands = [run_command(repo, c, config['timeout_seconds']) for c in config['commands']]
    if not config['commands']:
        violations.append({'code': 'LINT-000', 'severity': 'WARNING', 'line': None, 'path': CONFIG,
                           'message': '프로젝트 lint 명령이 등록되지 않았습니다. setup에서 기존 도구를 연결하세요'})
    errors = sum(v['severity'] == 'ERROR' for v in violations) + sum(c['status'] in ('failed', 'timeout') for c in commands)
    return {'schema_version': 1, 'base': base, 'merge_base': merge_base, 'head': head, 'config_sha256': digest,
            'commands': commands, 'violations': violations,
            'summary': {'files': files, 'errors': errors,
                        'warnings': sum(v['severity'] == 'WARNING' for v in violations),
                        'unavailable': sum(c['status'] == 'unavailable' for c in commands)}}


def stamp(repo, head):
    """done-gate(Stop hook)가 읽는 통과 기록. 체크아웃별 git 디렉터리에 둔다."""
    try:
        gate = Path(git(repo, 'rev-parse', '--absolute-git-dir')) / 'fullops-gate'
        gate.mkdir(exist_ok=True)
        (gate / 'pass.json').write_text(json.dumps({'head': head}) + '\n')
    except (OSError, subprocess.CalledProcessError):
        pass  # 기록 실패는 lint 결과를 바꾸지 않는다


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, help='검사할 체크아웃 루트 (worker 워크트리)')
    parser.add_argument('--from', required=True, dest='base', help='기준 ref. merge-base 이후 변경만 검사')
    parser.add_argument('--out', help='결과 JSON 경로 (리뷰 디렉터리의 lint.json)')
    args = parser.parse_args()
    try:
        repo = active_repo(args.repo)
        result = lint(repo, args.base)
    except (OSError, ValueError, KeyError, TypeError, re.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f'lint 실패: {error}\n')
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    for c in result['commands']:
        print(f"[{c['status']}] {c['name']}: {' '.join(c['run'])}")
        if c['status'] == 'failed':
            print(c['output_tail'])
    for v in result['violations']:
        print(f"{v['severity']} {v['code']} {v['path']}{':' + str(v['line']) if v['line'] else ''} {v['message']}")
    s = result['summary']
    print(f"head {result['head'][:12]} / 파일 {s['files']} / ERROR {s['errors']} / WARNING {s['warnings']} / 실행 불가 {s['unavailable']}")
    if not (s['errors'] or s['unavailable']):
        stamp(repo, result['head'])
    raise SystemExit(1 if s['errors'] or s['unavailable'] else 0)


if __name__ == '__main__':
    main()
