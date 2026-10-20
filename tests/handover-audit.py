"""핸드오버 로그의 dispatch마다 지시 본문·탐색 패킷 줄 수와 노이즈 지표를 센다. 점검 도구이며 변경하지 않는다.

python3 tests/handover-audit.py <레포>/.fullops-squad/handovers/logs/*_to_dev.md [--json <출력 경로>]
"""
import argparse
import json
from pathlib import Path
import re


def audit(path):
    lines = path.read_text(encoding='utf-8').split('\n')
    starts = [i for i, line in enumerate(lines) if line.startswith('<!-- fullops-attempt')]
    rows = []
    for start, end in zip(starts, starts[1:] + [len(lines)]):
        segment = lines[start:end]
        key = lines[start].split()[2]
        packet_start = next((i for i, l in enumerate(segment) if 'fullops-packet:start' in l), None)
        packet_end = next((i for i, l in enumerate(segment) if 'fullops-packet:end' in l), None)
        report = next((i for i, l in enumerate(segment) if l.startswith('## 완료 보고')), len(segment))
        body = packet_start if packet_start is not None else report
        packet = segment[packet_start:packet_end + 1] if packet_start is not None and packet_end is not None else []
        items = [l for l in packet if l.startswith('- `')]
        first_read, inside = 0, False
        for line in segment[:body]:
            if line.startswith('## 먼저 읽을 문서'):
                inside = True
            elif line.startswith('## '):
                inside = False
            elif inside and line.strip():
                first_read += len(re.findall(r'`[^`]+`', line)) or 1
        previous = next((i for i, l in enumerate(segment) if l.startswith('## 이전 완료 기록')), None)
        previous_lines = 0
        if previous is not None:
            previous_lines = next((i for i, l in enumerate(segment[previous + 1:]) if l.startswith('## ')), len(segment) - previous - 1)
        rows.append({'file': path.name, 'line': start + 1, 'key': key, 'body_lines': body, 'packet_lines': len(packet),
                     'packet_items': len(items), 'required': sum(l.rstrip().endswith('· 필수') for l in items),
                     'unknown_span': sum('전체/미확인' in l for l in items), 'inferred': sum('· inferred' in l for l in items),
                     'self_reference': sum('handovers/to_' in l for l in items), 'first_read_refs': first_read,
                     'placeholders': sum(any(m in l for m in ('(worker-start', '<과제 키>', '탐색 패킷의 task/role/attempt')) for l in segment[:body]),
                     'previous_record_lines': previous_lines})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', nargs='+')
    parser.add_argument('--json', help='집계 JSON 출력 경로')
    args = parser.parse_args()
    rows = [row for log in args.logs for row in audit(Path(log))]
    for row in rows:
        ratio = row['packet_lines'] / row['body_lines'] if row['body_lines'] else 0
        print(f"{row['file']} L{row['line']} {row['key']} body={row['body_lines']} packet={row['packet_lines']} ({ratio:.1f}x) "
              f"items={row['packet_items']} required={row['required']} unknown_span={row['unknown_span']} self={row['self_reference']} "
              f"first_read={row['first_read_refs']} placeholders={row['placeholders']} previous_record={row['previous_record_lines']}")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
