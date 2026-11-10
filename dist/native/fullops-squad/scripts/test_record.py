"""jev_test_web·jev_test_unity 실행 결과를 사람이 읽는 report.md로 남긴다. 판정 근거는 result.json·events.jsonl이다."""
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import subprocess
from deliverables import render
from storage import write_json, atomic_write


def begin(out, scenario):
    out.mkdir(parents=True, exist_ok=True)
    if any((out / name).exists() for name in ('events.jsonl', 'result.json', 'report.md')):
        raise ValueError('이전 실행 증거가 있습니다. 새 실행 경로를 사용하세요')
    (out / 'events.jsonl').touch(exist_ok=False)
    plugin = json.loads((Path(__file__).resolve().parents[1] / 'plugin.json').read_text(encoding='utf-8'))
    target = subprocess.run(['git', '-C', str(out), 'rev-parse', 'HEAD'], capture_output=True, text=True, encoding='utf-8')
    # ../..는 qa-reports 폴더다(<key>-test/<run>). 실행 증거는 작업 트리 변경으로 보지 않는다
    dirty = subprocess.run(['git', '-C', str(out), 'status', '--porcelain', '--', ':/', ':(exclude)../..'], capture_output=True, text=True, encoding='utf-8')
    files = ('jev_test_web.py', 'web_contract.py', 'web_dom.js', 'web_playwright.py', 'web_playwright.cjs', 'web_ego.py', 'web_ego.mjs') if 'url' in scenario else ('jev_test_unity.py',)
    hashes = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in files}
    return {'plugin_version': plugin['version'], 'target_sha': target.stdout.strip() if target.returncode == 0 else None,
            'worktree_dirty': bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
            'scenario_sha256': hashlib.sha256(json.dumps(scenario, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            'executor_files_sha256': hashes}


def append(out, event):
    with (out / 'events.jsonl').open('a', encoding='utf-8') as output:
        output.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')
        output.flush()
        os.fsync(output.fileno())


def finish(out, summary, events, kind, error=None):
    """실행이 error로 멈췄으면 증거에 남기고 error를 다시 던진다. 기록 실패는 error가 없을 때만 올린다."""
    if error:
        summary.update(error_type=type(error).__name__, evidence_unavailable='execution stopped before final evidence')
    try:
        write_json(out / 'result.json', summary)
        if kind == 'web':
            rows = [(e['step'], e['operation'], e['target'], e['value'], confidence(e), e['outcome']) for e in events]
            header = ['스텝', '동작', '대상', '입력값 키', '확신', '결과']
        else:
            rows = [(e['step'], e['action'], f"{e['confidence']:.2f}", e['lastOutcome'] or '-') for e in events]
            header = ['스텝', '행동', '확신', '직전 행동 결과']
        write(out, summary, rows, header)
    except Exception:  # noqa: BLE001
        if error is None:
            raise
    if error:
        raise error
    return summary


def confidence(event):
    return f"{event['confidence']:.2f}" if event.get('confidence') is not None else '-'


def costs(events):
    known = round(sum(e['cost'] for e in events if type(e.get('cost')) in (int, float)), 6)
    unknown = any(e.get('cost') is None for e in events)
    return {'cost': None if unknown else known, 'known_cost': known, 'cost_status': 'unknown' if unknown else 'complete'}


def measured(call, calls):
    """응답 검증/조작이 실패해도 이미 확인한 API 비용은 보존한다. payload·키·원문은 기록하지 않는다."""
    from jev_observe import validated
    def invoke(payload):
        entry = {'cost': None, 'requested_model': payload['model'],
                 'input_sha256': hashlib.sha256(json.dumps(payload['state'], sort_keys=True).encode()).hexdigest(),
                 'question_sha256': hashlib.sha256(json.dumps(payload['questions'], sort_keys=True).encode()).hexdigest()}
        calls.append(entry)
        try:
            result = call(payload)
            _, usage, elapsed, model = validated(result, payload['questions'])
            entry.update(cost=usage['cost'], usage=usage, latency_s=elapsed, response_model=model, cached=result[0].get('cached', False))
            return result
        except Exception as error:
            entry['error_type'] = type(error).__name__
            raise
    return invoke


def cell(value):
    return str(value if value is not None else '-').replace('|', '\\|').replace('\n', ' ')


def describe(condition):
    """검증 조건을 읽기 쉬운 문장으로. 읽은 값 칸과 짝이 맞게 쓴다."""
    if 'field' in condition:
        return f"{condition['field']} {condition.get('op', '==')} {condition['value']}"
    if 'actor' in condition:
        return f"{condition['actor']} 그룹이 {'없어야' if condition.get('absent') else '있어야'} 함 (읽은 값: 있음 여부)"
    if 'text' in condition:
        return f"문구 \"{condition['text']}\"가 보여야 함"
    if 'url' in condition:
        return f"주소에 \"{condition['url']}\" 포함"
    return f"js `{condition.get('js')}` == {condition.get('equals', True)}"


def write(out, summary, rows, header):
    """rows: 스텝마다 표 한 줄의 값 목록. header: 그 열 이름."""
    verdict = '통과' if summary['passed'] else '실패'
    lines = [f"# {out.parent.name[:-len('-test')]} 조작 테스트 — {verdict} ({summary['result']})", '',
             f"- 시나리오: `{summary.get('scenario', '-')}`",
             f"- covers: {', '.join(summary.get('covers') or []) or '-'}",
             f"- 목표: {summary['goal']}",
             f"- 스텝 {summary['steps']} · Jev {summary['jev_calls']}회 · 비용 {summary['cost'] if summary['cost'] is not None else 'unknown'} · Jev 시간 {summary['latency_s']}초", '',
             '## 검증 조건', '', '| 조건 | 읽은 값 | 결과 |', '|---|---|---|']
    for check in summary.get('checks') or []:
        lines.append(f"| {cell(describe(check['condition']))} | {cell(check['value'])} | {'통과' if check['passed'] else '실패'} |")
    if not summary.get('checks'):
        lines.append('| - | - | 판정 전에 끝남 |')
    if summary.get('error_type'):
        lines += ['', f"오류: {summary['error_type']} / {summary.get('evidence_unavailable', '')}"]
    if summary.get('executor'):
        lines += ['', f"실행기: `{summary['executor'].get('name')}` / `{summary['executor'].get('version')}` · 범위: `{summary.get('scope')}`",
                  f"관측: `{json.dumps(summary.get('coverage'), ensure_ascii=False)}`",
                  f"중단 사유: `{summary['result']}` · 독립 assertions: `{summary.get('assertions_passed')}`"]
    lines += ['', '## 진행', '', '| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    lines += ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows]
    lines += ['', '원본: `result.json`(판정), `events.jsonl`(스텝별 선택·확률·비용).', '']
    meta = {'title': lines[0][2:], 'status': 'draft', 'updated': date.today().isoformat(),
            'owner': 'tester', 'tasks': [out.parent.name[:-len('-test')]], 'summary': summary['goal']}
    atomic_write(out / 'report.md', render(meta) + '\n' + '\n'.join(lines))
