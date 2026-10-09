#!/usr/bin/env python3
"""FullOps flow-gate hook. coordinator·설계 역할·worker가 route → dispatch → 질문 → 완료 보고 흐름을 벗어나지 않게 막는다.

역할은 현재 브랜치로 정한다. `fullops.json`의 역할 브랜치가 아니거나 라우팅 기준의 coordinator 역할이면 coordinator,
라우팅 기준의 설계 역할이면 설계 역할이다.
coordinator 세션이 끝날 때마다 작업 현황판 데이터(board/board-data.js)를 다시 만든다.
Claude Code·Codex(snake_case)와 grok(camelCase) 입력을 함께 읽는다. 셸 우회까지 막지는 못하며, 어떤 오류도 작업을 막지 않는다.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

import board
import deps
import env_link
import deliverables
import integration
import policy
from orca_wait import find_orca
from done_gate import CODE, field, git
from jev_route import coordinator_role, guide, marked_role, product_roles
from storage import write_json

DISPATCH = re.compile(r'--dispatch-id[ =]+([A-Za-z0-9_.:-]+)')
INJECT = re.compile(r'\bterminal\s+send\b.*handovers/|\bdispatch\b.*--inject\b', re.S)
SEND_LIMIT = 20  # coordinator가 terminal send로 보낼 수 있는 글자 수. 확인 프롬프트 응답(y, 1)은 허용하고 작업 지시는 막는다
HANDOVER = re.compile(r'(?:^|/)\.fullops-squad/handovers/to_([a-z][a-z0-9_-]*)\.md$')
TITLE = re.compile(r'#\s+([A-Za-z0-9][A-Za-z0-9._-]*)\s+—')
STARTED = re.compile(r'\borchestration\s+worker-start\b.*?--run[ =]+["\']?([A-Za-z0-9_-]+)', re.S)
ROUTED = re.compile(r'\bjev_route\.py\b.*?--key[ =]+["\']?([A-Za-z0-9][A-Za-z0-9._-]*)', re.S)


def context(root):
    """(역할 또는 'coordinator', 설계 역할 또는 None). 역할 브랜치가 아니거나 지정된 coordinator 역할이면 coordinator다."""
    config = policy.load(root)
    try:
        designer = guide(root)[1]
    except (OSError, ValueError):
        designer = None
    return policy.identity(root, config, coordinator_role(root))[0], designer


def primary(root, state):
    return policy.identity(root, policy.load(root), coordinator_role(root), bool(state.get('dispatch')))[1]


def route_of(root, key):
    try:
        data = json.loads((root / f'.fullops-squad/docs/evaluations/jev/{key}-route.json').read_text(encoding='utf-8'))
        roles = integration.config(root)['roles']
        if not isinstance(data, dict) or data.get('version') not in ('jev-route-v1', 'jev-route-v2', 'jev-route-v3', 'jev-route-v4') or data.get('task_key') != key:
            return None
        if data.get('route') not in ('simple', 'design', 'product', 'implementation', 'unresolved'):
            return None
        if data.get('role') not in roles and data.get('route') != 'unresolved':
            return None
        return data
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
    if command.lstrip().startswith('*** Begin Patch'):  # 패치 본문은 실행 명령이 아니다
        chunks = re.split(r'^\*\*\* (?:Add|Update) File: (.+)$', command, flags=re.M)
        for name, body in zip(chunks[1::2], chunks[2::2]):
            moved = re.search(r'^\*\*\* Move to: (.+)$', body, flags=re.M)
            added = [line[1:] for line in body.splitlines() if line.startswith('+')]
            files.append(((moved.group(1) if moved else name).strip(),
                          '\n'.join(added) if added else None))
        command = ''
    return command, files


def key_in(root, text, path=None):
    match = TITLE.search(text or '')
    if not match and path and path.is_file():
        match = TITLE.search(deliverables.split(path.read_text(encoding='utf-8'))[1].lstrip().split('\n', 1)[0])
    return match and match.group(1)


def inbox_denial(root, name, content):
    """과제명 파일 생성과 진행 중 인박스의 다른 과제 덮어쓰기를 막는다."""
    path = Path(name.replace('\\', '/'))
    path = path if path.is_absolute() else root / path
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    parent, _, filename = relative.rpartition('/')
    if parent != '.fullops-squad/handovers' or not filename.lower().endswith('.md') or filename == '_TEMPLATE.md':
        return None
    if not HANDOVER.fullmatch(relative):
        return ('현재 지시서는 역할 인박스 `handovers/to_<역할>.md`에 작성하세요. '
                '다음 과제는 PLANS.md에 대기시키고 완료 기록은 handovers/logs/에 보존하세요. '
                '기존 미완료 추가 자료는 handovers/pending/에서 참조하세요.')
    old = board.read(path)
    if old.strip() and isinstance(content, str) and not content.strip():
        return '역할 인박스를 직접 비우지 마세요. work.py finish로 지시서·완료 보고 전문을 로그에 보존한 뒤 비우세요.'
    current, incoming = key_in(root, old), key_in(root, content, path)
    if old.strip() and incoming and current != incoming:
        return (f'진행 중 역할 인박스({current or filename})를 다른 과제({incoming})로 덮어쓸 수 없습니다. '
                '후속 과제는 PLANS.md에 대기시키세요. 같은 과제의 수정은 현재 인박스에 반영하고, '
                '완료하면 work.py finish로 로그를 보존한 뒤 다음 과제를 만드세요.')
    return None


def dispatch_inbox_denial(command):
    """추가 자료만으로 착수하지 않고 현재 역할 인박스를 전달하게 한다."""
    paths = re.findall(r'handovers[/\\][^\s\'"`]+\.md', command)
    if paths and not any(re.fullmatch(r'handovers[/\\]to_[a-z][a-z0-9_-]*\.md', path) for path in paths):
        return ('dispatch의 현재 지시서는 역할 인박스 `handovers/to_<역할>.md`를 지정하세요. '
                '과제명 파일·pending·logs는 참조 자료입니다. 역할 인박스가 사용 중이면 다음 과제는 PLANS.md에 대기시키세요.')
    return None


def handover_denial(root, designer, role, key):
    if role == designer:
        return None
    if not key:
        return '지시서 본문 첫 줄을 `# <과제 키> — <목표>`로 쓰세요.'
    route = route_of(root, key)
    if not route:
        return f'{key}의 route 기록이 없습니다. 먼저 `jev_route.py --key {key}`를 실행하세요.'
    if product_roles(root):
        if route.get('route') == 'implementation' and route.get('role') == role:
            return None
        return f'{key}는 {route.get("route")} → {route.get("role")}입니다. 담당 역할·제품 범위를 확인하고 근거를 남겨 재분류하세요.'
    if route.get('route') != 'simple' or route.get('role') != role:
        return (f'{key}는 {route.get("route")} → {route.get("role")}로 분류됐습니다. '
                f'{role} 지시서는 설계 역할({designer})이 씁니다. 설계 역할을 dispatch하세요.')
    return None


def orca(*args):
    """Orca CLI를 JSON으로 호출한다. 실패하면 None. hook은 coordinator 터미널 환경에서 돌아 호출자가 그 터미널로 식별된다."""
    return integration.orca(*args)


def shell_commands(command):
    """here-doc 본문은 데이터로 두고 최상위 명령만 어휘 분석한다. 셸 실행기는 아니다."""
    lines, visible, delimiter = command.splitlines(keepends=True), [], None
    quote, escaped = None, False
    for line in lines:
        if delimiter:
            if line.strip() == delimiter:
                delimiter = None
            continue
        visible.append(line)
        for n, char in enumerate(line):
            if escaped:
                escaped = False
            elif char == '\\' and quote != "'":
                escaped = True
            elif quote:
                if char == quote:
                    quote = None
            elif char in "'\"":
                quote = char
            elif line.startswith('<<', n) and (n == 0 or line[n - 1] != '<'):
                heredoc = re.match(r'<<-?\s*[\'\"]?([A-Za-z_][A-Za-z0-9_]*)[\'\"]?', line[n:])
                if heredoc:
                    delimiter = heredoc.group(1)
                    break
    command = ''.join(visible)
    lexer = shlex.shlex(command, posix=False, punctuation_chars=';&|\n')
    lexer.whitespace = ' \t\r'
    lexer.whitespace_split = True
    lexer.commenters = ''
    chunks, words = [], []
    try:
        for word in lexer:
            if word and all(c in ';&|\n' for c in word):
                chunks.append(words)
                words = []
            else:
                words.append(word)
    except ValueError:
        return []  # 해석할 수 없는 본문 예시를 실행 명령으로 승격하지 않는다.
    chunks.append(words)
    result, aliases = [], {}
    for words in chunks:
        while words and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.+', words[0]):
            name, value = words.pop(0).split('=', 1)
            aliases[name] = value.strip('\'\"')
        if not words:
            continue
        executable = words[0].strip('\'\"')
        if executable.startswith('$'):
            executable = aliases.get(executable[1:], '')
        result.append([executable, *words[1:]])
    return result


def operation_commands(command, operation, group='orchestration'):
    return [' '.join(words) for words in shell_commands(command) if
            Path(words[0]).name in ('orca', 'orca.exe', 'orca.cmd', 'orca-ide', 'orca-dev') and
            words[1:3] == [group, operation] and not any(word in ('--help', '-h') for word in words)]


def settlement_command(command, state):
    """확인 가능한 단일 Orca 전송만 추적한다. 인용문·echo·도움말·다른 dispatch는 제외한다."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|\n')
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return None
    if len(words) < 4 or Path(words[0]).name not in ('orca', 'orca.exe', 'orca.cmd', 'orca-ide') or words[1:3] != ['orchestration', 'send']:
        return None
    if any(word in ('--help', '-h') or re.fullmatch(r'[;&|]+', word) for word in words):
        return None
    flags = {}
    for n, word in enumerate(words):
        if word.startswith('--'):
            name, sep, value = word.partition('=')
            flags[name] = value if sep else words[n + 1] if n + 1 < len(words) else ''
    if '--payload' in flags:
        try:
            payload = json.loads(flags['--payload'])
            flags['--task-id'], flags['--dispatch-id'] = payload.get('taskId'), payload.get('dispatchId')
        except (ValueError, AttributeError):
            return None
    if flags.get('--type') not in ('worker_done', 'escalation') or flags.get('--dispatch-id') != state.get('dispatch'):
        return None
    if state.get('task') and flags.get('--task-id') != state['task']:
        return None
    return {'command_sha256': hashlib.sha256(command.encode()).hexdigest(), 'dispatch': state['dispatch']}


