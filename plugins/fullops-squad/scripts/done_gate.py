#!/usr/bin/env python3
"""FullOps done-gate hook. 이 세션에서 코드를 바꿨는데 현재 HEAD의 lint.py 통과 기록이 없으면 종료(Stop)를 막는다.

Canny(qkal/canny)의 "사실만 막는다"를 ledger 없이 줄였다. SessionStart에 세션 시작 지점과 규칙을 남기고,
Stop에서 이 체크아웃이 직접 만든 커밋(HEAD reflog의 commit 항목)과 미커밋 변경의 코드 파일만 본다.
막힌 뒤 아무것도 바뀌지 않은 채 다시 끝내면 경고만 하고 통과시킨다. 어떤 오류도 종료를 막지 않는다.
"""
from fnmatch import fnmatch
import json
from pathlib import Path
import re
import subprocess
import sys

from lint import C_STYLE, CONFIG, DEFAULT, HASH, PY

CODE = PY | HASH | C_STYLE
LINT = Path(__file__).resolve().with_name('lint.py')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()


def reflog(root):
    try:
        return git(root, 'reflog', '--format=%H %gs', 'HEAD').splitlines()
    except subprocess.CalledProcessError:
        return []  # 첫 커밋 전


def excluded(root):
    try:
        return json.loads((root / CONFIG).read_text()).get('exclude', DEFAULT['exclude'])
    except (OSError, ValueError, AttributeError):
        return DEFAULT['exclude']


def code_changes(root, state):
    """(이 세션이 만든 커밋의 코드 파일, 미커밋 코드 파일)"""
    skip = excluded(root)

    def code(path):
        return Path(path).suffix.lower() in CODE and not any(
            fnmatch(path, p) or (p.startswith('**/') and fnmatch(path, p[3:])) for p in skip)
    entries = reflog(root)
    own = [line.split(' ', 1)[0] for line in entries[:max(0, len(entries) - state['reflog'])]
           if line.split(' ', 1)[1:2] and line.split(' ', 1)[1].startswith('commit')]
    committed = set()
    for sha in own:
        committed |= set(git(root, 'diff-tree', '--no-commit-id', '--name-only', '-r', '--root', sha).splitlines())
    fields = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '-z', '--untracked-files=all'],
                                     text=True).split('\0')
    dirty, i = set(), 0
    while i < len(fields) and len(fields[i]) > 3:
        dirty.add(fields[i][3:])
        i += 2 if fields[i][0] in 'RC' else 1  # rename·copy는 원래 경로가 다음 필드다
    return sorted(filter(code, committed)), sorted(filter(code, dirty))


def main():
    mode = sys.argv[1]
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = {}
    root = Path(git(event.get('cwd') or '.', 'rev-parse', '--show-toplevel'))
    if not (root / '.fullops-squad/fullops.json').is_file():
        return {}
    gate = Path(git(root, 'rev-parse', '--absolute-git-dir')) / 'fullops-gate'
    gate.mkdir(exist_ok=True)
    session = gate / (re.sub(r'[^A-Za-z0-9_-]', '_', str(event.get('session_id') or 'default'))[:100] + '.json')
    state = json.loads(session.read_text()) if session.is_file() else None
    if mode == 'start':
        if state is None:  # resume·compact는 처음 시작 지점을 유지한다
            session.write_text(json.dumps({'reflog': len(reflog(root))}))
        if event.get('source', 'startup') not in ('startup', 'clear'):
            return {}
        try:
            names = [c['name'] for c in json.loads((root / CONFIG).read_text()).get('commands', [])]
        except (OSError, ValueError, AttributeError, KeyError, TypeError):
            names = []
        brief = (f'FullOps done-gate: 이 세션에서 코드 파일을 바꾸면 끝내기 전에 변경을 커밋하고 '
                 f'`python3 {LINT} --repo {root} --from <지시서의 기준 ref>`를 통과시킨다'
                 f"{' (등록 명령: ' + ', '.join(names) + ')' if names else ''}. "
                 '통과 기록이 없으면 종료가 한 번 막힌다. 적용할 검사가 없으면 이유를 말하고 다시 끝낸다. '
                 '테스트 로그를 증거로 남길 때 `| tail` 등으로 명령 자신의 종료코드를 가리지 않는다.')
        return {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': brief}}
    if state is None:
        return {}  # 게이트 도입 전에 시작한 세션
    committed, dirty = code_changes(root, state)
    if not committed and not dirty:
        return {}
    head = git(root, 'rev-parse', 'HEAD')
    try:
        passed = json.loads((gate / 'pass.json').read_text()).get('head') == head
    except (OSError, ValueError, AttributeError):
        passed = False
    if passed and not dirty:
        return {}
    marker = [head, [[p, (root / p).stat().st_mtime_ns if (root / p).exists() else None] for p in dirty]]
    if event.get('stop_hook_active') and state.get('blocked') == marker:
        return {'systemMessage': 'FullOps: lint.py 통과 기록 없이 세션을 끝냈습니다. 완료 보고의 검증 항목을 확인하세요.'}
    session.write_text(json.dumps({**state, 'blocked': marker}))
    files = (dirty or committed)[:5]
    action = '변경을 커밋하고 ' if dirty else ''
    return {'decision': 'block',
            'reason': f"FullOps: 코드 파일({', '.join(files)})이 바뀌었지만 HEAD {head[:12]}의 lint.py 통과 기록이 없습니다. "
                      f'{action}`python3 {LINT} --repo {root} --from <지시서의 기준 ref>`를 실행해 ERROR를 고친 뒤 끝내세요. '
                      '적용할 검사가 없거나 실행할 수 없으면 이유를 말하고 다시 끝내면 됩니다.'}


if __name__ == '__main__':
    try:
        output = main()
    except Exception:  # noqa: BLE001 — hook은 실패해도 종료를 막지 않는다
        output = {}
    print(json.dumps(output, ensure_ascii=False))
