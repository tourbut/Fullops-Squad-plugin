#!/usr/bin/env python3
"""coordinator가 받은 요청을 Jev로 분류해 simple이면 담당 역할로, 아니면 설계 역할로 보낸다.

`orca-agents.md`의 `## 라우팅 기준`을 Jev의 state로 보내 레포 기준으로 판단하게 한다. 확신이 낮거나
기준·키가 없거나 호출이 실패하면 항상 설계 역할로 보낸다. 잘못된 simple은 재작업이고 잘못된 design은 비용뿐이다.
같은 요청으로 갱신할 산출물(D01–D13)도 고른다. 산출물 front matter의 title·summary가 선택지 설명이 된다.
배정할 역할이 정해지면 `## 모델 후보`에서 그 역할의 후보 중 작업 난이도에 맞는 에이전트·모델·effort를 고른다.
설계를 거친 worker는 `--model-only --role <역할>`이 그 역할의 지시서를 읽고 고른다.
"""
import argparse
import json
import os
import re

from pathlib import Path

from board import deliverables
from jev_observe import MODEL, api_key, checked_answer, checked_noul, request, safe_text
from work import KEY, active_repo, safe_file

SIMPLE, ROLE = 0.8, 0.6  # ponytail: 보수적 초기값. 기록된 route 결과와 실제 재작업을 비교해 다시 정한다
# 산출물마다 독립된 예/아니오로 묻는다. Choice는 여러 문서가 해당하면 확률을 나눠 가져 문서마다 낮아진다
DOC, DOC_MAX = 0.5, 3  # 산출물: 확률 하한, 최대 개수
CANDIDATE = re.compile(r'^- `([a-z][a-z0-9_-]*)` `([A-Za-z0-9._-]+)` `([A-Za-z0-9._:/-]+)` `([A-Za-z0-9_-]+)`\s*:\s*(.+?)\s*$', re.M)
MODEL_TIE = 0.05  # 1등과 이만큼 이내인 후보가 있으면 품질 쪽(더 높은 레벨)을 쓴다
PROVIDER = {'claude': 'anthropic', 'codex': 'openai', 'grok': 'xai', 'agy': 'google'}  # 에이전트 CLI → 모델 제공사
MODEL_HINT = ('Candidates are ordered by level: level 1 is the cheapest and weakest, the highest level is the strongest '
              'and most expensive, across providers. Pick the lowest level that can still do `request` well for this role. Choose a higher '
              'level only when the work needs design judgment, touches many files or modules, or is risky.')
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


def coordinator_role(repo):
    """라우팅 기준의 "- coordinator 역할: `<역할>`" 줄. 없으면 None(기본 브랜치 체크아웃이 coordinator)."""
    return marked_role(repo, 'coordinator')