def delivered(event, state):
    command, _ = targets(field(event, 'tool_input') or {})
    candidate = settlement_command(command, state)
    pending = state.get('sending')
    if not candidate or not pending or candidate != {k: pending[k] for k in candidate}:
        return False
    if pending.get('tool_use_id') != field(event, 'tool_use_id'):
        return False
    response = field(event, 'tool_response')
    if isinstance(response, dict):
        if response.get('exit_code', response.get('exitCode')) not in (None, 0) or response.get('is_error') or response.get('interrupted'):
            return False
        response = response.get('stdout', response.get('output', response))
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except ValueError:
            return False
    return isinstance(response, dict) and response.get('ok') is True and isinstance(response.get('result'), dict) and \
        (response['result'].get('lifecycle') or {}).get('action') != 'rejected' and bool(
            (response['result'].get('message') or {}).get('id') or (response['result'].get('relay') or {}).get('messageId'))


def settled_in_runtime(state):
    """변수·wrapper 호출의 receipt를 해석하지 못하면 현재 Dispatch의 정본 완료를 확인한다."""
    status = orca('orchestration', 'worker-show', '--dispatch', state['dispatch']) or {}
    projection = status.get('projection') or {}
    return projection.get('dispatchId') == state['dispatch'] and bool(state.get('task')) and \
        projection.get('taskId') == state['task'] and projection.get('outcome') in ('succeeded', 'failed') and \
        (projection.get('stage') or {}).get('dispatch') in ('completed', 'failed')


