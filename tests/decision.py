#!/usr/bin/env python3
"""사용자 결정 기록: 번호 부여, 닫기, 워크트리 사이 공유, 잘못된 입력."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/fullops-squad/scripts/decision.py'


def git(cwd, *args):
    subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True)


def run(cwd, *args, ok=True):
    done = subprocess.run([sys.executable, str(SCRIPT), *args, '--repo', str(cwd)], text=True,
                          capture_output=True, encoding='utf-8')
    assert (done.returncode == 0) == ok, done.stderr
    return json.loads(done.stdout) if ok else done.stderr


with tempfile.TemporaryDirectory() as directory:
    repo = Path(directory) / 'repo'
    repo.mkdir()
    git(repo, 'init', '-q')
    git(repo, '-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q', '--allow-empty', '-m', 'init')
    tree = Path(directory) / 'coor-tree'
    git(repo, 'worktree', 'add', '-q', str(tree))

    first = run(repo, 'add', '--question', 'DB를 바꿀까요?', '--key', 'K1', '--option', '예', '--option', '아니오')
    second = run(tree, 'add', '--question', '배포 창은 언제?', '--blocks', 'dev K2 question m-7')
    assert (first['id'], second['id']) == ('D001', 'D002')
    assert first['options'] == ['예', '아니오'] and second['blocks'] == 'dev K2 question m-7'

    # 다른 워크트리(새 세션)에서도 같은 기록을 읽는다
    assert [d['id'] for d in run(tree, 'list')['decisions']] == ['D001', 'D002']
    assert run(tree, 'answer', '--id', 'D001', '--answer', '예')['decided_by'] == 'user'
    assert run(repo, 'drop', '--id', 'D002', '--reason', '범위에서 뺌')['status'] == 'dropped'
    assert run(repo, 'list')['decisions'] == []
    assert [d['status'] for d in run(repo, 'list', '--all')['decisions']] == ['answered', 'dropped']

    assert '이미 answered' in run(repo, 'answer', '--id', 'D001', '--answer', '아니오', ok=False)
    assert '없습니다' in run(repo, 'answer', '--id', '../x', '--answer', 'a', ok=False)
    assert '--question' in run(repo, 'add', '--question', '  ', ok=False)
    assert run(repo, 'add', '--question', '다음 결정')['id'] == 'D003'

print('PASS: decision ledger numbers, closes, shares across worktrees and rejects bad input')
