"""coordinator hook만 과제 상태 파일을 쓰고, 노드가 route → 배정 → worker_done → 리뷰 → 병합으로 옮겨 가며, 모든 워크트리가 읽는지 확인한다."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import integration  # noqa: E402


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-flow-state-') as tmp:
        root = Path(tmp)
        repo, worker = root / 'repo', root / 'worker'
        repo.mkdir()

        def git(*args, cwd=repo):
            return subprocess.check_output(['git', '-C', str(cwd), *args], text=True, encoding='utf-8', stderr=subprocess.DEVNULL).strip()

        def commit(cwd, message):
            git('add', '-A', cwd=cwd)
            git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', message, cwd=cwd)
            return git('rev-parse', 'HEAD', cwd=cwd)

        def post(command, cwd=repo):
            event = {'cwd': str(cwd), 'session_id': 'coor', 'tool_name': 'Bash', 'tool_input': {'command': command}}
            done = subprocess.run([sys.executable, str(SCRIPTS / 'flow_gate.py'), 'post'], input=json.dumps(event),
                                  text=True, capture_output=True, encoding='utf-8', env={**os.environ, 'FULLOPS_ORCA_CLI': 'missing-orca'})
            assert done.returncode == 0, done.stderr

        def state(key):
            path = integration.directory(repo).with_name('fullops-flow') / f'{key}.json'
            return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None

        git('init', '-q', '-b', 'main')
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', str(repo), '--roles', 'dev', '--local-only'],
                       check=True, capture_output=True)
        commit(repo, 'setup')
        git('worktree', 'add', '-q', '-b', 'fullops/dev', str(worker))

        post('python3 jev_route.py --repo . --key K1 --text "add feature"')
        assert state('K1')['node'] == 'design' and state('K1')['gates'] == ['route'], state('K1')
        post('orca orchestration worker-start --run run_1 --worktree "w" --spec "Task key: K1; Purpose: implementation"')
        assert state('K1')['node'] == 'build'
        (worker / 'f.py').write_text('f = 1\n', encoding='utf-8')
        first = commit(worker, 'feature')
        (worker / 'g.py').write_text('g = 1\n', encoding='utf-8')
        sha = commit(worker, 'record')
        time.sleep(0.05)  # 완료 보고 기록이 마지막 확인 시각보다 나중이어야 한다
        # 구현·기록 SHA를 둘 다 적으면 나머지를 포함하는 끝 커밋을 쓴다
        integration.record(repo, [{'id': 'm1', 'type': 'worker_done', 'body': f'[완료] K1 | 브랜치 fullops/dev | 구현 SHA {first}, 기록 SHA {sha}'}])
        post('orca orchestration check --run run_1')
        assert state('K1')['node'] == 'report' and state('K1')['sha'] == sha
        post(f'python3 review.py check --repo . --key K1-DEV-REVIEW-R2 --from main --to {sha}')
        assert state('K1')['node'] == 'review' and state('K1-DEV-REVIEW-R2') is None  # 리뷰 키는 과제에 묶인다
        time.sleep(0.05)
        for record in integration.directory(repo).glob('*.json'):  # 같은 완료 보고를 다시 써도 리뷰에서 되돌리지 않는다
            record.write_bytes(record.read_bytes())
        post('python3 jev_route.py --repo . --key ../escape --text x')  # 경로가 되는 키는 기록하지 않는다
        assert state('K1')['node'] == 'review' and not (integration.directory(repo).parent / 'escape.json').exists()
        git('merge', '-q', '--ff-only', sha)
        post(f'git merge --ff-only {sha}')
        final = state('K1')
        assert final['node'] == 'merge' and final['gates'] == ['route', 'dispatch', 'worker_done', 'review', 'merge'], final
        assert final['rounds'] == 0 and final['budget'] == 2 and final['updated']
        # 차수 키는 원래 과제의 상태로 모이고 반복 횟수를 센다
        route = repo / '.fullops-squad/docs/evaluations/jev/K1-FIX-route.json'
        route.parent.mkdir(parents=True, exist_ok=True)
        route.write_text(json.dumps({'task_key': 'K1-FIX', 'route': 'simple', 'role': 'dev'}), encoding='utf-8')
        post('python3 jev_route.py --repo . --key K1-FIX --text fix')
        assert state('K1')['node'] == 'design' and state('K1')['rounds'] == 1 and state('K1-FIX') is None
        # worker 세션은 쓰지 않고, 모든 워크트리가 같은 상태를 읽는다
        git('merge', '-q', '--ff-only', 'main', cwd=worker)
        post('python3 jev_route.py --repo . --key K2 --text other', cwd=worker)
        assert state('K2') is None
        listed = subprocess.run([sys.executable, str(SCRIPTS / 'flow_state.py'), '--repo', str(worker)],
                                capture_output=True, text=True, encoding='utf-8', check=True)
        assert [s['key'] for s in json.loads(listed.stdout)] == ['K1']
    print('PASS: flow state nodes from route to merge, round keys fold into the task, coordinator-only writes, shared reads')


def published_settlement():
    """원격 기본 브랜치에만 들어간 SHA, SHA 없는 리뷰 노드 기록, 재배정 사건, 역할로 끝나는 과제 키의 리뷰 키"""
    import flow_state
    with tempfile.TemporaryDirectory(prefix='fullops-flow-published-') as tmp:
        repo = Path(tmp)

        def git(*args):
            return subprocess.check_output(['git', '-C', str(repo), *args], text=True, encoding='utf-8', stderr=subprocess.DEVNULL).strip()

        def commit(message):
            git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q', '--allow-empty', '-m', message)
            return git('rev-parse', 'HEAD')

        def state(key):
            path = flow_state.directory(repo) / f'{key}.json'
            return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
        git('init', '-q', '-b', 'main')
        (repo / '.fullops-squad').mkdir()
        (repo / '.fullops-squad/fullops.json').write_text(json.dumps(
            {'roles': {'dev': 'fullops/dev'}, 'git': {'remote': 'origin', 'base': 'main'}}), encoding='utf-8')
        commit('setup')
        git('checkout', '-qb', 'work')
        first, second = commit('k1'), commit('k2')
        git('checkout', '-q', 'main')  # 로컬 main은 뒤처지고 원격 ref만 움직인다
        git('update-ref', 'refs/remotes/origin/main', second)
        # 첫 확인 전의 완료 보고는 펼치지 않으므로 K2 흐름 기록에는 SHA가 없다
        integration.record(repo, [{'id': 'm2', 'type': 'worker_done', 'body': f'[완료] K2 | 브랜치 fullops/dev | SHA {second}'}])
        assert integration.pending(repo) == []
        flow_state.update(repo, 'K1', 'build')
        flow_state.update(repo, 'K1', 'build')  # 수정 후 재배정
        assert [e['node'] for e in state('K1')['events']] == ['build', 'build'], state('K1')
        flow_state.update(repo, 'K1', 'report', first)
        flow_state.update(repo, 'K2-DEV-REVIEW', 'review')
        assert state('K2')['node'] == 'review' and 'sha' not in state('K2')
        flow_state.observe(repo, [])
        assert state('K1')['node'] == 'merge' and state('K2')['node'] == 'merge', (state('K1'), state('K2'))
        assert [e['node'] for e in state('K1')['events']] == ['build', 'build', 'report', 'merge']
        # 오래된 보류가 풀리며 다시 쓴 완료 기록은 다음 차수로 간 과제를 report로 되돌리지 않는다
        flow_state.update(repo, 'K1', 'design')
        integration.record(repo, [{'id': 'm1', 'type': 'worker_done', 'body': f'[완료] K1 | 브랜치 fullops/dev | SHA {first}'}])
        held = integration.directory(repo) / (hashlib.sha256(b'm1').hexdigest() + '.json')
        held.write_text(json.dumps({**json.loads(held.read_text(encoding='utf-8')), 'hold': {'reason': 'r'}}), encoding='utf-8')
        integration.pending(repo)
        assert 'released_hold' in json.loads(held.read_text(encoding='utf-8'))
        flow_state.observe(repo, [])
        assert state('K1')['node'] == 'design', state('K1')
        # 과제 키 자체가 역할로 끝나면 리뷰 키(-REVIEW-<n>)는 그 과제 기록을 옮긴다
        flow_state.update(repo, 'K3-DEV', 'build')
        flow_state.update(repo, 'K3-DEV-REVIEW-2', 'review')
        assert state('K3-DEV')['node'] == 'review' and state('K3') is None and state('K3-DEV-REVIEW-2') is None


if __name__ == '__main__':
    published_settlement()
    main()
