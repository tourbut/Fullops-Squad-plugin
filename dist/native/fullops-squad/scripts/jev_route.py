#!/usr/bin/env python3
"""레포의 라우팅 기준으로 담당 역할·산출물을 고르고, coordinator가 고른 모델 tuple을 함께 기록한다.

기존 구조는 simple/design을 사용하고 불확실한 요청을 설계 역할로 보낸다.
제품 기획/기술 계획 역할을 명시한 레포는 implementation/product를 사용한다.
이 구조에서 호출 실패나 낮은 확신은 unresolved로 보류한다.
산출물 front matter의 title·summary를 판단에 사용한다. 모델은 Jev가 고르지 않는다.
"""
import argparse
import json
import os
import re
import sys
import time
import subprocess

from pathlib import Path

from board import deliverables
from jev_observe import MODEL, api_key, checked_answer, checked_noul, request, safe_text, validated, require_online, git_env
from work import KEY, active_repo, safe_file, input_identity, save_result

SIMPLE, ROLE = 0.8, 0.6  # ponytail: 보수적 초기값. 기록된 route 결과와 실제 재작업을 비교해 다시 정한다
# 산출물마다 독립된 예/아니오로 묻는다. Choice는 여러 문서가 해당하면 확률을 나눠 가져 문서마다 낮아진다
DOC, DOC_MAX = 0.5, 3  # 산출물: 확률 하한, 최대 개수
REVIEWER = 'reviewer'  # 고정 SHA 독립 리뷰 세션의 키. fullops.json 역할이 아니라 지시서가 없다
PROVIDER = {'claude': 'anthropic', 'codex': 'openai', 'grok': 'xai', 'agy': 'google'}  # 에이전트 CLI → 모델 제공사
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
    import policy
    config = policy.load(repo)
    role = marked_role(repo, 'coordinator')
    if config['mode'] == 'coor':
        return config.get('primary_role') or role
    return None if role == config['primary_role'] else role


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


def fixed_model(agent=None, model=None, effort=None):
    """coordinator가 `## 모델 후보`에서 고른(또는 사용자가 고정한) tuple. 일부만 주면 임의로 채우지 않는다."""
    if all(v is None for v in (agent, model, effort)):
        return None
    agent = 'claude' if agent == 'claude-code' else agent
    if agent not in PROVIDER or not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9._:/-]+', model) or not isinstance(effort, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', effort):
        raise ValueError('모델 기록에는 --agent <CLI> --model <모델> --effort <effort> 전체를 지정하세요')
    return {'agent': agent, 'provider': PROVIDER[agent], 'model': model, 'effort': effort, 'source': 'user'}


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


def route(repo, key, text, call, override_role=None, reason=None, agent=None, model=None, effort=None):
    """역할·산출물을 분류한다. 모델은 coordinator가 넘긴 tuple만 기록한다."""
    chosen = fixed_model(agent, model, effort)
    result = classify(repo, key, text, call)
    if override_role:
        roles = json.loads(safe_file(repo, '.fullops-squad/fullops.json').read_text(encoding='utf-8'))['roles']
        split = product_roles(repo)
        if not split and result['route'] != 'simple':
            raise ValueError('역할 변경은 simple 분류에서만 허용합니다. design 결과는 설계 역할에 배정하세요')
        import policy
        config = policy.load(repo)
        primary = config.get('primary_role') if config['mode'] == 'dev' else None
        if override_role not in roles or override_role == coordinator_role(repo) or (not split and override_role == marked_role(repo, '설계') and override_role != primary):
            raise ValueError(f'배정할 수 없는 역할: {override_role}')
        if not reason or not reason.strip():
            raise ValueError('역할 변경 근거를 기록하세요')
        result['original_role'], result['role'] = result['role'], override_role
        if split:
            result['original_route'] = result['route']
            result['route'] = 'product' if override_role == split[0] else 'implementation'
        result['override_reason'] = reason
    result['model'] = chosen if result.get('role') else None
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', 'HEAD'], capture_output=True, text=True, env=git_env())
    result['head'] = head.stdout.strip() if head.returncode == 0 else None
    result['requires_packet'] = True
    if result.get('role'):
        try:
            result.update(input_identity(repo, result['role'], key, {'policy': 'route-v4'}))
        except ValueError:
            pass  # 지시서 작성 전 분류는 --bind-inbox로 현재 시도와 명시적으로 연결한다.
    return result


