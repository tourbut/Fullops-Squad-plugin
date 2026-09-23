#!/usr/bin/env python3
"""Small synthetic checks for the observation CLI."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/fullops-squad/scripts/jev_observe.py'
spec = importlib.util.spec_from_file_location('jev_observe', SCRIPT)
jev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jev)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


with tempfile.TemporaryDirectory() as directory:
    repo = Path(directory).resolve()
    git(repo, 'init', '-q')
    git(repo, 'config', 'user.email', 'test@example.invalid')
    git(repo, 'config', 'user.name', 'Test')
    for path in jev.REQUIRED:
        file = repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('mandatory context\n')
    (repo / 'relevant.py').write_text('def fixed(): return True\n')
    (repo / 'irrelevant.py').write_text('old unrelated code\n')
    (repo / 'conflict.py').write_text('The proposed assumption is false.\n')
    (repo / 'test.log').write_text('command=python3 -m test\n1 test passed\nexit_code=0\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'fixture')
    head = git(repo, 'rev-parse', 'HEAD')
    relevant = (repo / 'relevant.py').read_bytes()
    irrelevant = (repo / 'irrelevant.py').read_bytes()
    conflict = (repo / 'conflict.py').read_bytes()
    log = (repo / 'test.log').read_bytes()
    base = {'task': 'Verify fixed() works', 'head': head,
            'candidates': [{'id': 'good', 'path': 'relevant.py', 'source':
                            {'sha256': hashlib.sha256(relevant).hexdigest(), 'at_head': True,
                             'span': {'start_line': 1, 'end_line': 1}}},
                           {'id': 'old', 'path': 'irrelevant.py', 'source':
                            {'sha256': hashlib.sha256(irrelevant).hexdigest(), 'at_head': True,
                             'span': {'start_line': 1, 'end_line': 1}}},
                           {'id': 'contrary', 'path': 'conflict.py', 'source':
                            {'sha256': hashlib.sha256(conflict).hexdigest(), 'at_head': True,
                             'span': {'quote': 'The proposed assumption is false.'}}},
                           {'id': 'summary_only', 'path': 'irrelevant.py', 'summary': 'unrelated'}],
            'claims': [{'id': 'claim', 'criterion': 'fixed returns True',
                        'report': 'fixed returns True', 'evidence_ids': ['source']}],
            'evidence': [{'id': 'source', 'path': 'relevant.py', 'at_head': True,
                          'sha256': hashlib.sha256(relevant).hexdigest(),
                          'span': {'quote': 'def fixed(): return True'}}]}

    def response(payload):
        answers = {}
        for qid in payload['questions']:
            labels = list(payload['questions'][qid]['criteria'])
            choice = ('irrelevant' if qid in ('c1', 'c2', 'c3') else
                      'contradicts' if qid == 'x2' else
                      'does_not_contradict' if qid.startswith('x') else
                      'supports' if qid.startswith('v') else 'needed')
            answers[qid] = {'type': 'choice', 'choice': choice, 'confidence': 0.99,
                            'probabilities': {label: 1.0 if label == choice else 0.0 for label in labels}}
        return {'model': 'typesafe/jev-1.13-20260917', 'answers': answers,
                'usage': {'input_tokens': 100, 'output_tokens': 10, 'cost': 0.001}}, 0.2

    observed = jev.observe(json.loads(json.dumps(base)), repo, response)
    assert observed['context']['recommended_ids'][0] == 'good'
    assert 'old' not in observed['context']['recommended_ids'], observed
    assert 'contrary' in observed['context']['recommended_ids']
    assert 'summary_only' in observed['context']['recommended_ids']
    assert len(observed['context']['recommended_ids']) == 3 + len(jev.REQUIRED)
    assert observed['claims']['claim']['status'] == 'supports'
    assert observed['context']['signals']['contrary']['conflict']['choice'] == 'contradicts'
    assert observed['context']['signals']['old']['decision'] == 'suggest_omit'
    assert observed['usage']['cost'] == 0.001

    wrong = jev.observe(json.loads(json.dumps(base)), repo,
                        lambda payload: ({'answers': {'bogus': {'type': 'choice', 'choice': 'irrelevant', 'confidence': 1}}}, 0))
    assert wrong['context']['recommended_ids'] == wrong['context']['baseline_ids']
    assert wrong['claims']['claim']['status'] == 'error'

    def failed(payload):
        raise RuntimeError('network unavailable')
    down = jev.observe(json.loads(json.dumps(base)), repo, failed)
    assert down['context']['recommended_ids'] == down['context']['baseline_ids']
    assert down['claims']['claim']['status'] == 'error'

    missing = json.loads(json.dumps(base))
    missing['evidence'][0]['sha256'] = '0' * 64
    result = jev.observe(missing, repo, response)
    assert result['claims']['claim']['status'] == 'insufficient_evidence'

    unmatched = json.loads(json.dumps(base))
    unmatched['evidence'][0]['span']['quote'] = 'never in file'
    result = jev.observe(unmatched, repo, response)
    assert result['claims']['claim']['status'] == 'insufficient_evidence'
    assert result['evidence_checks']['source']['reason'] == 'quote missing or ambiguous'

    partial = json.loads(json.dumps(base))
    partial['claims'][0]['criterion'] = 'all tests passed'
    partial['claims'][0]['report'] = 'all tests passed'
    partial['evidence'][0] = {'id': 'source', 'path': 'test.log', 'kind': 'test_log',
                              'sha256': hashlib.sha256(log).hexdigest(),
                              'span': {'start_line': 2, 'end_line': 2}}
    result = jev.observe(partial, repo, response)
    assert result['claims']['claim']['status'] == 'uncertain'
    assert result['evidence_checks']['source']['coverage'] == 'partial'
    assert result['evidence_checks']['source']['exit_code'] == 0
    complete = json.loads(json.dumps(partial))
    complete['claims'][0]['test_command'] = 'python3 -m test'
    complete['evidence'][0]['span'] = {'start_line': 1, 'end_line': 3}
    result = jev.observe(complete, repo, response)
    assert result['claims']['claim']['status'] == 'supports'
    complete['claims'][0]['test_command'] = 'npm test'
    result = jev.observe(complete, repo, response)
    assert result['claims']['claim']['status'] == 'uncertain'

    def contradicts(payload):
        answer, elapsed = response(payload)
        answer['answers']['v0']['choice'] = 'contradicts'
        answer['answers']['v0']['probabilities'] = {'supports': 0.0, 'contradicts': 1.0, 'insufficient': 0.0}
        return answer, elapsed
    result = jev.observe(json.loads(json.dumps(base)), repo, contradicts)
    assert result['claims']['claim']['status'] == 'contradicts'

    def insufficient(payload):
        answer, elapsed = response(payload)
        answer['answers']['v0']['choice'] = 'insufficient'
        answer['answers']['v0']['probabilities'] = {'supports': 0.0, 'contradicts': 0.0, 'insufficient': 1.0}
        return answer, elapsed
    result = jev.observe(json.loads(json.dumps(base)), repo, insufficient)
    assert result['claims']['claim']['status'] == 'insufficient_evidence'

    (repo / jev.REQUIRED[0]).unlink()
    result = jev.observe(json.loads(json.dumps(base)), repo, response)
    assert result['context']['recommended_ids'] == result['context']['baseline_ids']
    assert jev.REQUIRED[0] in result['context']['missing_required_paths']
    (repo / jev.REQUIRED[0]).write_text('mandatory context\n')

    bad = json.loads(json.dumps(base))
    bad['candidates'][0]['path'] = '../escape.py'
    result = jev.observe(bad, repo, response)
    assert result['context']['recommended_ids'] == result['context']['baseline_ids']

    calls = []
    def no_call(payload):
        calls.append(payload)
        raise AssertionError('API must not be called')
    secret = repo / '.env.local'
    secret.write_text('OPENROUTER_API_KEY=fake-only-fixture\n')
    unsafe = json.loads(json.dumps(base))
    unsafe['evidence'][0] = {'id': 'source', 'path': '.env.local',
                             'sha256': hashlib.sha256(secret.read_bytes()).hexdigest()}
    result = jev.observe(unsafe, repo, no_call)
    assert not calls and result['context']['fallback'] == 'sensitive or symlink input'
    assert result['evidence_checks']['source']['status'] == 'unverified'
    blocked_input, blocked_output = repo / 'blocked-input.json', repo / 'blocked-output.json'
    blocked_input.write_text(json.dumps(unsafe))
    subprocess.run([sys.executable, str(SCRIPT), '--repo', str(repo), '--input', str(blocked_input),
                    '--output', str(blocked_output), '--env-file', str(repo / 'no-key-file')],
                   check=True, capture_output=True, text=True)
    assert json.loads(blocked_output.read_text())['context']['fallback'] == 'sensitive or symlink input'

    unsafe = json.loads(json.dumps(base))
    unsafe['candidates'][0]['path'] = '.env.local'
    result = jev.observe(unsafe, repo, no_call)
    assert not calls and result['context']['recommended_ids'] == result['context']['baseline_ids']

    (repo / 'linked.py').symlink_to(repo / 'relevant.py')
    unsafe = json.loads(json.dumps(base))
    unsafe['evidence'][0]['path'] = 'linked.py'
    result = jev.observe(unsafe, repo, no_call)
    assert not calls and result['evidence_checks']['source']['reason'] == 'symlink path'

    for field, value in [('summary', 'OPENROUTER_API_KEY=fake-only-fixture'),
                         ('report', 'token: fake-only-fixture')]:
        unsafe = json.loads(json.dumps(base))
        (unsafe['candidates'][0] if field == 'summary' else unsafe['claims'][0])[field] = value
        try:
            jev.observe(unsafe, repo, no_call)
            raise AssertionError('sensitive text accepted')
        except ValueError:
            pass
        assert not calls

    for invalid in (None, [], {}, {'type': 'choice', 'choice': 'invented', 'confidence': 1,
                                'probabilities': {'invented': 1}},
                    {'type': 'choice', 'choice': 'needed', 'confidence': float('nan'),
                     'probabilities': {'needed': 1, 'optional': 0, 'irrelevant': 0}},
                    {'type': 'choice', 'choice': 'needed', 'confidence': 1,
                     'probabilities': {'needed': float('nan'), 'optional': 0, 'irrelevant': 0}},
                    {'type': 'choice', 'choice': 'needed', 'confidence': 1,
                     'probabilities': {'needed': 1.5, 'optional': 0, 'irrelevant': 0}}):
        def malformed(payload):
            answer, elapsed = response(payload)
            answer['answers']['c0'] = invalid
            return answer, elapsed
        result = jev.observe(json.loads(json.dumps(base)), repo, malformed)
        assert result['context']['recommended_ids'] == result['context']['baseline_ids']
        assert result['claims']['claim']['status'] == 'error'

    def bad_usage(payload):
        answer, elapsed = response(payload)
        answer['usage']['cost'] = float('nan')
        return answer, elapsed
    result = jev.observe(json.loads(json.dumps(base)), repo, bad_usage)
    assert result['claims']['claim']['status'] == 'error'
    assert result['context']['recommended_ids'] == result['context']['baseline_ids']

    def uncertain(payload):
        answer, elapsed = response(payload)
        answer['answers']['v0'].update(choice='supports', confidence=0.1,
                                       probabilities={'supports': 0.5, 'contradicts': 0.25,
                                                      'insufficient': 0.25})
        return answer, elapsed
    result = jev.observe(json.loads(json.dumps(base)), repo, uncertain)
    assert result['claims']['claim']['status'] == 'uncertain'
    assert result['claims']['claim']['judgment']['probabilities']['supports'] == 0.5

    real_repo = SCRIPT.parents[3]
    cases = json.loads((SCRIPT.parents[3] / 'tests/fixtures/jev-observe-cases.json').read_text())
    assert {case['human_label'] for case in cases} == {'supports', 'insufficient'}
    for case in cases:
        source = subprocess.check_output(['git', '-C', str(real_repo), 'show',
                                          f'{case["head"]}:{case["evidence_path"]}']).decode()
        assert source.count(case['quote']) == 1
        assert case['reason']

    if len(sys.argv) == 3 and sys.argv[1] == '--live-env-file':
        input_file, output_file = repo / 'input.json', repo / 'output.json'
        input_file.write_text(json.dumps(base))
        subprocess.run([sys.executable, str(SCRIPT), '--repo', str(repo),
                        '--input', str(input_file), '--output', str(output_file),
                        '--env-file', sys.argv[2]], check=True, capture_output=True, text=True)
        live = json.loads(output_file.read_text())
        print(json.dumps({'fallback': live['context']['fallback'],
                          'recommended_count': len(live['context']['recommended_ids']),
                          'claim_status': live['claims']['claim']['status'],
                          'response_model': live['response_model'], 'usage': live['usage'],
                          'latency_seconds': live['latency_seconds']}))

print('synthetic Jev observation checks passed')
