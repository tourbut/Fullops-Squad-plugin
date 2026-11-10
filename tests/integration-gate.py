"""완료 보고 수신부터 기본 브랜치 병합·push·다음 배정의 최신 기준까지 확인한다."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/fullops-squad/scripts'


def main():
    sys.path.insert(0, str(SCRIPTS))
    import integration
    # dispatch_spec가 정리한 키 앞에 원래 spec('… Task key: K1.')을 붙여도 같은 키다
    assert integration.dispatch_key('Task key: K1 Implement the form. Task key: K1.') == 'K1'
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
        route.write_text(json.dumps({'version': 'jev-route-v3', 'task_key': 'K1', 'route': 'simple', 'role': 'dev'}))
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
        route.write_text(json.dumps({'version': 'jev-route-v3', 'task_key': 'K2', 'route': 'simple', 'role': 'dev'}))
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
        # 경계 알림(docs/flow-graph.md E7·E11): 형식 누락, lint 통과 뒤 코드 변경, 보고 SHA 뒤 커밋까지 병합. 막지 않는다
        (worker / 'a.py').write_text('a = 1\n')
        linted = commit(worker, 'a')
        gate = Path(git('rev-parse', '--absolute-git-dir', cwd=worker)) / 'fullops-gate'
        gate.mkdir(exist_ok=True)
        (gate / 'pass.json').write_text(json.dumps({'head': linted}))
        (worker / 'b.py').write_text('b = 1\n')
        reported = commit(worker, 'b')
        fake.write_text('import json\nprint(' + repr(json.dumps({'ok': True, 'result': {'messages': [
            {'id': 'msg_k3', 'type': 'worker_done', 'body': f'[완료] K3 | 브랜치 fullops/dev | SHA {reported}'},
            {'id': 'msg_free', 'type': 'worker_done', 'body': 'K4 끝났습니다'}]}})) + ')\n', encoding='utf-8')
        subprocess.run([sys.executable, str(SCRIPTS / 'orca_wait.py'), '--repo', str(repo), '--orca', str(cli),
                        '--run', 'run_3'], check=True, capture_output=True)
        note = hook('post', session_id='notes', tool_input={'command': 'orca orchestration check --run run_3'})
        note = note['hookSpecificOutput']['additionalContext']
        assert f'lint 통과 HEAD {linted[:12]}' in note and 'b.py' in note and '형식이 아닙니다' in note, note
        assert 'K1' not in note  # 형식을 지킨 보고는 알리지 않는다
        assert hook('post', session_id='notes2', tool_input={'command': 'git status'}) == {}  # 한 번만 알린다
        (worker / 'c.py').write_text('c = 1\n')
        extra = commit(worker, 'c')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'merge', '-q', '--no-ff', '-m', 'merge dev', 'fullops/dev')
        drift = hook('post', session_id='merge', tool_input={'command': 'git merge --no-ff fullops/dev'})
        drift = drift['hookSpecificOutput']['additionalContext']
        assert f'{extra[:12]}는 리뷰·완료 보고 SHA가 아닙니다' in drift and f'{reported[:12]} 뒤의 커밋 1개' in drift, drift
        # coordinator가 자기 워크트리에서 원본 체크아웃으로 옮겨(`cd`·Set-Location) 병합해도 같은 위치를 본다
        coor = root / 'coor'
        git('worktree', 'add', '-q', '-b', 'coor-session', str(coor))
        for moved in (f'cd "{repo}" && git merge --no-ff fullops/dev', f'Set-Location -Path "{repo}"; git merge --no-ff fullops/dev'):
            note = hook('post', cwd=str(coor), session_id=moved[:2], tool_input={'command': moved})
            assert f'{reported[:12]} 뒤의 커밋 1개' in note['hookSpecificOutput']['additionalContext'], (moved, note)
        assert hook('post', cwd=str(coor), session_id='stay', tool_input={'command': 'git merge --no-ff fullops/dev'}) == {}
        git('worktree', 'remove', '--force', str(coor))
        git('reset', '-q', '--keep', 'HEAD~1')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'merge', '-q', '--no-ff', '-m', 'merge dev', reported)
        assert hook('post', session_id='merge2', tool_input={'command': f'git merge --no-ff {reported}'}) == {}
        # 본문에서 SHA를 읽지 못한 보고는 hold 없이 SHA를 직접 기록한다. 없는 커밋은 받지 않는다
        bad = subprocess.run([*script, 'set-sha', '--message', 'msg_free', '--sha', '0' * 40], capture_output=True, text=True, encoding='utf-8')
        assert bad.returncode == 2 and '이 저장소의 커밋이 아닙니다' in bad.stderr, bad.stderr
        fixed = subprocess.run([*script, 'set-sha', '--message', 'msg_free', '--sha', reported[:12], '--key', 'FREE-1'],
                               check=True, capture_output=True, text=True, encoding='utf-8')
        assert not any(item['message'] == 'msg_free' and item['action'] == '병합' for item in json.loads(fixed.stdout)['pending'])
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'merge', '-q', '-m', 'sync', 'main', cwd=worker)
        # 로컬 전용 setup도 지원한다. 기본 브랜치 이름을 main으로 가정하지 않는다.
        git('branch', '-m', 'main', 'trunk')
        data.pop('git')
        config.write_text(json.dumps(data), encoding='utf-8')
        status = subprocess.run([*script, 'status'], capture_output=True, text=True)
        assert json.loads(status.stdout)['pending'] == []
        assert hook('tool', session_id='local', tool_input={'command': command}) == {}
    print('PASS: completed SHA merge, base push, durable Stop gate, worker baseline')


def concurrent_record():
    """orca_wait를 동시에 실행해도 빈 파일을 읽어 죽지 않고, 이전 버전이 남긴 빈 기록은 다시 쓴다(#112)."""
    sys.path.insert(0, str(SCRIPTS))
    import integration
    with tempfile.TemporaryDirectory(prefix='fullops-record-') as tmp:
        repo = Path(tmp)
        subprocess.run(['git', 'init', '-q', tmp], check=True)
        (repo / '.fullops-squad').mkdir()
        (repo / '.fullops-squad/fullops.json').write_text('{}', encoding='utf-8')
        messages = [{'type': 'worker_done', 'id': f'm{n}', 'body': f'[완료] K{n} | 브랜치 fullops/dev | SHA abcdef{n}'} for n in range(4)]
        empty = integration.directory(repo) / (hashlib.sha256(b'm0').hexdigest() + '.json')
        empty.parent.mkdir(parents=True)
        empty.write_text('', encoding='utf-8')
        with ThreadPoolExecutor(8) as pool:
            list(pool.map(lambda _: integration.record(repo, messages), range(8)))
        for n, message in enumerate(messages):
            saved = json.loads((empty.parent / (hashlib.sha256(message['id'].encode()).hexdigest() + '.json')).read_text(encoding='utf-8'))
            assert saved['key'] == f'K{n}' and saved['sha'] == f'abcdef{n}', saved


def review_report_not_merged():
    """리뷰어의 worker_done은 병합 대상이 아니다. Purpose는 task spec에 있고 spec은 --full일 때만 온다(Orca 1.4.251)."""
    sys.path.insert(0, str(SCRIPTS))
    import integration
    with tempfile.TemporaryDirectory(prefix='fullops-review-report-') as tmp:
        repo = Path(tmp)
        subprocess.run(['git', 'init', '-q', tmp], check=True)
        (repo / '.fullops-squad').mkdir()
        (repo / '.fullops-squad/fullops.json').write_text('{}', encoding='utf-8')

        def tasks(*args, **_):
            spec = {'spec': 'Task key: K1; Purpose: review'} if '--full' in args else {'title': 'x'}
            return {'tasks': [{'id': 'task_1', 'status': 'completed', **spec}]}
        message = {'type': 'worker_done', 'id': 'm1', 'run_id': 'run_1', 'payload': {'taskId': 'task_1'},
                   'body': '[완료] K1 | 브랜치 detached | SHA abcdef1'}
        with patch.object(integration, 'orca', side_effect=tasks):
            integration.record(repo, [message])
        assert not list(integration.directory(repo).glob('*.json'))


def published_holds():
    """coordinator가 역할 워크트리에서 병합·push하면 원본 체크아웃의 로컬 main은 뒤처진다. 원격 ref에 들어간 보류는 풀고 사유를 남긴다"""
    sys.path.insert(0, str(SCRIPTS))
    import integration
    with tempfile.TemporaryDirectory(prefix='fullops-published-') as tmp:
        repo = Path(tmp)

        def git(*args):
            return subprocess.check_output(['git', '-C', str(repo), *args], text=True, stderr=subprocess.DEVNULL).strip()

        def commit(message):
            git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q', '--allow-empty', '-m', message)
            return git('rev-parse', 'HEAD')
        git('init', '-q', '-b', 'main')
        (repo / '.fullops-squad').mkdir()
        (repo / '.fullops-squad/fullops.json').write_text(json.dumps(
            {'roles': {'dev': 'fullops/dev'}, 'git': {'remote': 'origin', 'base': 'main'}}), encoding='utf-8')
        commit('setup')
        git('checkout', '-qb', 'side')
        unmerged = commit('unmerged')
        git('checkout', '-q', 'main')
        git('checkout', '-qb', 'work')
        merged = [commit(f'c{n}') for n in range(11)]
        git('checkout', '-q', 'main')  # 로컬 main은 setup에 머문다
        git('update-ref', 'refs/remotes/origin/main', merged[9])  # c10은 원격에도 없다
        shas = [unmerged, *merged]
        integration.record(repo, [{'id': f'm{n}', 'type': 'worker_done', 'body': f'[완료] K{n} | 브랜치 fullops/dev | SHA {sha}'}
                                  for n, sha in enumerate(shas)])
        paths = [integration.directory(repo) / (hashlib.sha256(f'm{n}'.encode()).hexdigest() + '.json') for n in range(len(shas))]
        for n, path in enumerate(paths[:11]):  # 병합 전 보류가 가장 오래됐다
            item = json.loads(path.read_text(encoding='utf-8'))
            path.write_text(json.dumps({**item, 'hold': {'reason': f'r{n}', 'owner': 'coor', 'resume': 'x'}}), encoding='utf-8')
            os.utime(path, (1000 + n, 1000 + n))
        assert [item['key'] for item in integration.pending(repo)] == ['K11']  # 원격에도 로컬 main에도 없다

        def load(n):
            return json.loads(paths[n].read_text(encoding='utf-8'))
        released = [n for n in range(11) if load(n).get('integrated')]
        assert released == [1, 2, 3, 4], released  # 한 호출에 HOLD_CAP개만 본다
        integration.pending(repo)  # 다음 호출은 병합 전 보류에 막히지 않고 이어서 본다
        released = [n for n in range(11) if load(n).get('integrated')]
        assert released == list(range(1, 10)), released
        assert load(1)['released_hold']['reason'] == 'r1' and 'hold' not in load(1)
        assert load(0)['hold'] and not load(0).get('integrated')
        done = subprocess.run([sys.executable, str(SCRIPTS / 'integration.py'), '--repo', str(repo), 'settle'],
                              capture_output=True, text=True, check=True)
        assert json.loads(done.stdout) == {'released': 1}, done.stdout
        assert all(load(n).get('integrated') for n in range(1, 11)) and load(0)['hold']
        git('checkout', '-qb', 'temp')
        denied = integration.baseline_denial(repo, f'orca orchestration worker-start --worktree "{repo}" --spec "Task key: K9"')
        assert '별도 워크트리를 만들지 마세요' in denied, denied


if __name__ == '__main__':
    published_holds()
    review_report_not_merged()
    concurrent_record()
    main()
