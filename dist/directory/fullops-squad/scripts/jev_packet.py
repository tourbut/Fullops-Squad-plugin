#!/usr/bin/env python3
"""기존 route/find/context를 실제 검색 근거와 연결해 인박스로 전달한다. 모델 점수는 수락 게이트가 아니다."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess

from board import deliverables
from deliverables import front_matter
from jev_find import code_map, git, result_path, MAX_BLOB
from jev_observe import local_file, REQUIRED, digest, safe_text, git_env
from work import active_repo, instruction, instruction_digest, input_identity, previous_result, save_result, task_excerpt, KEY
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
    current = input_identity(repo, role, key, {})
    sources, unknown, entries, producer_status = {}, [], {}, {}
    for suffix in ('route', 'find', 'documents-find', 'context'):
        path = result_path(repo, key, suffix)
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                unknown.append({'source': suffix, 'reason': 'invalid producer JSON; regenerate'})
                continue
            if not isinstance(data, dict) or any(data.get(k) != current[k] for k in ('task_key', 'role', 'head', 'attempt', 'instruction_sha256')) or not data.get('attempt'):
                unknown.append({'source': suffix, 'reason': 'task/role/SHA/attempt/instruction differs or absent; regenerate/bind route'})
            else:
                sources[suffix] = data
                producer_status[suffix] = {k: data[k] for k in ('error', 'partial', 'input_partial', 'docs_status', 'unresolved_deliverables',
                    'remaining_candidates', 'refused_paths', 'unsent_sources', 'ranking_status', 'fallback') if k in data}
                ctx_status = data.get('context') or {}
                if ctx_status.get('fallback'):
                    producer_status[suffix]['context_fallback'] = ctx_status['fallback']
                if data.get('error') or data.get('partial') or data.get('input_partial') or data.get('docs_status') == 'partial' or data.get('unresolved_deliverables') or data.get('remaining_candidates') or data.get('refused_paths') or data.get('unsent_sources') or data.get('fallback') or ctx_status.get('fallback'):
                    unknown.append({'source': suffix, 'reason': 'producer uncertainty; inspect producer_status', **producer_status[suffix]})
    recommended = {c['path'] for c in sources.get('find', {}).get('candidates', [])} | set(sources.get('find', {}).get('seed_paths', []))
    explicit = set(seeds)
    dirty = git(repo, 'status', '--porcelain', '--untracked-files=all')
    explicit.update(p for p in git(repo, 'diff', '--name-only', 'HEAD').splitlines() if not p.startswith(
                  ('.fullops-squad/handovers/', '.fullops-squad/board/', '.fullops-squad/docs/evaluations/jev/')))
    direct = explicit
    mandatory = set(REQUIRED) | set(required) | {inbox.relative_to(repo).as_posix()}
    route = sources.get('route', {})
    update_ids = set(updates) | set(route.get('deliverables', [])) | set(route.get('additional_deliverables', []))
    documents = {c['path'] for c in sources.get('documents-find', {}).get('candidates', [])} | set(sources.get('documents-find', {}).get('seed_paths', [])) | {p for p in recommended if p.endswith('.md')}
    ctx = sources.get('context', {}).get('context') or {}
    contexts = {path: cid for cid, path in ctx.get('candidate_paths', {}).items()}
    optional = {p for p, cid in contexts.items() if (ctx.get('signals', {}).get(cid) or {}).get('decision') == 'suggest_omit'}
    mandatory.update(path for path in ctx.get('required_paths', []) if path)
    mapped = {path for scope in ('code', 'documents') for path, _ in code_map(repo, head, scope)}
    mapped.update(direct | mandatory | documents | set(contexts))
    texts, file_hashes, source_basis = {}, {}, {}
    tracked = set(git(repo, 'ls-files', '-z').split('\0'))
    for name in sorted(mapped):
        try:
            path = local_file(repo, name)
            raw = path.read_bytes() if path.stat().st_size <= MAX_BLOB else b''
            if not raw:
                raise ValueError('oversized or empty; read manually')
            safe_text(raw.decode('utf-8'), MAX_BLOB)
            body = text if path == inbox else raw.decode('utf-8')
            texts[name] = body
            file_hashes[name] = instruction_digest(body) if path == inbox else digest(body.replace('\r\n', '\n').encode())
            saved = subprocess.run(['git', '-C', str(repo), 'cat-file', '--filters', f'{head}:{name}'],
                                   capture_output=True, env=git_env())
            source_basis[name] = ('HEAD' if saved.returncode == 0 and saved.stdout == raw else
                                  'tracked_worktree_overlay' if name in tracked else 'explicit_untracked_or_required')
        except (OSError, ValueError, UnicodeError):
            unknown.append({'path': name, 'reason': 'missing, oversized, sensitive or invalid; manual inspection'})

    def add(path, category, reason, evidence=None, doc_id=None):
        item = entries.setdefault(path, {'path': path, 'categories': [], 'reasons': [], 'evidence': [],
            'doc_ids': [], 'required': path in mandatory, 'status': 'inferred' if path in texts else 'unknown',
            'priority': 0 if path in mandatory else 1, 'source_sha256': file_hashes.get(path),
            'source_basis': source_basis.get(path)})
        if category not in item['categories']:
            item['categories'].append(category)
        if reason not in item['reasons']:
            item['reasons'].append(reason)
        if evidence and evidence not in item['evidence']:
            item['evidence'].append(evidence)
        if doc_id and doc_id not in item['doc_ids']:
            item['doc_ids'].append(doc_id)

    for path in direct:
        add(path, 'document_update' if path.endswith('.md') else 'direct_edit', 'explicit edit seed/diff' if path in explicit else 'code find recommendation')
    for path in mandatory | documents | recommended | (set(contexts) - optional):
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
        if len(definitions) > 64:
            unknown.append({'path': path, 'reason': 'definition budget exceeded; remaining definitions require search', 'remaining_definitions': len(definitions) - 64})
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
                        link_path = linked.resolve().relative_to(repo.resolve()).as_posix()
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
    for path in optional:
        if path not in entries:
            add(path, 'document_read' if path.endswith('.md') else 'impact_check', 'optional context; suggest_omit')
            entries[path]['optional'] = True
        entries[path]['context_signal'] = ctx.get('signals', {}).get(contexts[path])
    for decision in decisions:
        if decision.get('path') not in entries or decision.get('action') not in ('add', 'exclude', 'change') or not decision.get('reason', '').strip():
            raise ValueError('worker decision needs existing path, action and reason; use --seeds to add a path')
        if decision['action'] == 'exclude' and entries[decision['path']]['required']:
            raise ValueError('mandatory context cannot be excluded')
    identity = input_identity(repo, role, key, {'policy': 'packet-v3', 'seeds': sorted(explicit), 'required': sorted(mandatory),
        'updates': sorted(update_ids), 'sources': file_hashes, 'search_results': {k: digest(json.dumps(v, sort_keys=True).encode()) for k, v in sources.items()},
        'decisions': decisions})
    if identity['head'] != head:
        raise ValueError('HEAD changed while preparing packet; regenerate')
    items = sorted(entries.values(), key=lambda item: (bool(item.get('optional')), item['priority'], item['path']))
    primary = [i['path'] for i in items if not i['required'] and not i.get('optional')]
    return {**identity, 'version': 'jev-packet-v2', 'base': head, 'worktree_dirty': bool(dirty), 'items': items,
        'snapshot': 'HEAD search with tracked worktree and explicit/required local overlays',
        'source_hash_policy': 'verify before worker start; regenerate on change; completion allows implementation changes',
        'categories': {c: [i['path'] for i in items if c in i['categories']] for c in CATEGORIES},
        'input_partial': len(text) > 3500, 'task_excerpt': task_excerpt(text), 'instruction': inbox.relative_to(repo).as_posix(),
        'partial': bool(unknown), 'unknown': unknown, 'producer_status': producer_status,
        'worker_decisions': decisions, 'worker_decisions_mode': 'annotations; original recommendations preserved',
        'fallback': 'bounded string/definition search; dynamic references and language server semantics unverified',
        'context_paths': primary[:20], 'required_paths': sorted(mandatory),
        'optional_context_paths': [i['path'] for i in items if i.get('optional')], 'remaining_context_paths': primary[20:]}


def handover(result, output):
    lines = ['<!-- fullops-packet:start -->', '### 탐색 근거와 읽을 구간', '', f'정본: `{output}` / SHA `{result["head"]}` / partial={result["partial"]}']
    for item in result['items']:
        if item.get('optional'):
            continue
        spans = ', '.join(str(e.get('line')) for e in item['evidence'] if e.get('line'))
        lines.append(f'- `{item["path"]}` ({", ".join(item["categories"])}) · 줄 {spans or "전체/미확인"} · {item["status"]}' +
                     (' · 필수' if item['required'] else '') + (f' · {item["context_signal"]}' if item.get('context_signal') else ''))
    for decision in result['worker_decisions']:
        lines.append(f'- 작업자 의견(원본 추천 유지): `{decision["path"]}` {decision["action"]} — {decision["reason"]}')
    lines += [f'미확인 {len(result["unknown"])}건: 정본의 unknown/producer_status/remaining_context_paths/optional_context_paths 확인. {result["fallback"]}', '<!-- fullops-packet:end -->']
    return '\n'.join(lines)


def check(repo, role, key, completion=False, required=False, head=None, text=None):
    """추천은 수정 의무가 아니다. 현재 시도의 패킷 전달과 항목별 처리 근거를 검사한다."""
    def read(relative):
        if head:
            return git(repo, 'show', f'{head}:{relative}')
        return local_file(repo, relative).read_text(encoding='utf-8')
    relative = result_path(repo, key, 'packet').relative_to(repo).as_posix()
    if text is None:
        _, text = instruction(repo, role, key)
    route = result_path(repo, key, 'route')
    required = required or '<!-- fullops-packet:start -->' in text or result_path(repo, key, 'packet').is_file() or (route.is_file() and json.loads(route.read_text()).get('requires_packet'))
    if not required:
        return
    try:
        result = json.loads(read(relative))
        meta = front_matter(text) or {}
        sha = instruction_digest(text)
        if result.get('task_key') != key or result.get('role') != role or not meta.get('attempt') or result.get('attempt') != meta['attempt'] or result.get('instruction_sha256') != sha:
            raise ValueError('packet task/role/attempt/instruction identity differs')
        current_head = head or git(repo, 'rev-parse', 'HEAD')
        if completion:
            subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', result['head'], current_head], check=True, capture_output=True, env=git_env())
        elif result.get('head') != current_head:
            raise ValueError('packet SHA differs from worker HEAD')
        if not completion:
            for item in result['items']:
                if not item.get('optional') and (item.get('required') or item.get('status') != 'unknown'):
                    body = read(item['path'])  # 워크트리 간 파일 공유를 가정하지 않는다.
                    if item['path'] == result.get('instruction'):
                        body = re.sub(r'<!-- fullops-packet:start -->[\s\S]*?<!-- fullops-packet:end -->\n*', '', body)
                    actual = instruction_digest(body) if item['path'] == result.get('instruction') else digest(body.replace('\r\n', '\n').encode())
                    if item.get('source_sha256') and actual != item['source_sha256']:
                        raise ValueError('packet source changed; regenerate packet before worker start')
            return
        outcomes = json.loads(read(result_path(repo, key, 'packet-outcomes').relative_to(repo).as_posix()))
        if outcomes.get('packet_input_sha256') != result['input_sha256'] or outcomes.get('attempt') != result['attempt']:
            raise ValueError('packet outcomes identity differs')
        expected = {(i['path'], c) for i in result['items'] if not i.get('optional') for c in i['categories']}
        rows = outcomes.get('items', [])
        seen = set()
        for item in rows:
            pair = (item.get('path'), item.get('category'))
            if pair in seen or pair not in expected or item.get('status') not in ('completed', 'no_change') or not isinstance(item.get('reason'), str) or not item['reason'].strip():
                raise ValueError('packet item needs unique completed/no_change status and reason; unknown remains pending')
            seen.add(pair)
        if seen != expected:
            raise ValueError('packet document/read/impact outcomes incomplete')
        if result.get('partial') and not str(outcomes.get('uncertainty_review') or '').strip():
            raise ValueError('partial packet needs manual uncertainty review evidence')
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise ValueError(f'탐색 패킷 전달/완료 검사 실패: {error}') from error


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
