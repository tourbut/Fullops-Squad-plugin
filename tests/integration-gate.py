"""완료 보고 수신부터 기본 브랜치 병합·push·다음 배정의 최신 기준까지 확인한다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/fullops-squad/scripts'


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-integration-') as tmp:
        root = Path(tmp)
        repo, remote, worker = root / 'repo', root / 'remote.git', root / 'worker'
        repo.mkdir()
        environment = dict(os.environ)

        def git(*args, cwd=repo):
            return subprocess.check_output(['git', '-C', str(cwd), *args], text=True, stderr=subprocess.DEVNULL).strip()

        def commit(cwd, message):
            git('add', '-A', cwd=cwd)
            git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', message, cwd=cwd)
            return git('rev-parse', 'HEAD', cwd=cwd)

        def hook(mode, **event):
            event.setdefault('cwd', str(repo))
            output = subprocess.check_output([sys.executable, str(SCRIPTS / 'flow_gate.py'), mode],
                                             input=json.dumps(event), text=True, env=environment)
            return json.loads(output)

        git('init', '-q', '-b', 'main')
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', str(repo), '--roles', 'dev',
                        '--local-only'], check=True, capture_output=True)
        config = repo / '.fullops-squad/fullops.json'
        data = json.loads(config.read_text(encoding='utf-8'))
        data['git'] = {'remote': 'origin', 'base': 'main'}
        config.write_text(json.dumps(data), encoding='utf-8')
        commit(repo, 'setup')
        git('init', '--bare', '-q', str(remote))
        git('remote', 'add', 'origin', str(remote))
        git('push', '-q', 'origin', 'main')
        git('worktree', 'add', '-q', '-b', 'fullops/dev', str(worker))
        (worker / 'feature.txt').write_text('worker result\n')
        sha = commit(worker, 'feature')
        # 가짜 Orca는 실제 대기 스크립트에 완료 보고를 전달한다. ACK 후에도 게이트가 기억해야 한다.
        fake = root / 'fake.py'
        message = {'id': 'msg_done', 'type': 'worker_done', 'body':
                   f'[완료] K1 | 브랜치 fullops/dev | SHA {sha} | 검증: 통과'}
        fake.write_text('import json\nprint(' + repr(json.dumps({'ok': True, 'result': {
            'deliveryId': 'delivery_1', 'messages': [message]}})) + ')\n', encoding='utf-8')
        cli = root / ('orca.cmd' if os.name == 'nt' else 'orca')
        cli.write_text(f'@"{sys.executable}" "{fake}" %*\n' if os.name == 'nt' else
                       f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n', encoding='utf-8')
        cli.chmod(0o755)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'orca_wait.py'), '--repo', str(repo),
                                 '--orca', str(cli), '--run', 'run_1'], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        stopped = hook('stop', session_id='new-session')
        assert stopped.get('decision') == 'block' and '병합' in stopped['reason'], stopped
        assert hook('stop', session_id='new-session', stop_hook_active=True).get('decision') == 'block'
        route = repo / '.fullops-squad/docs/evaluations/jev/K1-route.json'
        route.parent.mkdir(parents=True, exist_ok=True)
        route.write_text(json.dumps({'route': 'simple', 'role': 'dev'}))
        review = f'orca orchestration worker-start --run run_2 --worktree "{worker}" --spec "K1 리뷰"'
        assert hook('tool', session_id='review', tool_input={'command': review}) == {}
        unrelated = hook('tool', session_id='other', tool_input={'command': review.replace('K1', 'K2')})
        assert '통합' in unrelated['hookSpecificOutput']['permissionDecisionReason'], unrelated
        assert '--worktree' in hook('tool', session_id='missing-path', tool_input={
            'command': 'orca orchestration worker-start --run run_2 --spec "K1 리뷰"'
        })['hookSpecificOutput']['permissionDecisionReason']
        # 보류는 명시적 사유·담당·재개 조건이 있어야 한다. 재전달과 세션 변경에도 보존한다.
        script = [sys.executable, str(SCRIPTS / 'integration.py'), '--repo', str(repo)]
        invalid = subprocess.run([*script, 'hold', '--message', 'msg_done', '--reason', '검수 대기'],
                                 capture_output=True, text=True)
        assert invalid.returncode != 0
        assert hook('stop', session_id='invalid-hold').get('decision') == 'block'
        held = subprocess.run([*script, 'hold', '--message', 'msg_done', '--reason', '독립 검수 대기',
                               '--owner', 'tester', '--resume', '검수 통과'], capture_output=True, text=True)
        assert held.returncode == 0, held.stderr
        assert hook('stop', session_id='held') == {}
        result = subprocess.run([sys.executable, str(SCRIPTS / 'orca_wait.py'), '--repo', str(repo),
                                 '--orca', str(cli), '--run', 'run_1', '--quiet-types', 'worker_done'],
                                capture_output=True, text=True)
        assert json.loads(result.stdout)['status'] == 'actionable'
        assert hook('stop', session_id='redelivered') == {}
        subprocess.run([*script, 'resume', '--message', 'msg_done'], check=True, capture_output=True)
        assert hook('stop', session_id='resumed').get('decision') == 'block'
        # 작업 중 상태를 건드리지 않고, 공용 저널만 모든 워크트리에서 읽는다.
        status = subprocess.run([sys.executable, str(SCRIPTS / 'integration.py'), '--repo', str(worker),
                                 'status'], capture_output=True, text=True)
        assert json.loads(status.stdout)['pending'][0]['sha'] == sha
        # 직접 check/ACK 경로도 완료 보고를 저장한다. --task의 후속 spec은 같은 과제로 인식한다.
        direct = {**message, 'id': 'msg_direct'}
        fake.write_text('import json\nprint(' + repr(json.dumps({'ok': True, 'result': {
            'messages': [direct], 'tasks': [{'id': 'task_review', 'spec': 'K1 리뷰'}]}})) + ')\n', encoding='utf-8')
        environment['FULLOPS_ORCA_CLI'] = str(cli)
        assert hook('tool', session_id='direct', tool_input={
            'command': 'orca orchestration check --run run_1 --ack delivery_1'}) == {}
        status = subprocess.run([*script, 'status'], capture_output=True, text=True)
        assert {item['message'] for item in json.loads(status.stdout)['pending']} == {'msg_done', 'msg_direct'}
        assert hook('tool', session_id='task-review', tool_input={'command':
            f'orca orchestration worker-start --run run_2 --task task_review --worktree "{worker}"'}) == {}
        environment.pop('FULLOPS_ORCA_CLI')
        # coordinator 역할 브랜치만 병합해도 main 통합으로 인정하지 않는다.
        git('checkout', '-qb', 'fullops/coor')
        git('merge', '--ff-only', sha)
        assert hook('stop', session_id='coor').get('decision') == 'block'
        git('checkout', '-q', 'main')
        git('merge', '--ff-only', sha)
        assert 'push' in hook('stop', session_id='push')['reason']
        git('push', '-q', 'origin', 'main')
        assert hook('stop', session_id='pushed') == {}
        # 최신 main을 받지 않은 워크트리에는 새 과제를 보내지 않는다.
        (repo / 'new.txt').write_text('next baseline\n')
        commit(repo, 'baseline')
        git('push', '-q', 'origin', 'main')
        route = repo / '.fullops-squad/docs/evaluations/jev/K2-route.json'
        route.parent.mkdir(parents=True, exist_ok=True)
        route.write_text(json.dumps({'route': 'simple', 'role': 'dev'}))
        command = f'orca orchestration worker-start --run run_2 --worktree "{worker}" --spec "K2 작업"'
        denied = hook('tool', session_id='dispatch', tool_input={'command': command})
        assert '동기화' in denied['hookSpecificOutput']['permissionDecisionReason'], denied
        # 차단은 작업 중 파일과 worker HEAD를 변경하지 않는다.
        (worker / 'dirty.txt').write_text('in progress\n')
        old_head = git('rev-parse', 'HEAD', cwd=worker)
        hook('tool', session_id='dirty', tool_input={'command': command})
        assert git('rev-parse', 'HEAD', cwd=worker) == old_head
        assert (worker / 'dirty.txt').read_text() == 'in progress\n'
        git('merge', '--ff-only', 'main', cwd=worker)
        assert hook('tool', session_id='dispatch', tool_input={'command': command}) == {}
        # 로컬 전용 setup도 지원한다. 기본 브랜치 이름을 main으로 가정하지 않는다.
        git('branch', '-m', 'main', 'trunk')
        data.pop('git')
        config.write_text(json.dumps(data), encoding='utf-8')
        status = subprocess.run([*script, 'status'], capture_output=True, text=True)
        assert json.loads(status.stdout)['pending'] == []
        assert hook('tool', session_id='local', tool_input={'command': command}) == {}
    print('PASS: completed SHA merge, base push, durable Stop gate, worker baseline')


if __name__ == '__main__':
    main()
