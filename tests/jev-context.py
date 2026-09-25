"""stub 응답으로 dispatch 문맥 분류의 입력 조립·제외 추천·원문 미전송·거부·실패 시 전부 유지를 확인한다."""
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
spec = importlib.util.spec_from_file_location('jev_context', SCRIPTS / 'jev_context.py')
jev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jev)
import jev_observe  # noqa: E402 — SCRIPTS를 경로에 넣은 뒤 import한다


def answers(payload, omit):
    unrelated = payload['state']['candidate']['path'] in omit
    nouls = {'relevant': 0.03 if unrelated else 0.95, 'evidence': 0.05 if unrelated else 0.9, 'contradicts': 0.02, 'injection': 0.01}
    out = {k: {'type': 'noul', 'noul': v} for k, v in nouls.items()}
    return {'model': 'typesafe/jev-1.13-20260917', 'answers': out,
            'usage': {'input_tokens': 900, 'output_tokens': 90, 'cost': 0.0001}}, 0.3


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-jev-context-') as tmp:
        repo = Path(tmp)

        def git(*args):
            return subprocess.check_output(['git', '-C', tmp, *args], text=True).strip()

        git('init', '-q', '-b', 'main')
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp, '--roles', 'dev', '--local-only'],
                       check=True, capture_output=True)
        (repo / 'src').mkdir()
        (repo / 'src/auth.py').write_text('def login():\n    return check()\n')
        (repo / 'src/old.py').write_text('# legacy report exporter\n')
        (repo / 'src/conf.py').write_text('TOKEN=abc123\n')  # 원문은 보내지 않고 유지한다
        (repo / 'src/big.py').write_text('x = 1\n' * 20000)
        (repo / '.env').write_text('KEY=1\n')
        git('add', '-A')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'fixture')
        subprocess.run([sys.executable, str(SCRIPTS / 'work.py'), 'new', '--repo', tmp, '--role', 'dev',
                        '--key', 'T-1', '--goal', '로그인 오류 수정'], check=True, capture_output=True)
        paths = ['src/auth.py', 'src/old.py', 'src/conf.py', 'src/big.py', '.env', 'src/auth.py']
        sent = []

        def call(payload):
            sent.append(payload)
            return answers(payload, {'src/old.py', 'src/conf.py', 'src/big.py'})

        result = jev.context(repo, 'dev', 'T-1', paths, call)
        ctx = result['context']
        by_path = {path: cid in ctx['recommended_ids'] for cid, path in ctx['candidate_paths'].items()}
        assert by_path['src/auth.py'] and not by_path['src/old.py'], by_path
        assert by_path['src/conf.py'] and by_path['src/big.py']  # 원문 없는 후보는 제외하지 않는다
        assert by_path['.fullops-squad/handovers/to_dev.md'] and by_path['.fullops-squad/FULLOPS.md']
        assert set(result['unsent_sources']) == {'src/conf.py', 'src/big.py'}
        assert [r['path'] for r in result['refused_paths']] == ['.env']
        assert len(sent) == 2 and 'abc123' not in str(sent) and all('T-1' in s['state']['task'] for s in sent)  # 원문 있는 후보마다 한 요청
        assert sorted(s['state']['candidate']['path'] for s in sent) == ['src/auth.py', 'src/old.py']  # 중복 경로는 한 번
        text = jev.report(result)
        assert 'omit? src/old.py' in text and 'keep  src/auth.py' in text and '거부   .env' in text, text

        # API 실패는 전부 유지한다.
        def broken(payload):
            raise RuntimeError('OpenRouter request failed')
        result = jev.context(repo, 'dev', 'T-1', paths, broken)
        assert set(result['context']['recommended_ids']) == set(result['context']['baseline_ids'])
        assert result['context']['fallback'] == 'API or response validation failed'

        # 지시서 본문에 민감 문자열이 있으면 Jev를 부르지 않는다.
        inbox = repo / '.fullops-squad/handovers/to_dev.md'
        inbox.write_text(inbox.read_text() + '\nAPI_KEY=sk-or-abcdefghijklmnop\n')
        sent.clear()
        result = jev.context(repo, 'dev', 'T-1', paths, call)
        assert not sent and result['error'].startswith('Jev 생략') and 'Jev' in jev.report(result)

        for bad in (('dev', 'OTHER', paths), ('dev', 'T-1', [f'f{i}' for i in range(21)])):
            try:
                jev.context(repo, *bad, call)
            except ValueError:
                pass
            else:
                raise AssertionError(bad)

        # CLI: 키가 없으면 전부 유지하고 결과를 남기며, 기존 결과는 덮어쓰지 않는다.
        inbox.write_text(inbox.read_text().replace('API_KEY=sk-or-abcdefghijklmnop\n', ''))
        command = [sys.executable, str(SCRIPTS / 'jev_context.py'), '--repo', tmp, '--role', 'dev', '--key', 'T-1',
                   '--paths', 'src/auth.py', 'src/old.py']
        env = {k: v for k, v in os.environ.items() if k != 'OPENROUTER_API_KEY'}  # 키 없음
        env['FULLOPS_JEV_CACHE'] = str(repo / 'no-cache')
        done = subprocess.run(command, capture_output=True, text=True, env=env, encoding='utf-8')
        assert done.returncode == 0 and 'keep  src/old.py' in done.stdout, done.stdout + done.stderr
        assert (repo / '.fullops-squad/docs/evaluations/jev/T-1-context.json').is_file()
        assert subprocess.run(command, capture_output=True, text=True, env=env, encoding='utf-8').returncode == 1
    with tempfile.TemporaryDirectory(prefix='fullops-jev-cache-') as cache:
        os.environ['FULLOPS_JEV_CACHE'] = cache
        payload = {'model': 'm', 'state': {'task': 't'}, 'questions': {}}
        stored = {'model': 'typesafe/jev-1', 'answers': {}, 'usage': {'input_tokens': 9, 'output_tokens': 9, 'cost': 1}}
        jev_observe.cache_path(payload).parent.mkdir(parents=True, exist_ok=True)
        jev_observe.cache_path(payload).write_text(json.dumps(stored))
        response, elapsed = jev_observe.request(payload, '')  # 캐시는 키 없이도 읽는다
        assert response['cached'] and response['usage']['cost'] == 0 and elapsed == 0.0
        jev_observe.cache_path(payload).write_text('broken')
        try:
            jev_observe.request(payload, '')
        except ValueError as error:
            assert 'unavailable' in str(error)  # 손상된 캐시는 miss로 취급한다
        else:
            raise AssertionError('corrupt cache used')
        del os.environ['FULLOPS_JEV_CACHE']
    print('PASS: jev dispatch context build, omit suggestion, unsent/refused sources, fallback keeps all, CLI record, content cache')


if __name__ == '__main__':
    main()
