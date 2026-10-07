#!/usr/bin/env python3
"""완료 보고의 기본 브랜치 병합·원격 반영을 Git 공용 디렉터리에서 추적한다."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import shlex

from done_gate import git
from storage import write_json


def dispatch_key(text):
    """명시 선언, 현재 인박스 또는 spec 첫 단어만 과제 정체성으로 쓴다."""
    named = re.findall(r'\bTask\s+key\s*[:=]?\s*([A-Za-z0-9][A-Za-z0-9._-]*)', text, re.I)
    if named:
        return named[0].rstrip('.') if len(set(named)) == 1 else None
    spec = re.search(r'--spec(?:=|\s+)["\']([^"\']+)', text)
    if spec:
        return re.match(r'[A-Za-z0-9][A-Za-z0-9._-]*', spec.group(1)).group(0) if re.match(r'[A-Za-z0-9]', spec.group(1)) else None
    return None


def orca(*args, cwd=None):
    """공유 읽기 전용 Orca 조회. 실패하면 None을 반환한다."""
    from orca_wait import find_orca
    exe = os.environ.get('FULLOPS_ORCA_CLI') or find_orca() or 'orca'
    try:
        done = subprocess.run([shutil.which(exe) or exe, *args, '--json'], cwd=cwd,
                              capture_output=True, text=True, encoding='utf-8', timeout=15)
        data = json.loads(done.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return data.get('result') if isinstance(data, dict) and data.get('ok') else None


def key_present(key, text):
    # 문장 끝 마침표는 구분자지만 K1.2 같은 실제 키의 일부는 구분자가 아니다.
    return re.search(rf'(?<![A-Za-z0-9._-]){re.escape(key)}(?![A-Za-z0-9_-]|\.[A-Za-z0-9._-])', text)


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
    tasks = {}
    for message in messages:
        if message.get('type') != 'worker_done':
            continue
        body = str(message.get('body') or '')
        if not body and not message.get('id'):
            continue  # peek의 개수 요약은 완료 보고 본문이 아니다.
        identifier = str(message.get('id') or hashlib.sha256(body.encode()).hexdigest())
        path = directory(root) / (hashlib.sha256(identifier.encode()).hexdigest() + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        label = r'(?:SHA|commit|커밋)(?:는|은|:|=)?\s*([0-9a-fA-F]{7,40})(?![0-9a-fA-F])'
        final = re.findall(r'(?:최종(?:\s+로컬)?|final(?:\s+local)?|local)\s+' + label, body, re.I)
        candidates = re.findall(r'(?<![A-Za-z])' + label, body, re.I)
        hashes = set(final or candidates)
        sha = next(iter(hashes)) if len(hashes) == 1 else None
        key = re.search(r'\[(?:완료|설계)\]\s*([A-Za-z0-9][A-Za-z0-9._-]*)', body)
        payload = message.get('payload') or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        task_id = payload.get('taskId')
        task_key = key.group(1) if key else ''
        if not task_key and task_id:
            run = message.get('run_id')
            if run not in tasks:
                listing = orca('orchestration', 'task-list', *(['--run', run] if run else []), cwd=root)
                tasks[run] = (listing or {}).get('tasks') or []
            task = next((t for t in tasks[run] if t.get('id') == task_id), {})
            spec = str(task.get('spec') or '')
            keys = [p.name.removesuffix('-route.json') for p in
                    (Path(root) / '.fullops-squad/docs/evaluations/jev').glob('*-route.json')]
            explicit = re.search(r'\bTask\s+key\s*[:=]?\s*([A-Za-z0-9][A-Za-z0-9._-]*)', spec, re.I)
            named = explicit.group(1).rstrip('.') if explicit else None
            found = [named] if named in keys else [k for k in keys if key_present(k, spec)]
            if len(found) == 1:
                task_key = found[0]
        data = {'message': identifier, 'key': task_key,
                'sha': sha}
        try:
            with path.open('x', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False)
        except FileExistsError:
            saved = json.loads(path.read_text(encoding='utf-8'))
            changed = False
            for field in ('key', 'sha'):
                if not saved.get(field) and data.get(field):
                    saved[field] = data[field]
                    changed = True
            if changed:
                write_json(path, saved)


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
        items = [item for item in items if not item['key'] or item['key'] != dispatch_key(command)]
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
    selector = next(value for value in match.groups() if value is not None)
    if selector.startswith('path:'):
        selector = selector.removeprefix('path:')
    elif selector.startswith('id:') and '::' in selector:
        selector = selector.split('::', 1)[1]
    elif selector == 'active' or selector == 'current' or selector.startswith(('name:', 'branch:')):
        selected = orca('worktree', 'show', '--worktree', selector, cwd=root)
        selector = ((selected or {}).get('worktree') or {}).get('path')
        if not selector:
            return '워크트리 선택자를 확인할 수 없습니다. --worktree path:<실제 경로>를 지정하세요.'
    worker = Path(selector)
    if not worker.is_absolute():
        worker = Path(root) / worker
    settings = config(root)
    try:
        branch = git(worker, 'symbolic-ref', '--short', 'HEAD')
    except subprocess.CalledProcessError:
        branch = None
    purpose = re.search(r'\bPurpose\s*[:=]\s*(implementation|review)\b', command, re.I)
    purpose = purpose.group(1).lower() if purpose else 'implementation'
    if purpose == 'review':
        fields = {}
        for name in ('Review SHA', 'Implementer session', 'Reviewer session'):
            found = re.search(rf'\b{name}\s*[:=]\s*([A-Za-z0-9._-]+)', command, re.I)
            fields[name] = found.group(1) if found else None
        try:
            from review import check_independence
            head = fields['Review SHA']
            if not dispatch_key(command) or not head or not re.fullmatch('[0-9a-f]{40}', head):
                raise ValueError('Task key와 정확한 Review SHA가 필요합니다')
            check_independence(root, {'review_schema_version': 2, 'head': head, 'independence': {
                'snapshot_path': str(worker), 'snapshot_head': head, 'read_only': True,
                'implementer_session': fields['Implementer session'], 'reviewer_session': fields['Reviewer session']}})
            if not ancestor(worker, head, head) or not ancestor(root, head, head):
                raise ValueError('현재 저장소의 commit이 아닙니다')
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            return f'리뷰 snapshot 정체성 확인 실패: {error}'
        return None
    if branch not in settings.get('roles', {}).values():
        return 'implementation은 등록 역할 브랜치의 기존 워크트리를 사용하세요. 리뷰는 Purpose: review와 고정 SHA·독립 세션을 선언하세요.'
    if directory(worker) != directory(root):
        return '등록 역할의 워크트리가 현재 레포와 다릅니다. 실제 워크트리 경로를 확인하세요.'
    try:
        from flow_gate import route_of
        route = route_of(Path(root), dispatch_key(command))
        if route and settings['roles'].get(route['role']) != branch:
            return 'route 담당 역할과 worker 브랜치가 다릅니다. 기존 역할 경로를 선택하거나 근거를 남겨 재분류하세요.'
        packet = Path(root) / f'.fullops-squad/docs/evaluations/jev/{dispatch_key(command)}-packet.json'
        if packet.is_file():
            value = json.loads(packet.read_text(encoding='utf-8'))
            if value.get('version') != 'jev-packet-v1' or value.get('task_key') != dispatch_key(command) or value.get('role') != route['role'] or value.get('head') != git(worker, 'rev-parse', 'HEAD') or not all(c in value.get('categories', {}) for c in ('direct_edit', 'impact_check', 'document_read', 'document_update')):
                return '탐색 패킷의 과제·역할·worker SHA/범주가 다릅니다. 같은 지시서와 대상 SHA에서 jev_packet.py --force로 갱신하세요.'
    except (KeyError, TypeError):
        return '배정 역할을 확인할 수 없습니다'
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
    parser.add_argument('--run', help='누락된 완료 메시지를 다시 조회할 Run')
    parser.add_argument('--terminal', help='완료 메시지를 받은 coordinator 터미널')
    args = parser.parse_args()
    root = Path(git(args.repo, 'rev-parse', '--show-toplevel'))
    if args.action != 'status':
        if not args.message:
            parser.error('--message가 필요합니다')
        path = directory(root) / (hashlib.sha256(args.message.encode()).hexdigest() + '.json')
        if not path.exists():
            flags = [flag for name, value in (('--run', args.run), ('--terminal', args.terminal))
                     if value for flag in (name, value)]
            inbox = orca('orchestration', 'check', *flags, '--peek', cwd=root)
            if inbox:
                record(root, inbox.get('messages') or [])
        if not path.exists():
            parser.error('완료 기록이 없습니다. --run <Run> --terminal <coordinator 핸들>로 다시 조회하세요. '
                         '이미 ACK한 보고는 원본 완료 메시지를 다시 수집한 뒤 재시도하세요.')
        item = json.loads(path.read_text(encoding='utf-8'))
        if args.action == 'hold':
            if not all(value and value.strip() for value in (args.reason, args.owner, args.resume)):
                parser.error('hold에는 --reason, --owner, --resume이 필요합니다')
            item['hold'] = {'reason': args.reason, 'owner': args.owner, 'resume': args.resume}
        else:
            item.pop('hold', None)
        write_json(path, item)
    print(json.dumps({'pending': pending(root)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
