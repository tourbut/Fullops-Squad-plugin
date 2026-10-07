#!/usr/bin/env python3
"""레포의 라우팅 기준으로 담당 역할·산출물·모델을 고른다.

기존 구조는 simple/design을 사용하고 불확실한 요청을 설계 역할로 보낸다.
제품 기획/기술 계획 역할을 명시한 레포는 implementation/product를 사용한다.
이 구조에서 호출 실패나 낮은 확신은 unresolved로 보류한다.
산출물 front matter의 title·summary와 역할별 모델 후보를 판단에 사용한다.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

from pathlib import Path

from board import deliverables
from jev_observe import MODEL, api_key, checked_answer, checked_noul, request, safe_text, validated
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
PRODUCT_SCOPE = {'implementation': 'Implement, analyze or fix within agreed product requirements. The worker owns technical planning, API/structure choices and tests, even across many modules.',
                 'product': 'Requires a product-rule decision, scope expansion, user acceptance criteria or unresolved shared product rules. Technical complexity alone is not product planning.'}


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


def product_roles(repo):
    """제품 기획/기술 계획 책임 분리의 명시적 opt-in. 기존 설계 라우팅은 유지한다."""
    planner, developer = marked_role(repo, '제품 기획'), marked_role(repo, '기술 계획')
    if not planner and not developer:
        return None
    roles = json.loads(safe_file(repo, '.fullops-squad/fullops.json').read_text(encoding='utf-8'))['roles']
    if not planner or not developer or planner == developer or any(r not in roles for r in (planner, developer)):
        raise ValueError('제품 기획/기술 계획 역할을 서로 다른 등록 역할로 지정하세요')
    if coordinator_role(repo) in (planner, developer) or marked_role(repo, '설계') != planner:
        raise ValueError('제품 기획 역할은 설계 역할과 같고 coordinator와 분리돼야 합니다')
    return planner, developer


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


def candidate_hash(repo, role):
    candidates = model_candidates(repo).get(role or '', [])
    return hashlib.sha256(json.dumps(candidates, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def checked_request(text):
    """라우팅 입력 오류를 호출 실패와 구분하고 비밀값 자체는 출력하지 않는다."""
    if len(text) > 4000:
        raise ValueError(f'입력 {len(text):,}자 > 4,000자. 요청을 글자 단위로 요약해 다시 실행하세요')
    try:
        text.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError('입력이 유효한 UTF-8이 아닙니다. 바이트 단위로 자르지 말고 글자 단위로 전달하세요') from None
    try:
        return safe_text(text)
    except ValueError:
        raise ValueError('입력에 비밀값으로 보이는 표현이 있습니다. 해당 값을 제거해 다시 실행하세요') from None


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
        values, usage, elapsed, model = validated(call({'model': MODEL, 'state': {'role': role, 'request': safe_text(text)}, 'questions': question}), question)
        answer = checked_answer(values['model'], criteria)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        return {**strongest, 'source': 'fallback', 'error': f'Jev 생략: {error}'}
    top = answer['probabilities'][answer['choice']]
    close = [c for c in candidates if answer['probabilities'][c['id']] >= top - MODEL_TIE]
    chosen = close[-1]  # 후보는 약한 것부터 적으므로 마지막이 가장 강하다
    return {**{k: chosen[k] for k in ('agent', 'provider', 'model', 'effort')}, 'source': 'jev',
            **({'tie_break': answer['choice']} if chosen['id'] != answer['choice'] else {}),
            'probabilities': {f"{c['agent']} {c['model']} {c['effort']}": answer['probabilities'][c['id']] for c in candidates},
            'usage': usage}


def document_options(repo):
    """갱신 후보 산출물 선택지. 범위 밖 산출물은 빼고, 비밀값처럼 보이는 요약은 버린다."""
    options = {}
    for d in deliverables(Path(repo) / '.fullops-squad'):
        if '범위 밖' in d['status']:
            continue
        if not re.fullmatch(r'D\d{2}', d['id']):
            continue
        fields = []
        for value in (d['name'], d['stage'], d['summary']):
            try:
                fields.append(safe_text(value or '', 200))
            except ValueError:
                fields.append('[omitted]')
        label = f"{d['id']} {fields[0]} ({fields[1]})" + (f': {fields[2]}' if fields[2] else '')
        try:
            options[d['id']] = safe_text(label, 300)
        except ValueError:
            options[d['id']] = f"{d['id']} Project deliverable"
    return options


def picked(probabilities):
    """{산출물 ID: 갱신 필요 확률}에서 DOC 이상인 것을 높은 순으로 최대 DOC_MAX개."""
    ranked = sorted((probabilities or {}).items(), key=lambda kv: -kv[1])
    return [doc for doc, probability in ranked if probability >= DOC][:DOC_MAX]


def route(repo, key, text, call, override_role=None, reason=None):
    """역할·산출물을 분류하고, 배정할 역할의 모델 후보가 있으면 모델도 고른다."""
    result = classify(repo, key, text, call)
    if override_role:
        roles = json.loads(safe_file(repo, '.fullops-squad/fullops.json').read_text(encoding='utf-8'))['roles']
        split = product_roles(repo)
        if not split and result['route'] != 'simple':
            raise ValueError('역할 변경은 simple 분류에서만 허용합니다. design 결과는 설계 역할에 배정하세요')
        if override_role not in roles or override_role == coordinator_role(repo) or (not split and override_role == marked_role(repo, '설계')):
            raise ValueError(f'배정할 수 없는 역할: {override_role}')
        if not reason or not reason.strip():
            raise ValueError('역할 변경 근거를 기록하세요')
        result['original_role'], result['role'] = result['role'], override_role
        if split:
            result['original_route'] = result['route']
            result['route'] = 'product' if override_role == split[0] else 'implementation'
        result['override_reason'] = reason
    result['model'] = pick_model(repo, result['role'], text, call) if result.get('role') else None
    result['candidate_hash'] = candidate_hash(repo, result['role'])
    return result


def model_only(repo, key, role, call, text=None):
    """설계를 거친 worker용. 요청 원문 대신 그 역할의 지시서(없으면 --request)로 모델을 고른다."""
    handover = safe_file(repo, f'.fullops-squad/handovers/to_{role}.md')
    body = text or (handover.read_text(encoding='utf-8')[:3500] if handover.is_file() else '')
    if not body.strip():
        raise ValueError(f'{role} 지시서가 비어 있습니다. 지시서를 먼저 쓰거나 --request를 주세요')
    checked_request(body)
    return {'version': 'jev-model-v1', 'task_key': key, 'role': role, 'model': pick_model(repo, role, body, call),
            'candidate_hash': candidate_hash(repo, role)}


def classify(repo, key, text, call):
    roles = list(json.loads(safe_file(repo, '.fullops-squad/fullops.json').read_text(encoding='utf-8'))['roles'])
    result = {'version': 'jev-route-v3', 'task_key': key, 'requested_model': MODEL, 'route': None, 'role': None,
              'deliverables': [], 'thresholds': {'simple': SIMPLE, 'role': ROLE, 'deliverable': DOC},
              'answers': None, 'usage': None, 'error': None}
    split = None
    try:
        split = product_roles(repo)
        body, designer, described = guide(repo)
    except (OSError, ValueError) as error:
        opted = marked_role(repo, '제품 기획') or marked_role(repo, '기술 계획')
        return {**result, 'route': 'unresolved' if opted else 'design', 'error': str(error)}
    result['role'] = designer
    if designer not in roles:
        return {**result, 'route': 'design', 'error': f'설계 역할 {designer}이 fullops.json에 없습니다'}
    coordinator = coordinator_role(repo)
    workers = {r: f'{r}: {described.get(r, r)}' for r in roles if r not in (designer, coordinator)}
    if not workers:
        return {**result, 'route': 'design', 'error': '설계 역할 외 worker 역할이 없습니다'}
    if split:
        result.update(version='jev-route-v4', role=None)
    fallback = 'unresolved' if split else 'design'
    questions = {'scope': {'type': 'choice', 'criteria': PRODUCT_SCOPE if split else SCOPE, 'instructions':
                           ('Does request need a product-rule/scope decision, or can its owner plan and implement under agreed requirements? Technical complexity is implementation.' if split else
                            'Using the repository routing `guide`, can a worker do `request` directly without a design step?')},
                 'role': {'type': 'choice', 'criteria': workers, 'instructions':
                          'Using the repository routing `guide`, which role owns most of the work in `request`?'}}
    docs = document_options(repo)
    for doc in docs:
        questions[f'doc_{doc}'] = {'type': 'noul', 'instructions':
                                   f'Must the project deliverable `deliverables.{doc}` be written or updated because of `request`?'}
    try:
        state = {'guide': safe_text(body), 'request': safe_text(text), **({'deliverables': docs} if docs else {})}
        safe_text(json.dumps(state, ensure_ascii=False), 20000)
        values, usage, elapsed, model = validated(call({'model': MODEL, 'state': state, 'questions': questions}), questions, partial=True)
        answers = {q: checked_answer(values[q], questions[q]['criteria']) for q in ('scope', 'role')}
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        return {**result, 'route': fallback, 'error': f'Jev 생략: {error}'}
    answers['docs'], unresolved = {}, []
    for doc in docs:
        try:
            answers['docs'][doc] = checked_noul(values[f'doc_{doc}'])
        except (ValueError, KeyError, TypeError):
            unresolved.append(doc)
    positive = [doc for doc, probability in answers['docs'].items() if probability >= DOC]
    result.update(docs_status='partial' if unresolved else 'complete', unresolved_deliverables=unresolved,
                  additional_deliverables=[doc for doc in positive if doc not in picked(answers['docs'])])
    scope, role = answers['scope'], answers['role']
    if split:
        product = scope['probabilities']['product'] >= SIMPLE
        implementation = scope['probabilities']['implementation'] >= SIMPLE and role['probabilities'][role['choice']] >= ROLE
        return {**result, 'route': 'product' if product else 'implementation' if implementation else 'unresolved',
                'role': designer if product else role['choice'] if implementation else None,
                'deliverables': picked(answers['docs']), 'answers': answers, 'usage': usage,
                'latency_seconds': elapsed, 'response_model': model}
    simple = scope['probabilities']['simple'] >= SIMPLE and role['probabilities'][role['choice']] >= ROLE
    return {**result, 'route': 'simple' if simple else 'design', 'role': role['choice'] if simple else designer,
            'deliverables': picked(answers['docs']), 'answers': answers, 'usage': usage, 'latency_seconds': elapsed,
            'response_model': model}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--request', help='사용자 요청 원문 (4000자 이하, 비밀값 금지). --model-only면 생략 시 지시서를 읽는다')
    parser.add_argument('--model-only', action='store_true', help='분류 없이 --role의 모델만 고른다(설계 뒤 worker 배정용)')
    parser.add_argument('--role', help='--model-only 대상 역할')
    parser.add_argument('--override-role', help='담당 역할 변경(사유 기록; 제품/기술 책임 분리 레포에서는 unresolved도 명시 배정)')
    parser.add_argument('--reason', help='--override-role의 근거(500자 이하)')
    parser.add_argument('--force', action='store_true', help='기존 결과를 백업하고 같은 키로 재선정')
    parser.add_argument('--strict', action='store_true', help='Jev 폴백이 발생하면 결과를 기록하지 않고 오류로 종료')
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
        if args.override_role and (args.model_only or not args.reason or len(args.reason) > 500):
            raise ValueError('--override-role은 일반 라우팅에서 --reason <500자 이하 근거>와 함께 사용하세요')
        if args.reason and not args.override_role:
            raise ValueError('--reason에는 --override-role이 필요합니다')
        if args.request:
            checked_request(args.request)
        if args.reason:
            checked_request(args.reason)
        name = f'{args.key}-model-{args.role}.json' if args.model_only else f'{args.key}-route.json'
        output = safe_file(repo, f'.fullops-squad/docs/evaluations/jev/{name}')
        if output.exists() and not args.force:
            warning = ''
            try:
                previous = json.loads(output.read_text(encoding='utf-8'))
                role = args.role if args.model_only else previous.get('role')
                old_hash = previous.get('candidate_hash')
                if old_hash and old_hash != candidate_hash(repo, role):
                    warning = ' 모델 후보가 변경됐습니다.'
                elif not old_hash and previous.get('model'):
                    model = previous['model']
                    if not any(all(c.get(k) == model.get(k) for k in ('agent', 'model', 'effort'))
                               for c in model_candidates(repo).get(role or '', [])):
                        warning = ' 기록된 모델이 현재 후보에 없습니다.'
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            parser.exit(1, f'이미 결과가 있어 호출하지 않았습니다: {output.relative_to(repo)}. '
                           f'기존 결과는 보존합니다.{warning} 다시 고르려면 --force를 사용하세요\n')
    except (OSError, ValueError) as error:
        parser.exit(1, f'Jev 라우팅 실패: {error}\n')

    def call(payload):
        return request(payload, api_key(args.env_file, repo))
    try:
        result = (model_only(repo, args.key, args.role, call, args.request) if args.model_only else
                  route(repo, args.key, args.request, call, args.override_role, args.reason))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Jev 라우팅 실패: {error}\n')
    errors = [error for error in (result.get('error'), (result.get('model') or {}).get('error')) if error]
    if result.get('docs_status') == 'partial':
        errors.append('산출물 일부 미확인: ' + ', '.join(result.get('unresolved_deliverables') or []))
    if args.strict and errors:
        parser.exit(2, 'Jev 라우팅 실패: ' + ' / '.join(errors) + '\n')
    for error in errors:
        print(f'경고: {error}', file=sys.stderr)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        backup = output.with_name(f'{output.stem}.prior-{time.time_ns()}.json')
        with backup.open('xb') as archived:
            archived.write(output.read_bytes())
        print(f'이전 결과 보존: {backup.relative_to(repo)}', file=sys.stderr)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    model = result.get('model')
    model_line = (f"모델: {model.get('provider')} {model['model']} via {model['agent']} effort={model['effort']} ({model['source']})" if model
                  else '모델: 후보 없음 (orca-agents.md ## 모델 후보)')
    if args.model_only:
        print(model_line)
        print(output.relative_to(repo))
        return
    answers = result['answers']
    scope_label = 'simple' if not answers or 'simple' in answers['scope']['probabilities'] else 'implementation'
    detail = (f" ({scope_label} {answers['scope']['probabilities'][scope_label]:.2f}, "
              f"{answers['role']['choice']} {answers['role']['probabilities'][answers['role']['choice']]:.2f})") if answers else ''
    print(f"route: {result['route']} → {result['role'] or '-'}{detail} / {result['error'] or '정상'}")
    print(f"갱신할 산출물: {', '.join(result['deliverables']) or '없음'}")
    if result.get('docs_status') == 'partial':
        print('산출물 미확인: ' + ', '.join(result['unresolved_deliverables']))
    if result.get('additional_deliverables'):
        print('추가 확인할 산출물: ' + ', '.join(result['additional_deliverables']))
    print(model_line)
    print(output.relative_to(repo))


if __name__ == '__main__':
    main()
