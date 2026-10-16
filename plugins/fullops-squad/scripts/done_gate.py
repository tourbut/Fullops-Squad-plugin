#!/usr/bin/env python3
"""FullOps done-gate hook. 이 세션의 변경에 현재 HEAD의 lint.py 통과 기록이 없으면 종료(Stop)를 막는다.

Canny(qkal/canny)의 "사실만 막는다"를 ledger 없이 줄였다. SessionStart에 세션 시작 지점과 규칙을 남기고,
Stop에서 이 체크아웃이 직접 만든 커밋(HEAD reflog의 commit 항목)과 미커밋 변경의 코드 파일만 본다.
기존 worker는 반복 Stop을 경고로 통과시킨다. dev 직접 개발은 설정·에셋도 검사하고 독립 리뷰를 필수로 유지한다.
"""
from fnmatch import fnmatch
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

from lint import C_STYLE, CONFIG, DEFAULT, HASH, PY
import deliverables
import policy
from storage import write_json

CODE = PY | HASH | C_STYLE
LINT = Path(__file__).resolve().with_name('lint.py')


def hook_status(root, session):
    """세션별 실제 호출 근거만 읽는다. 기록 없음은 설치 여부와 무관하게 unknown이다."""
    gate = Path(git(root, 'rev-parse', '--absolute-git-dir')) / 'fullops-gate/hooks'
    key = re.sub(r'[^A-Za-z0-9_-]', '_', str(session or 'default'))[:100]
    result = {}
    for name in ('done', 'flow'):
        try:
            record = json.loads((gate / f'{name}-{key}.json').read_text(encoding='utf-8'))
            if not isinstance(record, dict) or not isinstance(record.get('events', {}), dict) or not isinstance(record.get('warned', []), list):
                raise ValueError('invalid hook record')
            result[name] = record
        except (OSError, ValueError):
            result[name] = {'status': 'unknown'}
    return result


def run_hook(callback, name):
    """기존 hook 판정은 유지하고 실행·오류를 남긴다. 같은 오류 안내는 세션당 한 번이다."""
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            event = {}
    except ValueError:
        event = {}
    mode = sys.argv[1]
    error = None
    try:
        output = callback(event)
    except policy.PolicyError as problem:
        output = ({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                   'permissionDecisionReason': str(problem)}} if name == 'flow' and mode == 'tool' else
                  {'decision': 'block', 'reason': str(problem)} if mode == 'stop' else
                  {'systemMessage': str(problem)})
    except Exception as problem:  # noqa: BLE001 — hook 오류는 작업을 막지 않는다
        output, error = {}, type(problem).__name__
    if mode == 'status':
        return output
    try:
        root = Path(git(field(event, 'cwd') or '.', 'rev-parse', '--show-toplevel'))
        if not (root / '.fullops-squad/fullops.json').is_file():
            return output
        session = re.sub(r'[^A-Za-z0-9_-]', '_', str(field(event, 'session_id') or 'default'))[:100]
        path = Path(git(root, 'rev-parse', '--absolute-git-dir')) / 'fullops-gate/hooks' / f'{name}-{session}.json'
        previous = hook_status(root, session)[name]
        warned = previous.get('warned', [])
        first = bool(error and error not in warned)
        record = {'status': 'error' if error else 'executed', 'mode': mode,
                  'at': datetime.now(timezone.utc).isoformat(), 'error': error,
                  'warned': warned + ([error] if first else [])}
        record['events'] = {**previous.get('events', {}), mode: {k: record[k] for k in ('status', 'at', 'error')}}
        write_json(path, record)
        if first:
            output['systemMessage'] = f'FullOps {name} hook 오류({error}). 작업은 계속하고 수락 전 필수 검사 증거를 확인하세요.'
    except Exception:  # noqa: BLE001 — 기록 경로도 사용할 수 없으면 기존 fail-open을 유지한다
        pass
    return output


def field(event, name):
    """Claude·Codex는 snake_case, grok은 camelCase 키로 보낸다."""
    return event.get(name, event.get(re.sub(r'_(\w)', lambda m: m.group(1).upper(), name)))


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


