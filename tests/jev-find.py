"""stub 응답으로 Jev 코드 탐색의 지도 구성·순위·존재 판정·디렉터리 2단계·실패 처리·적중률 기록을 확인한다."""
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
spec = importlib.util.spec_from_file_location('jev_find', SCRIPTS / 'jev_find.py')
jev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jev)


def stub(sent, prefer, found=0.95):
    """prefer 문자열 순서대로 높은 확률을 주는 가짜 Jev."""
    def call(payload):
        sent.append(payload)
        answers = {}
        for qid, question in payload['questions'].items():
            labels = list(question['criteria'])
            if qid == 'exists':
                probabilities = {'found': found, 'absent': 1 - found}
            else:
                weights = {label: 0.001 for label in labels}
                for rank, needle in enumerate(prefer):
                    for label in labels:
                        if needle in question['criteria'][label] and weights[label] == 0.001:
                            weights[label] = [0.85, 0.1, 0.03][rank]
                total = sum(weights.values())
                probabilities = {label: w / total for label, w in weights.items()}
            choice = max(probabilities, key=probabilities.get)
            answers[qid] = {'type': 'choice', 'choice': choice, 'confidence': 0.9, 'probabilities': probabilities}
        return {'model': 'typesafe/jev-1.13-20260917', 'answers': answers,
                'usage': {'input_tokens': 500, 'output_tokens': 20, 'cost': 0.0001}}, 0.2
    return call


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-jev-find-') as tmp:
        repo = Path(tmp)

        def git(*args):
            return subprocess.check_output(['git', '-C', tmp, *args], text=True).strip()

        def commit(message):
            git('add', '-A')
            git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', message)
            return git('rev-parse', 'HEAD')

        git('init', '-q', '-b', 'main')
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp, '--roles', 'dev', '--local-only'],
                       check=True, capture_output=True)
        files = {'src/auth/login.py': '"""로그인 요청 검증과 세션 발급."""\n', 'src/auth/token.py': '"""JWT 발급·갱신."""\n',
                 'src/report/export.py': '# CSV 보고서 내보내기\n', 'docs/guide.md': '# 운영 가이드\n',
                 '.env': 'KEY=1\n', 'node_modules/dep/index.js': '// dep\n'}
        for name, text in files.items():
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            (repo / name).write_text(text)
        (repo / 'logo.png').write_bytes(b'\x89PNG\0\0data')
        (repo / 'link.py').symlink_to('src/auth/login.py')
        base = commit('fixture')
        subprocess.run([sys.executable, str(SCRIPTS / 'work.py'), 'new', '--repo', tmp, '--role', 'dev', '--key', 'F-1',
                        '--goal', '로그인 실패 시 세션을 만들지 않게 수정'], check=True, capture_output=True)

        mapped = dict(jev.code_map(repo, base))
        assert not [p for p in mapped if p.startswith('.fullops-squad/')]  # 하네스 문서는 코드 지도에 넣지 않는다
        assert mapped['src/auth/login.py'] == '로그인 요청 검증과 세션 발급.' and mapped['docs/guide.md'] == '운영 가이드'
        assert not {'.env', 'node_modules/dep/index.js', 'logo.png', 'link.py'} & set(mapped), set(mapped)

        sent = []
        result = jev.find(repo, 'dev', 'F-1', stub(sent, ['auth/login', 'auth/token']))
        assert [c['path'] for c in result['candidates']] == ['src/auth/login.py', 'src/auth/token.py'], result['candidates']
        assert result['existence']['status'] == 'found' and result['error'] is None
        assert len(sent) == 1 and set(sent[0]['questions']) == {'where', 'exists'} and 'F-1' in sent[0]['state']['task']
        assert result['usage']['cost'] == 0.0001 and result['passes'] == [{'level': 'file', 'options': len(mapped)}]
        assert jev.find(repo, 'dev', 'F-1', stub([], ['auth/login'], found=0.1))['existence']['status'] == 'absent'
        assert jev.find(repo, 'dev', 'F-1', stub([], ['auth/login'], found=0.5))['existence']['status'] == 'unclear'
        side = repo / '.fullops-squad/handovers/F-1-dev.md'
        side.write_text('# F-1 — 사이드 지시서\n로그인만 고친다.\n', encoding='utf-8')
        (repo / '.fullops-squad/handovers/to_dev.md').write_text('# OTHER — 다른 과제\n', encoding='utf-8')
        try:
            jev.find(repo, 'dev', 'F-1', stub([], ['auth/login']))
        except ValueError:
            pass
        else:
            raise AssertionError('wrong inbox')
        sent.clear()
        side_result = jev.find(repo, 'dev', 'F-1', stub(sent, ['auth/login']), handover='.fullops-squad/handovers/F-1-dev.md')
        assert side_result['candidates'][0]['path'] == 'src/auth/login.py' and '사이드 지시서' in sent[-1]['state']['task']
        (repo / '.fullops-squad/handovers/to_dev.md').write_text(
            '# F-1 — 로그인 실패 시 세션을 만들지 않게 수정\n', encoding='utf-8')

        def broken(payload):
            raise RuntimeError('OpenRouter request failed')
        failed = jev.find(repo, 'dev', 'F-1', broken)
        assert failed['candidates'] == [] and failed['error'].startswith('API or response validation failed')
        try:
            jev.find(repo, 'dev', 'OTHER', broken)
        except ValueError:
            pass
        else:
            raise AssertionError('다른 과제 키')

        # score: 실제 변경과 비교한다. 새 파일은 찾을 수 없으므로 따로 센다.
        out = jev.result_path(repo, 'F-1', 'find')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result))
        jev.result_path(repo, 'F-1', 'context').write_text(json.dumps({'context': {
            'candidate_paths': {'c0': 'src/auth/login.py', 'c1': 'src/report/export.py'}, 'recommended_ids': ['c1']}}))
        (repo / 'src/auth/login.py').write_text('"""로그인 요청 검증과 세션 발급."""\nFIXED = True\n')
        (repo / 'src/auth/mfa.py').write_text('"""2단계 인증."""\n')
        head = commit('work')
        scored = jev.score(repo, 'F-1', base, head)
        assert scored['changed_existing'] == ['src/auth/login.py'] and scored['new_files'] == ['src/auth/mfa.py'], scored
        assert scored['recall'] == 1.0 and scored['precision'] == 0.5 and scored['existence_correct'] is True
        assert scored['context_wrong_omits'] == ['src/auth/login.py']  # 제외 추천했는데 실제로 바뀐 파일

        # 파일이 255개를 넘으면 디렉터리를 먼저 고르고, 존재 질문은 한 번만 한다.
        for i in range(300):
            (repo / f'gen/part{i % 3}/file{i}.py').parent.mkdir(parents=True, exist_ok=True)
            (repo / f'gen/part{i % 3}/file{i}.py').write_text(f'"""생성 코드 {i}."""\n')
        commit('many')
        sent = []
        big = jev.find(repo, 'dev', 'F-1', stub(sent, ['src/', 'auth/login']))
        assert big['passes'][0]['level'] == 'directory' and big['passes'][0]['chosen'][0][0] == 'src', big['passes']
        assert big['candidates'][0]['path'] == 'src/auth/login.py'
        assert 'exists' in sent[0]['questions'] and 'exists' not in sent[-1]['questions']
        assert all(len(p['questions']['where']['criteria']) <= 255 for p in sent)

        # CLI: 키가 없으면 오류를 기록하고 후보 없이 끝나며, 기존 결과는 덮어쓰지 않는다.
        out.unlink()
        command = [sys.executable, str(SCRIPTS / 'jev_find.py'), 'find', '--repo', tmp, '--role', 'dev', '--key', 'F-1']
        env = {**{k: v for k, v in os.environ.items() if k != 'OPENROUTER_API_KEY'},  # Windows는 SYSTEMROOT 등이 필요하다
               'HOME': tmp, 'FULLOPS_JEV_CACHE': str(repo / '.git/jev-cache')}
        done = subprocess.run(command, capture_output=True, text=True, env=env, encoding='utf-8')
        assert done.returncode == 0 and 'paths: \n' in done.stdout + '\n' and 'API or response' in done.stdout, done.stdout + done.stderr
        assert subprocess.run(command, capture_output=True, text=True, env=env, encoding='utf-8').returncode == 1
        score_cmd = [sys.executable, str(SCRIPTS / 'jev_find.py'), 'score', '--repo', tmp, '--key', 'F-1',
                     '--from', base, '--to', 'HEAD']
        done = subprocess.run(score_cmd, capture_output=True, text=True, env=env, encoding='utf-8')
        assert done.returncode == 0 and 'recall' in done.stdout, done.stdout + done.stderr
    print('PASS: jev find map, ranking, existence, directory pass, fallback, score vs actual diff, CLI')


if __name__ == '__main__':
    main()
