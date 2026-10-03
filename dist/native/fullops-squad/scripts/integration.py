#!/usr/bin/env python3
"""완료 보고의 기본 브랜치 병합·원격 반영을 Git 공용 디렉터리에서 추적한다."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from done_gate import git


def config(root):
    path = Path(root) / '.fullops-squad/fullops.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def directory(root):
    common = Path(git(root, 'rev-parse', '--git-common-dir'))
    return (common if common.is_absolute() else Path(root) / common).resolve() / 'fullops-integration'


def record(root, messages):
    """ACK 전에 저장한다. 메시지별 파일로 워크트리·세션 사이의 상태를 보존한다."""
    if config(root) is None:
        return
    for message in messages:
        if message.get('type') != 'worker_done':
            continue
        body = str(message.get('body') or '')
        if not body and not message.get('id'):
            continue  # peek의 개수 요약은 완료 보고 본문이 아니다.
        identifier = str(message.get('id') or hashlib.sha256(body.encode()).hexdigest())
        path = directory(root) / (hashlib.sha256(identifier.encode()).hexdigest() + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        sha = re.search(r'\bSHA\s*[:=]?\s*([0-9a-fA-F]{7,40})\b', body)
        key = re.search(r'\[(?:완료|설계)\]\s*([A-Za-z0-9][A-Za-z0-9._-]*)', body)
        data = {'message': identifier, 'key': key.group(1) if key else '',
                'sha': sha.group(1) if sha else None}
        try:
            with path.open('x', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False)
        except FileExistsError:
            pass  # 재전달은 기존 보류 기록을 덮어쓰지 않는다.


def ancestor(root, source, target):
    return subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', source, target],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def references(root, settings):
    connection = settings.get('git') or {}
    if connection:
        base = 'refs/heads/' + connection['base']
        return base, f'refs/remotes/{connection["remote"]}/{connection["base"]}'
    # 로컬 전용 setup에는 git.base가 없다. 원본 체크아웃의 브랜치를 기준으로 사용한다.
    primary = git(root, 'worktree', 'list', '--porcelain').split('\n\n', 1)[0]
    branch = next((line.removeprefix('branch ') for line in primary.splitlines() if line.startswith('branch ')), None)
    if not branch:
        raise ValueError('로컬 전용 레포의 원본 체크아웃에 기본 브랜치가 필요합니다')
    return branch, None


def pending(root):
    settings = config(root)
    if settings is None:
        return []
    base, published = references(root, settings)
    result = []
    for path in sorted(directory(root).glob('*.json')):
        item = json.loads(path.read_text(encoding='utf-8'))
        if item.get('hold'):
            continue
        sha = item.get('sha')
        if not sha or not ancestor(root, sha, base):
            result.append({**item, 'action': '병합', 'base': base})
        elif published and not ancestor(root, sha, published):
            result.append({**item, 'action': 'push', 'base': base})
    return result


def denial(root, command=None):
    items = pending(root)
    if command is not None:
        # 같은 과제의 리뷰·수정 배정은 통합 선행 조건을 해결한다.
        items = [item for item in items if not item['key'] or not re.search(
            rf'(?<![A-Za-z0-9._-]){re.escape(item["key"])}(?![A-Za-z0-9._-])', command)]
    if not items:
        return None
    labels = ', '.join(f'{item["key"] or item["message"]}: {item["action"]}' for item in items[:5])
    return (f'완료 결과의 기본 브랜치 통합이 남아 있습니다({labels}). fullops-orca의 merge 절차대로 '
            '현재 SHA를 리뷰하고 기본 브랜치에 병합·push하세요. 역할 브랜치 push만으로 완료되지 않습니다. '
            '실패·검수 대기·사용자 제한이면 integration.py hold에 사유·담당·재개 조건을 기록하세요.')


def baseline_denial(root, command):
    match = re.search(r'--worktree(?:=|\s+)(?:"([^"]+)"|\'([^\']+)\'|(\S+))', command)
    if not match:
        return '`worker-start`에 --worktree <실제 워크트리 경로>를 넣어 최신 기본 브랜치 동기화를 확인하세요.'
    worker = Path(next(value for value in match.groups() if value is not None))
    if not worker.is_absolute():
        worker = Path(root) / worker
    settings = config(root)
    try:
        branch = git(worker, 'symbolic-ref', '--short', 'HEAD')
    except subprocess.CalledProcessError:
        # detached HEAD는 고정 SHA 리뷰에 사용한다. 경로 자체는 유효한 Git 레포여야 한다.
        try:
            git(worker, 'rev-parse', 'HEAD')
        except subprocess.CalledProcessError:
            return '실제 Git 워크트리 경로를 --worktree에 지정하세요.'
        return None
    if branch not in settings.get('roles', {}).values():
        return None  # 읽기 전용 고정 SHA 리뷰 snapshot은 동기화 대상이 아니다.
    if directory(worker) != directory(root):
        return '등록 역할의 워크트리가 현재 레포와 다릅니다. 실제 워크트리 경로를 확인하세요.'
    base, published = references(root, settings)
    sources = [base]
    if published:
        sources.append(published)
    if any(not ancestor(root, source, branch) for source in sources):
        return (f'{branch}에 최신 기본 브랜치가 없습니다. worker가 작업을 끝내고 작업 트리가 깨끗해지면 '
                '기본 브랜치를 merge 또는 fast-forward로 동기화한 뒤 dispatch하세요. 진행 중 작업은 보존하세요.')
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    parser.add_argument('action', choices=['status', 'hold', 'resume'])
    parser.add_argument('--message')
    parser.add_argument('--reason')
    parser.add_argument('--owner')
    parser.add_argument('--resume')
    args = parser.parse_args()
    root = Path(git(args.repo, 'rev-parse', '--show-toplevel'))
    if args.action != 'status':
        if not args.message:
            parser.error('--message가 필요합니다')
        path = directory(root) / (hashlib.sha256(args.message.encode()).hexdigest() + '.json')
        item = json.loads(path.read_text(encoding='utf-8'))
        if args.action == 'hold':
            if not all(value and value.strip() for value in (args.reason, args.owner, args.resume)):
                parser.error('hold에는 --reason, --owner, --resume이 필요합니다')
            item['hold'] = {'reason': args.reason, 'owner': args.owner, 'resume': args.resume}
        else:
            item.pop('hold', None)
        path.write_text(json.dumps(item, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'pending': pending(root)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
