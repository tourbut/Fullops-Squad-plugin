#!/usr/bin/env python3
"""Unity 플레이어를 --jev-play로 띄워 Jev가 행동을 고르게 하고, 시나리오의 검증 조건으로 판정한다.

게임 쪽 브리지(com.fullops.jevplay, `unity_bridge.py install`로 설치)가 결정마다 게임을 멈추고 state-<n>.json을 쓰면,
이 스크립트가 Jev에 묻고 action-<n>.json을 쓴다. 행동은 브리지가 준 목록에서만 고른다. 결과는 qa-reports/<과제 키>-test/에 남는다.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from jev_observe import MODEL, api_key, checked_answer, request, safe_text
import test_record

CONFIG = '.fullops-squad/test/unity-play.json'
FINISH = {'done': 'The goal is complete according to the current state.',
          'blocked': 'The goal cannot progress: the needed actor or action is missing, or the game is stuck.'}
HINT = ('You play a game to reach `goal`. Choose the next action from `actions`. Distances, reach and directions are already '
        'measured in `player` and `actors`. Use `history` and `lastOutcome` to avoid repeating a step that did not help. '
        'Choose done only when the state shows the goal is complete.')
STALL = 3


def problems(scenario):
    """실행 전에 시나리오를 점검한다. Jev 비용과 플레이어 실행 전에 잘못 쓴 시나리오를 거른다."""
    found = []
    if not isinstance(scenario.get('goal'), str) or not scenario['goal'].strip():
        found.append('goal이 없다')
    covers = scenario.get('covers')
    if not isinstance(covers, list) or not covers or not all(isinstance(c, str) and c.strip() for c in covers):
        found.append('covers에 이 시나리오가 검증하는 요구사항·통과 조건을 하나 이상 적는다')
    checks = scenario.get('checks')
    if not isinstance(checks, list) or not checks:
        found.append('checks가 없으면 통과를 판정할 수 없다')
    else:
        for n, c in enumerate(checks, 1):
            kinds = [k for k in ('field', 'text', 'actor') if isinstance(c, dict) and k in c]
            if len(kinds) != 1:
                found.append(f'checks[{n}]는 field, text, actor 중 하나만 가진다')
            elif kinds == ['field'] and ('value' not in c or c.get('op', '==') not in ('==', '!=', '>', '>=', '<', '<=')):
                found.append(f'checks[{n}] field는 value와 op(==, !=, >, >=, <, <=)가 필요하다')
    if not isinstance(scenario.get('player_args', []), list):
        found.append('player_args는 목록이다')
    if not isinstance(scenario.get('max_steps', 30), int) or not 1 <= scenario.get('max_steps', 30) <= 200:
        found.append('max_steps는 1~200이다')
    return found


def wait_file(path, process, timeout):
    """브리지가 쓴 파일을 기다린다. 플레이어가 먼저 끝나면 None."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass  # 쓰는 중이거나 Windows에서 교체 중
        if process.poll() is not None:
            return None
        time.sleep(0.05)
    return None


def write_action(play, step, action):
    temporary = play / f'action-{step}.json.tmp'
    temporary.write_text(json.dumps({'step': step, 'action': action}), encoding='utf-8')
    os.replace(temporary, play / f'action-{step}.json')


def model_state(state):
    """Jev에 보낼 상태. 브리지가 준 이름·문구는 비밀값 검사를 거친다."""
    def clean(value, limit=200):
        try:
            return safe_text(str(value), limit)
        except ValueError:
            return '[omitted]'
    actors = [{'name': clean(a.get('name')), 'group': a.get('group'), 'distance': round(a.get('distance', 0), 2),
               'direction': a.get('direction'), 'withinReach': a.get('withinReach')} for a in state.get('actors') or []]
    return {'player': state.get('player') and {'name': clean(state['player'].get('name'))},
            'actors': actors,
            'fields': {f['name']: clean(f.get('value') if not f.get('error') else 'error: ' + f['error']) for f in state.get('fields') or []},
            'texts': [clean(t, 160) for t in state.get('texts') or []],
            'lastAction': state.get('lastAction'), 'lastOutcome': state.get('lastOutcome')}


