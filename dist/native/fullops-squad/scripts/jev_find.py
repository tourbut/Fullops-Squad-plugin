#!/usr/bin/env python3
"""지시서에 맞는 코드 위치를 Jev로 찾고(find), 과제가 끝난 뒤 실제 변경과 비교해 적중률을 기록한다(score).

TypeSafe semantic_find 예제의 방식을 코드에 옮겼다. HEAD의 파일 목록과 파일 헤더 설명으로 지도를 만들고,
Choice 질문으로 순위를, 두 값짜리 존재 질문으로 "관련 코드 없음"을 판정한다. Choice 선택지는 255개가 한도라
파일이 더 많으면 디렉터리 단위로 먼저 고른다. 추천일 뿐이며 게이트에 쓰지 않는다.
"""
import argparse
import codecs
from collections import defaultdict
from fnmatch import fnmatch
import json
import os
import re
from pathlib import Path
import subprocess
import time

from jev_observe import MODEL, api_key, checked_answer, local_file, request, safe_text, validated
from lint import CONFIG, DEFAULT, header_summary, changed as changed_paths
from work import KEY, active_repo, instruction, safe_file, input_identity, previous_result, save_result, task_excerpt
from deliverables import split

MAX_OPTIONS = 255
FOUND, ABSENT = 0.7, 0.35  # 예제의 경계값. 코드 검색에 맞는 값은 score 기록으로 다시 정한다
MAX_BLOB = 65536
# 하네스 폴더는 코드 지도에서 뺀다. 지시서가 이 경로를 많이 적어 디렉터리 선택이 매번 여기로 끌려가고(erden recall 0~0.14),
# 규칙·설계 문서는 필수 문서와 지시서 참조로 이미 들어간다. Unity .meta는 짝 파일과 같은 내용이라 뺀다
HARNESS = '.fullops-squad/'
HARNESS_FILES = ('AGENTS.md', 'CLAUDE.md', 'GEMINI.md')  # 하네스 진입 파일
EXISTS = {'found': 'At least one entry is directly related to the task and must be read or changed.',
          'absent': 'No entry relates to the task; it needs new code or files.'}


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def result_path(repo, key, suffix):
    return safe_file(repo, f'.fullops-squad/docs/evaluations/jev/{key}-{suffix}.json')