def code_changes(root, state, all_files=False):
    """(이 세션이 만든 커밋 파일, 미커밋 파일). 직접 개발은 설정·에셋도 검사한다."""
    skip = excluded(root)

    def code(path):
        # board.py가 자동 관리하는 파일은 레포별 lint 제외 설정과 무관하게 개발 코드가 아니다.
        if path in ('.fullops-squad/board/board-data.js', '.fullops-squad/board/index.html'):
            return False
        return (all_files or Path(path).suffix.lower() in CODE) and not any(
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


def expected_base(root, state):
    roles = json.loads((root / '.fullops-squad/fullops.json').read_text()).get('roles', {})
    branch = git(root, 'rev-parse', '--abbrev-ref', 'HEAD')
    role = next((r for r, b in roles.items() if b == branch), None)
    inbox = root / f'.fullops-squad/handovers/to_{role}.md'
    meta = deliverables.front_matter(inbox.read_text(encoding='utf-8')) if role and inbox.is_file() else None
    base = (meta or {}).get('base') or state.get('base')
    if base:
        state['base'] = git(root, 'rev-parse', '--verify', base + '^{commit}')
    return state.get('base')


def main(event=None):
    mode = sys.argv[1]
    if event is None:
        try:
            event = json.load(sys.stdin)
        except ValueError:
            event = {}
    root = Path(git(field(event, 'cwd') or '.', 'rev-parse', '--show-toplevel'))
    if not (root / '.fullops-squad/fullops.json').is_file():
        return {}
    if mode == 'status':
        return hook_status(root, field(event, 'session_id'))
    config = policy.load(root)
    gate = Path(git(root, 'rev-parse', '--absolute-git-dir')) / 'fullops-gate'
    gate.mkdir(exist_ok=True)
    session = gate / (re.sub(r'[^A-Za-z0-9_-]', '_', str(field(event, 'session_id') or 'default'))[:100] + '.json')
    state = json.loads(session.read_text()) if session.is_file() else None
    flow_path = gate / ('flow-' + session.name)
    flow = json.loads(flow_path.read_text()) if flow_path.is_file() else {}
    from jev_route import coordinator_role
    direct = config['mode'] == 'dev' and policy.identity(root, config, coordinator_role(root), bool(flow.get('dispatch')))[1]
    if mode == 'start':
        if state is None:  # resume·compact는 처음 시작 지점을 유지한다
            state = {'reflog': len(reflog(root))}
            if direct:
                state['base'] = git(root, 'rev-parse', 'HEAD')
                state['implementer_session'] = str(field(event, 'session_id') or 'default')
        if not direct:
            expected_base(root, state)
        write_json(session, state)
        if (field(event, 'source') or 'startup') not in ('startup', 'clear'):
            return {}
        try:
            names = [c['name'] for c in json.loads((root / CONFIG).read_text()).get('commands', [])]
        except (OSError, ValueError, AttributeError, KeyError, TypeError):
            names = []
        scope = '개발 파일(설정·에셋 포함)' if direct else '코드 파일'
        completion = ('현재 SHA의 lint를 통과해야 하고, `review.py need`가 대규모 변경으로 판정하면 사용자에게 독립 리뷰 진행 여부를 묻고 '
                      '다른 세션의 독립 리뷰 또는 사용자 면제(`review.py waive`) 기록을 남겨야 한다. '
                      '반복 Stop으로 생략할 수 없다. ' if direct else
                      '통과 기록이 없으면 종료가 한 번 막힌다. 적용할 검사가 없으면 이유를 말하고 다시 끝낸다. ')
        brief = (f'FullOps done-gate: 이 세션에서 {scope}을 바꾸면 끝내기 전에 변경을 커밋하고 '
                 f'`python3 {LINT} --repo {root} --from <지시서의 기준 ref>`를 통과시킨다'
                 f"{' (등록 명령: ' + ', '.join(names) + ')' if names else ''}. "
                 f'{completion}'
                 '테스트 로그를 증거로 남길 때 `| tail` 등으로 명령 자신의 종료코드를 가리지 않는다.')
        return {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': brief}}
    if state is None or (field(event, 'reason') or 'end_turn') != 'end_turn':
        return {}  # 게이트 도입 전 세션, grok의 세션 종료 Stop
    committed, dirty = code_changes(root, state, all_files=direct)
    if not committed and not dirty:
        return {}
    head = git(root, 'rev-parse', 'HEAD')
    expected = state.get('base') if direct else expected_base(root, state)
    write_json(session, state)  # 성공 Stop 뒤 finish가 인박스를 비워도 기준을 보존한다.
    try:
        record = json.loads((gate / 'pass.json').read_text())
        passed = record.get('head') == head and (not expected or record.get('base') == expected)
    except (OSError, ValueError, AttributeError):
        passed = False
    if passed and not dirty:
        if direct:
            import review
            try:
                if not expected or review.need(root, expected, head)['required']:
                    review.direct_check(root, expected, head, state.get('implementer_session'))
            except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.CalledProcessError) as error:
                return {'decision': 'block', 'reason': 'FullOps: ' + str(error)}
        return {}
    marker = [head, [[p, (root / p).stat().st_mtime_ns if (root / p).exists() else None] for p in dirty]]
    if direct:
        return {'decision': 'block', 'reason': 'FullOps dev: 현재 HEAD의 lint 통과와 깨끗한 작업 경계가 필요합니다. '
                '직접 구현은 반복 Stop으로 검사를 생략할 수 없습니다.'}
    if field(event, 'stop_hook_active') and state.get('blocked') == marker:
        return {'systemMessage': 'FullOps: lint.py 통과 기록 없이 세션을 끝냈습니다. 완료 보고의 검증 항목을 확인하세요.'}
    write_json(session, {**state, 'blocked': marker})
    files = (dirty or committed)[:5]
    action = '변경을 커밋하고 ' if dirty else ''
    return {'decision': 'block',
            'reason': f"FullOps: 코드 파일({', '.join(files)})이 바뀌었지만 HEAD {head[:12]}의 lint.py 통과 기록이 없습니다. "
                      f'{action}`python3 {LINT} --repo {root} --from <지시서의 기준 ref>`를 실행해 ERROR를 고친 뒤 끝내세요. '
                      '적용할 검사가 없거나 실행할 수 없으면 이유를 말하고 다시 끝내면 됩니다.'}


if __name__ == '__main__':
    print(json.dumps(run_hook(main, 'done'), ensure_ascii=False))