def ask(call, scenario, state, history):
    actions = {a['id']: safe_text(a['description'], 300) for a in state.get('actions') or []}
    actions.update(FINISH)
    body = {'goal': safe_text(scenario['goal'], 1000), **model_state(state), 'history': history[-6:],
            'step': state['step'], 'steps_left': scenario.get('max_steps', 30) - state['step']}
    response, latency = call({'model': MODEL, 'state': body,
                              'questions': {'action': {'type': 'choice', 'instructions': HINT, 'criteria': actions}}})
    return {'action': checked_answer(response['answers']['action'], actions), 'latency_s': latency,
            'cost': (response.get('usage') or {}).get('cost'), 'cached': bool(response.get('cached'))}


def check(condition, state):
    """마지막 상태로 판정한다. field는 브리지가 읽은 값, text는 화면 문구, actor는 그룹의 존재 여부다."""
    if 'field' in condition:
        field = next((f for f in state.get('fields') or [] if f['name'] == condition['field']), None)
        value = None if field is None or field.get('error') else field.get('value')
        try:
            left, right = float(value), float(condition['value'])
        except (TypeError, ValueError):
            left, right = value, str(condition['value'])
        ops = {'==': left == right, '!=': left != right}
        if isinstance(left, float):
            ops.update({'>': left > right, '>=': left >= right, '<': left < right, '<=': left <= right})
        return {'condition': condition, 'value': value, 'passed': value is not None and ops.get(condition.get('op', '=='), False)}
    if 'text' in condition:
        found = any(condition['text'] in t for t in state.get('texts') or [])
        return {'condition': condition, 'value': found, 'passed': found}
    present = any(a.get('group') == condition['actor'] for a in state.get('actors') or [])
    return {'condition': condition, 'value': present, 'passed': present != bool(condition.get('absent'))}


