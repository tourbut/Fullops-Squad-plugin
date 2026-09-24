#!/usr/bin/env python3
"""원본 체크아웃의 .env* 파일을 워크트리에 심볼릭 링크로 연결한다. git이 추적하는 파일과 이미 있는 파일은 건드리지 않는다.

Orca 설정 스크립트는 워크트리를 만드는 방식에 따라 실행되지 않을 수 있어서, flow-gate SessionStart hook이
워크트리에서 시작하는 모든 세션마다 이 연결을 확인한다. 링크를 만들 수 없으면(Windows 개발자 모드 꺼짐) 복사한다.
"""
import argparse
from pathlib import Path
import shutil
import subprocess


def git(path, *args):
    done = subprocess.run(['git', '-C', str(path), *args], capture_output=True, text=True, encoding='utf-8')
    return done.stdout.strip() if done.returncode == 0 else ''


def main_checkout(worktree):
    """워크트리가 속한 원본(주) 체크아웃 경로. 워크트리가 아니거나 알 수 없으면 None."""
    common = git(worktree, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    top = git(worktree, 'rev-parse', '--show-toplevel')
    if not common or not top:
        return None
    root = Path(common).parent.resolve()
    return root if root != Path(top).resolve() and (root / '.git').exists() else None


def link(worktree):
    """[(파일 이름, 'link' 또는 'copy')]. 원본 체크아웃이 아니면 빈 목록."""
    worktree = Path(worktree).resolve()
    root = main_checkout(worktree)
    if root is None:
        return []
    top = Path(git(worktree, 'rev-parse', '--show-toplevel')).resolve()
    done = []
    for source in sorted(root.glob('.env*')):
        target = top / source.name
        if not source.is_file() or target.exists() or target.is_symlink():
            continue
        if git(root, 'ls-files', '--', source.name):  # .env.example 같은 추적 파일은 git이 옮긴다
            continue
        try:
            target.symlink_to(source)
            done.append((source.name, 'link'))
        except OSError:
            shutil.copy2(source, target)
            done.append((source.name, 'copy'))
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--worktree', action='append', help='연결할 워크트리 경로. 여러 번 줄 수 있다')
    parser.add_argument('--all', metavar='REPO', help='이 레포의 git worktree list 전체에 연결한다')
    args = parser.parse_args()
    targets = list(args.worktree or [])
    if args.all:
        targets += [line[len('worktree '):] for line in git(args.all, 'worktree', 'list', '--porcelain').splitlines()
                    if line.startswith('worktree ')]
    if not targets:
        parser.error('--worktree 또는 --all이 필요합니다')
    for path in targets:
        result = link(path)
        print(f"{path}: {', '.join(f'{name}({how})' for name, how in result) or '변경 없음'}")


if __name__ == '__main__':
    main()
