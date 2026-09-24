#!/usr/bin/env python3
"""FullOps flow-gate hook. coordinator·설계 역할·worker가 route → dispatch → 질문 → 완료 보고 흐름을 벗어나지 않게 막는다.

역할은 현재 브랜치로 정한다. `fullops.json`의 역할 브랜치가 아니거나 라우팅 기준의 coordinator 역할이면 coordinator,
라우팅 기준의 설계 역할이면 설계 역할이다.
coordinator 세션이 끝날 때마다 작업 현황판 데이터(board/board-data.js)를 다시 만든다.
Claude Code·Codex(snake_case)와 grok(camelCase) 입력을 함께 읽는다. 셸 우회까지 막지는 못하며, 어떤 오류도 작업을 막지 않는다.
"""
import json
from pathlib import Path
import re
import shlex
import sys

import board
import env_link
from done_gate import CODE, field, git
from jev_route import coordinator_role, guide

DISPATCH = re.compile(r'--dispatch-id[ =]+([A-Za-z0-9_.:-]+)')
SETTLE = re.compile(r'orchestration\s+send\b.*--type[ =]+(?:worker_done|escalation)\b', re.S)  # ask는 턴을 끝내지 않는다
INJECT = re.compile(r'\bterminal\s+send\b.*handovers/|\bdispatch\b.*--inject\b', re.S)
HANDOVER = re.compile(r'(?:^|/)\.fullops-squad/handovers/to_([a-z][a-z0-9_-]*)\.md$')
TITLE = re.compile(r'#\s+([A-Za-z0-9][A-Za-z0-9._-]*)\s+—')


def context(root):
    """(역할 또는 'coordinator', 설계 역할 또는 None). 역할 브랜치가 아니거나 지정된 coordinator 역할이면 coordinator다."""
    roles = json.loads((root / '.fullops-squad/fullops.json').read_text(encoding='utf-8')).get('roles', {})
    branch = git(root, 'rev-parse', '--abbrev-ref', 'HEAD')
    try:
        designer = guide(root)[1]
    except (OSError, ValueError):
        designer = None
    role = next((role for role, b in roles.items() if b == branch), 'coordinator')
    return ('coordinator' if role == coordinator_role(root) else role), designer