def run_state(run, root=None):
    """(처리하지 않은 worker_done·question·escalation 수, 아직 결과가 없는 Dispatch ID들). 확인할 수 없으면 None."""
    inbox, workers = orca('orchestration', 'check', '--run', run, '--peek'), orca('orchestration', 'worker-list', '--run', run)
    if inbox is None or workers is None:
        return None
    if root is not None:
        integration.record(root, inbox.get('messages') or [])
    unread = sum(1 for m in inbox.get('messages') or [] if m.get('type') in ('worker_done', 'question', 'escalation'))
    active = sorted(w.get('dispatchId') for w in workers.get('workers') or [] if
                    (w.get('projection') or {}).get('outcome') not in ('succeeded', 'failed'))
    return unread, active


def sent_text(command):
    """`orca terminal send`로 보내는 글자. 없으면 빈 문자열."""
    if not re.search(r'\bterminal\s+send\b', command):
        return ''
    try:
        words = shlex.split(command, posix=True)
    except ValueError:
        return command  # 따옴표가 깨진 명령은 길이로만 본다
    for n, word in enumerate(words):
        if word == '--text' and n + 1 < len(words):
            return words[n + 1]
        if word.startswith('--text='):
            return word[len('--text='):]
    return ''


def fingerprint(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def board_reminder(root, state, again):
    """coordinator가 PLANS.md를 바꿨는데 board.json 단계는 그대로면 한 번 알린다. 내용 지문으로 비교해 호스트와 커밋 여부에 상관없다."""
    plans, phases = fingerprint(root / '.fullops-squad/PLANS.md'), fingerprint(root / '.fullops-squad/board/board.json')
    if 'plans_seen' not in state or phases != state.get('board_seen'):
        state['plans_seen'], state['board_seen'] = plans, phases  # 첫 확인이거나 board.json을 고쳤다
        return None
    if plans == state['plans_seen']:
        return None
    if again and state.get('board_blocked') == plans:
        state['plans_seen'] = plans  # 단계가 바뀌지 않았다고 보고 넘어간다
        return None
    state['board_blocked'] = plans
    return ('FullOps: 이 세션에서 PLANS.md는 바뀌었는데 board/board.json의 프로젝트 단계는 그대로입니다. '
            '단계가 시작·완료·막힘·추가됐으면 board.json의 status와 note(80자 이내 한 줄)를 고치세요. '
            '단계가 바뀌지 않았으면 그대로 끝내도 됩니다.')


def handled(root, key):
    """현재 체크아웃과 정본 기본 브랜치의 인박스·로그·PLANS에서 처리 근거를 찾는다."""
    base = root / '.fullops-squad'
    places = [*base.glob('handovers/to_*.md'), *base.glob('handovers/logs/**/*.md'), base / 'PLANS.md']
    if any(integration.key_present(key, board.read(path)) for path in places):
        return True
    settings = integration.config(root)
    if settings is None:
        return False
    try:
        ref, _ = integration.references(root, settings)
        done = subprocess.run(['git', '-C', str(root), 'grep', '-h', '-F', '--', key, ref, '--',
                               '.fullops-squad/PLANS.md', ':(glob).fullops-squad/handovers/to_*.md',
                               ':(glob).fullops-squad/handovers/logs/**/*.md'],
                              capture_output=True, text=True, encoding='utf-8', timeout=10)
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0 and bool(integration.key_present(key, done.stdout))


def route_key_denial(root, command):
    """dispatch(worker-start·task-create)에 Jev 분류 기록이 있는 과제 키가 보이는지. `--task <id>`면 그 과제의 spec도 본다."""
    jev = root / '.fullops-squad/docs/evaluations/jev'
    routes = sorted(jev.glob('*-route.json'), key=lambda p: p.stat().st_mtime, reverse=True) if jev.is_dir() else []
    keys = [p.name[:-len('-route.json')] for p in routes]
    text = command
    for path in re.findall(r'[^\s\'"`]*handovers[/\\]to_[a-z][a-z0-9_-]*\.md', command):  # 지시서 경로를 넘기면 본문 첫 줄의 키
        handover = Path(path) if Path(path).is_absolute() else root / re.sub(r'^\.[/\\]', '', path)
        text += ' Task key: ' + (key_in(root, None, handover) or '')
    task, run = re.search(r'--task[ =]+["\']?(task_[A-Za-z0-9]+)', command), re.search(r'--run[ =]+["\']?([A-Za-z0-9_-]+)', command)
    if task:
        listing = orca('orchestration', 'task-list', *(['--run', run.group(1)] if run else []))
        if listing is None:
            return None  # 과제 내용을 확인할 수 없으면 막지 않는다
        found = next((t for t in listing.get('tasks') or [] if t.get('id') == task.group(1)), {})
        text += ' Task key: ' + (integration.dispatch_key('--spec ' + json.dumps(found.get('spec') or '')) or '')
    named = integration.dispatch_key(text)
    for key in keys:
        if key == named:
            route = route_of(root, key)
            if not route:
                return f'{key}의 route 기록 스키마가 잘못됐습니다. jev_route.py로 재분류하세요.'
            if route.get('route') == 'unresolved':
                return f'{key}의 담당 역할이 미확정입니다. 근거와 함께 재분류한 뒤 배정하세요.'
            return None
    where = f"`--task {task.group(1)}` 과제의 spec" if task else 'dispatch 명령의 spec'
    recent = ', '.join(keys[:5]) or '없음'
    return (f'{where}에 Jev로 분류한 과제 키가 보이지 않습니다. 모든 배정은 `jev_route.py --key <과제 키>`로 먼저 분류하고, '
            f'그 과제 키를 spec에 적어야 합니다. 최근 분류된 키: {recent}. 새 과제면 먼저 분류하고, 기존 과제의 후속이면 그 키를 spec에 넣으세요.')


def native_delegation(event):
    name = str(field(event, 'tool_name') or '').replace('__', '.').split('.')[-1]
    return name in ('Agent', 'Task', 'spawn_agent', 'followup_task')


def dispatch_spec(command, dispatch):
    """직접 spec·PowerShell 변수·저장된 Task를 동일한 배정 검사 입력으로 읽는다."""
    result = dispatch
    variable = re.search(r'--spec\s+(\$[A-Za-z_][A-Za-z0-9_]*)\b', dispatch)
    if variable:
        assignment = re.search(rf'{re.escape(variable.group(1))}\s*=\s*(?:@\'([\s\S]*?)\'@|@"([\s\S]*?)"@|\'([^\']*)\'|"([^"]*)")', command)
        if assignment:
            result += ' ' + next(value for value in assignment.groups() if value is not None)
    task = re.search(r'--task[ =]+["\']?(task_[A-Za-z0-9]+)', dispatch)
    if task:
        run = re.search(r'--run[ =]+["\']?([A-Za-z0-9_-]+)', dispatch)
        listing = orca('orchestration', 'task-list', *(['--run', run.group(1)] if run else []))
        if listing is not None:
            found = next((t for t in listing.get('tasks') or [] if t.get('id') == task.group(1)), {})
            result += ' Task key: ' + (integration.dispatch_key('--spec ' + json.dumps(found.get('spec') or '')) or '') + ' ' + str(found.get('spec') or '')
    return result


def delegation_denial(root, event, state, config, starting, lead):
    """선택 위임만 제한한다. 최상위 coor의 역할 배정과 필수 snapshot 리뷰는 유지한다."""
    native = native_delegation(event)
    optional = native or bool(starting and (state.get('dispatch') or (lead and config['mode'] == 'dev')))
    if not optional:
        return None
    if native:
        import issue_mode
        if (integration.directory(root).parent / 'fullops-issues/state.sqlite').is_file():
            automatic = issue_mode.Store(root).read()
            owner = automatic.get('owner') or {}
            session = field(event, 'session_id')
            if owner.get('provider_session') == session or any(
                    session in job.get('worker_sessions', {}) for job in automatic['jobs'].values()):
                return '자동 이슈의 하위 작업은 권한·중지·완료를 추적할 수 있는 Orca worker-start와 자기 child Run을 사용하세요'
        text = json.dumps(field(event, 'tool_input') or {}, ensure_ascii=False)
    else:
        text = '\n'.join(starting)
    level = config['subagent_level']
    # 필수 독립 리뷰는 기존 clean snapshot/작성자 분리 검사를 이어서 통과해야 한다.
    mandatory_review = (not native and lead and not state.get('dispatch') and
                        all(re.search(r'Purpose\s*:\s*review\b', item, re.I) and
                            all(label in item for label in ('Review SHA:', 'Implementer session:', 'Reviewer session:'))
                            for item in starting))
    if level == 'off' and not mandatory_review:
        return 'subagent_level=off입니다. 선택형 하위 위임 대신 직접 작업하거나 setup.py --subagent-level로 설정하세요'
    for item in ([text] if native else starting):
        purpose = re.search(r'Purpose\s*:\s*(research|review|implementation)\b', item, re.I)
        if not purpose:
            return '하위 작업에 Purpose: research|review|implementation과 파일 소유권·완료 조건을 명시하세요'
        if level == 'lite' and purpose.group(1).lower() == 'implementation':
            return 'subagent_level=lite는 읽기 전용 조사·리뷰만 허용합니다. 병렬 구현은 standard 또는 full을 선택하세요'
    return None


def tool_denial(root, event, state):
    tool = field(event, 'tool_input') or {}
    if not isinstance(tool, dict):
        return None
    command, files = targets(tool)
    import issue_mode
    try:
        denial = issue_mode.boundary(root, field(event, 'session_id'), command, files, shell_commands(command), state)
    except (OSError, ValueError, KeyError, issue_mode.sqlite3.Error):
        denial = '자동 이슈 상태/범위를 확인하지 못했습니다. 상태를 복구한 뒤 재개하세요'
    if denial:
        return denial
    candidate = settlement_command(command, state)
    if candidate:
        state['sending'] = {**candidate, 'tool_use_id': field(event, 'tool_use_id')}
    starting = operation_commands(command, 'worker-start')
    python_commands = [' '.join(words) for words in shell_commands(command) if re.fullmatch(r'python(?:3(?:\.\d+)?)?(?:\.exe)?', Path(words[0]).name)]
    for run in STARTED.findall('\n'.join(starting)):  # 띄운 worker의 결과를 받기 전에 끝내지 않게 Run을 기억한다
        state['runs'] = sorted(set(state.get('runs', [])) | {run})
    for key in ROUTED.findall('\n'.join(python_commands)):  # 분류한 과제는 세션이 끝나기 전에 배정했는지 확인한다
        state['routed'] = sorted(set(state.get('routed', [])) | {key})
    role, designer = context(root)
    lead = primary(root, state)
    config = policy.load(root)
    creating = operation_commands(command, 'task-create')
    specs = {item: dispatch_spec(command, item) for item in starting + creating}
    denial = delegation_denial(root, event, state, config, [specs[item] for item in starting], lead)
    if denial:
        return denial
    direct_role = config.get('primary_role') if lead and config['mode'] == 'dev' else None
    for name, content in files:
        denial = inbox_denial(root, name, content)
        if denial:
            return denial
    if lead:
        for check in operation_commands(command, 'check'):
            flags = []
            for flag in ('--run', '--terminal'):
                value = re.search(rf'{flag}[ =]+["\']?([A-Za-z0-9_-]+)', check)
                if value:
                    flags += [flag, value.group(1)]
            inbox = orca('orchestration', 'check', *flags, '--peek')
            if inbox is not None:
                integration.record(root, inbox.get('messages') or [])
    injection_commands = operation_commands(command, 'send', 'terminal') + operation_commands(command, 'dispatch')
    if INJECT.search('\n'.join(injection_commands)):
        return '지시서를 터미널로 주입하면 worker가 `worker_done`을 보낼 수 없습니다. `orchestration worker-start --run <run id>`로 띄우세요.'
    asking_help = re.search(r'(?:^|\s)(?:--help|-h)(?=\s|[;&|]|$)', command)
    if lead and any(len(sent_text(send)) > SEND_LIMIT for send in
                                     operation_commands(command, 'send', group='terminal')):
        return ('작업 지시를 `terminal send`로 보내면 Orca 추적 밖에서 돌아 `worker_done`·Run 대기·Stop 검사가 빠집니다. '
                '같은 과제의 후속은 조건이 맞으면 `worker-start --terminal <핸들>`로 붙이고, 실패하거나 오래 쉰 세션이면 '
                '새 세션으로 dispatch하세요(spec에 지시서 경로·이전 SHA). 짧은 확인 입력만 직접 보낼 수 있습니다.')
    for dispatch in starting:
        if '--run' not in dispatch:
            return '`worker-start`에 `--run <run id>`를 붙이세요. 없으면 완료 보고가 다른 Run으로 갈 수 있습니다.'
    for dispatch in (starting + creating if lead else []):
        integration_spec = specs[dispatch]
        denial = dispatch_inbox_denial(integration_spec)
        if denial:
            return denial
        denial = integration.denial(root, integration_spec)
        if denial:
            return denial
        denial = route_key_denial(root, integration_spec)
        if denial:
            return denial
        if dispatch in starting:
            denial = integration.baseline_denial(root, integration_spec)
            if denial:
                return denial
    if lead and designer:
        new = re.search(r'\bwork\.py\b.*\bnew\b', '\n'.join(python_commands))
        if new and not asking_help:
            try:
                words = shlex.split(command, posix=True)
            except ValueError:
                words = command.split()
            args = dict(zip(words, words[1:]))
            denial = None if direct_role and args.get('--role') == direct_role else handover_denial(
                root, designer, args.get('--role'), args.get('--key'))
            if denial:
                return denial
        for name, content in files:
            match = HANDOVER.search(name.replace('\\', '/'))
            if match and match.group(1) != direct_role:
                path = Path(name) if Path(name).is_absolute() else root / name
                denial = handover_denial(root, designer, match.group(1), key_in(root, content, path))
                if denial:
                    return denial
    if role == designer and not (lead and policy.load(root)['mode'] == 'dev'):
        for name, _ in files:
            if Path(name).suffix.lower() in CODE and '.fullops-squad/' not in name.replace('\\', '/'):
                return f'설계 역할은 코드를 고치지 않습니다({name}). 역할별 지시서에 적고 worker에게 맡기세요.'
    return None


BRIEF = {
    'primary-dev': ('FullOps dev 주 담당자: 사용자와 직접 기술 계획·구현·검증을 진행한다. 전문가가 필요하면 '
                    'jev_route.py 분류 → 역할 인박스 → worker-start --run으로 배정하고 결과를 리뷰·통합한다. '
                    '제품 범위 변경은 사용자/기획 담당과 확인한다. 직접 작업은 부모 dispatch·가짜 worker_done 없이 '
                    '기준 SHA와 완료 조건을 기록하고 현재 HEAD의 lint 및 다른 세션의 고정 SHA 독립 리뷰 후 완료한다.'),
    'coordinator': ('FullOps coordinator: 새 개발 요청은 과제 키를 정하고 `jev_route.py`로 먼저 분류한다. 플러그인·setup 갱신, 워크트리 동기화·병합, 현황판 정리 같은 운영 작업은 분류하지 않고 직접 처리한다. simple이면 그 역할 지시서를, '
                    'design이면 설계 역할을 `worker-start --run`으로 띄운다. 설계·범위 질문은 직접 답하지 않고 설계 역할에게 넘긴다. '
                    '프로젝트 단계가 바뀌거나 늘면 .fullops-squad/board/board.json을 고친다. 이 규칙은 hook이 강제하고, 세션이 끝나면 현황판이 갱신된다.'),
    'designer': ('FullOps 설계 역할: 설계 문서와 역할별 지시서만 쓰고 코드는 고치지 않는다. 끝나면 preamble의 `worker_done`으로 '
                 '`[설계] <과제 키> | 지시서: … | 역할: … | SHA …`를 보낸다.'),
    'tester': ('FullOps tester: 동작 검증을 맡는다. 제품 코드는 고치지 않고 테스트 코드·시나리오·검증 증거만 만든다. '
               '검증은 `fullops-test` 스킬의 도구와 순서를 따르고, 결과는 `qa-reports/<과제 키>-test/`에 남긴다. '
               '실패는 재현 절차와 증거로 보고하고 직접 고치지 않는다. 끝나면 preamble의 `worker_done`을 한 번 보낸다.'),
    'worker': ('FullOps worker: 설계·범위 판단이 필요하면 preamble의 `ask`로 묻고 추측하지 않는다. 끝나면 preamble의 '
               '`worker_done`을 한 번 보낸다. 보내지 않고 끝내면 hook이 한 번 막는다.'),
}

PRODUCT_BRIEF = {
    'coordinator': ('FullOps coordinator: 제품 규칙/범위/공유 제품 기준 결정만 기획자에게 배정한다. 기술 계획·분석·구현·테스트는 담당 worker의 같은 과제다. '
                    '`jev_route.py`의 implementation은 목표·규칙·범위·완료 조건·정본 링크로 짧게 인계하고, product는 기획자에게, unresolved는 배정 근거를 확인한다. '
                    '정상 worker는 worker_done 중심으로 기다리고 로그 재독은 설정된 간격을 따른다. 운영 작업은 직접 처리하고 PLANS/board 상태를 함께 갱신한다.'),
    'designer': ('FullOps 제품 기획자: 플레이/제품 목표·규칙/수치·화면/아트 방향·우선순위·사용자 완료 조건과 모호한 공유 제품 기준을 결정한다. '
                 '기술 계획·구조/API·버그 수정 방법은 DEV 책임이다. 제품 코드는 고치지 않는다. 완료하면 preamble의 worker_done으로 고정 SHA·결정·인계 링크를 보낸다.'),
    'worker': ('FullOps worker: 기존 요구 안의 코드 파악→짧은 기술 계획→구현→테스트·기술 문서 갱신을 같은 과제에서 수행한다. '
               '기술 판단은 직접 해결하고 제품 규칙 변경·범위 확대·공유 제품 기준 불명확성만 coordinator에게 ask한다. '
               '좁은 DEV/ART 규격은 담당자끼리 coordinator 경유 조율한다. 완료하면 preamble의 worker_done을 보낸다. 독립 코드 리뷰·직접 시각 검수·미해결 high 차단은 유지한다.'),
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
    try:
        config = policy.load(root)
    except policy.PolicyError:
        command, _ = targets(field(event, 'tool_input') or {})
        commands = shell_commands(command)
        if mode == 'tool' and len(commands) == 1:
            words = commands[0]
            if len(words) > 2 and re.fullmatch(r'python(?:3(?:\.\d+)?)?(?:\.exe)?', Path(words[0]).name) and (
                    Path(words[1].strip('\'"')).resolve() == Path(__file__).with_name('setup.py').resolve()) and '--repo' in words:
                index = words.index('--repo')
                if index + 1 < len(words) and Path(words[index + 1].strip('\'"')).resolve() == root and (
                        any(flag in words for flag in ('--rollback', '--mode', '--primary-role', '--test-level', '--subagent-level'))):
                    return {}
        raise
    current = [config['mode'], config.get('primary_role'), config.get('primary_branch')]
    if state.get('operating') is not None and state['operating'] != current:
        raise policy.PolicyError('운영 모드가 바뀌었습니다. 기존 세션에 주입하지 말고 새 세션을 시작하세요')
    before = dict(state)
    output = {}
    if mode == 'start':
        state['operating'] = current
        state['provider_session'] = field(event, 'session_id')
        state['orca_terminal'] = os.getenv('ORCA_TERMINAL_HANDLE')
        if state['provider_session'] and state['orca_terminal']:
            from issue_mode import hook_path
            write_json(hook_path(root, 'terminal-' + state['orca_terminal']),
                       {key: state[key] for key in ('provider_session', 'orca_terminal')})
        role, designer = context(root)
        kind = ('primary-dev' if config['mode'] == 'dev' and primary(root, state) else
                'coordinator' if role == 'coordinator' else 'designer' if role == designer
                else 'tester' if role == marked_role(root, 'tester') else 'worker')
        brief = PRODUCT_BRIEF.get(kind, BRIEF[kind]) if product_roles(root) else BRIEF[kind]
        brief += ' ' + policy.test_brief(config['test_level'])
        brief += ' ' + policy.subagent_brief(config['subagent_level'])
        brief += (' 현재 작업은 역할별 handovers/to_<역할>.md 한 곳에 쓴다. 다음 과제는 PLANS.md에 대기시키고, '
                  '완료하면 work.py finish로 지시서·결과 전문을 로그에 보존한 뒤 인박스를 재사용한다. '
                  '과제명 파일·pending·logs를 현재 지시서로 dispatch하지 않는다.')
        if kind in ('coordinator', 'primary-dev'):
            brief += (' 완료 보고마다 현재 SHA의 리뷰·기본 브랜치 병합·원격 push·하위 워크트리 동기화를 '
                      '바로 처리한다. 절차는 fullops-orca의 merge 절을 따른다. coordinator 역할 브랜치만 push하지 않는다.')
            brief += ' 자동 이슈 과제 GH-<저장소 ID>-<번호>-A<attempt>는 예외로 draft PR과 integration hold까지만 처리하고 main 병합은 사용자 판단을 기다린다.'
        try:  # 워크트리에 빠진 .fullops-squad/.env*를 연결한다. 실패해도 세션을 막지 않는다
            linked = env_link.link(root)
        except Exception:  # noqa: BLE001
            linked = []
        if linked:
            copied = [name for name, how in linked if how == 'copy']
            brief += (f" 워크트리에 없던 {', '.join(name for name, _ in linked)}를 원본 체크아웃에서 연결했다."
                      + (f" {', '.join(copied)}는 링크를 만들 수 없어 복사했으니 원본이 바뀌면 다시 복사해야 한다." if copied else ''))
        try:  # 마켓플레이스 설치는 npm 도구·사용자 스킬을 넣지 않으므로 빠졌으면 알린다
            absent = deps.missing_tools()
        except Exception:  # noqa: BLE001
            absent = []
        if absent:
            brief += (f" FullOps 필수 CLI가 없다: {', '.join(absent)}. 사용자에게 알리고 승인받아 "
                      f"`python3 {Path(__file__).resolve().parent / 'deps.py'} --host <지금 CLI>`로 의존성을 설치한다.")
        # 샌드박스 셸이 사용자 PATH를 물려받지 않으면 python3·orca를 못 찾는다. hook 환경에서 찾은 경로를 알린다
        brief += f' 셸에서 python3나 orca를 찾지 못하면 전체 경로를 쓴다: python3={sys.executable}, orca={find_orca() or "찾지 못함"}.'
        brief += f' 선택형 fullops-issues 활성화의 host SessionStart ID는 {field(event, "session_id")}이다. 활성화는 사용자 요청 때만 한다.'
        output = {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': brief}}
    elif mode == 'prompt':
        match = DISPATCH.search(str(field(event, 'prompt') or ''))
        if match and match.group(1) != state.get('dispatch'):
            state = {**{k: state[k] for k in ('provider_session', 'orca_terminal', 'operating') if k in state},
                     'dispatch': match.group(1), 'settled': False}
            task = re.search(r'--task-id[ =]+([A-Za-z0-9_.:-]+)', str(field(event, 'prompt') or ''))
            if task:
                state['task'] = task.group(1)
            if config['mode'] == 'dev':
                role, designer = context(root)
                kind = 'designer' if role == designer else 'tester' if role == marked_role(root, 'tester') else 'worker'
                brief = PRODUCT_BRIEF.get(kind, BRIEF[kind]) if product_roles(root) else BRIEF[kind]
                output = {'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit',
                          'additionalContext': brief + ' ' + policy.test_brief(config['test_level']) +
                          ' ' + policy.subagent_brief(config['subagent_level'])}}
    elif mode == 'tool':
        denial = tool_denial(root, event, state)
        if denial:
            output = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                             'permissionDecisionReason': 'FullOps: ' + denial}}
        else:
            import issue_mode
            command, _ = targets(field(event, 'tool_input') or {})
            try:
                issue_mode.reserve_dispatch(root, field(event, 'session_id'), shell_commands(command), context=state)
            except (OSError, ValueError, KeyError, TypeError, issue_mode.sqlite3.Error) as error:
                output = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                                 'permissionDecisionReason': 'FullOps: 배정 기록을 확인하지 못했습니다: ' + str(error)}}
    elif mode == 'post':
        if delivered(event, state):
            state['settled'] = True
            state.pop('sending', None)
    if mode in ('tool', 'post', 'prompt'):
        import issue_mode
        issue_mode.heartbeat(root, field(event, 'session_id'))
    if mode == 'stop' and (field(event, 'reason') or 'end_turn') == 'end_turn':
        if state.get('dispatch') and not state.get('settled') and settled_in_runtime(state):
            state['settled'] = True
            state['settlement_source'] = 'Orca current dispatch outcome'
        if state.get('dispatch') and not state.get('settled'):
            if field(event, 'stop_hook_active') and state.get('blocked'):
                output = {'systemMessage': 'FullOps: worker_done 없이 dispatched 세션을 끝냈습니다. coordinator가 계속 기다립니다.'}
            else:
                state['blocked'] = True
                output = {'decision': 'block', 'reason':
                          f"FullOps: Dispatch {state['dispatch']}의 `worker_done`을 보내지 않았습니다. 과제를 마쳤으면 preamble의 "
                          '`worker_done` 명령(`--outcome succeeded|failed`)을 보내고, 판단이 필요하면 `ask`, 막혔으면 `escalation`을 보내세요. '
                          '아직 작업 중이면 계속 진행하세요.'}
        pending = [k for k in state.get('routed', []) if not handled(root, k)]
        if pending and 'decision' not in output:
            if field(event, 'stop_hook_active') and state.get('pending_blocked') == pending:
                output = {'systemMessage': f"FullOps: 분류만 하고 배정하지 않은 과제가 있습니다: {', '.join(pending)}"}
            else:
                state['pending_blocked'] = pending
                output = {'decision': 'block', 'reason':
                          f"FullOps: `jev_route.py`로 분류한 과제 {', '.join(pending)}를 아직 배정하지 않았습니다. "
                          '대화 요약 뒤라면 route 기록(docs/evaluations/jev/<키>-route.json)을 다시 읽고 지시서 작성과 dispatch를 이어서 하세요. '
                          '배정하지 않을 이유가 있으면 PLANS.md에 과제 키와 보류 사유를 적고 끝내세요.'}
        for run in state.get('runs', []):
            status = None if 'decision' in output else run_state(run, root)
            if not status or not (status[0] or status[1]):
                continue
            unread, active = status
            marker = [run, unread, active]
            if field(event, 'stop_hook_active') and state.get('wait_blocked') == marker:
                output = {'systemMessage': f'FullOps: Run {run}의 worker 결과를 받지 않은 채 세션을 끝냈습니다.'}
            elif unread:
                state['wait_blocked'] = marker
                output = {'decision': 'block', 'reason':
                          f'FullOps: Run {run}에 처리하지 않은 worker_done·질문·escalation {unread}건이 있습니다. '
                          f'`orca orchestration check --run {run}`으로 받아 규칙대로 처리하고 ack하세요.'}
            else:
                state['wait_blocked'] = marker
                output = {'decision': 'block', 'reason':
                          f"FullOps: Run {run}의 worker({', '.join(active)})가 아직 실행 중입니다. Orca 알림은 보장되지 않고 "
                          'Codex·grok은 백그라운드 명령이 끝나도 세션을 깨우지 않습니다. '
                          f'`python3 <orca_wait.py> --orca <orca> --run {run}`을 포그라운드로 실행해 결과를 기다리세요. '
                          '지금 사용자와 다른 일을 해야 하면 그 이유를 말하고 다시 끝내면 됩니다.'}
            break
        if primary(root, state):
            denial = integration.denial(root)
            if denial and 'decision' not in output:
                output = {'decision': 'block', 'reason': 'FullOps: ' + denial}
            reminder = None if 'decision' in output else board_reminder(root, state, field(event, 'stop_hook_active'))
            if reminder:
                output = {'decision': 'block', 'reason': reminder}
            try:
                board.write(root)  # 현황판 데이터 갱신. 실패해도 종료를 막지 않는다
            except Exception:  # noqa: BLE001
                pass
    if state != before:
        write_json(session, state)
    return output


if __name__ == '__main__':
    try:
        result = main()
    except policy.PolicyError as error:
        result = ({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                   'permissionDecisionReason': str(error)}} if sys.argv[1] == 'tool' else
                  {'decision': 'block', 'reason': str(error)} if sys.argv[1] == 'stop' else
                  {'systemMessage': str(error)})
    except Exception:  # noqa: BLE001 — hook은 실패해도 작업을 막지 않는다
        result = {}
    print(json.dumps(result, ensure_ascii=False))