def model_only(repo, key, role, agent=None, model=None, effort=None):
    """설계를 거친 worker·리뷰어 배정 때 coordinator가 고른 tuple을 과제·역할별로 기록한다."""
    if role != REVIEWER:
        from work import validate_role
        validate_role(repo, role)
    chosen = fixed_model(agent, model, effort)
    if not chosen:
        raise ValueError('--model-only에는 --agent --model --effort가 필요합니다')
    return {'version': 'model-v2', 'task_key': key, 'role': role, 'model': chosen}


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
    import policy
    config = policy.load(repo)
    excluded = {designer, coordinator}
    if config['mode'] == 'dev':
        excluded.discard(config['primary_role'])
    workers = {r: f'{r}: {described.get(r, r)}' for r in roles if r not in excluded}
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
        require_online()
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
    parser.add_argument('--request', help='사용자 요청 원문 (4000자 이하, 비밀값 금지)')
    parser.add_argument('--model-only', action='store_true', help='분류 없이 --role에 배정할 tuple만 기록한다(설계 뒤 worker·리뷰어 배정용, API 호출 없음)')
    parser.add_argument('--role', help='--model-only 대상 역할. `reviewer`는 고정 SHA 독립 리뷰 세션 키다')
    parser.add_argument('--agent', choices=[*PROVIDER, 'claude-code'], help='배정할 CLI. --model·--effort와 함께 지정')
    parser.add_argument('--model', help='배정할 모델 (coordinator가 orca-agents.md `## 모델 후보`에서 고른다)')
    parser.add_argument('--effort', help='배정할 effort')
    parser.add_argument('--bind-inbox', action='store_true', help='API 호출 없이 기존 route를 현재 역할 지시서와 연결한다')
    parser.add_argument('--override-role', help='담당 역할 변경(사유 기록; 제품/기술 책임 분리 레포에서는 unresolved도 명시 배정)')
    parser.add_argument('--reason', help='--override-role의 근거(500자 이하)')
    parser.add_argument('--force', action='store_true', help='기존 결과를 백업하고 같은 키로 재선정')
    parser.add_argument('--strict', action='store_true', help='Jev 폴백이 발생하면 결과를 기록하지 않고 오류로 종료')
    parser.add_argument('--env-file', help='TYPESAFE_API_KEY 또는 OPENROUTER_API_KEY를 코드 실행 없이 읽는다')
    args = parser.parse_args()
    try:
        if not KEY.fullmatch(args.key):
            raise ValueError('과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요')
        repo = active_repo(args.repo)
        fixed_model(args.agent, args.model, args.effort)
        if args.bind_inbox:
            if not args.role or args.model_only or args.request or args.override_role or args.agent:
                raise ValueError('--bind-inbox에는 --role만 함께 지정하세요')
            output = safe_file(repo, f'.fullops-squad/docs/evaluations/jev/{args.key}-route.json')
            result = json.loads(output.read_text())
            identity = input_identity(repo, args.role, args.key, {'policy': 'route-v4'})
            # coordinator 워크트리에서 분류한 route도 지금 HEAD가 그 분류 시점을 포함하면 연결한다
            later = result.get('head') and subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', result['head'], identity['head']],
                                                          capture_output=True).returncode == 0
            if result.get('task_key') != args.key or result.get('role') != args.role or not later:
                raise ValueError('route의 과제/역할/SHA가 다릅니다. 먼저 재분류하세요')
            if result.get('attempt') and any(result.get(k) != identity[k] for k in ('attempt', 'instruction_sha256')):
                raise ValueError('이미 다른 시도/지시에 연결된 route입니다. --force로 재분류하세요')
            save_result(output, {**result, **identity, 'requires_packet': True})
            print(output.relative_to(repo))
            return
        if args.model_only and (not args.role or not args.agent or args.request):
            raise ValueError('--model-only에는 --role과 --agent --model --effort만 지정하세요')
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
            parser.exit(1, f'이미 결과가 있어 호출하지 않았습니다: {output.relative_to(repo)}. '
                           '기존 결과는 보존합니다. 다시 기록하려면 --force를 사용하세요\n')
    except (OSError, ValueError) as error:
        parser.exit(1, f'Jev 라우팅 실패: {error}\n')

    def call(payload):
        return request(payload, api_key(args.env_file, repo))
    try:
        result = (model_only(repo, args.key, args.role, args.agent, args.model, args.effort) if args.model_only else
                  route(repo, args.key, args.request, call, args.override_role, args.reason, args.agent, args.model, args.effort))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Jev 라우팅 실패: {error}\n')
    errors = [result['error']] if result.get('error') else []
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
                  else '모델: 미기록 (coordinator가 orca-agents.md `## 모델 후보`에서 골라 --agent --model --effort로 기록)')
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
