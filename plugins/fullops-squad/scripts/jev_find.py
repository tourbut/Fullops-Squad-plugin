#!/usr/bin/env python3
"""지시서에 맞는 코드 위치를 Jev로 찾고(find), 과제가 끝난 뒤 실제 변경과 비교해 적중률을 기록한다(score).

TypeSafe semantic_find 예제의 방식을 코드에 옮겼다. HEAD의 파일 목록과 파일 헤더 설명으로 지도를 만들고,
Choice 질문으로 순위를, 두 값짜리 존재 질문으로 "관련 코드 없음"을 판정한다. Choice 선택지는 255개가 한도라
파일이 더 많으면 디렉터리 단위로 먼저 고른다. 추천일 뿐이며 게이트에 쓰지 않는다.
"""
import argparse
from collections import defaultdict
from fnmatch import fnmatch
import json
import os
from pathlib import Path
import subprocess

from jev_observe import MODEL, checked_answer, key_from_file, local_file, request, safe_text
from lint import CONFIG, DEFAULT, header_summary
from work import KEY, active_repo, safe_file, validate_role

MAX_OPTIONS = 255
FOUND, ABSENT = 0.7, 0.35  # 예제의 경계값. 코드 검색에 맞는 값은 score 기록으로 다시 정한다
MAX_BLOB = 65536
EXISTS = {'found': 'At least one entry is directly related to the task and must be read or changed.',
          'absent': 'No entry relates to the task; it needs new code or files.'}


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def result_path(repo, key, suffix):
    return safe_file(repo, f'.fullops-squad/docs/evaluations/jev/{key}-{suffix}.json')


def code_map(repo, head):
    """(path, summary) 목록. 제외·민감·바이너리 파일은 넣지 않는다."""
    try:
        exclude = json.loads(git(repo, 'show', f'{head}:{CONFIG}')).get('exclude', DEFAULT['exclude'])
    except (subprocess.CalledProcessError, ValueError, AttributeError):
        exclude = DEFAULT['exclude']
    blobs = []
    for row in subprocess.check_output(['git', '-C', str(repo), 'ls-tree', '-r', '-z', head], text=True).split('\0'):
        meta, _, path = row.partition('\t')
        mode, kind, sha = (meta.split() + ['', '', ''])[:3]
        # 일반 파일만: 서브모듈(commit)·심볼릭 링크(120000)는 뺀다
        if kind == 'blob' and mode != '120000' and not any(
                fnmatch(path, x) or (x.startswith('**/') and fnmatch(path, x[3:])) for x in exclude):
            blobs.append((path, sha))
    batch = subprocess.run(['git', '-C', str(repo), 'cat-file', '--batch'], input=''.join(f'{sha}\n' for _, sha in blobs).encode(),
                           capture_output=True, check=True).stdout
    entries, offset = [], 0
    for path, _ in blobs:
        header_end = batch.index(b'\n', offset)
        size = int(batch[offset:header_end].split()[2])
        data = batch[header_end + 1:header_end + 1 + size]
        offset = header_end + 2 + size
        try:
            local_file(repo, path)  # 민감 경로는 지도에서도 뺀다
            text = data[:MAX_BLOB].decode('utf-8')
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if b'\0' in data[:8000]:
            continue
        summary = header_summary(text, Path(path).suffix.lower())[:100]
        try:
            safe_text(summary)
        except ValueError:
            summary = ''
        entries.append((path, summary))
    return entries


def ask(call, task, options, with_exists):
    """options: {id: 설명}. Choice 순위와 (필요하면) 존재 판정을 한 요청으로 묻는다."""
    questions = {'where': {'type': 'choice', 'criteria': options, 'instructions':
                           'Which entry is the best place to read or change first to do `task`? '
                           'Judge by the path and its one-line description.'}}
    if with_exists:
        questions['exists'] = {'type': 'choice', 'criteria': EXISTS, 'instructions':
                               'Does any listed entry already contain code or documents that `task` must read or change?'}
    response, elapsed = call({'model': MODEL, 'state': {'task': task}, 'questions': questions})
    answers = {qid: checked_answer(response['answers'][qid], question['criteria']) for qid, question in questions.items()}
    return answers, response.get('usage') or {}, elapsed, response.get('model')


def ranked(answer, cumulative, most):
    """확률 높은 순으로 누적 확률이 cumulative에 닿을 때까지, 최대 most개."""
    picked, total = [], 0.0
    for option, probability in sorted(answer['probabilities'].items(), key=lambda kv: -kv[1]):
        if picked and (total >= cumulative or len(picked) >= most):
            break
        picked.append((option, probability))
        total += probability
    return picked


