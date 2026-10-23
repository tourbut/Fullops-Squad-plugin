"""coordinator hook만 과제 상태 파일을 쓰고, 노드가 route → 배정 → worker_done → 리뷰 → 병합으로 옮겨 가며, 모든 워크트리가 읽는지 확인한다."""
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
            return subprocess.check_output(['git', '-C', str(cwd), *args], text=True, stderr=subprocess.DEVNULL).strip()

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
        assert state('K1')['node'] == '설계' and state('K1')['gates'] == ['route'], state('K1')
        post('orca orchestration worker-start --run run_1 --worktree "w" --spec "Task key: K1; Purpose: implementation"')
        assert state('K1')['node'] == '구현'
        (worker / 'f.py').write_text('f = 1\n')
        sha = commit(worker, 'feature')
        time.sleep(0.05)  # 완료 보고 기록이 마지막 확인 시각보다 나중이어야 한다
        integration.record(repo, [{'id': 'm1', 'type': 'worker_done', 'body': f'[완료] K1 | 브랜치 fullops/dev | SHA {sha}'}])
        post('orca orchestration check --run run_1')
        assert state('K1')['node'] == 'worker_done' and state('K1')['sha'] == sha
        post(f'python3 review.py check --repo . --key K1 --from main --to {sha}')
        assert state('K1')['node'] == '리뷰'
        git('merge', '-q', '--ff-only', sha)
        post(f'git merge --ff-only {sha}')
        final = state('K1')
        assert final['node'] == '병합' and final['gates'] == ['route', 'dispatch', 'worker_done', 'review', 'merge'], final
        assert final['rounds'] == 0 and final['budget'] == 2 and final['updated']
        # 차수 키는 원래 과제의 상태로 모이고 반복 횟수를 센다
        route = repo / '.fullops-squad/docs/evaluations/jev/K1-FIX-route.json'
        route.parent.mkdir(parents=True, exist_ok=True)
        route.write_text(json.dumps({'task_key': 'K1-FIX', 'route': 'simple', 'role': 'dev'}))
        post('python3 jev_route.py --repo . --key K1-FIX --text fix')
        assert state('K1')['node'] == '설계' and state('K1')['rounds'] == 1 and state('K1-FIX') is None
        # worker 세션은 쓰지 않고, 모든 워크트리가 같은 상태를 읽는다
        git('merge', '-q', '--ff-only', 'main', cwd=worker)
        post('python3 jev_route.py --repo . --key K2 --text other', cwd=worker)
        assert state('K2') is None
        listed = subprocess.run([sys.executable, str(SCRIPTS / 'flow_state.py'), '--repo', str(worker)],
                                capture_output=True, text=True, encoding='utf-8', check=True)
        assert [s['key'] for s in json.loads(listed.stdout)] == ['K1']
    print('PASS: flow state nodes from route to merge, round keys fold into the task, coordinator-only writes, shared reads')


if __name__ == '__main__':
    main()
