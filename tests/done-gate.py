"""임시 레포에서 done-gate hook의 세션 범위·차단·통과·재종료 허용·fail-open을 확인한다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-gate-') as tmp:
        repo = Path(tmp)

        def git(*args, cwd=tmp):
            return subprocess.check_output(['git', '-C', cwd, *args], text=True).strip()

        def commit(message):
            git('add', '-A')
            git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', message)
            return git('rev-parse', 'HEAD')

        def hook(mode, session='s1', cwd=tmp, **event):
            done = subprocess.run([sys.executable, str(SCRIPTS / 'done_gate.py'), mode], text=True, capture_output=True,
                                  input=json.dumps({'session_id': session, 'cwd': cwd, **event}))
            assert done.returncode == 0, done.stderr
            return json.loads(done.stdout)

        git('init', '-q', '-b', 'main')
        assert hook('start') == {} and hook('stop') == {}  # FullOps가 아닌 레포
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp, '--roles', 'dev', '--local-only'],
                       check=True, capture_output=True)
        (repo / 'app.py').write_text('x = 1\n')
        base = commit('base')

        brief = hook('start', source='startup')['hookSpecificOutput']
        assert brief['hookEventName'] == 'SessionStart' and 'lint.py' in brief['additionalContext']
        assert hook('start', session='s1', source='resume') == {}  # 시작 지점은 처음 것을 유지한다
        assert hook('stop') == {}  # 변경 없음

        (repo / 'notes.md').write_text('문서만 바꿨다\n')
        assert hook('stop') == {}  # 코드가 아니다
        (repo / 'app.py').write_text('x = 2\n')
        blocked = hook('stop')
        assert blocked['decision'] == 'block' and 'app.py' in blocked['reason'] and '커밋' in blocked['reason']
        assert 'systemMessage' in hook('stop', stop_hook_active=True)  # 아무것도 안 하고 다시 끝내면 통과
        (repo / 'app.py').write_text('x = 3\n')
        assert hook('stop', stop_hook_active=True)['decision'] == 'block'  # 새 변경은 다시 막는다

        head = commit('work')
        assert hook('stop')['decision'] == 'block'  # 이 세션이 만든 커밋
        lint = subprocess.run([sys.executable, str(SCRIPTS / 'lint.py'), '--repo', tmp, '--from', base],
                              capture_output=True, text=True)
        assert lint.returncode == 0, lint.stdout
        assert json.loads((repo / '.git/fullops-gate/pass.json').read_text())['head'] == head
        assert hook('stop') == {}  # 통과 기록이 현재 HEAD와 같다
        (repo / 'app.py').write_text('x = 4\n')
        assert hook('stop')['decision'] == 'block'  # 통과 뒤 미커밋 코드
        git('checkout', '-q', '--', 'app.py')

        # 다른 체크아웃에서 만든 커밋을 fast-forward로 받는 것은 이 세션의 코드 변경이 아니다.
        worker = repo.parent / f'{repo.name}-worker'
        git('worktree', 'add', '-q', '-b', 'fullops/dev-work', str(worker))
        (worker / 'feature.py').write_text('y = 1\n')
        git('add', '-A', cwd=str(worker))
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'worker', cwd=str(worker))
        assert hook('start', session='coord', source='startup')
        git('merge', '-q', '--ff-only', 'fullops/dev-work')
        assert hook('stop', session='coord') == {}
        assert hook('stop', session='before-gate') == {}  # 게이트 도입 전에 시작한 세션
        git('worktree', 'remove', '--force', str(worker))

        broken = subprocess.run([sys.executable, str(SCRIPTS / 'done_gate.py'), 'stop'], text=True,
                                capture_output=True, input='not json', cwd='/')
        assert broken.returncode == 0 and json.loads(broken.stdout) == {}  # fail-open
    print('PASS: done-gate session scope, doc-only allow, block, pass stamp, re-stop allow, ff merge, fail-open')


if __name__ == '__main__':
    main()
