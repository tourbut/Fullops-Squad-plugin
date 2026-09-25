#!/usr/bin/env python3
"""Orca 내장 브라우저에서 Jev가 요소와 동작을 골라 웹 시나리오를 진행하고, 시나리오의 검증 조건으로 판정한다.

루프: `orca snapshot`의 요소 번호(@e1…) → Jev 한 번 호출(동작·대상·입력값·위험을 함께 묻는다) → orca로 실행 → 반복.
입력할 글자는 시나리오 `values`에서 고르므로 LLM이 글을 쓰지 않는다. 페이지 문구는 데이터로만 쓰고,
실행하는 것은 스냅샷에 있던 요소 번호와 시나리오 값뿐이다. 결과는 qa-reports/<과제 키>-test/에 남는다.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from jev_observe import MODEL, api_key, checked_answer, request, safe_text
from orca_wait import find_orca
import test_record

CLICKABLE = {'button', 'link', 'tab', 'menuitem', 'option', 'radio', 'switch', 'treeitem'}
CHECKABLE = {'checkbox'}
FILLABLE = {'textbox', 'searchbox', 'combobox', 'spinbutton'}
OPERATIONS = {
    'click': 'Click one button, link, tab or menu item.',
    'check': 'Toggle one checkbox.',
    'fill': 'Replace the text of one input with one scenario value.',
    'fill_submit': 'Replace the text of one input with one scenario value, then press Enter to submit it.',
    'press_enter': 'Press Enter on the focused element.',
    'scroll_down': 'Scroll down to reveal more of the page.',
    'done': 'The goal is complete on the current page.',
    'blocked': 'The goal cannot progress: the needed control is missing or the page shows an error.',
}
HINT = ('You control a web browser to reach `goal`. Choose the next operation. Use `history` to avoid repeating a step '
        'that already succeeded or failed. Choose done only when `elements` show the goal is complete.')
RISK = ('Would the most likely next step cause an irreversible or out-of-scope effect such as a payment, deleting real '
        'data, sending a message to real people, or leaving the site named in `goal`?')
RISK_STOP = 0.7
# orca keypress는 Orca 창에 포커스가 없으면 페이지에 닿지 않는다. 포커스된 요소에 Enter 이벤트를 직접 보내고,
# 폼 안이면 제출한다. 모델 출력이 아닌 고정 스크립트다.
# ponytail: 키 이벤트와 폼 제출을 둘 다 처리하는 앱은 두 번 제출될 수 있다. 문제가 되면 폼 여부로 하나만 보낸다
ENTER = ("(() => { const el = document.activeElement || document.body; "
         "for (const type of ['keydown', 'keypress', 'keyup']) el.dispatchEvent(new KeyboardEvent(type, "
         "{key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true})); "
         "if (el.form && el.form.requestSubmit) el.form.requestSubmit(); return true; })()")
STALL = 3


def outline(text):
    """스냅샷 트리에서 요소별 상태([checked=false] 등)와 같은 항목 안의 글자를 뽑는다.

    같은 이름의 컨트롤(`checkbox "Toggle Todo"` 여러 개)은 옆 글자가 있어야 구별된다. 부모 항목이 작을 때만 붙인다."""
    nodes = []
    for line in text.splitlines():
        match = re.match(r'(\s*)- (\S+)(?: "((?:[^"\\]|\\.)*)")?(?: \[([^\]]*)\])?', line)
        if match:
            nodes.append((len(match.group(1)), match.group(2), match.group(3) or '', match.group(4) or ''))
    states, near = {}, {}
    for i, (depth, role, name, attrs) in enumerate(nodes):
        ref = re.search(r'ref=(e\d+)', attrs)
        if not ref:
            continue
        ref = ref.group(1)
        extra = [a.strip() for a in attrs.split(',') if a.strip() and not a.strip().startswith(('ref=', 'level='))]
        if extra:
            states[ref] = extra
        parent = next((j for j in range(i - 1, -1, -1) if nodes[j][0] < depth), None)
        if parent is None:
            continue
        end = next((j for j in range(parent + 1, len(nodes)) if nodes[j][0] <= nodes[parent][0]), len(nodes))
        if end - parent > 12:
            continue
        texts, j = [], parent + 1
        while j < end:  # 부모의 직계 자식 묶음 단위로 본다. 다른 컨트롤이 든 묶음의 글자는 그 컨트롤 몫이다
            stop = next((k for k in range(j + 1, end) if nodes[k][0] <= nodes[j][0]), end)
            group = nodes[j:stop]
            if not any('ref=' in n[3] for n in group) or j == i:
                texts += [n[2] for n in group if n[1] in ('StaticText', 'LabelText', 'text') and n[2] and n[2] != name]
            j = stop
        if texts:
            near[ref] = ' '.join(texts)[:100]
    return states, near


def problems(scenario):
    """실행 전에 시나리오를 점검한다. Jev 비용을 쓰기 전에 잘못 쓴 시나리오를 거른다."""
    found = []
    if not isinstance(scenario.get('url'), str) or not re.match(r'https?://', scenario['url']):
        found.append('url은 http(s) 주소여야 한다')
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
            if not isinstance(c, dict) or sum(k in c for k in ('text', 'url', 'js')) != 1:
                found.append(f'checks[{n}]는 text, url, js 중 하나만 가진다')
    values = scenario.get('values', {})
    if not isinstance(values, dict) or not all(isinstance(v, str) for v in values.values()):
        found.append('values는 {키: 입력할 글자}다')
    else:
        for k, v in values.items():
            try:
                safe_text(v, 500)
            except ValueError:
                found.append(f'values.{k}에 비밀값처럼 보이는 글자가 있다')
    if not isinstance(scenario.get('setup_js', []), (str, list)):
        found.append('setup_js는 식 하나 또는 식의 목록이다')
    if not isinstance(scenario.get('max_steps', 20), int) or not 1 <= scenario.get('max_steps', 20) <= 100:
        found.append('max_steps는 1~100이다')
    return found


class Browser:
    """orca CLI 한 명령 = 한 호출. 페이지 id를 고정해 다른 탭을 건드리지 않는다."""

    def __init__(self, orca, worktree):
        self.orca, self.worktree, self.page = orca, worktree, None

    def run(self, *args, retries=2):
        scope = ['--worktree', self.worktree] + (['--page', self.page] if self.page else [])
        for attempt in range(retries + 1):
            done = subprocess.run([self.orca, *args, *scope, '--json'], capture_output=True, text=True, encoding='utf-8')
            try:
                data = json.loads(done.stdout)
            except ValueError:
                data = {'ok': False, 'error': {'code': 'bad_output', 'message': (done.stderr or done.stdout)[-300:]}}
            if data.get('ok') or data.get('error', {}).get('code') != 'runtime_unavailable' or attempt == retries:
                return data
            time.sleep(1)  # 탭을 막 만든 직후 런타임이 한 번 연결을 끊는 경우가 있다

    def open(self, url):
        self.page = None
        data = self.run('tab', 'create', '--url', url)
        if not data.get('ok'):
            raise RuntimeError(f"tab create 실패: {data.get('error')}")
        self.page = data['result']['browserPageId']
        self.run('wait', '--load', 'networkidle')

    def snapshot(self):
        data = self.run('snapshot')
        if not data.get('ok'):
            raise RuntimeError(f"snapshot 실패: {data.get('error')}")
        result = data['result']
        states, near = outline(result.get('snapshot', ''))
        elements = [{'ref': ref, 'role': info.get('role', ''), 'name': (info.get('name') or '')[:120],
                     **({'state': states[ref]} if states.get(ref) else {}),
                     **({'near': near[ref]} if near.get(ref) else {})}
                    for ref, info in (result.get('refs') or {}).items()]
        return {'url': result.get('origin', ''), 'elements': elements[:80],
                'digest': hashlib.sha256(result.get('snapshot', '').encode()).hexdigest()[:16]}

    def act(self, operation, ref=None, value=None):
        steps = {'click': [('click', '--element', '@' + str(ref))],
                 'check': [('click', '--element', '@' + str(ref))],
                 'fill': [('fill', '--element', '@' + str(ref), '--value', value)],
                 'fill_submit': [('fill', '--element', '@' + str(ref), '--value', value), ('eval', '--expression', ENTER)],
                 'press_enter': [('eval', '--expression', ENTER)],
                 'scroll_down': [('scroll', '--direction', 'down', '--amount', '800')]}[operation]
        for step in steps:
            data = self.run(*step)
            if not data.get('ok'):
                return 'error: ' + str((data.get('error') or {}).get('code') or data.get('error'))
        self.run('wait', '--timeout', '800')
        return 'ok'

    def check(self, condition):
        """시나리오 검증 조건 하나. text/url은 페이지에서 읽고, js는 시나리오 작성자가 쓴 식을 평가한다."""
        if 'text' in condition:
            expression = f"document.body.innerText.includes({json.dumps(condition['text'])})"
        elif 'url' in condition:
            expression = f"location.href.includes({json.dumps(condition['url'])})"
        else:
            expression = condition['js']
        data = self.run('eval', '--expression', expression)
        value = (data.get('result') or {}).get('result')
        try:  # orca eval은 결과를 문자열로 돌려준다('true', '3')
            value = json.loads(value) if isinstance(value, str) and value in ('true', 'false', 'null') or \
                (isinstance(value, str) and re.fullmatch(r'-?\d+(\.\d+)?', value)) else value
        except ValueError:
            pass
        expected = condition.get('equals', True)
        return {'condition': condition, 'value': value, 'passed': data.get('ok', False) and value == expected}


def choices(elements, roles):
    return {e['ref']: f"{e['role']} \"{e['name']}\"" + (f" next to \"{e['near']}\"" if e.get('near') else '')
            + (f" ({', '.join(e['state'])})" if e.get('state') else '') for e in elements if e['role'] in roles}


def ask(call, scenario, page, history, step):
    """한 번의 요청에 동작·대상·입력값·위험 질문을 모두 넣고(speculative fan-out) 필요한 답만 쓴다."""
    clickable, checkable, fillable = (choices(page['elements'], r) for r in (CLICKABLE, CHECKABLE, FILLABLE))
    values = {k: safe_text(v, 500) for k, v in (scenario.get('values') or {}).items()}
    available = {'click': clickable, 'check': checkable, 'fill': fillable and values, 'fill_submit': fillable and values,
                 'press_enter': True, 'scroll_down': True, 'done': True, 'blocked': True}
    operations = {k: v for k, v in OPERATIONS.items() if available[k]}
    questions = {'operation': {'type': 'choice', 'instructions': HINT, 'criteria': operations},
                 'risky': {'type': 'noul', 'instructions': RISK}}
    if clickable:
        questions['click_target'] = {'type': 'choice', 'instructions': 'If the operation is click, which element?',
                                     'criteria': clickable}
    if checkable:
        questions['check_target'] = {'type': 'choice', 'instructions': 'If the operation is check, which checkbox?',
                                     'criteria': checkable}
    if fillable and values:
        questions['fill_target'] = {'type': 'choice', 'instructions': 'If the operation fills text, which input?',
                                    'criteria': fillable}
        questions['fill_value'] = {'type': 'choice', 'instructions': 'If the operation fills text, which value fits the goal now?',
                                   'criteria': values}
    state = {'goal': safe_text(scenario['goal'], 1000), 'page': {'url': page['url']},
             'elements': [{k: v for k, v in e.items()} for e in page['elements']],
             'values': values, 'history': history[-6:], 'step': step, 'steps_left': scenario.get('max_steps', 20) - step}
    response, latency = call({'model': MODEL, 'state': state, 'questions': questions})
    answers = response['answers']
    decision = {'operation': checked_answer(answers['operation'], operations), 'latency_s': latency,
                'cost': (response.get('usage') or {}).get('cost'), 'cached': bool(response.get('cached'))}
    risky = answers.get('risky') or {}
    decision['risk'] = next((risky[k] for k in ('noul', 'probability', 'value') if isinstance(risky.get(k), (int, float))), None)
    operation = decision['operation']['choice']
    target = {'click': 'click_target', 'check': 'check_target', 'fill': 'fill_target', 'fill_submit': 'fill_target'}.get(operation)
    if target:
        decision['target'] = checked_answer(answers[target], questions[target]['criteria'])
    if operation in ('fill', 'fill_submit'):
        decision['value'] = checked_answer(answers['fill_value'], values)
    return decision


def run(scenario, browser, call, out, log=print):
    browser.open(scenario['url'])
    setup = scenario.get('setup_js') or []
    for expression in [setup] if isinstance(setup, str) else setup:  # 저장 데이터 초기화처럼 매번 같은 출발 상태를 만든다
        browser.run('eval', '--expression', expression)
        browser.run('wait', '--load', 'networkidle')
    history, events, result = [], [], None
    repeats, last_digest, same_page = 0, None, 0
    for step in range(1, scenario.get('max_steps', 20) + 1):
        page = browser.snapshot()
        same_page = same_page + 1 if page['digest'] == last_digest else 0
        last_digest = page['digest']
        if same_page >= STALL:
            result = 'stalled'
            break
        decision = ask(call, scenario, page, history, step)
        operation = decision['operation']['choice']
        ref = decision.get('target', {}).get('choice')
        key = decision.get('value', {}).get('choice')
        entry = {'step': step, 'operation': operation, 'target': ref, 'value': key}
        if decision['risk'] is not None and decision['risk'] >= RISK_STOP:
            outcome, result = 'stopped: risky', 'blocked_risky'
        elif operation == 'blocked':
            outcome, result = 'blocked', 'blocked'
        elif operation == 'done':
            checks = [browser.check(c) for c in scenario.get('checks', [])]
            outcome = 'checks passed' if checks and all(c['passed'] for c in checks) else 'done but checks failed'
            entry['checks'] = checks
            if outcome == 'checks passed':
                result = 'passed'
        else:
            outcome = browser.act(operation, ref, scenario['values'][key] if key else None)
        entry['outcome'] = outcome
        repeats = repeats + 1 if history and {k: history[-1].get(k) for k in ('operation', 'target', 'value')} == \
            {k: entry[k] for k in ('operation', 'target', 'value')} else 0
        history.append({k: entry[k] for k in ('step', 'operation', 'target', 'value', 'outcome')})
        events.append({**entry, 'url': page['url'], 'elements': len(page['elements']), **{
            k: decision[k] for k in ('risk', 'latency_s', 'cost', 'cached')},
            'confidence': decision['operation']['confidence'], 'probabilities': decision['operation']['probabilities']})
        log(f"{step:>2} {operation:<12} {ref or '':<5} {key or '':<10} p={decision['operation']['confidence']:.2f} "
            f"risk={decision['risk'] if decision['risk'] is None else round(decision['risk'], 2)} "
            f"{decision['latency_s']:.2f}s → {outcome}")
        if result or repeats >= STALL - 1:
            result = result or 'stalled'
            break
    if result is None:
        result = 'max_steps'
    final = [browser.check(c) for c in scenario.get('checks', [])]
    passed = result == 'passed' or (bool(final) and all(c['passed'] for c in final) and result == 'max_steps')
    summary = {'version': 'jev-test-web-v1', 'result': result, 'passed': passed, 'steps': len(events),
               'jev_calls': len(events), 'cost': round(sum(e['cost'] or 0 for e in events), 6),
               'latency_s': round(sum(e['latency_s'] or 0 for e in events), 3), 'checks': final,
               'url': scenario['url'], 'goal': scenario['goal'], 'covers': scenario.get('covers') or []}
    out.mkdir(parents=True, exist_ok=True)
    (out / 'events.jsonl').write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events), encoding='utf-8')
    (out / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True, help='FullOps가 활성화된 레포 루트(결과 저장 위치)')
    parser.add_argument('--key', required=True, help='과제 키')
    parser.add_argument('--scenario', required=True, help='시나리오 JSON: url, goal, values, checks, max_steps')
    parser.add_argument('--worktree', help='Orca 워크트리 선택자(기본: path:<레포 루트>)')
    parser.add_argument('--env-file', help='OPENROUTER_API_KEY를 읽을 .env')
    parser.add_argument('--orca', help='orca 실행 파일(기본: 자동 탐색)')
    parser.add_argument('--validate', action='store_true', help='시나리오만 점검하고 실행하지 않는다')
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', args.key):
        parser.exit(2, '과제 키 형식이 잘못됐습니다\n')
    scenario = json.loads(Path(args.scenario).read_text(encoding='utf-8'))
    found = problems(scenario)
    if found or args.validate:
        parser.exit(2 if found else 0, ''.join(f'시나리오 문제: {p}\n' for p in found) or '시나리오 점검 통과\n')
    orca = args.orca or find_orca()
    if not orca:
        parser.exit(2, 'orca CLI를 찾지 못했습니다\n')
    key = api_key(args.env_file, repo)
    if not key:
        parser.exit(2, 'OPENROUTER_API_KEY가 없어 Jev를 쓸 수 없습니다\n')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    out = repo / f'.fullops-squad/docs/evaluations/qa-reports/{args.key}-test/web-{stamp}'
    browser = Browser(orca, args.worktree or f'path:{repo.as_posix()}')
    summary = run(scenario, browser, lambda payload: request(payload, key), out)
    path = Path(args.scenario).resolve()
    summary['scenario'] = path.relative_to(repo).as_posix() if path.is_relative_to(repo) else str(path)
    (out / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    events = [json.loads(line) for line in (out / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
    test_record.write(out, summary, [(e['step'], e['operation'], e['target'], e['value'], f"{e['confidence']:.2f}", e['outcome'])
                                     for e in events], ['스텝', '동작', '대상', '입력값 키', '확신', '결과'])
    print(f"결과: {summary['result']} passed={summary['passed']} steps={summary['steps']} "
          f"jev_cost=${summary['cost']} 기록: {out.relative_to(repo).as_posix()}")
    sys.exit(0 if summary['passed'] else 1)


if __name__ == '__main__':
    main()
