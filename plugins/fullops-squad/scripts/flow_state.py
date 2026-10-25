#!/usr/bin/env python3
"""과제 단위 흐름 상태(docs/flow-graph.md 노드). coordinator hook만 쓰고 모든 워크트리가 Git 공용 디렉터리에서 읽는다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

import harness_gate
import integration
from storage import write_json

# 노드 ID(docs/flow-graph.md 노드: 의도·설계·배정·구현·worker_done·리뷰·병합·검수·완료)와 그 노드에 들어올 때 지난 게이트
NODES = ('intent', 'design', 'assign', 'build', 'report', 'review', 'merge', 'qa', 'done')
REVIEW = re.compile(r'-REVIEW(?:-R\d+)?$', re.I)
GATES = {'design': 'route', 'build': 'dispatch', 'report': 'worker_done', 'review': 'review', 'merge': 'merge'}


def directory(root):
    return integration.directory(root).with_name('fullops-flow')


def read(root):
    folder = directory(root)
    states = []
    for path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        try:
            states.append(json.loads(path.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            continue
    return states


def task_of(root, key):
    """리뷰 키 `K-DEV-REVIEW-R2`는 과제 K의 리뷰다. 차수(rework)로 세지 않고 같은 과제 기록에 묶는다"""
    match = REVIEW.search(key)
    if not match or not match.start():
        return key
    key = key[:match.start()]
    try:
        roles = json.loads((Path(root) / '.fullops-squad/fullops.json').read_text(encoding='utf-8')).get('roles', {})
    except (OSError, ValueError):
        roles = {}
    role = next((r for r in roles if key.upper().endswith('-' + r.upper()) and len(key) > len(r) + 1), None)
    return key[:-len(role) - 1] if role else key


def update(root, key, node, sha=None):
    base = harness_gate.base_key(task_of(root, key))
    path = directory(root) / f'{base}.json'
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {'key': base, 'gates': []}
    if state.get('node') == node and (sha is None or state.get('sha') == sha):
        return
    count, budget = harness_gate.rework(root, base)[:2]
    state.update(node=node, rounds=count, budget=budget,
                 updated=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    if sha:
        state['sha'] = sha
    if GATES[node] not in state['gates']:
        state['gates'].append(GATES[node])
    write_json(path, state)


def observe(root, commands):
    """coordinator가 방금 실행한 명령과 새 완료 보고 기록으로 과제 노드를 옮긴다"""
    for words in commands:
        names = [Path(w.strip('\'"')).name for w in words]
        key = words[words.index('--key') + 1].strip('\'"') if '--key' in words[:-1] else None
        if 'jev_route.py' in names and key and '--model-only' not in words:
            update(root, key, 'design')
        elif 'review.py' in names and key and {'prepare', 'check'} & set(words):
            update(root, key, 'review')
        elif 'worker-start' in words:
            text = ' '.join(words)
            key = integration.dispatch_key(text)
            if key:
                update(root, key, 'review' if re.search(r'\bPurpose\s*[:=]\s*review\b', text, re.I) else 'build')
    folder, marker = integration.directory(root), directory(root) / '.scanned'
    if marker.is_file():
        since = marker.stat().st_mtime
    else:  # 처음에는 지난 완료 보고를 다시 펼치지 않는다
        since = time.time()
    for path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        if path.stat().st_mtime <= since:
            continue
        try:
            item = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if item.get('key') and item.get('sha'):
            update(root, item['key'], 'report', item['sha'])
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    settings = integration.config(root)
    base = integration.references(root, settings)[0]
    for state in read(root):
        if state.get('node') in ('report', 'review') and state.get('sha') and integration.ancestor(root, state['sha'], base):
            update(root, state['key'], 'merge')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    args = parser.parse_args()
    print(json.dumps(read(Path(args.repo).resolve()), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
