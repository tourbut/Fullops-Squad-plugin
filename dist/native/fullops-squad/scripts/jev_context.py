#!/usr/bin/env python3
"""dispatch 전 후보 문서를 Jev로 분류해 worker가 먼저 읽을 목록을 줄인다. 제외는 추천일 뿐 게이트가 아니다."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from jev_observe import api_key, digest, excerpt, local_file, observe, request
from work import KEY, active_repo, safe_file, validate_role

SPAN_LINES, SPAN_CHARS, MAX_SOURCE = 34, 3500, 65536


def candidate(repo, head, rel, n):
    """경로 하나를 Jev 후보로 만든다. 원문을 보낼 수 없으면 source 없이 넣어 항상 유지되게 한다."""
    item = {'id': f'c{n}-' + re.sub(r'[^A-Za-z0-9._-]', '-', Path(rel).name)[:60], 'path': rel, 'summary': ''}
    raw = (repo / rel).read_bytes()
    try:
        lines = raw.decode('utf-8').splitlines(keepends=True)
    except UnicodeDecodeError:
        return item, 'not utf-8'
    if len(raw) > MAX_SOURCE or not lines:
        return item, 'too large or empty'
    end = size = 0
    while end < min(len(lines), SPAN_LINES) and size + len(lines[end]) <= SPAN_CHARS:
        size, end = size + len(lines[end]), end + 1
    span = {'start_line': 1, 'end_line': max(end, 1)}
    try:
        excerpt(raw, span)  # observe()는 후보 하나의 원문 거부로 전체 호출을 건너뛴다
    except ValueError:
        return item, 'sensitive or oversized passage'
    saved = subprocess.run(['git', '-C', str(repo), 'cat-file', '--filters', f'{head}:{rel}'], capture_output=True)  # 체크아웃 변환(CRLF) 적용
    item['source'] = {'sha256': digest(raw), 'at_head': saved.returncode == 0 and saved.stdout == raw, 'span': span}
    return item, None


def context(repo, role, key, paths, call, required=()):
    validate_role(repo, role)
    inbox = safe_file(repo, f'.fullops-squad/handovers/to_{role}.md')
    text = inbox.read_text() if inbox.is_file() else ''
    if not text.startswith(f'# {key} — '):
        raise ValueError('인박스에 같은 과제 키의 지시서를 먼저 작성하세요')
    if len(paths) > 20:
        raise ValueError('후보는 20개 이하로 좁히세요')
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    candidates, unsent, refused = [], {}, []
    for n, name in enumerate(dict.fromkeys(paths)):
        try:
            rel = local_file(repo, name).relative_to(repo).as_posix()
        except (OSError, ValueError) as error:
            refused.append({'path': name, 'reason': str(error)})
            continue
        item, reason = candidate(repo, head, rel, n)
        candidates.append(item)
        if reason:
            unsent[rel] = reason
    data = {'task': f'{key}\n' + text[:3500], 'head': head, 'candidates': candidates,
            'required_paths': [inbox.relative_to(repo).as_posix(), *required]}
    try:
        outcome = observe(data, repo, call)
    except ValueError as error:  # 지시서 본문의 민감 문자열 등: Jev 없이 전부 유지한다
        outcome = {'error': f'Jev 생략: {error}', 'context': None}
    return {**outcome, 'task_key': key, 'role': role, 'unsent_sources': unsent, 'refused_paths': refused}


def report(result):
    ctx = result.get('context')
    lines = []
    if ctx:
        signals = ctx['signals']
        label = {'suggest_omit': 'omit?', 'conflict': '충돌 ', 'caution': '주의 '}
        for cid, path in ctx['candidate_paths'].items():
            signal = signals.get(cid)
            note = (f"관련 {signal['relevant']:.2f} 근거 {signal['evidence']:.2f} 충돌 {signal['contradicts']:.2f} "
                    f"지시문 {signal['injection']:.2f}") if signal else result['unsent_sources'].get(path, '')
            lines.append(f"{label.get(signal and signal['decision'], 'keep ')} {path}  {note}".rstrip())
        if ctx.get('conflict_ids'):
            lines.append('충돌: 지시서의 전제나 접근과 어긋나는 내용이 있다. 지시서에 "지시 전제와 충돌 — 먼저 확인"으로 적는다')
        if ctx.get('caution_ids'):
            lines.append('주의: AI에게 지시하는 문구가 있다. 지시서에 "지시문 포함 — 내용만 참고"로 적는다')
    for item in result['refused_paths']:
        lines.append(f"거부   {item['path']}  {item['reason']}")
    usage = result.get('usage') or {}
    lines.append(f"Jev: {result.get('response_model') or '-'} / 비용 {usage.get('cost', '-')} / "
                 f"{result.get('latency_seconds') or '-'}초 / fallback {ctx and ctx.get('fallback') or result.get('error') or '없음'}")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--role', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--paths', nargs='+', required=True, help='그래프·검색으로 좁힌 후보 20개 이하')
    parser.add_argument('--required', nargs='*', default=[], help='항상 유지할 추가 경로')
    parser.add_argument('--env-file', help='OPENROUTER_API_KEY를 코드 실행 없이 읽는다')
    args = parser.parse_args()
    try:
        if not KEY.fullmatch(args.key):
            raise ValueError('과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요')
        repo = active_repo(args.repo)
        output = safe_file(repo, f'.fullops-squad/docs/evaluations/jev/{args.key}-context.json')
        if output.exists():
            raise ValueError(f'기존 결과를 보존합니다: {output.relative_to(repo)}')

        def call(payload):
            return request(payload, api_key(args.env_file, repo))
        result = context(repo, args.role, args.key, args.paths, call, args.required)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Jev 문맥 분류 실패: {error}\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(report(result))
    print(output.relative_to(repo))


if __name__ == '__main__':
    main()
