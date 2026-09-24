"""임시 레포에서 워크트리 .env 연결(추적 파일·기존 파일 보존, 원본 체크아웃 무시)과 SessionStart hook 자동 연결을 확인한다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import env_link  # noqa: E402


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-env-') as tmp:
        base = Path(tmp)
        repo, wt1, wt2 = base / 'main', base / 'wt-dev', base / 'wt-art'
        repo.mkdir()

        def git(*args, cwd=repo):
            return subprocess.check_output(['git', '-C', str(cwd), *args], text=True, encoding='utf-8').strip()

        git('init', '-q', '-b', 'main')
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', str(repo), '--roles', 'dev', 'art', '--local-only'],
                       check=True, capture_output=True)
        (repo / '.gitignore').write_text('.env\n.env.local\n', encoding='utf-8')
        (repo / '.env.example').write_text('KEY=\n', encoding='utf-8')
        git('add', '-A')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'setup')
        (repo / '.env').write_text('KEY=1\n', encoding='utf-8')
        (repo / '.env.local').write_text('LOCAL=1\n', encoding='utf-8')
        git('worktree', 'add', '-q', '-b', 'fullops/dev', str(wt1))
        git('worktree', 'add', '-q', '-b', 'fullops/art', str(wt2))

        assert env_link.link(repo) == []  # 원본 체크아웃은 대상이 아니다
        assert env_link.main_checkout(wt1) == repo.resolve()
        (wt1 / '.env.local').write_text('MINE=1\n', encoding='utf-8')  # 이미 있는 파일은 보존
        result = env_link.link(wt1)
        assert [name for name, _ in result] == ['.env'], result
        assert (wt1 / '.env').read_text(encoding='utf-8') == 'KEY=1\n'
        assert (wt1 / '.env.local').read_text(encoding='utf-8') == 'MINE=1\n'
        assert (wt1 / '.env.example').read_text(encoding='utf-8') == 'KEY=\n' and not (wt1 / '.env.example').is_symlink()
        assert env_link.link(wt1) == []  # 다시 실행해도 바뀌지 않는다
        assert '.env' not in git('status', '--porcelain', cwd=wt1)  # gitignore 대상이라 변경으로 보이지 않는다

        # SessionStart hook이 워크트리에서 시작하는 세션마다 연결한다
        done = subprocess.run([sys.executable, str(SCRIPTS / 'flow_gate.py'), 'start'], capture_output=True, text=True,
                              encoding='utf-8', input=json.dumps({'session_id': 's', 'cwd': str(wt2), 'source': 'startup'}))
        brief = json.loads(done.stdout)['hookSpecificOutput']['additionalContext']
        assert '.env, .env.local' in brief and (wt2 / '.env').is_file() and (wt2 / '.env.local').is_file(), brief

        # CLI --all은 모든 워크트리를 처리한다
        (wt1 / '.env').unlink()
        out = subprocess.run([sys.executable, str(SCRIPTS / 'env_link.py'), '--all', str(repo)], capture_output=True,
                             text=True, encoding='utf-8')
        assert out.returncode == 0 and (wt1 / '.env').is_file() and '변경 없음' in out.stdout, out.stdout
    print('PASS: env link into worktrees, keeps tracked/existing files, skips main checkout, SessionStart auto-link, --all CLI')


if __name__ == '__main__':
    main()