def run(scenario, play, launch, call, out, log=print, timeout=120):
    """launch(play) → poll()/wait()/kill()이 있는 프로세스. 오프라인 테스트는 가짜 게임을 넘긴다."""
    process = launch(play)
    history, events, result, state = [], [], None, None
    last, repeats = None, 0
    try:
        for step in range(1, scenario.get('max_steps', 30) + 1):
            new = wait_file(play / f'state-{step}.json', process, timeout)
            if new is None:
                result = 'no state (player exited or timed out)'
                break
            state = new
            decision = ask(call, scenario, state, history)
            action = decision['action']['choice']
            if action in FINISH:
                write_action(play, step, 'quit')
                checks = [check(c, state) for c in scenario.get('checks', [])]
                result = 'passed' if action == 'done' and checks and all(c['passed'] for c in checks) else \
                    'done but checks failed' if action == 'done' else 'blocked'
            else:
                write_action(play, step, action)
            signature = (action, hashlib.sha256(json.dumps(model_state(state), sort_keys=True).encode()).hexdigest())
            repeats = repeats + 1 if signature == last else 0
            last = signature
            history.append({'step': step, 'action': action, 'lastOutcome': state.get('lastOutcome')})
            events.append({'step': step, 'action': action, 'confidence': decision['action']['confidence'],
                           'probabilities': decision['action']['probabilities'], 'lastOutcome': state.get('lastOutcome'),
                           **{k: decision[k] for k in ('latency_s', 'cost', 'cached')}})
            log(f"{step:>2} {action:<22} p={decision['action']['confidence']:.2f} {decision['latency_s']:.2f}s "
                f"← {state.get('lastOutcome') or '-'}")
            if result:
                break
            if repeats >= STALL - 1:
                write_action(play, step + 1, 'quit')
                result = 'stalled'
                break
        else:
            result = 'max_steps'
    finally:
        try:
            process.wait(timeout=20)
        except Exception:  # noqa: BLE001 — 끝나지 않는 플레이어는 정리한다
            process.kill()
    final = [check(c, state) for c in scenario.get('checks', [])] if state else []
    summary = {'version': 'jev-test-unity-v1', 'result': result, 'passed': result == 'passed', 'steps': len(events),
               'jev_calls': len(events), 'cost': round(sum(e['cost'] or 0 for e in events), 6),
               'latency_s': round(sum(e['latency_s'] or 0 for e in events), 3), 'checks': final, 'goal': scenario['goal'], 'covers': scenario.get('covers') or []}
    out.mkdir(parents=True, exist_ok=True)
    (out / 'events.jsonl').write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events), encoding='utf-8')
    (out / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True, help='FullOps가 활성화된 게임 레포 루트')
    parser.add_argument('--key', required=True, help='과제 키')
    parser.add_argument('--scenario', required=True, help='시나리오 JSON: goal, player_args, checks, max_steps')
    parser.add_argument('--player', help='브리지가 들어간 Unity 플레이어 실행 파일')
    parser.add_argument('--config', help=f'브리지 설정(기본: {CONFIG})')
    parser.add_argument('--graphics', action='store_true', help='창을 띄워 실행(기본은 -batchmode -nographics)')
    parser.add_argument('--env-file', help='OPENROUTER_API_KEY를 읽을 .env')
    parser.add_argument('--validate', action='store_true', help='시나리오만 점검하고 실행하지 않는다')
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', args.key):
        parser.exit(2, '과제 키 형식이 잘못됐습니다\n')
    scenario = json.loads(Path(args.scenario).read_text(encoding='utf-8'))
    found = problems(scenario)
    if found or args.validate:
        parser.exit(2 if found else 0, ''.join(f'시나리오 문제: {p}\n' for p in found) or '시나리오 점검 통과\n')
    if not args.player:
        parser.exit(2, '--player가 필요합니다\n')
    config = Path(args.config) if args.config else repo / CONFIG
    if not config.is_file():
        parser.exit(2, f'브리지 설정이 없습니다: {config}. `unity_bridge.py install`로 템플릿을 만드세요\n')
    key = api_key(args.env_file, repo)
    if not key:
        parser.exit(2, 'OPENROUTER_API_KEY가 없어 Jev를 쓸 수 없습니다\n')
    out = repo / f'.fullops-squad/docs/evaluations/qa-reports/{args.key}-test/unity-{datetime.now():%Y%m%d-%H%M%S}'
    play = out / 'play'
    play.mkdir(parents=True)
    shutil.copyfile(config, play / 'config.json')

    def launch(folder):
        mode = [] if args.graphics else ['-batchmode', '-nographics']
        return subprocess.Popen([args.player, *mode, '--jev-play', str(folder), '-logFile', str(folder / 'player.log'),
                                 *[str(a) for a in scenario.get('player_args', [])]])
    summary = run(scenario, play, launch, lambda payload: request(payload, key), out)
    path = Path(args.scenario).resolve()
    summary['scenario'] = path.relative_to(repo).as_posix() if path.is_relative_to(repo) else str(path)
    (out / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    events = [json.loads(line) for line in (out / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
    test_record.write(out, summary, [(e['step'], e['action'], f"{e['confidence']:.2f}", e['lastOutcome'] or '-') for e in events],
                      ['스텝', '행동', '확신', '직전 행동 결과'])
    log = play / 'player.log'  # 전체 로그는 커밋하지 않는다(.gitignore). 실패하면 원인 확인용으로 끝부분만 남긴다
    if not summary['passed'] and log.is_file():
        tail = log.read_text(encoding='utf-8', errors='replace').splitlines()[-200:]
        (play / 'player-tail.log').write_text('\n'.join(tail) + '\n', encoding='utf-8')
    print(f"결과: {summary['result']} passed={summary['passed']} steps={summary['steps']} "
          f"jev_cost=${summary['cost']} 기록: {out.relative_to(repo).as_posix()}")
    sys.exit(0 if summary['passed'] else 1)


if __name__ == '__main__':
    main()