def prefix_blob(repo, sha, size):
    """큰 Git blob도 처음 MAX_BLOB 바이트만 읽는다. 불완전한 마지막 UTF-8 문자만 제외한다."""
    with subprocess.Popen(['git', '-C', str(repo), 'cat-file', 'blob', sha], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as process:
        data = process.stdout.read(min(size, MAX_BLOB))
        process.stdout.close()
        if size > MAX_BLOB:
            process.terminate()
        process.wait()
    if b'\0' in data[:8000]:
        return ''
    return codecs.getincrementaldecoder('utf-8')().decode(data, final=size <= MAX_BLOB)


def code_map(repo, head, scope='code'):
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
        document = path.endswith('.md')
        eligible = document if scope == 'documents' else not path.startswith(HARNESS) and path not in HARNESS_FILES
        # 하네스 문서는 코드 lint 제외와 무관하다. 나머지 경로의 의존성·빌드 제외는 유지한다.
        excluded = any(fnmatch(path, x) or (x.startswith('**/') and fnmatch(path, x[3:])) for x in exclude)
        if kind == 'blob' and mode != '120000' and eligible and not path.endswith('.meta') and (
                scope == 'documents' and path.startswith(HARNESS) or not excluded):
            try:
                local_file(repo, path, historical=True)
            except ValueError:
                continue
            blobs.append((path, sha))
    sizes = subprocess.check_output(['git', '-C', str(repo), 'cat-file', '--batch-check=%(objectsize)'],
                                    input=''.join(f'{sha}\n' for _, sha in blobs).encode()).splitlines()
    entries = []
    for (path, sha), size in zip(blobs, sizes):
        try:
            text = prefix_blob(repo, sha, int(size))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        meta, body = split(text) if path.endswith('.md') else (None, text)
        summary = ((' — '.join(str(meta.get(k, '')) for k in ('title', 'summary') if meta.get(k)) if meta else '')
                   or header_summary(body, Path(path).suffix.lower()))[:240]
        if not text.strip():
            continue
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
    values, usage, elapsed, model = validated(call({'model': MODEL, 'state': {'task': task}, 'questions': questions}), questions)
    answers = {qid: checked_answer(values[qid], question['criteria']) for qid, question in questions.items()}
    return answers, usage, elapsed, model


def ranked(answer, cumulative, most):
    """확률 높은 순으로 누적 확률이 cumulative에 닿을 때까지, 최대 most개."""
    picked, total = [], 0.0
    for option, probability in sorted(answer['probabilities'].items(), key=lambda kv: -kv[1]):
        if picked and (total >= cumulative or len(picked) >= most):
            break
        picked.append((option, probability))
        total += probability
    return picked


def find(repo, role, key, call, limit=12, handover=None, scope='code'):
    started = time.monotonic()
    _, text = instruction(repo, role, key, handover)
    task = safe_text(f'{key}\n' + task_excerpt(text))
    head = git(repo, 'rev-parse', 'HEAD')
    entries = code_map(repo, head, scope)
    result = {**input_identity(repo, role, key, {'policy': 'find-v2', 'scope': scope, 'limit': limit}),
              'version': 'jev-find-v1', 'requested_model': MODEL, 'files': len(entries),
              'scope': scope, 'passes': [], 'candidates': [], 'existence': None, 'truncated': False,
              'usage': {'input_tokens': 0, 'output_tokens': 0, 'cost': 0}, 'latency_seconds': 0.0, 'error': None}
    existence, seen, candidates = [], 0, []
    try:
        for offset in range(0, len(entries), MAX_OPTIONS):
            pool = entries[offset:offset + MAX_OPTIONS]
            options = {f'F{i:03d}': f'{path} — {summary}' if summary else path for i, (path, summary) in enumerate(pool)}
            answers = record(result, *ask(call, task, options, True))
            seen += len(pool)
            existence.append(result['existence']['found_probability'])
            picked = ranked(answers['where'], 0.99, limit)
            result['passes'].append({'level': 'file', 'options': len(options)})
            candidates.extend({'path': pool[int(o[1:])][0], 'summary': pool[int(o[1:])][1], 'probability': probability,
                               'probability_scope': 'batch', 'batch_start': offset, 'batch_rank': rank} for rank, (o, probability) in enumerate(picked))
        # ponytail: 배치 간 확률은 비교할 수 없다. 전역 재평가 전에는 배치 순서와 partial을 보존한다.
        result['candidates'] = sorted(candidates, key=lambda item: (item['batch_rank'], item['batch_start']))[:limit]
        result['remaining_candidates'] = [item['path'] for item in candidates if item not in result['candidates']]
        if existence:
            found = max(existence)
            result['existence'] = {'found_probability': found, 'status': 'found' if found >= FOUND else
                                   'absent' if all(p <= ABSENT for p in existence) else 'unclear'}
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError) as error:
        result['error'] = f'API or response validation failed: {type(error).__name__}'
        result['candidates'] = []
        result['existence'] = {'status': 'unknown', 'found_probability': None}
    result.update(presented_files=seen, partial=seen != len(entries) or len(entries) > MAX_OPTIONS,
                  ranking_status='batch_only' if len(entries) > MAX_OPTIONS else 'single_batch',
                  fallback='keyword/symbol search' if seen != len(entries) or len(entries) > MAX_OPTIONS else None,
                  input_partial=len(text) > 3500, instruction_chars=len(text))
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    result['usage'].update(known_cost=result['usage']['cost'], cost_status='unknown' if result['error'] else 'complete')
    if result['error']:
        result['usage']['cost'] = None
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