def route_of(root, key):
    try:
        return json.loads((root / f'.fullops-squad/docs/evaluations/jev/{key}-route.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def targets(tool):
    """도구 입력에서 (셸 명령, [(수정 경로, 새 내용 또는 None)])"""
    command = tool.get('command') or tool.get('cmd') or ''
    if isinstance(command, list):
        command = ' '.join(map(str, command))
    files = []
    path = tool.get('file_path') or tool.get('path') or tool.get('target_file')
    if isinstance(path, str):
        files.append((path, tool.get('content')))
    for name in re.findall(r'^\*\*\* (?:Add|Update) File: (.+)$', command, re.M):  # Codex apply_patch
        files.append((name.strip(), None))
    return command, files


def key_in(root, text, path=None):
    match = TITLE.search(text or '')
    if not match and path and path.is_file():
        match = TITLE.search(path.read_text(encoding='utf-8').split('\n', 1)[0])
    return match and match.group(1)


def handover_denial(root, designer, role, key):
    if role == designer:
        return None
    if not key:
        return '지시서 첫 줄을 `# <과제 키> — <목표>`로 쓰세요.'
    route = route_of(root, key)
    if not route:
        return f'{key}의 route 기록이 없습니다. 먼저 `jev_route.py --key {key}`를 실행하세요.'
    if route.get('route') != 'simple' or route.get('role') != role:
        return (f'{key}는 {route.get("route")} → {route.get("role")}로 분류됐습니다. '
                f'{role} 지시서는 설계 역할({designer})이 씁니다. 설계 역할을 dispatch하세요.')
    return None


def tool_denial(root, event, state):
    tool = field(event, 'tool_input') or {}
    if not isinstance(tool, dict):
        return None
    command, files = targets(tool)
    if SETTLE.search(command):
        state['settled'] = True
    role, designer = context(root)
    if INJECT.search(command):
        return '지시서를 터미널로 주입하면 worker가 `worker_done`을 보낼 수 없습니다. `orchestration worker-start --run <run id>`로 띄우세요.'
    if re.search(r'\borchestration\s+worker-start\b', command):
        if '--run' not in command:
            return '`worker-start`에 `--run <run id>`를 붙이세요. 없으면 완료 보고가 다른 Run으로 갈 수 있습니다.'
        if role == 'coordinator':
            jev = root / '.fullops-squad/docs/evaluations/jev'
            keys = [p.name[:-len('-route.json')] for p in jev.glob('*-route.json')] if jev.is_dir() else []
            if not any(re.search(rf'(?<![A-Za-z0-9._-]){re.escape(k)}(?![A-Za-z0-9._-])', command) for k in keys):
                return 'dispatch spec에 route 기록이 있는 과제 키가 없습니다. 먼저 `jev_route.py`로 분류하고 spec에 과제 키를 넣으세요.'
    if role == 'coordinator' and designer:
        new = re.search(r'\bwork\.py\b.*\bnew\b', command)
        if new:
            try:
                words = shlex.split(command, posix=True)
            except ValueError:
                words = command.split()
            args = dict(zip(words, words[1:]))
            denial = handover_denial(root, designer, args.get('--role'), args.get('--key'))
            if denial:
                return denial
        for name, content in files:
            match = HANDOVER.search(name.replace('\\', '/'))
            if match:
                path = Path(name) if Path(name).is_absolute() else root / name
                denial = handover_denial(root, designer, match.group(1), key_in(root, content, path))
                if denial:
                    return denial
    if role == designer:
        for name, _ in files:
            if Path(name).suffix.lower() in CODE and '.fullops-squad/' not in name.replace('\\', '/'):
                return f'설계 역할은 코드를 고치지 않습니다({name}). 역할별 지시서에 적고 worker에게 맡기세요.'
    return None


BRIEF = {
    'coordinator': ('FullOps coordinator: 새 요청은 과제 키를 정하고 `jev_route.py`로 먼저 분류한다. simple이면 그 역할 지시서를, '
                    'design이면 설계 역할을 `worker-start --run`으로 띄운다. 설계·범위 질문은 직접 답하지 않고 설계 역할에게 넘긴다. '
                    '프로젝트 단계가 바뀌거나 늘면 .fullops-squad/board/board.json을 고친다. 이 규칙은 hook이 강제하고, 세션이 끝나면 현황판이 갱신된다.'),
    'designer': ('FullOps 설계 역할: 설계 문서와 역할별 지시서만 쓰고 코드는 고치지 않는다. 끝나면 preamble의 `worker_done`으로 '
                 '`[설계] <과제 키> | 지시서: … | 역할: … | SHA …`를 보낸다.'),
    'worker': ('FullOps worker: 설계·범위 판단이 필요하면 preamble의 `ask`로 묻고 추측하지 않는다. 끝나면 preamble의 '
               '`worker_done`을 한 번 보낸다. 보내지 않고 끝내면 hook이 한 번 막는다.'),
}


def main():
    mode = sys.argv[1]
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = {}
    root = Path(git(field(event, 'cwd') or '.', 'rev-parse', '--show-toplevel'))
    if not (root / '.fullops-squad/fullops.json').is_file():
        return {}
    gate = Path(git(root, 'rev-parse', '--absolute-git-dir')) / 'fullops-gate'
    gate.mkdir(exist_ok=True)
    session = gate / ('flow-' + re.sub(r'[^A-Za-z0-9_-]', '_', str(field(event, 'session_id') or 'default'))[:100] + '.json')
    state = json.loads(session.read_text()) if session.is_file() else {}
    before = dict(state)
    output = {}
    if mode == 'start':
        role, designer = context(root)
        kind = 'coordinator' if role == 'coordinator' else 'designer' if role == designer else 'worker'
        brief = BRIEF[kind]
        try:  # 워크트리에 빠진 .env*를 원본 체크아웃에서 연결한다. 실패해도 세션을 막지 않는다
            linked = env_link.link(root)
        except Exception:  # noqa: BLE001
            linked = []
        if linked:
            copied = [name for name, how in linked if how == 'copy']
            brief += (f" 워크트리에 없던 {', '.join(name for name, _ in linked)}를 원본 체크아웃에서 연결했다."
                      + (f" {', '.join(copied)}는 링크를 만들 수 없어 복사했으니 원본이 바뀌면 다시 복사해야 한다." if copied else ''))
        output = {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': brief}}
    elif mode == 'prompt':
        match = DISPATCH.search(str(field(event, 'prompt') or ''))
        if match and match.group(1) != state.get('dispatch'):
            state = {'dispatch': match.group(1), 'settled': False}
    elif mode == 'tool':
        denial = tool_denial(root, event, state)
        if denial:
            output = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                             'permissionDecisionReason': 'FullOps: ' + denial}}
    elif mode == 'stop' and (field(event, 'reason') or 'end_turn') == 'end_turn':
        if state.get('dispatch') and not state.get('settled'):
            if field(event, 'stop_hook_active') and state.get('blocked'):
                output = {'systemMessage': 'FullOps: worker_done 없이 dispatched 세션을 끝냈습니다. coordinator가 계속 기다립니다.'}
            else:
                state['blocked'] = True
                output = {'decision': 'block', 'reason':
                          f"FullOps: Dispatch {state['dispatch']}의 `worker_done`을 보내지 않았습니다. 과제를 마쳤으면 preamble의 "
                          '`worker_done` 명령(`--outcome succeeded|failed`)을 보내고, 판단이 필요하면 `ask`, 막혔으면 `escalation`을 보내세요. '
                          '아직 작업 중이면 계속 진행하세요.'}
        if context(root)[0] == 'coordinator':
            try:
                board.write(root)  # 현황판 데이터 갱신. 실패해도 종료를 막지 않는다
            except Exception:  # noqa: BLE001
                pass
    if state != before:
        session.write_text(json.dumps(state))
    return output


if __name__ == '__main__':
    try:
        result = main()
    except Exception:  # noqa: BLE001 — hook은 실패해도 작업을 막지 않는다
        result = {}
    print(json.dumps(result, ensure_ascii=False))