def marked_role(repo, label):
    """라우팅 기준의 "- <label> 역할: `<역할>`" 줄이 가리키는 역할. 없으면 None."""
    try:
        text = safe_file(repo, '.fullops-squad/orca-agents.md').read_text(encoding='utf-8')
    except OSError:
        return None
    section = re.search(r'^## 라우팅 기준\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    match = section and re.search(rf'^- {re.escape(label)} 역할: `([a-z][a-z0-9_-]*)`', section.group(1), re.M)
    return match.group(1) if match else None


def model_candidates(repo):
    """`## 모델 후보`의 "- `역할` `에이전트` `모델` `effort`: 언제 쓰는지" 줄. {역할: [후보]}, 약한 것부터 강한 순이다."""
    try:
        text = safe_file(repo, '.fullops-squad/orca-agents.md').read_text(encoding='utf-8')
    except OSError:
        return {}
    section = re.search(r'^## 모델 후보\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    result = {}
    body = re.sub(r'^```.*?^```', '', section.group(1), flags=re.M | re.S) if section else ''  # 코드 블록 예시는 읽지 않는다
    for role, agent, model, effort, note in CANDIDATE.findall(body):
        items = result.setdefault(role, [])
        items.append({'id': f'm{len(items) + 1}', 'agent': agent, 'provider': PROVIDER.get(agent, 'unknown'),
                      'model': model, 'effort': effort, 'note': note})
    return result


def pick_model(repo, role, text, call):
    """역할의 후보 중 작업에 맞는 것을 고른다. 후보가 없으면 None, 하나면 그것, Jev가 실패하면 품질 쪽인 마지막(가장 강한) 후보."""
    candidates = model_candidates(repo).get(role or '', [])
    if not candidates:
        return None
    strongest = {k: candidates[-1][k] for k in ('agent', 'provider', 'model', 'effort')}
    if len(candidates) == 1:
        return {**strongest, 'source': 'only'}
    criteria = {}
    for level, c in enumerate(candidates, 1):
        label = f"level {level}/{len(candidates)}: {c['provider']} {c['model']} via {c['agent']} effort={c['effort']}"
        try:
            criteria[c['id']] = safe_text(f"{label}: {c['note']}", 300)
        except ValueError:
            criteria[c['id']] = label
    question = {'model': {'type': 'choice', 'criteria': criteria, 'instructions': MODEL_HINT}}
    try:
        response, _ = call({'model': MODEL, 'state': {'role': role, 'request': safe_text(text)}, 'questions': question})
        answer = checked_answer(response['answers']['model'], criteria)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        return {**strongest, 'source': 'fallback', 'error': f'Jev 생략: {error}'}
    top = answer['probabilities'][answer['choice']]
    close = [c for c in candidates if answer['probabilities'][c['id']] >= top - MODEL_TIE]
    chosen = close[-1]  # 후보는 약한 것부터 적으므로 마지막이 가장 강하다
    return {**{k: chosen[k] for k in ('agent', 'provider', 'model', 'effort')}, 'source': 'jev',
            **({'tie_break': answer['choice']} if chosen['id'] != answer['choice'] else {}),
            'probabilities': {f"{c['agent']} {c['model']} {c['effort']}": answer['probabilities'][c['id']] for c in candidates},
            'usage': response.get('usage') or {}}


def document_options(repo):
    """갱신 후보 산출물 선택지. 범위 밖 산출물은 빼고, 비밀값처럼 보이는 요약은 버린다."""
    options = {}
    for d in deliverables(Path(repo) / '.fullops-squad'):
        if '범위 밖' in d['status']:
            continue
        label = f"{d['id']} {d['name']} ({d['stage']})"
        try:
            options[d['id']] = safe_text(f"{label}: {d['summary']}" if d['summary'] else label, 300)
        except ValueError:
            options[d['id']] = label
    return options


def picked(probabilities):
    """{산출물 ID: 갱신 필요 확률}에서 DOC 이상인 것을 높은 순으로 최대 DOC_MAX개."""
    ranked = sorted((probabilities or {}).items(), key=lambda kv: -kv[1])
    return [doc for doc, probability in ranked if probability >= DOC][:DOC_MAX]


def route(repo, key, text, call):
    """역할·산출물을 분류하고, 배정할 역할의 모델 후보가 있으면 모델도 고른다."""
    result = classify(repo, key, text, call)
    result['model'] = pick_model(repo, result['role'], text, call) if result.get('role') else None
    return result


def model_only(repo, key, role, call, text=None):
    """설계를 거친 worker용. 요청 원문 대신 그 역할의 지시서(없으면 --request)로 모델을 고른다."""
    handover = safe_file(repo, f'.fullops-squad/handovers/to_{role}.md')
    body = text or (handover.read_text(encoding='utf-8')[:3500] if handover.is_file() else '')
    if not body.strip():
        raise ValueError(f'{role} 지시서가 비어 있습니다. 지시서를 먼저 쓰거나 --request를 주세요')
    return {'version': 'jev-model-v1', 'task_key': key, 'role': role, 'model': pick_model(repo, role, body, call)}


def classify(repo, key, text, call):
    roles = list(json.loads(safe_file(repo, '.fullops-squad/fullops.json').read_text(encoding='utf-8'))['roles'])
    result = {'version': 'jev-route-v3', 'task_key': key, 'requested_model': MODEL, 'route': None, 'role': None,
              'deliverables': [], 'thresholds': {'simple': SIMPLE, 'role': ROLE, 'deliverable': DOC},
              'answers': None, 'usage': None, 'error': None}
    try:
        body, designer, described = guide(repo)
    except (OSError, ValueError) as error:
        return {**result, 'route': 'design', 'error': str(error)}
    result['role'] = designer
    if designer not in roles:
        return {**result, 'route': 'design', 'error': f'설계 역할 {designer}이 fullops.json에 없습니다'}
    coordinator = coordinator_role(repo)
    workers = {r: f'{r}: {described.get(r, r)}' for r in roles if r not in (designer, coordinator)}
    if not workers:
        return {**result, 'route': 'design', 'error': '설계 역할 외 worker 역할이 없습니다'}
    questions = {'scope': {'type': 'choice', 'criteria': SCOPE, 'instructions':
                           'Using the repository routing `guide`, can a worker do `request` directly without a design step?'},
                 'role': {'type': 'choice', 'criteria': workers, 'instructions':
                          'Using the repository routing `guide`, which role owns most of the work in `request`?'}}
    docs = document_options(repo)
    for doc in docs:
        questions[f'doc_{doc}'] = {'type': 'noul', 'instructions':
                                   f'Must the project deliverable `deliverables.{doc}` be written or updated because of `request`?'}
    try:
        state = {'guide': safe_text(body), 'request': safe_text(text), **({'deliverables': docs} if docs else {})}
        response, elapsed = call({'model': MODEL, 'state': state, 'questions': questions})
        answers = {q: checked_answer(response['answers'][q], questions[q]['criteria']) for q in ('scope', 'role')}
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        return {**result, 'route': 'design', 'error': f'Jev 생략: {error}'}
    try:  # 산출물 답이 이상해도 역할 라우팅은 유지한다
        answers['docs'] = {doc: checked_noul(response['answers'][f'doc_{doc}']) for doc in docs} if docs else None
    except (ValueError, KeyError, TypeError):
        answers['docs'] = None
    scope, role = answers['scope'], answers['role']
    simple = scope['probabilities']['simple'] >= SIMPLE and role['probabilities'][role['choice']] >= ROLE
    return {**result, 'route': 'simple' if simple else 'design', 'role': role['choice'] if simple else designer,
            'deliverables': picked(answers['docs']), 'answers': answers, 'usage': response.get('usage') or {}, 'latency_seconds': elapsed,
            'response_model': response.get('model')}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--request', help='사용자 요청 원문 (4000자 이하, 비밀값 금지). --model-only면 생략 시 지시서를 읽는다')
    parser.add_argument('--model-only', action='store_true', help='분류 없이 --role의 모델만 고른다(설계 뒤 worker 배정용)')
    parser.add_argument('--role', help='--model-only 대상 역할')
    parser.add_argument('--env-file', help='OPENROUTER_API_KEY를 코드 실행 없이 읽는다')
    args = parser.parse_args()
    try:
        if not KEY.fullmatch(args.key):
            raise ValueError('과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요')
        repo = active_repo(args.repo)
        if args.model_only and not args.role:
            raise ValueError('--model-only에는 --role이 필요합니다')
        if not args.model_only and not args.request:
            raise ValueError('--request가 필요합니다')
        name = f'{args.key}-model-{args.role}.json' if args.model_only else f'{args.key}-route.json'
        output = safe_file(repo, f'.fullops-squad/docs/evaluations/jev/{name}')
        if output.exists():
            raise ValueError(f'기존 결과를 보존합니다: {output.relative_to(repo)}')
    except (OSError, ValueError) as error:
        parser.exit(1, f'Jev 라우팅 실패: {error}\n')

    def call(payload):
        return request(payload, api_key(args.env_file, repo))
    try:
        result = model_only(repo, args.key, args.role, call, args.request) if args.model_only else route(repo, args.key, args.request, call)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Jev 라우팅 실패: {error}\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    model = result.get('model')
    model_line = (f"모델: {model.get('provider')} {model['model']} via {model['agent']} effort={model['effort']} ({model['source']})" if model
                  else '모델: 후보 없음 (orca-agents.md ## 모델 후보)')
    if args.model_only:
        print(model_line)
        print(output.relative_to(repo))
        return
    answers = result['answers']
    detail = (f" (simple {answers['scope']['probabilities']['simple']:.2f}, "
              f"{answers['role']['choice']} {answers['role']['probabilities'][answers['role']['choice']]:.2f})") if answers else ''
    print(f"route: {result['route']} → {result['role'] or '-'}{detail} / {result['error'] or '정상'}")
    print(f"갱신할 산출물: {', '.join(result['deliverables']) or '없음'}")
    print(model_line)
    print(output.relative_to(repo))


if __name__ == '__main__':
    main()
