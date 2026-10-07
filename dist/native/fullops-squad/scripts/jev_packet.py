#!/usr/bin/env python3
"""기존 route/find/context를 실제 검색 근거와 연결해 인박스로 전달한다. 모델 점수는 수락 게이트가 아니다."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess

from board import deliverables
from jev_find import code_map, git, result_path, MAX_BLOB
from jev_observe import local_file, REQUIRED, digest, safe_text
from work import active_repo, instruction, input_identity, previous_result, save_result, task_excerpt, KEY
from storage import atomic_write

CATEGORIES = ('direct_edit', 'impact_check', 'document_read', 'document_update')


def evaluate(result, labels=None):
    if labels is None:
        return {'status': 'not_run', 'reason': 'explicit expected read/impact/update labels unavailable'}
    if not isinstance(labels, dict) or set(labels) != set(CATEGORIES) or any(
            not isinstance(paths, list) or any(not isinstance(p, str) for p in paths) for paths in labels.values()):
        raise ValueError('labels must name expected paths for each of the four categories')
    metrics = {}
    for category in CATEGORIES:
        expected, selected = set(labels[category]), set(result['categories'][category])
        hits = selected & expected
        metrics[category] = {'expected': sorted(expected), 'selected': sorted(selected), 'hits': sorted(hits),
            'missed': sorted(expected - selected), 'extra': sorted(selected - expected),
            'recall': len(hits) / len(expected) if expected else None, 'precision': len(hits) / len(selected) if selected else None}
    return {'status': 'evaluated', 'head': result['head'], 'input_sha256': result['input_sha256'],
            'metric': 'explicit labels; independent of changed-file overlap', 'categories': metrics}


def packet(repo, role, key, seeds=(), required=(), updates=(), decisions=()):
    inbox, text = instruction(repo, role, key)
    text = re.sub(r'<!-- fullops-packet:start -->[\s\S]*?<!-- fullops-packet:end -->\n*', '', text)
    head = git(repo, 'rev-parse', 'HEAD')
    sources, unknown, entries = {}, [], {}
    for suffix in ('route', 'find', 'documents-find', 'context'):
        path = result_path(repo, key, suffix)
        if path.is_file():
            data = json.loads(path.read_text(encoding='utf-8'))
            if data.get('task_key') != key or data.get('head', head) != head or data.get('role', role) != role:
                unknown.append({'source': suffix, 'reason': 'task/role/SHA differs; regenerate'})
            else:
                sources[suffix] = data
    direct = set(seeds) | {c['path'] for c in sources.get('find', {}).get('candidates', [])}
    dirty = git(repo, 'status', '--porcelain', '--untracked-files=all')
    direct.update(p for p in git(repo, 'diff', '--name-only', 'HEAD').splitlines() if not p.startswith(
                  ('.fullops-squad/handovers/', '.fullops-squad/board/', '.fullops-squad/docs/evaluations/jev/')))
    mandatory = set(REQUIRED) | set(required) | {inbox.relative_to(repo).as_posix()}
    route = sources.get('route', {})
    update_ids = set(updates) | set(route.get('deliverables', [])) | set(route.get('additional_deliverables', []))
    documents = {c['path'] for c in sources.get('documents-find', {}).get('candidates', [])}
    ctx = sources.get('context', {}).get('context') or {}
    contexts = {path: cid for cid, path in ctx.get('candidate_paths', {}).items()}
    mandatory.update(path for path in ctx.get('required_paths', []) if path)
    mapped = {path for scope in ('code', 'documents') for path, _ in code_map(repo, head, scope)}
    mapped.update(direct | mandatory | documents | set(contexts))
    texts, file_hashes = {}, {}
    for name in sorted(mapped):
        try:
            path = local_file(repo, name)
            raw = path.read_bytes() if path.stat().st_size <= MAX_BLOB else b''
            if not raw:
                raise ValueError('oversized or empty; read manually')
            safe_text(raw.decode('utf-8'), MAX_BLOB)
            body = text if path == inbox else raw.decode('utf-8')
            texts[name], file_hashes[name] = body, digest(body.encode())
        except (OSError, ValueError, UnicodeError):
            unknown.append({'path': name, 'reason': 'missing, oversized, sensitive or invalid; manual inspection'})

    def add(path, category, reason, evidence=None, doc_id=None):
        item = entries.setdefault(path, {'path': path, 'categories': [], 'reasons': [], 'evidence': [],
            'doc_ids': [], 'required': path in mandatory, 'status': 'inferred' if path in texts else 'unknown',
            'priority': 0 if path in mandatory else 1, 'source_sha256': file_hashes.get(path)})
        if category not in item['categories']:
            item['categories'].append(category)
        if reason not in item['reasons']:
            item['reasons'].append(reason)
        if evidence and evidence not in item['evidence']:
            item['evidence'].append(evidence)
        if doc_id and doc_id not in item['doc_ids']:
            item['doc_ids'].append(doc_id)

    for path in direct:
        add(path, 'document_update' if path.endswith('.md') else 'direct_edit', 'explicit seed, diff or find recommendation')
    for path in mandatory | documents | set(contexts):
        add(path, 'document_read' if path.endswith('.md') else 'impact_check', 'required or existing context recommendation')
        if path in contexts:
            entries[path]['context_signal'] = ctx.get('signals', {}).get(contexts[path])

    goal = re.search(r'^# [^\n]+', text, re.M)
    query = goal.group(0) if goal else text[:500]
    query += ' ' + ' '.join(re.findall(r'`([A-Za-z_][A-Za-z_0-9]*_[A-Za-z_0-9]+)`', text))
    terms = set(re.findall(r'`([A-Za-z_][A-Za-z_0-9]*)`|\b([A-Za-z_][A-Za-z_0-9]{3,})\b', query))
    terms = {a or b for a, b in terms} - {'Task', 'read', 'None', 'True', 'False', 'with', 'from', 'import',
        'Rename', 'rename', 'returns', 'return', 'update', 'callers', 'tests', 'response', 'contract', 'and', 'add', 'the', 'API'}
    symbols = {}
    for path in direct:
        body = texts.get(path, '')
        try:
            tree = ast.parse(body) if path.endswith('.py') else None
            definitions = [(n.name, n.lineno) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))] if tree else []
        except SyntaxError:
            definitions = []
        if not definitions:
            definitions = [(m.group(1), body[:m.start()].count('\n') + 1) for m in re.finditer(
                r'\b(?:function|class|def|fn|func)\s+([A-Za-z_][A-Za-z_0-9]*)', body)]
        for symbol, line in definitions[:64]:
            symbols.setdefault(symbol, []).append(path)
            add(path, 'direct_edit', 'seed definition', {'method': 'definition', 'symbol': symbol, 'line': line, 'seed': path})
    for term in sorted(terms)[:64]:
        symbols.setdefault(term, []).append('inbox')
    if len(terms) > 64:
        unknown.append({'reason': 'keyword budget exceeded; full inbox search required'})
    for path, body in texts.items():
        for line, value in enumerate(body.splitlines(), 1):
            matches = [s for s in symbols if re.search(rf'\b{re.escape(s)}\b', value)]
            for symbol in matches[:4]:
                if path in direct:
                    continue
                category = 'document_read' if path.endswith('.md') else 'impact_check'
                add(path, category, 'symbol/keyword occurrence; reference semantics require verification',
                    {'method': 'string-search', 'symbol': symbol, 'line': line, 'seeds': symbols[symbol]})
            if path.endswith('.md'):
                for target in re.findall(r'\]\(([^)\s]+)\)', value):
                    if re.match(r'[a-z]+:|#', target):
                        continue
                    linked = (repo / path).parent / target.split('#')[0]
                    try:
                        link_path = linked.resolve().relative_to(repo).as_posix()
                    except ValueError:
                        continue
                    if link_path in direct:
                        add(path, 'document_read', 'local link to seed', {'method': 'markdown-link', 'line': line, 'seed': link_path})
                        entries[path]['sections'] = [target.split('#', 1)[1]] if '#' in target else []
    for doc in deliverables(repo / '.fullops-squad'):
        for source in doc['documents']:
            path = '.fullops-squad/' + source['path']
            if doc['id'] in update_ids or path in entries or doc['id'] in text:
                add(path, 'document_update' if doc['id'] in update_ids else 'document_read',
                    'route/explicit update candidate' if doc['id'] in update_ids else 'source mapping/reference; keep unchanged unless verified',
                    {'method': 'deliverable-index', 'id': doc['id'], 'source': doc['source']}, doc['id'])
        if doc['id'] in update_ids and not doc['documents']:
            unknown.append({'doc_id': doc['id'], 'reason': 'no existing source; create/locate canonical source'})
    for decision in decisions:
        if decision.get('path') not in entries or decision.get('action') not in ('add', 'exclude', 'change') or not decision.get('reason', '').strip():
            raise ValueError('worker decision needs existing path, action and reason; use --seeds to add a path')
        if decision['action'] == 'exclude' and entries[decision['path']]['required']:
            raise ValueError('mandatory context cannot be excluded')
    identity = input_identity(repo, role, key, {'policy': 'packet-v1', 'seeds': sorted(direct), 'required': sorted(mandatory),
        'updates': sorted(update_ids), 'sources': file_hashes, 'search_results': {k: digest(json.dumps(v, sort_keys=True).encode()) for k, v in sources.items()},
        'decisions': decisions})
    items = sorted(entries.values(), key=lambda item: (item['priority'], item['path']))
    return {**identity, 'version': 'jev-packet-v1', 'base': head, 'worktree_dirty': bool(dirty), 'items': items,
        'categories': {c: [i['path'] for i in items if c in i['categories']] for c in CATEGORIES},
        'input_partial': len(text) > 3500, 'task_excerpt': task_excerpt(text), 'instruction': inbox.relative_to(repo).as_posix(),
        'partial': bool(unknown), 'unknown': unknown, 'worker_decisions': decisions,
        'fallback': 'bounded string/definition search; dynamic references and language server semantics unverified',
        'context_paths': [i['path'] for i in items if not i['required']][:20], 'required_paths': sorted(mandatory),
        'remaining_context_paths': [i['path'] for i in items if not i['required']][20:]}


def handover(result, output):
    lines = ['<!-- fullops-packet:start -->', '### 탐색 근거와 읽을 구간', '', f'정본: `{output}` / SHA `{result["head"]}` / partial={result["partial"]}']
    for item in result['items']:
        spans = ', '.join(str(e.get('line')) for e in item['evidence'] if e.get('line'))
        lines.append(f'- `{item["path"]}` ({", ".join(item["categories"])}) · 줄 {spans or "전체/미확인"} · {item["status"]}' +
                     (' · 필수' if item['required'] else '') + (f' · {item["context_signal"]}' if item.get('context_signal') else ''))
    lines += [f'미확인 {len(result["unknown"])}건: 정본의 unknown/remaining_context_paths 확인. {result["fallback"]}', '<!-- fullops-packet:end -->']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'role', 'key'):
        parser.add_argument('--' + name, required=True)
    for name in ('seeds', 'required', 'update-docs'):
        parser.add_argument('--' + name, nargs='*', default=[])
    parser.add_argument('--decisions', help='worker의 추가/제외/변경 사유 JSON 목록')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--write-inbox', action='store_true', help='현재 인박스에 근거 목록 연결')
    args = parser.parse_args()
    try:
        if not KEY.fullmatch(args.key):
            raise ValueError('invalid task key')
        repo = active_repo(args.repo)
        decisions = json.loads(local_file(repo, args.decisions).read_text()) if args.decisions else []
        result = packet(repo, args.role, args.key, args.seeds, args.required, args.update_docs, decisions)
        output = result_path(repo, args.key, 'packet')
        reused = previous_result(output, result, args.force)
        if not reused:
            save_result(output, result)
        if args.write_inbox:
            inbox, text = instruction(repo, args.role, args.key)
            text = re.sub(r'<!-- fullops-packet:start -->[\s\S]*?<!-- fullops-packet:end -->\n*', '', text)
            block = handover(result, output.relative_to(repo))
            atomic_write(inbox, text.replace('## 완료 보고', block + '\n\n## 완료 보고', 1))
        print(output.relative_to(repo))
        print(f'후보 {len(result["items"])} · partial={result["partial"]} · 미확인 {len(result["unknown"])}')
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'탐색 패킷 실패: {error}\n')


if __name__ == '__main__':
    main()
