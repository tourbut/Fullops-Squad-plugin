"""jev_test_web·jev_test_unity 실행 결과를 사람이 읽는 report.md로 남긴다. 판정 근거는 result.json·events.jsonl이다."""


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
             f"- 스텝 {summary['steps']} · Jev {summary['jev_calls']}회 · 비용 ${summary['cost']} · Jev 시간 {summary['latency_s']}초", '',
             '## 검증 조건', '', '| 조건 | 읽은 값 | 결과 |', '|---|---|---|']
    for check in summary.get('checks') or []:
        lines.append(f"| {cell(describe(check['condition']))} | {cell(check['value'])} | {'통과' if check['passed'] else '실패'} |")
    if not summary.get('checks'):
        lines.append('| - | - | 판정 전에 끝남 |')
    lines += ['', '## 진행', '', '| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    lines += ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows]
    lines += ['', '원본: `result.json`(판정), `events.jsonl`(스텝별 선택·확률·비용).', '']
    (out / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
