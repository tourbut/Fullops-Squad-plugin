#!/usr/bin/env python3
"""coordinator가 받은 요청을 Jev로 분류해 simple이면 담당 역할로, 아니면 설계 역할로 보낸다.

`orca-agents.md`의 `## 라우팅 기준`을 Jev의 state로 보내 레포 기준으로 판단하게 한다. 확신이 낮거나
기준·키가 없거나 호출이 실패하면 항상 설계 역할로 보낸다. 잘못된 simple은 재작업이고 잘못된 design은 비용뿐이다.
"""
import argparse
import json
import os
import re

from jev_observe import MODEL, checked_answer, key_from_file, request, safe_text
from work import KEY, active_repo, safe_file

SIMPLE, ROLE = 0.8, 0.6  # ponytail: 보수적 초기값. 기록된 route 결과와 실제 재작업을 비교해 다시 정한다
SCOPE = {'simple': 'Files, acceptance and checks are clear from the request and it stays inside one role.',
         'design': 'Needs design decisions, changes a shared contract, spans several roles, or is ambiguous.'}


def guide(repo):
    """(라우팅 기준 본문, 설계 역할, {역할: 설명})"""
    text = safe_file(repo, '.fullops-squad/orca-agents.md').read_text(encoding='utf-8')
    section = re.search(r'^## 라우팅 기준\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not section:
        raise ValueError('orca-agents.md에 ## 라우팅 기준 섹션이 없습니다')
    body = section.group(1).strip()
    designer = re.search(r'^- 설계 역할: `([a-z][a-z0-9_-]*)`', body, re.M)
    if not designer:
        raise ValueError('라우팅 기준에 "- 설계 역할: `<역할>`" 줄이 없습니다')
    described = dict(re.findall(r'^- `([a-z][a-z0-9_-]*)`\s*:\s*(.+)$', body, re.M))
    return body, designer.group(1), described


def route(repo, key, text, call):
    roles = list(json.loads(safe_file(repo, '.fullops-squad/fullops.json').read_text(encoding='utf-8'))['roles'])
    result = {'version': 'jev-route-v1', 'task_key': key, 'requested_model': MODEL, 'route': None, 'role': None,
              'thresholds': {'simple': SIMPLE, 'role': ROLE}, 'answers': None, 'usage': None, 'error': None}
    try:
        body, designer, described = guide(repo)
    except (OSError, ValueError) as error:
        return {**result, 'route': 'design', 'error': str(error)}
    result['role'] = designer
    if designer not in roles:
        return {**result, 'route': 'design', 'error': f'설계 역할 {designer}이 fullops.json에 없습니다'}
    workers = {r: f'{r}: {described.get(r, r)}' for r in roles if r != designer}
    if not workers:
        return {**result, 'route': 'design', 'error': '설계 역할 외 worker 역할이 없습니다'}
    questions = {'scope': {'type': 'choice', 'criteria': SCOPE, 'instructions':
                           'Using the repository routing `guide`, can a worker do `request` directly without a design step?'},
                 'role': {'type': 'choice', 'criteria': workers, 'instructions':
                          'Using the repository routing `guide`, which role owns most of the work in `request`?'}}
    try:
        response, elapsed = call({'model': MODEL, 'state': {'guide': safe_text(body), 'request': safe_text(text)},
                                  'questions': questions})
        answers = {q: checked_answer(response['answers'][q], questions[q]['criteria']) for q in questions}
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        return {**result, 'route': 'design', 'error': f'Jev 생략: {error}'}
    scope, role = answers['scope'], answers['role']
    simple = scope['probabilities']['simple'] >= SIMPLE and role['probabilities'][role['choice']] >= ROLE
    return {**result, 'route': 'simple' if simple else 'design', 'role': role['choice'] if simple else designer,
            'answers': answers, 'usage': response.get('usage') or {}, 'latency_seconds': elapsed,
            'response_model': response.get('model')}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--request', required=True, help='사용자 요청 원문 (4000자 이하, 비밀값 금지)')
    parser.add_argument('--env-file', help='OPENROUTER_API_KEY를 코드 실행 없이 읽는다')
    args = parser.parse_args()
    try:
        if not KEY.fullmatch(args.key):
            raise ValueError('과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요')
        repo = active_repo(args.repo)
        output = safe_file(repo, f'.fullops-squad/docs/evaluations/jev/{args.key}-route.json')
        if output.exists():
            raise ValueError(f'기존 결과를 보존합니다: {output.relative_to(repo)}')
    except (OSError, ValueError) as error:
        parser.exit(1, f'Jev 라우팅 실패: {error}\n')

    def call(payload):
        return request(payload, key_from_file(args.env_file) if args.env_file
                       else os.environ.get('OPENROUTER_API_KEY', ''))
    result = route(repo, args.key, args.request, call)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    answers = result['answers']
    detail = (f" (simple {answers['scope']['probabilities']['simple']:.2f}, "
              f"{answers['role']['choice']} {answers['role']['probabilities'][answers['role']['choice']]:.2f})") if answers else ''
    print(f"route: {result['route']} → {result['role'] or '-'}{detail} / {result['error'] or '정상'}")
    print(output.relative_to(repo))


if __name__ == '__main__':
    main()
