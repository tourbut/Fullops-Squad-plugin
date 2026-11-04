#!/usr/bin/env python3
"""병합 후보를 auto·delay·ask 등급으로 판정해 기록한다(섀도 모드). 기존 병합·리뷰 흐름은 바꾸지 않는다.

판정은 기준 시점(merge-base) fullops.json의 autonomy_policy·review_policy, review.py need, lint·리뷰 결과로 코드가 한다.
읽지 못한 입력과 애매한 경우는 ask다. lint ERROR와 미해결 critical/high는 등급과 관계없이 blocked다.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

import decision
from lint import changed_paths, matches
import policy
import review
from storage import write_json
from work import KEY

VERSION = 1
# 섀도 모드는 등급만 기록한다. auto·delay 개방은 섀도 결과를 본 뒤 사용자가 정한다(#125 3단계).
POLICY = {
    'mode': 'shadow',
    'auto': ['**/*.md', 'docs/**', 'tests/**'],
    'ask': ['.github/**', '.fullops-squad/fullops.json', '.fullops-squad/lint/**', '.fullops-squad/review/**',
            '**/auth/**', '**/*auth*.*', '**/*payment*/**', '**/*billing*/**', '**/migrations/**', '**/*.sql',
            '**/Dockerfile', '**/docker-compose*.yml', '**/deploy/**', '**/*.tf', '**/.env*',
            '**/package.json', '**/package-lock.json', '**/pnpm-lock.yaml', '**/pyproject.toml', '**/requirements*.txt'],
    'delay_minutes': 60,
    'approval_hours': 24,
}
UNREADABLE = (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.CalledProcessError)


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def rules(config):
    """기준 시점 autonomy_policy에 기본값을 채운다. 형식이 틀리면 ValueError이고 판정은 ask가 된다."""
    custom = config.get('autonomy_policy') or {}
    if not isinstance(custom, dict):
        raise ValueError('autonomy_policy는 객체여야 합니다')
    merged = {**POLICY, **custom}
    if merged['mode'] != 'shadow':
        raise ValueError('autonomy_policy.mode는 아직 shadow만 지원합니다')
    if any(not isinstance(merged[k], list) or not all(isinstance(g, str) and g for g in merged[k]) for k in ('auto', 'ask')):
        raise ValueError('autonomy_policy.auto·ask는 경로 glob 목록이어야 합니다')
    if any(type(merged[k]) is not int or merged[k] < 1 for k in ('delay_minutes', 'approval_hours')):
        raise ValueError('autonomy_policy.delay_minutes·approval_hours는 1 이상 정수여야 합니다')
    return merged


def lint_problem(repo, base, head, source):
    """같은 base·head·설정에서 통과한 lint 결과가 없으면 (사유, 결과를 읽었는지)를 돌려준다."""
    target = {'base': base, 'head': head}
    try:
        if not source:
            found, _ = review.worker_lint(repo, target)
            return (None, True) if found else ('같은 base·head·설정에서 통과한 lint 결과가 없습니다', False)
        data = json.loads(Path(source).read_bytes())
        errors = (sum(v['severity'] == 'ERROR' for v in data['violations'])
                  + sum(c['status'] in ('failed', 'timeout') for c in data['commands']))
        if errors:
            return f'lint ERROR {errors}건', True
        review.check_lint(repo, target, data)
    except UNREADABLE as error:
        return f'lint 결과를 확인하지 못했습니다: {error}', False
    return None, True


def open_findings(repo, key):
    """리뷰 result.json에서 아직 해결하지 않은 critical·high finding."""
    if not KEY.fullmatch(key):
        raise ValueError('리뷰 키 형식이 아닙니다')
    path = Path(repo) / f'.fullops-squad/docs/evaluations/qa-reports/{key}-review/result.json'
    findings = json.loads(path.read_text(encoding='utf-8')).get('findings') or []
    return [f for f in findings if f.get('severity') in ('critical', 'high') and not f.get('resolved')]


def judge(repo, base, head, key=None, review_key=None, lint=None, origin='user'):
    out = {'version': VERSION, 'kind': 'autonomy_judgment', 'mode': 'shadow', 'grade': 'ask', 'merge_allowed': False,
           'blocked': False, 'blockers': [], 'reasons': [], 'key': key, 'origin': origin, 'base': base, 'head': head,
           'merge_base': None, 'policy': None, 'inputs': {}, 'judged_at': now()}
    try:
        base, head = review.sha(repo, base), review.sha(repo, head)
        need = review.need(repo, base, head)
        config, raw = policy.config_at_ref(repo, need['merge_base'])
        if raw is None:
            raise ValueError('기준 시점에 .fullops-squad/fullops.json이 없습니다')
        rule = rules(config)
        paths = changed_paths(repo, need['merge_base'], head)
    except UNREADABLE as error:
        out['reasons'].append(f'입력을 읽지 못했습니다: {error}')
        out.update(blocked=True, blockers=['입력을 읽지 못해 lint·리뷰 결과를 확인하지 못했습니다'])
        return out
    out.update(base=base, head=head, merge_base=need['merge_base'], policy=rule, inputs={'need': need, 'paths': paths})
    risky = [p for p in paths if matches(p, rule['ask']) or matches(p, config['review_policy']['always'])]
    if not paths:
        out['reasons'].append('바뀐 파일이 없습니다')
    elif risky:
        out['reasons'].append('사람 승인 범주 경로: ' + ', '.join(risky[:5]))
    elif need['required']:
        out['reasons'].append('대규모 변경: ' + need['reason'])
    elif all(matches(p, rule['auto']) for p in paths):
        out['grade'] = 'auto'
        out['reasons'].append('모든 변경이 autonomy_policy.auto 범위입니다')
    else:
        out['grade'] = 'delay'
        out['reasons'].append('소규모 코드 변경입니다')

    problem, read = lint_problem(repo, base, head, lint)
    out['inputs']['lint'] = {'source': str(lint) if lint else 'worktrees', 'passed': problem is None}
    if problem:
        out['blockers'].append(problem)
    if not read:
        out['grade'] = 'ask'
    if review_key:
        try:
            found = open_findings(repo, review_key)
        except UNREADABLE as error:
            out['blockers'].append(f'리뷰 결과를 읽지 못했습니다: {error}')
            out['grade'] = 'ask'
        else:
            out['inputs']['review'] = {'key': review_key, 'open_critical_high': len(found)}
            if found:
                out['blockers'].append(f'미해결 critical/high {len(found)}건')
    out['blocked'] = bool(out['blockers'])
    return out


def directory(repo):
    return policy.common_dir(str(Path(repo).resolve())) / 'fullops-autonomy'


def record(repo, judgment):
    """같은 과제·SHA의 판정은 덮어쓴다. 저장소의 다른 파일은 바꾸지 않는다."""
    folder = directory(repo)
    folder.mkdir(parents=True, exist_ok=True)
    key = judgment['key'] if judgment['key'] and KEY.fullmatch(judgment['key']) else 'nokey'
    head = judgment['head'] if re.fullmatch(r'[0-9a-f]{40}', judgment['head'] or '') else 'unresolved'  # 읽지 못한 ref는 경로에 쓰지 않는다
    path = folder / f'{key}-{head[:12]}.json'
    write_json(path, judgment)
    return path


def compare(repo):
    """기록한 섀도 판정과 같은 과제·SHA의 사람 결정을 나란히 놓는다."""
    decisions = {(d.get('key'), d.get('sha')): d for d in decision.items(repo) if d.get('sha')}
    rows = []
    for path in sorted(directory(repo).glob('*.json')):
        try:
            item = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        made = decisions.get((item.get('key'), item.get('head')))
        rows.append({'key': item.get('key'), 'head': item.get('head'), 'grade': item.get('grade'),
                     'blocked': item.get('blocked'), 'judged_at': item.get('judged_at'),
                     'decision': made and {'id': made['id'], 'status': made['status'], 'answer': made.get('answer')}})
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=['judge', 'compare'])
    parser.add_argument('--repo', default='.')
    parser.add_argument('--from', dest='base', help='지시서의 기준 ref. lint.py --from과 같아야 lint 결과를 찾는다')
    parser.add_argument('--to', dest='head', help='판정할 worker SHA')
    parser.add_argument('--key', help='과제 키')
    parser.add_argument('--review-key', help='미해결 critical/high를 확인할 리뷰 키')
    parser.add_argument('--lint', help='lint-result.json 경로. 없으면 등록된 워크트리에서 같은 base·head 결과를 찾는다')
    parser.add_argument('--origin', choices=['user', 'bot'], default='user', help='요청이 들어온 진입점')
    parser.add_argument('--record', action='store_true', help='Git 공용 디렉터리 fullops-autonomy/에 판정을 남긴다')
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    if args.action == 'compare':
        print(json.dumps({'judgments': compare(repo)}, ensure_ascii=False))
        return
    if not (args.base and args.head):
        parser.error('judge에는 --from과 --to가 필요합니다')
    if args.key and not KEY.fullmatch(args.key):
        parser.error('과제 키 형식이 아닙니다')
    result = judge(repo, args.base, args.head, args.key, args.review_key, args.lint, args.origin)
    if args.record:
        result['recorded'] = record(repo, result).as_posix()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
