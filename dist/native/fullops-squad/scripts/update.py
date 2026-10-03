#!/usr/bin/env python3
"""기존 설치와 레포 적용 버전 이후의 릴리스 및 적용 절차를 출력한다. 레포는 수정하지 않는다."""
import argparse
import json
from pathlib import Path
import re
import subprocess

PLUGIN = Path(__file__).resolve().parents[1]


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError(f'지원하지 않는 릴리스 버전: {value!r}')
    return tuple(map(int, value.split('.')))


def plan(repo, previous=None, plugin=PLUGIN):
    repo = Path(repo).expanduser().resolve(strict=True)
    root = Path(subprocess.check_output(
        ['git', '-C', str(repo), 'rev-parse', '--show-toplevel'], text=True).strip()).resolve()
    if repo != root:
        raise ValueError(f'레포 루트를 지정하세요: {root}')
    marker = repo / '.fullops-squad/fullops.json'
    if marker.is_symlink() or marker.parent.is_symlink():
        raise ValueError('심볼릭 링크 설정은 사용하지 않습니다')
    if not marker.is_file():
        raise ValueError('활성 FullOps 레포가 아닙니다. 신규 레포는 setup-fullops를 사용하세요')
    config = json.loads(marker.read_text(encoding='utf-8'))
    if not isinstance(config, dict) or config.get('schema_version') != 1:
        raise ValueError('지원하지 않는 FullOps 설정 버전')
    applied = config.get('plugin_version')
    target = json.loads((plugin / 'plugin.json').read_text(encoding='utf-8'))['version']
    baseline = min([applied] + ([previous] if previous is not None else []), key=version)
    if any(version(v) > version(target) for v in [applied, previous or applied]):
        raise ValueError('설치 또는 레포 적용 버전이 대상보다 높습니다. 다운그레이드는 자동 적용하지 않습니다')
    releases = plugin / 'releases'
    if not releases.is_dir():
        releases = plugin.parents[1] / 'docs/releases'  # 개발 체크아웃
    if not (releases / f'{target}.md').is_file():
        raise ValueError(f'대상 릴리스 노트가 없습니다: {target}')
    notes = []
    for file in sorted(releases.glob('*.md'), key=lambda p: version(p.stem)):
        if version(baseline) < version(file.stem) <= version(target):
            notes.append({'version': file.stem, 'path': str(file.resolve()),
                          'content': file.read_text(encoding='utf-8')})
    return {
        'previous_installed_version': previous,
        'installed_version': target,
        'repo_applied_version': applied,
        'baseline': baseline,
        'releases': notes,
        'steps': [
            '기존 변경·역할·진행 중 작업과 이전 업데이트의 보류 항목을 확인하고 보존한다.',
            '출력된 릴리스를 오래된 순서로 읽고 기존 레포 적용 항목을 적용·해당 없음·보류로 분류한다.',
            '새 setup을 기존 역할로 dry-run하고 없는 파일만 추가한다. 기존 문서는 템플릿과 비교해 필요한 절을 통합한다.',
            '해당되는 운영 문서·규칙·후속 지시서를 반영하고 변경에 맞는 검증을 실행한다.',
            '릴리스별 적용 근거와 해당 없음 사유, 보류 담당·재개 조건을 업데이트 기록에 남긴다.',
            '필수 레포 적용이 완료된 경우에만 fullops.json의 plugin_version을 설치 버전으로 갱신한다.',
            '준비 커밋을 확보하고 허가된 깨끗한 유휴 워크트리에 전달한다. 진행 중 워크트리는 동기화를 예약한다.',
            '적용 버전·변경 문서·검증·보류 사항을 보고하고 다음 개발은 새 세션에서 진행한다.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--from', dest='previous', help='업데이트 전에 확인한 실제 설치 버전')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        result = plan(args.repo, args.previous)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"설치 버전: {result['previous_installed_version'] or '미확인'} → {result['installed_version']}")
    print(f"레포 적용 버전: {result['repo_applied_version']} / 적용 기준: {result['baseline']}")
    for note in result['releases']:
        print(f"\n릴리스 {note['version']} / {note['path']}\n{note['content']}")
    if not result['releases']:
        print('이후 릴리스 없음. 보류된 적용·동기화 기록을 확인하세요.')
    print('\n수행할 내용:')
    for index, step in enumerate(result['steps'], 1):
        print(f'{index}. {step}')


if __name__ == '__main__':
    main()
