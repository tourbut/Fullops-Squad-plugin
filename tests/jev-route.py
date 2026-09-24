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


def stub(sent, simple, role, role_p=0.9):
    def call(payload):
        sent.append(payload)
        roles = list(payload['questions']['role']['criteria'])
        rest = (1 - role_p) / max(len(roles) - 1, 1)
        answers = {'scope': {'type': 'choice', 'choice': 'simple' if simple >= 0.5 else 'design', 'confidence': 0.9,
                             'probabilities': {'simple': simple, 'design': 1 - simple}},
                   'role': {'type': 'choice', 'choice': role, 'confidence': 0.9,
                            'probabilities': {r: role_p if r == role else rest for r in roles}}}
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
        assert '게임플레이' in questions['role']['criteria']['dev']

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
