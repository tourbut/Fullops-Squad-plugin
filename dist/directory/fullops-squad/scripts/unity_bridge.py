#!/usr/bin/env python3
"""게임 레포의 Unity 프로젝트에 Jev 조작 브리지(com.fullops.jevplay)를 embedded package로 설치·갱신한다.

브리지의 정본은 이 플러그인이다. 게임 레포에는 Packages/com.fullops.jevplay/ 복사본과 게임별 설정
`.fullops-squad/test/unity-play.json`만 둔다. manifest는 고치지 않는다(Packages/ 아래 폴더는 Unity가 자동으로 읽는다).
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

PLUGIN = Path(__file__).resolve().parents[1]
PACKAGE = PLUGIN / 'assets/unity/com.fullops.jevplay'
TEMPLATE = PLUGIN / 'assets/unity/unity-play.json'
NAME = 'com.fullops.jevplay'
CONFIG = '.fullops-squad/test/unity-play.json'


def projects(repo):
    """레포 안의 Unity 프로젝트(ProjectSettings/ProjectVersion.txt가 있는 폴더). Library 등 생성 폴더는 건너뛴다."""
    skip = {'Library', 'Temp', 'Logs', 'node_modules', '.git', 'builds', 'Builds'}
    found = []

    def walk(folder, depth):
        if (folder / 'ProjectSettings/ProjectVersion.txt').is_file():
            found.append(folder)
            return
        if depth < 4:
            for child in sorted(p for p in folder.iterdir() if p.is_dir() and p.name not in skip and not p.is_symlink()):
                walk(child, depth + 1)
    walk(repo, 0)
    return found


def version(package):
    try:
        data = json.loads((package / 'package.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data.get('version') if data.get('name') == NAME else None


def install(repo, project=None, dry_run=False):
    repo = Path(repo).resolve()
    if not (repo / '.fullops-squad/fullops.json').is_file():
        raise ValueError('FullOps setup이 된 레포 루트를 지정하세요')
    candidates = [Path(project).resolve()] if project else projects(repo)
    if len(candidates) != 1:
        raise ValueError('Unity 프로젝트를 하나로 정할 수 없습니다. --project로 지정하세요: '
                         + (', '.join(str(p.relative_to(repo)) for p in candidates) or '없음'))
    target = candidates[0] / 'Packages' / NAME
    if target.is_symlink() or (target.exists() and version(target) is None):
        raise ValueError(f'{target}는 FullOps 브리지가 아닙니다. 덮어쓰지 않습니다')
    before, after = version(target), version(PACKAGE)
    changes = []
    if before != after or not target.exists():
        changes.append(f"{target.relative_to(repo).as_posix()} {before or '없음'} → {after}")
        if not dry_run:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(PACKAGE, target)
    config = repo / CONFIG
    if not config.exists():
        changes.append(f'{CONFIG} 템플릿 생성 (게임에 맞게 고쳐야 함)')
        if not dry_run:
            config.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(TEMPLATE, config)
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['install', 'check'])
    parser.add_argument('--repo', required=True, help='FullOps가 활성화된 게임 레포 루트')
    parser.add_argument('--project', help='Unity 프로젝트 폴더(레포에 여러 개일 때)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        changes = install(args.repo, args.project, dry_run=args.dry_run or args.command == 'check')
    except ValueError as error:
        parser.exit(2, f'{error}\n')
    if args.command == 'check':
        print('\n'.join(['갱신 필요:', *changes]) if changes else '브리지 최신')
        sys.exit(1 if changes else 0)
    print('\n'.join(changes) if changes else '변경 없음')


if __name__ == '__main__':
    main()
