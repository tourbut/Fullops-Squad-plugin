"""임시 신뢰 목록으로 grok 신뢰 확인·추가(워크트리→원본 경로, 기존 항목 보존, 상위 폴더 신뢰, 중복 없음)를 확인한다."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-grok-') as tmp:
        base = Path(tmp)
        repo, wt = base / 'main', base / 'wt-ops'
        repo.mkdir()
        store = base / 'trusted_folders.toml'
        store.write_text("[folders.'C:\\other']\ntrusted = true\ndecided_at = 1\n", encoding='utf-8')
        env = {**os.environ, 'FULLOPS_GROK_TRUST_FILE': str(store)}

        def git(*args):
            subprocess.check_output(['git', '-C', str(repo), *args], text=True)

        git('init', '-q', '-b', 'main')
        (repo / 'a.txt').write_text('a\n', encoding='utf-8')
        git('add', '-A')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'init')
        git('worktree', 'add', '-q', '-b', 'fullops/ops', str(wt))

        def run(*args):
            return subprocess.run([sys.executable, str(SCRIPTS / 'grok_trust.py'), *args], capture_output=True, text=True,
                                  encoding='utf-8', env=env)

        check = run('--repo', str(wt), '--check')
        assert check.returncode == 1 and str(repo.resolve()) in check.stdout, check.stdout  # 워크트리는 원본 경로로 판단
        added = run('--repo', str(wt), '--add')
        assert added.returncode == 0 and '추가' in added.stdout, added.stdout
        text = store.read_text(encoding='utf-8')
        assert text.startswith("[folders.'C:\\other']") and f"[folders.'{repo.resolve()}']\ntrusted = true" in text, text
        assert run('--repo', str(repo), '--check').returncode == 0 and run('--repo', str(wt), '--check').returncode == 0
        assert '이미 됨' in run('--repo', str(wt), '--add').stdout and store.read_text(encoding='utf-8') == text  # 중복 없음

        # 상위 폴더가 신뢰돼 있으면 하위 레포도 신뢰된 것으로 본다. trusted = false는 신뢰가 아니다
        store.write_text(f"[folders.'{base.resolve()}']\ntrusted = true\n", encoding='utf-8')
        assert run('--repo', str(wt), '--check').returncode == 0
        store.write_text(f"[folders.'{repo.resolve()}']\ntrusted = false\n", encoding='utf-8')
        assert run('--repo', str(wt), '--check').returncode == 1
    print('PASS: grok trust check/add via main checkout, keeps entries, parent trust, no duplicates, false is untrusted')


if __name__ == '__main__':
    main()
