#!/usr/bin/env python3
"""리뷰 폴더에 남은 lint 결과와 리뷰 지적을 모아 잡음 규칙·느린 명령의 lint.json 조정 후보를 보여 준다. 설정은 바꾸지 않는다."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from lint import CONFIG, DEFAULT, SLOW_SECONDS

REVIEWS = '.fullops-squad/docs/evaluations/qa-reports'


def load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def tune(repo, min_warnings=50):
    repo = Path(repo)
    config = {**DEFAULT, **(load(repo / CONFIG) or {})}
    runs, warnings, paths, seconds, findings = 0, Counter(), defaultdict(Counter), defaultdict(list), []
    for folder in sorted((repo / REVIEWS).glob('*-review')):
        result = load(folder / 'lint.json')
        if isinstance(result, dict):
            runs += 1
            for v in result.get('violations') or []:
                warnings[v.get('code')] += 1
                paths[v.get('code')][v.get('path') or ''] += 1
            for c in result.get('commands') or []:
                if isinstance(c.get('seconds'), (int, float)):
                    seconds[c.get('name')].append(c['seconds'])
        review = load(folder / 'result.json')
        if isinstance(review, dict):
            findings += [str(f.get('content') or '') for f in review.get('findings') or [] if isinstance(f, dict)]
    configurable = {r.get('code'): r for r in config.get('rules') or []}
    rules = []
    for code, count in warnings.most_common():
        # shortcut: 지적 본문에서 규칙 코드를 찾는 추정이다. 지적이 코드를 적지 않으면 0으로 센다
        cited = sum(1 for text in findings if re.search(rf'\b{re.escape(code)}\b', text))
        row = {'code': code, 'warnings': count, 'cited_by_findings': cited,
               'top_paths': [p for p, _ in paths[code].most_common(5)]}
        if code in configurable and count >= min_warnings and not cited:
            row['proposal'] = '지적으로 이어진 적이 없다. exclude_paths(상위 경로)·severity·enabled: false를 검토한다'
        rules.append(row)
    commands = []
    for c in config.get('commands') or []:
        times = seconds.get(c.get('name')) or []
        row = {'name': c.get('name'), 'runs': len(times),
               'avg_seconds': round(sum(times) / len(times)) if times else None,
               'max_seconds': round(max(times)) if times else None,
               'scoped': bool(c.get('paths') or c.get('level'))}
        if times and row['avg_seconds'] > SLOW_SECONDS and not row['scoped']:
            row['proposal'] = '범위 없이 코드 변경마다 돈다. paths나 level로 좁힐지 검토한다'
        commands.append(row)
    return {'reviews_with_lint': runs, 'findings': len(findings), 'min_warnings': min_warnings,
            'rules': rules, 'commands': commands,
            'note': '제안만 한다. 사용자 승인 뒤 기본 브랜치의 lint.json을 고치고 README 규칙 변경 기록에 이유를 남긴다'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, help='리뷰 기록이 있는 레포 루트')
    parser.add_argument('--min-warnings', type=int, default=50, help='잡음 후보로 볼 최소 경고 수')
    args = parser.parse_args()
    print(json.dumps(tune(args.repo, args.min_warnings), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