def find(repo, role, key, call, limit=12):
    validate_role(repo, role)
    inbox = safe_file(repo, f'.fullops-squad/handovers/to_{role}.md')
    text = inbox.read_text() if inbox.is_file() else ''
    if not text.startswith(f'# {key} — '):
        raise ValueError('인박스에 같은 과제 키의 지시서를 먼저 작성하세요')
    task = safe_text(f'{key}\n' + text[:3500])
    head = git(repo, 'rev-parse', 'HEAD')
    entries = code_map(repo, head)
    result = {'version': 'jev-find-v1', 'task_key': key, 'head': head, 'requested_model': MODEL, 'files': len(entries),
              'passes': [], 'candidates': [], 'existence': None, 'truncated': False,
              'usage': {'input_tokens': 0, 'output_tokens': 0, 'cost': 0}, 'latency_seconds': 0.0, 'error': None}
    pool, depth = entries, 0
    try:
        while len(pool) > MAX_OPTIONS and depth < 4:
            groups = defaultdict(list)
            for path, summary in pool:
                parts = Path(path).parts
                groups['/'.join(parts[:min(depth + 1, len(parts) - 1)]) or '.'].append((path, summary))
            depth += 1
            if len(groups) < 2 or len(groups) > MAX_OPTIONS:
                continue  # 한 디렉터리뿐이거나 너무 많으면 한 단계 더 내려가 다시 묶는다
            names = sorted(groups)
            options = {f'D{i:03d}': f"{name}/ ({len(groups[name])} files) "
                       + '; '.join(s or Path(p).name for p, s in groups[name][:3])[:160] for i, name in enumerate(names)}
            answers = record(result, *ask(call, task, options, result['existence'] is None))
            chosen = ranked(answers['where'], 0.8, 3)
            result['passes'].append({'level': 'directory', 'options': len(options),
                                     'chosen': [[names[int(o[1:])], p] for o, p in chosen]})
            pool = [entry for o, _ in chosen for entry in groups[names[int(o[1:])]]]
        if len(pool) > MAX_OPTIONS:
            pool, result['truncated'] = pool[:MAX_OPTIONS], True
        if pool:
            options = {f'F{i:03d}': f'{path} — {summary}' if summary else path for i, (path, summary) in enumerate(pool)}
            answers = record(result, *ask(call, task, options, result['existence'] is None))
            picked = ranked(answers['where'], 0.9, limit)
            result['passes'].append({'level': 'file', 'options': len(options)})
            result['candidates'] = [{'path': pool[int(o[1:])][0], 'summary': pool[int(o[1:])][1], 'probability': p}
                                    for o, p in picked]
    except (KeyError, TypeError, ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        result['error'] = f'API or response validation failed: {type(error).__name__}'
        result['candidates'] = []
    return result


def record(result, answers, usage, elapsed, model):
    for field in ('input_tokens', 'output_tokens', 'cost'):
        result['usage'][field] += usage.get(field, 0) if isinstance(usage.get(field, 0), (int, float)) else 0
    result['latency_seconds'] = round(result['latency_seconds'] + elapsed, 3)
    result['response_model'] = model
    if 'exists' in answers:
        found = answers['exists']['probabilities']['found']
        result['existence'] = {'found_probability': found,
                               'status': 'found' if found >= FOUND else 'absent' if found <= ABSENT else 'unclear'}
    return answers


def score(repo, key, base, head):
    found = json.loads(result_path(repo, key, 'find').read_text())
    head, merge_base = git(repo, 'rev-parse', head), git(repo, 'merge-base', base, head)
    mapped = {path for path, _ in code_map(repo, found['head'])}
    changed = set(git(repo, 'diff', '--name-only', '--no-renames', merge_base, head).splitlines())
    existing = changed & mapped
    new = {p for p in changed - mapped if not p.startswith('.fullops-squad/')}
    candidates = {c['path'] for c in found['candidates']}
    hit = candidates & existing
    status = (found.get('existence') or {}).get('status')
    out = {'task_key': key, 'find_head': found['head'], 'base': merge_base, 'head': head,
           'changed_existing': sorted(existing), 'new_files': sorted(new), 'candidates': sorted(candidates),
           'hits': sorted(hit), 'recall': round(len(hit) / len(existing), 3) if existing else None,
           'precision': round(len(hit) / len(candidates), 3) if candidates else None,
           'existence_status': status,
           'existence_correct': None if status in (None, 'unclear') else (status == 'found') == bool(existing)}
    context = result_path(repo, key, 'context')
    if context.is_file():
        ctx = json.loads(context.read_text()).get('context') or {}
        omitted = {path for cid, path in ctx.get('candidate_paths', {}).items() if cid not in ctx.get('recommended_ids', [])}
        out['context_omitted'], out['context_wrong_omits'] = sorted(omitted), sorted(omitted & changed)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=('find', 'score'))
    parser.add_argument('--repo', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--role', help='find: 지시서를 쓴 역할')
    parser.add_argument('--limit', type=int, default=12)
    parser.add_argument('--env-file', help='OPENROUTER_API_KEY를 코드 실행 없이 읽는다')
    parser.add_argument('--from', dest='base', help='score: 기준 ref')
    parser.add_argument('--to', help='score: worker 결과 ref')
    args = parser.parse_args()
    try:
        if not KEY.fullmatch(args.key):
            raise ValueError('과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요')
        repo = active_repo(args.repo)
        output = result_path(repo, args.key, 'find' if args.mode == 'find' else 'find-score')
        if output.exists():
            raise ValueError(f'기존 결과를 보존합니다: {output.relative_to(repo)}')
        if args.mode == 'find':
            if not args.role:
                raise ValueError('find에는 --role이 필요합니다')

            def call(payload):
                return request(payload, key_from_file(args.env_file) if args.env_file
                               else os.environ.get('OPENROUTER_API_KEY', ''))
            result = find(repo, args.role, args.key, call, args.limit)
        else:
            if not (args.base and args.to):
                raise ValueError('score에는 --from과 --to가 필요합니다')
            result = score(repo, args.key, args.base, args.to)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Jev 탐색 실패: {error}\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    if args.mode == 'find':
        for c in result['candidates']:
            print(f"{c['probability']:.2f} {c['path']}  {c['summary']}".rstrip())
        existence = result['existence'] or {}
        print(f"존재: {existence.get('status', '-')} ({existence.get('found_probability', '-')}) / 파일 {result['files']} / "
              f"비용 {result['usage']['cost']} / {result['error'] or '정상'}")
        print('paths: ' + ' '.join(c['path'] for c in result['candidates']))
    else:
        print(f"recall {result['recall']} / precision {result['precision']} / 존재 판정 {result['existence_correct']} / "
              f"새 파일 {len(result['new_files'])}")
    print(output.relative_to(repo))


if __name__ == '__main__':
    main()
