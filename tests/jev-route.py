"""stub 응답으로 Jev 라우팅의 기준 전달·simple/design 판정·설계 역할 fallback·결과 기록을 확인한다."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('jev_route', SCRIPTS / 'jev_route.py')
jev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jev)


def stub(sent, simple, role, role_p=0.9, docs=None):
    """docs: {산출물 ID 또는 'none': 확률}. 나머지 선택지가 남은 확률을 나눠 갖는다. None이면 답하지 않는다."""
    def call(payload):
        sent.append(payload)
        roles = list(payload['questions']['role']['criteria'])
        rest = (1 - role_p) / max(len(roles) - 1, 1)
        answers = {'scope': {'type': 'choice', 'choice': 'simple' if simple >= 0.5 else 'design', 'confidence': 0.9,
                             'probabilities': {'simple': simple, 'design': 1 - simple}},
                   'role': {'type': 'choice', 'choice': role, 'confidence': 0.9,
                            'probabilities': {r: role_p if r == role else rest for r in roles}}}
        if docs is not None and 'docs' in payload['questions']:
            options = list(payload['questions']['docs']['criteria'])
            left = (1 - sum(docs.values())) / max(len(options) - len(docs), 1)
            probabilities = {o: docs.get(o, left) for o in options}
            answers['docs'] = {'type': 'choice', 'choice': max(probabilities, key=probabilities.get), 'confidence': 0.8,
                               'probabilities': probabilities}
        return {'model': 'typesafe/jev-test', 'answers': answers, 'usage': {'cost': 0.0001}}, 0.1
    return call


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-jev-route-') as tmp:
        repo = Path(tmp)
        subprocess.check_output(['git', 'init', '-q', '-b', 'main', tmp])
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp,
                        '--roles', 'architecture', 'dev', 'art', 'ops', '--local-only'], check=True, capture_output=True)
        agents = repo / '.fullops-squad/orca-agents.md'
        assert '## 라우팅 기준' in agents.read_text(encoding='utf-8')

        sent = []
        result = jev.route(repo, 'T-1', '점프 높이 수치를 1.2로 바꿔줘', stub(sent, 0.93, 'dev'))
        assert (result['route'], result['role'], result['error']) == ('simple', 'dev', None), result
        state, questions = sent[0]['state'], sent[0]['questions']
        assert '설계 역할' in state['guide'] and state['request'].startswith('점프')
        assert set(questions['role']['criteria']) == {'dev', 'art', 'ops'}  # 설계 역할은 후보가 아니다
        guide_file = repo / '.fullops-squad/orca-agents.md'
        original = guide_file.read_text(encoding='utf-8')
        guide_file.write_text(original.replace('- 설계 역할: `architecture`', '- 설계 역할: `architecture`\n- coordinator 역할: `ops`'),
                              encoding='utf-8')
        sent2 = []
        jev.route(repo, 'T-1b', '빌드 설정 바꿔줘', stub(sent2, 0.9, 'dev'))
        assert set(sent2[0]['questions']['role']['criteria']) == {'dev', 'art'}  # coordinator 역할도 후보가 아니다
        guide_file.write_text(original, encoding='utf-8')
        assert '게임플레이' in questions['role']['criteria']['dev']
        assert result['deliverables'] == [] and result['answers']['docs'] is None  # 산출물 답이 없어도 역할 라우팅 유지

        # 산출물 라우팅: 선택지는 인덱스와 front matter에서 만들고 범위 밖은 뺀다
        fo = repo / '.fullops-squad'
        index = fo / 'docs/deliverables/README.md'
        index.write_text(index.read_text(encoding='utf-8').replace('| 테이블정의서 | `docs/generated/db-schema.md` | 미작성 |',
                                                                  '| 테이블정의서 | `docs/generated/db-schema.md` | 범위 밖 |'), encoding='utf-8')
        (fo / 'docs/design-docs').mkdir(parents=True, exist_ok=True)
        (fo / 'docs/design-docs/architecture.md').write_text(
            '---\nid: D03\ntitle: 점프 시스템 설계\nstatus: draft\nupdated: 2026-09-24\nsummary: 점프 물리와 입력 처리 구조\n---\n', encoding='utf-8')
        sent = []
        result = jev.route(repo, 'T-7', '점프 물리 구조를 바꿔줘', stub(sent, 0.3, 'dev', docs={'D03': 0.55, 'D10': 0.3}))
        docs = sent[0]['questions']['docs']['criteria']
        assert 'D08' not in docs and 'none' in docs and docs['D03'] == 'D03 점프 시스템 설계 (설계): 점프 물리와 입력 처리 구조'
        assert (result['route'], result['deliverables']) == ('design', ['D03', 'D10']), result
        result = jev.route(repo, 'T-8', '문구 오타 수정', stub([], 0.95, 'dev', docs={'none': 0.7}))
        assert (result['route'], result['deliverables']) == ('simple', []), result
        result = jev.route(repo, 'T-9', '전체 개편', stub([], 0.9, 'dev', docs={'D02': 0.3, 'D03': 0.25, 'D04': 0.2, 'D05': 0.2}))
        assert result['deliverables'] == ['D02', 'D03', 'D04'], result  # 최대 3개
        assert result['model'] is None  # 모델 후보가 없으면 고르지 않는다

        # 모델 후보: 역할마다 사용자가 정한 후보 중 작업 난이도에 맞는 것을 고른다
        guide_path = repo / '.fullops-squad/orca-agents.md'
        guide_path.write_text(guide_path.read_text(encoding='utf-8').replace('## 모델 후보\n', '## 모델 후보\n\n'
            '- `dev` `codex` `gpt-6-sol` `low`: 문구·수치 같은 단순 수정\n'
            '- `dev` `claude` `claude-opus-5-5` `high`: 여러 모듈에 걸친 구현\n'
            '- `art` `codex` `gpt-6-sol` `medium`: 에셋 교체\n', 1), encoding='utf-8')
        candidates = jev.model_candidates(repo)
        assert [c['model'] for c in candidates['dev']][:2] == ['gpt-6-sol', 'claude-opus-5-5'], candidates
        seen = []

        def two_calls(route_stub, prefer):
            def call(payload):
                if 'model' in payload['questions']:
                    seen.append(payload)
                    labels = list(payload['questions']['model']['criteria'])
                    probabilities = {l: (0.8 if l == prefer else 0.2 / (len(labels) - 1)) for l in labels}
                    return {'model': 'jev-test', 'answers': {'model': {'type': 'choice', 'choice': prefer, 'confidence': 0.9,
                                                                        'probabilities': probabilities}}, 'usage': {}}, 0.1
                return route_stub(payload)
            return call

        simple_fix = jev.route(repo, 'M-1', '점프 수치를 1.5로', two_calls(stub([], 0.95, 'dev'), 'm1'))
        assert (simple_fix['role'], simple_fix['model']['model'], simple_fix['model']['effort']) == ('dev', 'gpt-6-sol', 'low'), simple_fix
        criteria = seen[-1]['questions']['model']['criteria']
        assert criteria['m1'].startswith('level 1/2: openai gpt-6-sol via codex') and criteria['m2'].startswith('level 2/2: anthropic')
        assert simple_fix['model']['provider'] == 'openai' and '단순 수정' in criteria['m1'] and seen[-1]['state']['role'] == 'dev'
        seen.clear()
        broken = jev.route(repo, 'M-2', '점프 수치', two_calls(stub([], 0.95, 'dev'), 'mX'))  # 잘못된 답
        assert broken['model']['source'] == 'fallback' and broken['model']['model'] == 'claude-opus-5-5'  # 가장 강한 후보
        seen.clear()
        only = jev.route(repo, 'M-3', '캐릭터 스프라이트 교체', two_calls(stub([], 0.95, 'art'), 'm1'))
        assert only['model'] == {'agent': 'codex', 'provider': 'openai', 'model': 'gpt-6-sol', 'effort': 'medium', 'source': 'only'} and not seen
        design = jev.route(repo, 'M-4', '저장 구조 개편', two_calls(stub([], 0.2, 'dev'), 'm1'))
        assert design['role'] == 'architecture' and design['model'] is None  # 설계 역할은 후보가 없다
        (repo / '.fullops-squad/handovers/to_dev.md').write_text('# M-4-DEV — 저장 구조 개편 구현\n여러 모듈 변경\n', encoding='utf-8')
        picked_after = jev.model_only(repo, 'M-4-DEV', 'dev', two_calls(None, 'm2'))
        assert picked_after['model']['model'] == 'claude-opus-5-5' and 'M-4-DEV' in seen[-1]['state']['request']
        (repo / '.fullops-squad/handovers/to_dev.md').write_text('', encoding='utf-8')
        try:
            jev.model_only(repo, 'M-5', 'dev', two_calls(None, 'm1'))
            raise AssertionError('빈 지시서 허용')
        except ValueError:
            pass

        for simple, role_p in ((0.6, 0.9), (0.95, 0.4)):  # scope나 role 확신이 낮으면 설계로
            result = jev.route(repo, 'T-2', '저장 형식을 바꿔줘', stub([], simple, 'dev', role_p))
            assert (result['route'], result['role']) == ('design', 'architecture'), result

        def broken(payload):
            raise RuntimeError('OpenRouter request failed')
        result = jev.route(repo, 'T-3', '무엇이든', broken)
        assert (result['route'], result['role']) == ('design', 'architecture') and 'Jev 생략' in result['error']

        sent = []
        result = jev.route(repo, 'T-4', 'API_KEY=sk-or-abcdefghijklmnop 로 바꿔줘', stub(sent, 0.99, 'ops'))
        assert result['route'] == 'design' and not sent  # 비밀값이 섞인 요청은 보내지 않는다

        agents.write_text('# Orca 역할 배정\n', encoding='utf-8')
        result = jev.route(repo, 'T-5', '무엇이든', stub([], 0.99, 'dev'))
        assert result['route'] == 'design' and '라우팅 기준' in result['error']

        agents.write_text('## 라우팅 기준\n- 설계 역할: `architecture`\n', encoding='utf-8')
        cli = subprocess.run([sys.executable, str(SCRIPTS / 'jev_route.py'), '--repo', tmp, '--key', 'T-6',
                              '--request', '버그 수정'], capture_output=True, text=True,
                             env={**os.environ, 'OPENROUTER_API_KEY': '', 'FULLOPS_JEV_CACHE': str(repo / 'cache')})
        assert cli.returncode == 0 and 'route: design → architecture' in cli.stdout, cli.stdout + cli.stderr
        saved = json.loads((repo / '.fullops-squad/docs/evaluations/jev/T-6-route.json').read_text(encoding='utf-8'))
        assert saved['route'] == 'design' and saved['error']
        again = subprocess.run([sys.executable, str(SCRIPTS / 'jev_route.py'), '--repo', tmp, '--key', 'T-6',
                                '--request', '버그 수정'], capture_output=True, text=True)
        assert again.returncode == 1 and '보존' in again.stderr
    print('PASS: jev route guide state, simple/design thresholds, designer fallback, secret refusal, CLI record')


if __name__ == '__main__':
    main()
