#!/usr/bin/env python3
"""Jev observation for context candidates and completion evidence; never changes gates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

MODEL = '~typesafe/jev-latest'
URL = 'https://openrouter.ai/api/v1/systemone'
VERSION = 'jev-observe-v1'
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
    path = path.resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(repo) or path.name == '.env':
        raise ValueError('path outside repository or not a file')
    return path


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', value):
        raise ValueError('invalid candidate or claim ID')
    return value


def key_from_file(path):
    for line in Path(path).read_text().splitlines():
        match = re.fullmatch(r'\s*OPENROUTER_API_KEY\s*=\s*["\']?([A-Za-z0-9._-]+)["\']?\s*', line)
        if match:
            return match.group(1)
    raise ValueError('OPENROUTER_API_KEY is unavailable')


def request(payload, key):
    import tempfile
    if not key or not re.fullmatch(r'[A-Za-z0-9._-]+', key):
        raise ValueError('OPENROUTER_API_KEY is unavailable')
    started = time.monotonic()
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8') as body:
        json.dump(payload, body, ensure_ascii=False)
        body.flush()
        config = f'header = "Authorization: Bearer {key}"\n'
        result = subprocess.run(
            ['curl', '--config', '-', '--silent', '--show-error', '--fail', '--max-time', '30',
             '--header', 'Content-Type: application/json', '--data-binary', '@' + body.name, URL],
            input=config, text=True, capture_output=True,
        )
    if result.returncode:
        raise RuntimeError('OpenRouter request failed')
    return json.loads(result.stdout), round(time.monotonic() - started, 3)


def observe(data, repo, call):
    if not isinstance(data.get('task'), str) or not data['task'].strip():
        raise ValueError('task is required')
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
    candidates = [dict(item) for item in candidates]
    ids = [identifier(x['id']) for x in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate candidate ID')
    explicit = data.get('required_paths', [])
    if not isinstance(explicit, list) or any(not isinstance(p, str) for p in explicit):
        raise ValueError('required_paths must be an array of paths')
    required_paths = set(REQUIRED) | set(explicit)
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
    for item in candidates:
        try:
            local_file(repo, item['path'])
        except (OSError, ValueError, KeyError):
            context['fallback'] = 'invalid candidate path'
    context['missing_required_paths'].sort()
    questions = {}
    state = {'task': data['task'], 'candidates': candidates}
    for n, item in enumerate(candidates):
        questions[f'c{n}'] = {'type': 'choice', 'instructions':
            f'For task, how necessary is candidate {item["id"]} at {item.get("path", "")} for the worker? Judge only this candidate.',
            'criteria': {'needed': 'Directly needed to implement or verify the task.',
                         'optional': 'Potentially useful; retain for further exploration.',
                         'irrelevant': 'Clearly unrelated to the task.'}}
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
            if type(item.get('at_head', False)) is not bool:
                raise ValueError('at_head must be boolean')
            path = local_file(repo, item['path'])
            raw = path.read_bytes()
            if len(raw) > 65536 or digest(raw) != item['sha256']:
                raise ValueError('evidence hash or size mismatch')
            if item.get('at_head'):
                saved = subprocess.check_output(['git', '-C', str(repo), 'show',
                                                 f'{head}:{path.relative_to(repo)}'], stderr=subprocess.DEVNULL)
                if saved != raw:
                    raise ValueError('evidence differs from head')
            checked[eid] = {'status': 'verified', 'text': raw.decode('utf-8')}
        except (OSError, ValueError, UnicodeError, KeyError, subprocess.CalledProcessError):
            checked[eid] = {'status': 'missing_or_changed'}
        evidence_checks[eid] = {'path': item.get('path'), 'sha256': item.get('sha256'),
                                'at_head': item.get('at_head', False), 'status': checked[eid]['status']}
    claim_ids = [identifier(x['id']) for x in claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError('duplicate claim ID')
    verdicts = {}
    for n, item in enumerate(claims):
        links = item.get('evidence_ids', [])
        if not isinstance(links, list) or any(eid not in checked or checked[eid]['status'] != 'verified' for eid in links) or not links:
            verdicts[item['id']] = {'status': 'insufficient_evidence', 'evidence_ids': links}
            continue
        text = '\n'.join(f'{eid}: {checked[eid]["text"]}' for eid in links)
        state[f'claim_{n}'] = {'criterion': item['criterion'], 'worker_report': item['report'], 'evidence': text}
        questions[f'v{n}'] = {'type': 'choice', 'instructions':
            f'Does claim_{n}.evidence support claim_{n}.worker_report against claim_{n}.criterion? Use only the cited evidence.',
            'criteria': {'supports': 'Evidence directly supports the reported completion.',
                         'contradicts': 'Evidence shows the reported completion is false.',
                         'insufficient': 'Evidence does not establish either conclusion.'}}
        verdicts[item['id']] = {'status': 'unjudged', 'evidence_ids': links}
    outcome = {'version': VERSION, 'mode': 'observation', 'head': head, 'requested_model': MODEL,
               'input_sha256': input_hash,
               'question_sha256': digest(json.dumps(questions, sort_keys=True).encode()),
               'context': context, 'evidence_checks': evidence_checks, 'claims': verdicts,
               'usage': None, 'latency_seconds': None,
               'response_model': None, 'error': None}
    if context['missing_required_paths'] or context['fallback']:
        context['fallback'] = context['fallback'] or 'missing required path'
        return outcome
    if not questions:
        return outcome
    try:
        response, elapsed = call({'model': MODEL, 'state': state, 'questions': questions})
        answers = response['answers']
        if not isinstance(answers, dict) or set(answers) != set(questions):
            raise ValueError('invalid answer IDs')
        if not isinstance(response.get('model'), str) or not response['model'].startswith('typesafe/jev-'):
            raise ValueError('invalid response model')
        usage = response.get('usage')
        if not isinstance(usage, dict) or any(type(usage.get(k)) not in (int, float) or usage[k] < 0
                                               for k in ('input_tokens', 'output_tokens', 'cost')):
            raise ValueError('invalid usage')
        for qid, question in questions.items():
            answer = answers[qid]
            if answer.get('type') != 'choice' or answer.get('choice') not in question['criteria']:
                raise ValueError('invalid choice')
            if type(answer.get('confidence')) not in (int, float) or not 0 <= answer['confidence'] <= 1:
                raise ValueError('invalid confidence')
        outcome['latency_seconds'] = elapsed
        outcome['response_model'] = response.get('model')
        outcome['usage'] = {k: usage[k] for k in ('input_tokens', 'output_tokens', 'cost')}
        for n, item in enumerate(candidates):
            answer = answers[f'c{n}']
            context['signals'][item['id']] = {'choice': answer['choice'], 'confidence': answer['confidence']}
            if answer['choice'] == 'irrelevant' and answer['confidence'] >= 0.8 and not item.get('required') and item['path'] not in required_paths:
                context['recommended_ids'].remove(item['id'])
        for n, item in enumerate(claims):
            if f'v{n}' in answers:
                answer = answers[f'v{n}']
                verdicts[item['id']]['status'] = answer['choice']
                verdicts[item['id']]['confidence'] = answer['confidence']
    except (KeyError, TypeError, ValueError, RuntimeError, OSError, json.JSONDecodeError):
        context['recommended_ids'] = baseline[:]
        context['signals'] = {}
        context['fallback'] = 'API or response validation failed'
        for verdict in verdicts.values():
            if verdict['status'] == 'unjudged':
                verdict['status'] = 'unjudged'
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
    key = key_from_file(args.env_file) if args.env_file else os.environ.get('OPENROUTER_API_KEY', '')
    result = observe(data, repo, lambda payload: request(payload, key))
    output = Path(args.output)
    if output.exists():
        parser.error('output already exists')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    main()
