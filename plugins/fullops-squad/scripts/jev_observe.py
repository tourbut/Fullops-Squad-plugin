#!/usr/bin/env python3
"""Jev observation for context candidates and completion evidence; never changes gates."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

MODEL = '~typesafe/jev-latest'
URL = 'https://openrouter.ai/api/v1/systemone'
VERSION = 'jev-observe-v2'
MAX_EXCERPT = 4000
REQUIRED = (
    '.fullops-squad/FULLOPS.md', '.fullops-squad/project.md',
    '.fullops-squad/rules/common/README.md',
    '.fullops-squad/rules/common/coding-style.md',
    '.fullops-squad/rules/common/security.md',
    '.fullops-squad/rules/common/testing.md',
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def local_file(repo, name):
    if not isinstance(name, str) or not name or name.startswith('-'):
        raise ValueError('invalid path')
    path = Path(name)
    path = path if path.is_absolute() else repo / path
    if not path.is_relative_to(repo):
        raise ValueError('path outside repository')
    parts = path.relative_to(repo).parts
    if any(part in ('.', '..') or part.startswith('.env') or part.startswith('.secret') or
           re.search(r'(^|[._-])env($|[._-])', part, re.I) or
           part in ('.git', '.codex', '.agents', '.claude', '.ssh', '.aws', '.netrc', '.npmrc', '.pypirc') or
           re.fullmatch(r'(secrets?|credentials?)(\..*)?', part, re.I) or
           re.fullmatch(r'id_(rsa|dsa|ecdsa|ed25519)(\.pub)?', part, re.I) or
           part.lower().endswith(('.pem', '.key', '.p12', '.pfx')) for part in parts):
        raise ValueError('sensitive path')
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != repo and parent.is_relative_to(repo)):
        raise ValueError('symlink path')
    path = path.resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(repo):
        raise ValueError('path outside repository or not a file')
    return path


def safe_text(value, limit=4000):
    if not isinstance(value, str) or len(value) > limit or re.search(
        r'(?i)(?:OPENROUTER_API_KEY|API[_-]?KEY|SECRET|PASSWORD|TOKEN)\s*[:=]\s*\S+|'
        r'-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-(?:or-)?[A-Za-z0-9_-]{12,}', value):
        raise ValueError('sensitive or invalid input text')
    return value


def excerpt(raw, spec):
    """Return a checked, bounded verbatim passage and its source range."""
    if not isinstance(spec, dict) or set(spec) - {'start_line', 'end_line', 'quote'}:
        raise ValueError('invalid excerpt specification')
    if set(spec) not in ({'quote'}, {'start_line', 'end_line'}):
        raise ValueError('choose one exact quote or line span')
    text = raw.decode('utf-8')
    lines = text.splitlines(keepends=True)
    if 'quote' in spec:
        quote = safe_text(spec['quote'])
        if not quote or text.count(quote) != 1:
            raise ValueError('quote missing or ambiguous')
        offset = text.index(quote)
        selected_start = text[:offset].count('\n') + 1
        selected_end = text[:offset + len(quote) - 1].count('\n') + 1
    else:
        if type(spec.get('start_line')) is not int or type(spec.get('end_line')) is not int:
            raise ValueError('line span required')
        selected_start, selected_end = spec['start_line'], spec['end_line']
    if selected_start < 1 or selected_end < selected_start or selected_end > len(lines) or selected_end - selected_start + 1 > 40:
        raise ValueError('invalid line span')
    start, end = max(0, selected_start - 4), min(len(lines), selected_end + 3)
    while end - start > 40 or len(''.join(lines[start:end])) > MAX_EXCERPT:
        left, right = selected_start - 1 - start, end - selected_end
        if right >= left and right:
            end -= 1
        elif left:
            start += 1
        else:
            raise ValueError('excerpt too long')
    passage = ''.join(lines[start:end])
    safe_text(passage)
    return {'start_line': start + 1, 'end_line': end, 'selected_start_line': selected_start,
            'selected_end_line': selected_end, 'text': passage}


def checked_answer(value, labels):
    if not isinstance(value, dict) or value.get('type') != 'choice' or value.get('choice') not in labels:
        raise ValueError('invalid choice')
    probabilities = value.get('probabilities')
    if not isinstance(probabilities, dict) or set(probabilities) != set(labels):
        raise ValueError('invalid distribution')
    if any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
           for p in probabilities.values()) or not 0.98 <= sum(probabilities.values()) <= 1.02:
        raise ValueError('invalid distribution')
    confidence = value.get('confidence')
    if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError('invalid confidence')
    if probabilities[value['choice']] < max(probabilities.values()) - 0.02:
        raise ValueError('choice disagrees with distribution')
    return {k: value[k] for k in ('choice', 'probabilities', 'confidence')}


def verified_bytes(repo, head, path, spec):
    if not isinstance(spec, dict) or type(spec.get('at_head', False)) is not bool or not re.fullmatch(
            r'[0-9a-f]{64}', spec.get('sha256', '') if isinstance(spec.get('sha256'), str) else ''):
        raise ValueError('invalid source hash or commit flag')
    if path.stat().st_size > 65536:
        raise ValueError('source too large')
    raw = path.read_bytes()
    if digest(raw) != spec['sha256']:
        raise ValueError('source hash or size mismatch')
    if spec.get('at_head'):
        saved = subprocess.check_output(['git', '-C', str(repo), 'cat-file', '--filters',  # 체크아웃 변환(CRLF) 적용
                                         f'{head}:{path.relative_to(repo).as_posix()}'], stderr=subprocess.DEVNULL)
        if saved != raw:
            raise ValueError('source differs from head')
    return raw


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', value):
        raise ValueError('invalid candidate or claim ID')
    return value


def key_from_file(path):
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.fullmatch(r'\s*OPENROUTER_API_KEY\s*=\s*["\']?([A-Za-z0-9._-]+)["\']?\s*', line)
        if match:
            return match.group(1)
    raise ValueError('OPENROUTER_API_KEY is unavailable')


def api_key(env_file=None, repo=None):
    """--env-file → 환경 변수 → 레포 루트 .env 순으로 키를 찾는다. 없으면 빈 문자열(Jev 없이 진행)."""
    if env_file:
        return key_from_file(env_file)
    if os.environ.get('OPENROUTER_API_KEY'):
        return os.environ['OPENROUTER_API_KEY']
    local = Path(repo) / '.env' if repo else None
    if local and local.is_file():
        try:
            return key_from_file(local)
        except ValueError:
            pass
    return ''


def cache_path(payload):
    root = Path(os.environ.get('FULLOPS_JEV_CACHE') or Path.home() / '.cache/fullops-squad/jev')
    return root / (digest(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()) + '.json')


def request(payload, key):
    """Same payload, same answer: Jev drifts between runs, so answers are cached by content (as Canny does)."""
    import tempfile
    cached = cache_path(payload)
    try:
        response = json.loads(cached.read_text(encoding='utf-8'))
        response['usage'] = {'input_tokens': 0, 'output_tokens': 0, 'cost': 0}  # no new spend
        response['cached'] = True
        return response, 0.0
    except (OSError, ValueError, TypeError):
        pass
    if not key or not re.fullmatch(r'[A-Za-z0-9._-]+', key):
        raise ValueError('OPENROUTER_API_KEY is unavailable')
    started = time.monotonic()
    # Windows는 열려 있는 NamedTemporaryFile을 다른 프로세스가 열 수 없다(curl exit 26). 닫은 뒤 넘기고 지운다.
    handle, body = tempfile.mkstemp(suffix='.json')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as output:
            json.dump(payload, output, ensure_ascii=False)
        config = f'header = "Authorization: Bearer {key}"\n'  # 키는 명령줄이 아니라 표준입력으로 넘긴다
        result = subprocess.run(
            [shutil.which('curl') or 'curl', '--config', '-', '--silent', '--show-error', '--fail', '--max-time', '30',
             '--header', 'Content-Type: application/json', '--data-binary', '@' + body, URL],
            input=config, text=True, capture_output=True,
        )
    finally:
        os.unlink(body)
    if result.returncode:
        raise RuntimeError('OpenRouter request failed')
    response = json.loads(result.stdout)
    try:  # a cache that cannot be written is not an error; the answer is already in hand
        cached.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = cached.with_suffix(f'.{os.getpid()}.tmp')
        temporary.write_text(json.dumps(response, ensure_ascii=False), encoding='utf-8')
        temporary.chmod(0o600)
        temporary.replace(cached)
    except OSError:
        pass
    return response, round(time.monotonic() - started, 3)


def observe(data, repo, call):
    if not isinstance(data, dict) or not isinstance(data.get('task'), str) or not data['task'].strip():
        raise ValueError('task is required')
    safe_text(data['task'])
    head = data.get('head')
    if not isinstance(head, str) or not re.fullmatch(r'[0-9a-f]{40}', head):
        raise ValueError('full head SHA is required')
    actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', '--verify', head + '^{commit}'], text=True).strip()
    if actual != head:
        raise ValueError('head SHA does not resolve exactly')
    input_hash = digest(json.dumps(data, sort_keys=True, ensure_ascii=False).encode())
    candidates = data.get('candidates', [])
    claims = data.get('claims', [])
    evidence = data.get('evidence', [])
    if not all(isinstance(x, list) for x in (candidates, claims, evidence)):
        raise ValueError('candidates, claims and evidence must be arrays')
    if len(candidates) > 20 or len(claims) > 12 or len(evidence) > 12:
        raise ValueError('too many candidates, claims or evidence files; narrow retrieval first')
    if any(not isinstance(item, dict) for item in candidates + claims + evidence):
        raise ValueError('candidates, claims and evidence must contain objects')
    candidates = [dict(item) for item in candidates]
    ids = [identifier(x['id']) for x in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate candidate ID')
    explicit = data.get('required_paths', [])
    if not isinstance(explicit, list) or any(not isinstance(p, str) for p in explicit):
        raise ValueError('required_paths must be an array of paths')
    required_paths = set(REQUIRED) | set(explicit)
    for item in candidates:
        if type(item.get('required', False)) is not bool:
            raise ValueError('required must be boolean')
        safe_text(item.get('summary', ''), 1000)
    for item in claims:
        safe_text(item['criterion'], 2000)
        safe_text(item['report'], 4000)
        if 'test_command' in item:
            safe_text(item['test_command'], 1000)
    for n, path in enumerate(sorted(required_paths)):
        if path not in [item.get('path') for item in candidates]:
            rid = f'required_{n}'
            while rid in ids:
                rid += '_'
            candidates.append({'id': rid, 'path': path, 'required': True,
                               'summary': 'Required project or task context'})
            ids.append(rid)
    baseline = ids[:]
    context = {'baseline_ids': baseline, 'recommended_ids': baseline[:], 'signals': {}, 'fallback': None,
               'candidate_paths': {item['id']: item.get('path') for item in candidates},
               'required_paths': sorted(required_paths), 'missing_required_paths': []}
    for path in required_paths:
        try:
            local_file(repo, path)
        except (OSError, ValueError):
            context['missing_required_paths'].append(path)
    state_candidates = []
    for item in candidates:
        try:
            path = local_file(repo, item['path'])
            selected = {'id': item['id'], 'path': path.relative_to(repo).as_posix(),
                        'summary': item.get('summary', '')}
            if 'source' in item:
                source = item['source']
                raw = verified_bytes(repo, head, path, source)
                selected['source'] = excerpt(raw, source['span'])
            state_candidates.append(selected)
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, subprocess.CalledProcessError):
            context['fallback'] = 'invalid candidate path'
    context['missing_required_paths'].sort()
    questions = {}
    state = {'task': data['task'], 'candidates': state_candidates}
    for n, item in enumerate(candidates):
        questions[f'c{n}'] = {'type': 'choice', 'instructions':
            f'For task, how necessary is candidate {item["id"]} at {item.get("path", "")} for the worker? Judge its source passage when present.',
            'criteria': {'needed': 'Directly needed to implement or verify the task.',
                         'optional': 'Potentially useful; retain for further exploration.',
                         'irrelevant': 'Clearly unrelated to the task.'}}
        questions[f'x{n}'] = {'type': 'choice', 'instructions':
            f'Does candidate {item["id"]} contain evidence against a factual assumption or proposed approach in task? Judge independently of relevance.',
            'criteria': {'contradicts': 'Source passage challenges a task premise or proposed approach.',
                         'does_not_contradict': 'Source passage does not challenge a premise or approach.',
                         'unclear': 'Insufficient passage or ambiguous relationship; retain for inspection.'}}
    evidence_by_id = {}
    for item in evidence:
        eid = identifier(item['id'])
        if eid in evidence_by_id:
            raise ValueError('duplicate evidence ID')
        evidence_by_id[eid] = item
    checked = {}
    evidence_checks = {}
    for eid, item in evidence_by_id.items():
        try:
            path = local_file(repo, item['path'])
            raw = verified_bytes(repo, head, path, item)
            lines = raw.decode('utf-8').splitlines(keepends=True)
            span = item.get('span', {'start_line': 1, 'end_line': min(len(lines), 40)})
            passage = excerpt(raw, span)
            text = raw.decode('utf-8')
            codes = re.findall(r'(?m)^exit_code=(-?\d+)\r?$', text)  # CRLF 로그 허용
            commands = re.findall(r'(?m)^command=(.*?)\r?$', text)
            exit_code = int(codes[0]) if len(codes) == 1 else None
            command = safe_text(commands[0], 1000) if len(commands) == 1 else None
            if item.get('kind', 'file') not in ('file', 'test_log'):
                raise ValueError('invalid evidence kind')
            checked[eid] = {'status': 'verified', 'path': path.relative_to(repo).as_posix(),
                            'passage': passage, 'coverage': 'complete' if passage['selected_start_line'] == 1 and
                            passage['selected_end_line'] == len(lines) else 'partial', 'exit_code': exit_code,
                            'kind': item.get('kind', 'file'), 'command': command}
        except (OSError, ValueError, UnicodeError, KeyError, TypeError, subprocess.CalledProcessError) as error:
            checked[eid] = {'status': 'unverified', 'reason': str(error) if str(error) in
                            ('quote missing or ambiguous', 'invalid line span', 'excerpt too long',
                             'sensitive path', 'symlink path', 'sensitive or invalid input text') else
                            'missing, changed, or invalid evidence'}
        evidence_checks[eid] = {'path': item.get('path'), 'sha256': item.get('sha256'),
                                'at_head': item.get('at_head', False), 'status': checked[eid]['status'],
                                'reason': checked[eid].get('reason'), 'coverage': checked[eid].get('coverage'),
                                'exit_code': checked[eid].get('exit_code'),
                                'command': checked[eid].get('command'), 'kind': item.get('kind', 'file')}
    claim_ids = [identifier(x['id']) for x in claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError('duplicate claim ID')
    verdicts = {}
    for n, item in enumerate(claims):
        links = item.get('evidence_ids', [])
        if not isinstance(links, list) or any(not isinstance(eid, str) or eid not in checked or
                checked[eid]['status'] != 'verified' for eid in links) or not links:
            verdicts[item['id']] = {'status': 'insufficient_evidence', 'evidence_ids': links,
                                    'decision': 'review', 'reason': 'missing_or_unverified_evidence'}
            continue
        state[f'claim_{n}'] = {'criterion': item['criterion'], 'worker_report': item['report'],
                              'test_command': item.get('test_command'),
                              'evidence': {eid: {k: v for k, v in checked[eid].items() if k != 'status'}
                                           for eid in links}}
        questions[f'v{n}'] = {'type': 'choice', 'instructions':
            f'Does claim_{n}.evidence directly support claim_{n}.worker_report against claim_{n}.criterion? '
            'A partial log or one command never proves a broader test suite passed. Do not infer execution from code alone.',
            'criteria': {'supports': 'Evidence directly supports the reported completion.',
                         'contradicts': 'Evidence shows the reported completion is false.',
                         'insufficient': 'Evidence does not establish either conclusion.'}}
        verdicts[item['id']] = {'status': 'uncertain', 'evidence_ids': links, 'decision': 'review'}
    outcome = {'version': VERSION, 'mode': 'observation', 'head': head, 'requested_model': MODEL,
               'input_sha256': input_hash,
               'question_sha256': digest(json.dumps(questions, sort_keys=True).encode()),
               'context': context, 'evidence_checks': evidence_checks, 'claims': verdicts,
               'usage': None, 'latency_seconds': None,
               'response_model': None, 'error': None}
    sensitive = any(check.get('reason') in ('sensitive path', 'symlink path',
                    'sensitive or invalid input text') for check in evidence_checks.values())
    if context['missing_required_paths'] or context['fallback'] or sensitive:
        context['fallback'] = context['fallback'] or ('sensitive or symlink input' if sensitive else 'missing required path')
        if sensitive:
            outcome['error'] = 'sensitive or symlink input'
        return outcome
    if not questions:
        return outcome
    started = time.monotonic()
    try:
        response, elapsed = call({'model': MODEL, 'state': state, 'questions': questions})
        if not isinstance(response, dict) or type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('invalid response')
        answers = response['answers']
        if not isinstance(answers, dict) or set(answers) != set(questions):
            raise ValueError('invalid answer IDs')
        if not isinstance(response.get('model'), str) or not response['model'].startswith('typesafe/jev-'):
            raise ValueError('invalid response model')
        usage = response.get('usage')
        if (not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                                               for k in ('input_tokens', 'output_tokens')) or
                type(usage.get('cost')) not in (int, float) or
                not math.isfinite(usage['cost']) or usage['cost'] < 0):
            raise ValueError('invalid usage')
        judgments = {qid: checked_answer(answers[qid], question['criteria'])
                     for qid, question in questions.items()}
        outcome['latency_seconds'] = elapsed
        outcome['response_model'] = response.get('model')
        outcome['usage'] = {k: usage[k] for k in ('input_tokens', 'output_tokens', 'cost')}
        for n, item in enumerate(candidates):
            relevance, conflict = judgments[f'c{n}'], judgments[f'x{n}']
            decision = 'keep'
            if (item.get('source') and not item.get('required') and item['path'] not in required_paths and
                    relevance['choice'] == 'irrelevant' and relevance['probabilities']['irrelevant'] >= 0.9 and
                    relevance['confidence'] >= 0.8 and conflict['choice'] == 'does_not_contradict' and
                    conflict['probabilities']['does_not_contradict'] >= 0.9 and conflict['confidence'] >= 0.8):
                decision = 'suggest_omit'
                context['recommended_ids'].remove(item['id'])
            context['signals'][item['id']] = {'relevance': relevance, 'conflict': conflict, 'decision': decision}
        for n, item in enumerate(claims):
            if f'v{n}' in judgments:
                answer = judgments[f'v{n}']
                verdict = verdicts[item['id']]
                verdict['judgment'] = answer
                top = answer['probabilities'][answer['choice']]
                logs = [checked[eid] for eid in verdict['evidence_ids'] if checked[eid]['kind'] == 'test_log']
                command = item.get('test_command')
                matching = [log for log in logs if log['command'] == command] if command else []
                complete = [log for log in matching if log['coverage'] == 'complete']
                reason = None
                if command and any(log['exit_code'] is not None and log['exit_code'] != 0 for log in complete):
                    verdict['status'], verdict['reason'] = 'contradicts', 'test_command_failed'
                    continue
                if command:
                    if not logs:
                        reason = 'missing_test_log'
                    elif not matching:
                        reason = 'test_command_mismatch'
                    elif not complete:
                        reason = 'partial_test_log'
                    elif not any(log['exit_code'] == 0 for log in complete):
                        reason = 'missing_test_result'
                elif logs:
                    reason = 'missing_test_command'
                if reason:
                    verdict['status'], verdict['reason'] = 'insufficient_evidence', reason
                    continue
                verdict['status'] = (('insufficient_evidence' if answer['choice'] == 'insufficient' else answer['choice'])
                                     if top >= 0.9 and answer['confidence'] >= 0.8 else 'uncertain')
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError, json.JSONDecodeError):
        outcome['latency_seconds'] = round(time.monotonic() - started, 3)
        context['recommended_ids'] = baseline[:]
        context['signals'] = {}
        context['fallback'] = 'API or response validation failed'
        for verdict in verdicts.values():
            if verdict['status'] != 'insufficient_evidence':
                verdict['status'] = 'error'
                verdict.pop('judgment', None)
        outcome['error'] = 'API or response validation failed'
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--env-file', help='Read OPENROUTER_API_KEY without sourcing shell code')
    args = parser.parse_args()
    repo = Path(args.repo).resolve(strict=True)
    data = json.loads(Path(args.input).read_text())
    result = observe(data, repo, lambda payload: request(
        payload, api_key(args.env_file, args.repo)))
    output = Path(args.output)
    if output.exists():
        parser.error('output already exists')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    main()
