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
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'fixture')
    head = git(repo, 'rev-parse', 'HEAD')
    relevant = (repo / 'relevant.py').read_bytes()
    base = {'task': 'Verify fixed() works', 'head': head,
            'candidates': [{'id': 'good', 'path': 'relevant.py'},
                           {'id': 'old', 'path': 'irrelevant.py'}],
            'claims': [{'id': 'claim', 'criterion': 'fixed returns True',
                        'report': 'fixed returns True', 'evidence_ids': ['source']}],
            'evidence': [{'id': 'source', 'path': 'relevant.py', 'at_head': True,
                          'sha256': hashlib.sha256(relevant).hexdigest()}]}

    def response(payload):
        answers = {}
        for qid in payload['questions']:
            choice = 'irrelevant' if qid == 'c1' else ('supports' if qid.startswith('v') else 'needed')
            answers[qid] = {'type': 'choice', 'choice': choice, 'confidence': 0.99}
        return {'model': 'typesafe/jev-1.13-20260917', 'answers': answers,
                'usage': {'input_tokens': 100, 'output_tokens': 10, 'cost': 0.001}}, 0.2

    observed = jev.observe(json.loads(json.dumps(base)), repo, response)
    assert observed['context']['recommended_ids'][0] == 'good'
    assert 'old' not in observed['context']['recommended_ids'], observed
    assert len(observed['context']['recommended_ids']) == 1 + len(jev.REQUIRED)
    assert observed['claims']['claim']['status'] == 'supports'
    assert observed['usage']['cost'] == 0.001

    wrong = jev.observe(json.loads(json.dumps(base)), repo,
                        lambda payload: ({'answers': {'bogus': {'type': 'choice', 'choice': 'irrelevant', 'confidence': 1}}}, 0))
    assert wrong['context']['recommended_ids'] == wrong['context']['baseline_ids']
    assert wrong['claims']['claim']['status'] == 'unjudged'

    def failed(payload):
        raise RuntimeError('network unavailable')
    down = jev.observe(json.loads(json.dumps(base)), repo, failed)
    assert down['context']['recommended_ids'] == down['context']['baseline_ids']

    missing = json.loads(json.dumps(base))
    missing['evidence'][0]['sha256'] = '0' * 64
    result = jev.observe(missing, repo, response)
    assert result['claims']['claim']['status'] == 'insufficient_evidence'

    def contradicts(payload):
        answer, elapsed = response(payload)
        answer['answers']['v0']['choice'] = 'contradicts'
        return answer, elapsed
    result = jev.observe(json.loads(json.dumps(base)), repo, contradicts)
    assert result['claims']['claim']['status'] == 'contradicts'

    (repo / jev.REQUIRED[0]).unlink()
    result = jev.observe(json.loads(json.dumps(base)), repo, response)
    assert result['context']['recommended_ids'] == result['context']['baseline_ids']
    assert jev.REQUIRED[0] in result['context']['missing_required_paths']
    (repo / jev.REQUIRED[0]).write_text('mandatory context\n')

    bad = json.loads(json.dumps(base))
    bad['candidates'][0]['path'] = '../escape.py'
    result = jev.observe(bad, repo, response)
    assert result['context']['recommended_ids'] == result['context']['baseline_ids']

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
