"""가짜 브라우저와 stub Jev로 웹 조작 루프의 요소 문맥·fan-out 질문·통과/위험 중단/정체 판정·기록을 확인한다."""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/fullops-squad/scripts'))
import jev_test_web as web  # noqa: E402

SNAPSHOT = '''- textbox "What needs to be done?" [ref=e3]
- list
  - listitem [level=1]
    - checkbox "Toggle Todo" [checked=false, ref=e7]
    - LabelText
      - StaticText "우유 사기"'''


class FakeBrowser:
    def __init__(self):
        self.todos, self.acts = [], []

    def open(self, url):
        self.url = url

    def snapshot(self):
        text = SNAPSHOT if self.todos else SNAPSHOT.splitlines()[0]
        states, near = web.outline(text)
        refs = {'e3': ('textbox', 'What needs to be done?'), **({'e7': ('checkbox', 'Toggle Todo')} if self.todos else {})}
        return {'url': self.url, 'digest': str(len(self.acts)),
                'elements': [{'ref': r, 'role': role, 'name': name, **({'state': states[r]} if r in states else {}),
                              **({'near': near[r]} if r in near else {})} for r, (role, name) in refs.items()]}

    def act(self, operation, ref=None, value=None):
        self.acts.append((operation, ref, value))
        if operation == 'fill_submit':
            self.todos.append(value)
        return 'ok'

    def check(self, condition):
        return {'condition': condition, 'value': condition['text'] in self.todos, 'passed': condition['text'] in self.todos}


def answer(labels, pick):
    top = 0.9 if len(labels) > 1 else 1.0
    rest = (1 - top) / max(len(labels) - 1, 1)
    return {'type': 'choice', 'choice': pick, 'confidence': top, 'probabilities': {l: top if l == pick else rest for l in labels}}


def jev(plan, risk=0.05, seen=None):
    """plan: 스텝별 (동작, 대상, 값) 목록. 요청에 들어온 선택지로 답을 만든다."""
    steps = iter(plan)

    def call(payload):
        (seen if seen is not None else []).append(payload)
        operation, target, value = next(steps)
        q = payload['questions']
        answers = {'operation': answer(list(q['operation']['criteria']), operation), 'risky': {'type': 'noul', 'noul': risk}}
        for name, pick in (('click_target', target), ('check_target', target), ('fill_target', target), ('fill_value', value)):
            if name in q:
                labels = list(q[name]['criteria'])
                answers[name] = answer(labels, pick if pick in labels else labels[0])
        return {'answers': answers, 'usage': {'cost': 0.0001}}, 0.2
    return call


def main():
    scenario = {'url': 'https://example.test/todo', 'goal': 'Add 우유 사기 and complete it.',
                'values': {'milk': '우유 사기'}, 'checks': [{'text': '우유 사기'}], 'max_steps': 6,
                'covers': ['TODO-1 할 일 추가']}
    assert web.problems(scenario) == []
    bad = web.problems({'url': 'file:///x', 'goal': '', 'checks': [{'text': 'a', 'url': 'b'}], 'values': {'pw': 'PASSWORD=hunter2'}})
    assert len(bad) == 5, bad  # url·goal·covers·checks 모양·비밀값
    with tempfile.TemporaryDirectory(prefix='fullops-jev-web-') as tmp:
        seen = []
        browser = FakeBrowser()
        summary = web.run(scenario, browser, jev([('fill_submit', 'e3', 'milk'), ('check', 'e7', None), ('done', None, None)],
                                                 seen=seen), Path(tmp) / 'ok', log=lambda _: None)
        assert summary['passed'] and summary['result'] == 'passed' and summary['steps'] == 3, summary
        assert browser.acts == [('fill_submit', 'e3', '우유 사기'), ('check', 'e7', None)]
        q = seen[1]['questions']
        assert q['check_target']['criteria']['e7'] == 'checkbox "Toggle Todo" next to "우유 사기" (checked=false)'
        assert set(q) >= {'operation', 'risky', 'fill_target', 'fill_value', 'check_target'}  # 한 요청에 모두
        assert 'done' in q['operation']['criteria'] and 'check' not in seen[0]['questions']['operation']['criteria']
        events = (Path(tmp) / 'ok/events.jsonl').read_text(encoding='utf-8').splitlines()
        assert len(events) == 3 and json.loads(events[0])['value'] == 'milk'  # 값 자체가 아니라 키를 기록한다
        assert json.loads((Path(tmp) / 'ok/result.json').read_text(encoding='utf-8'))['cost'] == 0.0003

        risky = web.run(scenario, FakeBrowser(), jev([('fill_submit', 'e3', 'milk')], risk=0.9), Path(tmp) / 'risky',
                        log=lambda _: None)
        assert risky['result'] == 'blocked_risky' and not risky['passed']  # 위험 질문이 선택보다 우선

        stuck = FakeBrowser()
        stalled = web.run(scenario, stuck, jev([('scroll_down', None, None)] * 6), Path(tmp) / 'stall', log=lambda _: None)
        assert stalled['result'] == 'stalled' and len(stuck.acts) == 3, stalled  # 같은 동작을 세 번 반복하면 멈춘다

        empty = web.run({**scenario, 'checks': []}, FakeBrowser(), jev([('done', None, None), ('blocked', None, None)]),
                        Path(tmp) / 'empty', log=lambda _: None)
        assert not empty['passed']  # 검증 조건이 없으면 통과가 아니다

        premature = web.run({**scenario, 'max_steps': 2}, FakeBrowser(), jev([('done', None, None), ('blocked', None, None)]),
                            Path(tmp) / 'early', log=lambda _: None)
        assert premature['result'] == 'blocked' and not premature['passed']  # 검증 없는 done은 통과가 아니다
    import test_record
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'K-1-test' / 'web-20260925-000000'
        out.mkdir(parents=True)
        test_record.write(out, {**summary, 'scenario': 'scenarios/web/a.json', 'covers': ['REQ | 1']},
                          [(1, 'fill', 'e3', 'milk', '0.90', 'ok')], ['스텝', '동작', '대상', '값', '확신', '결과'])
        report = (out / 'report.md').read_text(encoding='utf-8')
        assert report.startswith('# K-1 조작 테스트 — 통과 (passed)') and '| 1 | fill | e3 | milk | 0.90 | ok |' in report, report
        assert '`scenarios/web/a.json`' in report and '| 통과 |' in report
    print('PASS: jev web loop element context, fan-out questions, pass/risk/stall/premature-done, records')


if __name__ == '__main__':
    main()