def score(repo, key, base, head, scope='code', labels=None):
    found = json.loads(result_path(repo, key, 'documents-find' if scope == 'documents' else 'find').read_text())
    head, merge_base = git(repo, 'rev-parse', head), git(repo, 'merge-base', base, head)
    mapped = {path for path, _ in code_map(repo, found['head'], found.get('scope', 'code'))}
    changed = set(git(repo, 'diff', '--name-only', '--no-renames', merge_base, head).splitlines())
    existing = changed & mapped
    statuses = changed_paths(repo, merge_base, head)
    new = {path for old, path in statuses if old is None and path and not path.startswith('.fullops-squad/')}
    candidates = {c['path'] for c in found['candidates']}
    hit = candidates & existing
    status = (found.get('existence') or {}).get('status')
    out = {'task_key': key, 'find_head': found['head'], 'base': merge_base, 'head': head, 'scope': scope,
           'metric': 'changed-file overlap; does not measure required reading or impact coverage',
           'deleted_files': sorted(old for old, path in statuses if path is None),
           'renamed_files': [[old, path] for old, path in statuses if old and path and old != path],
           'changed_existing': sorted(existing), 'new_files': sorted(new), 'candidates': sorted(candidates),
           'hits': sorted(hit), 'recall': round(len(hit) / len(existing), 3) if existing else None,
           'precision': round(len(hit) / len(candidates), 3) if candidates else None,
           'existence_status': status,
           'existence_correct': None if status in (None, 'unclear', 'unknown') else (status == 'found') == bool(existing)}
    packet = result_path(repo, key, 'packet')
    if packet.is_file():
        from jev_packet import evaluate
        out['packet_evaluation'] = evaluate(json.loads(packet.read_text()), labels)
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
    parser.add_argument('--role', help='find: 지시서를 받는 역할')
    parser.add_argument('--handover', help='find: 현재 역할 인박스의 상대 경로. .fullops-squad/handovers/to_<역할>.md만 허용')
    parser.add_argument('--limit', type=int, default=12)
    parser.add_argument('--scope', choices=('code', 'documents'), default='code', help='documents: 하네스 문서를 포함한 Markdown의 title·summary로 탐색')
    parser.add_argument('--force', action='store_true', help='이전 결과를 history에 보존하고 갱신')
    parser.add_argument('--env-file', help='OPENROUTER_API_KEY를 코드 실행 없이 읽는다')
    parser.add_argument('--from', dest='base', help='score: 기준 ref')
    parser.add_argument('--to', help='score: worker 결과 ref')
    parser.add_argument('--labels', help='score: 직접 수정/영향/문서 read/update의 기대 경로 JSON; diff와 별도 평가')
    args = parser.parse_args()
    try:
        if not KEY.fullmatch(args.key):
            raise ValueError('과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요')
        repo = active_repo(args.repo)
        suffix = 'find' if args.mode == 'find' else 'find-score'
        output = result_path(repo, args.key, ('documents-' if args.scope == 'documents' else '') + suffix)
        reused = None
        if args.mode == 'find':
            if not args.role:
                raise ValueError('find에는 --role이 필요합니다')

            identity = input_identity(repo, args.role, args.key, {'policy': 'find-v2', 'scope': args.scope, 'limit': args.limit})
            reused = previous_result(output, identity, args.force)

            def call(payload):
                return request(payload, api_key(args.env_file, repo))
            result = reused or {**find(repo, args.role, args.key, call, args.limit, args.handover, args.scope), **identity}
        else:
            if not (args.base and args.to):
                raise ValueError('score에는 --from과 --to가 필요합니다')
            labels = json.loads(local_file(repo, args.labels).read_text()) if args.labels else None
            result = score(repo, args.key, args.base, args.to, args.scope, labels)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Jev 탐색 실패: {error}\n')
    if not reused:
        save_result(output, result)
    if args.mode == 'find':
        for c in result['candidates']:
            print(f"{c['probability']:.2f} {c['path']}  {c['summary']}".rstrip())
        existence = result['existence'] or {}
        print(f"존재: {existence.get('status', '-')} ({existence.get('found_probability', '-')}) / 파일 {result['files']} / "
              f"비용 {result['usage']['cost']} / {result['error'] or '정상'}")
        if result.get('partial') or result.get('input_partial'):
            print(f"부분 탐색: 제시 {result.get('presented_files', 0)}/{result['files']}, 지시서 전체 확인 및 일반 검색 필요")
        print('paths: ' + ' '.join(c['path'] for c in result['candidates']))
    else:
        print(f"recall {result['recall']} / precision {result['precision']} / 존재 판정 {result['existence_correct']} / "
              f"새 파일 {len(result['new_files'])}")
    print(output.relative_to(repo))


if __name__ == '__main__':
    main()
