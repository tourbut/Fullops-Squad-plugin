"""실제 OCR delegate와 임시 레포로 준비·누락·SHA·규칙·심각도 검증을 확인한다."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'


with tempfile.TemporaryDirectory(prefix='fullops-delegate-') as tmp:
    repo = Path(tmp)
    def git(*args):
        return subprocess.check_output(['git', '-C', tmp, *args], text=True).strip()
    git('init', '-q', '-b', 'main')
    def commit():
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-q', '--allow-empty', '-m', 'test')
    subprocess.run(['python3', str(SCRIPTS / 'setup.py'), '--repo', tmp,
                    '--roles', 'implementer', '--local-only'], check=True, capture_output=True)
    git('add', '.')
    commit()
    base = git('rev-parse', 'HEAD')
    for name in ['sample.py', 'guide.md', 'sample.test.ts', 'scene.tscn']:
        (repo / name).write_text('sample\n')
    evidence = repo / '.fullops-squad/docs/evaluations/qa-reports/K-evidence'
    evidence.mkdir(parents=True)
    (evidence / 'frame.png').write_bytes(b'png')
    (evidence / 'manifest.json').write_text('{}\n')
    git('add', '.')
    commit()
    lint_out = repo / '.git/fullops-lint.json'
    subprocess.run(['python3', str(SCRIPTS / 'lint.py'), '--repo', tmp, '--from', base, '--out', str(lint_out)],
                   capture_output=True)
    def run(mode):
        return subprocess.run(['python3', str(SCRIPTS / 'review.py'), mode, '--repo', tmp,
                               '--key', 'REVIEW-1', '--from', base, '--to', 'HEAD'], capture_output=True, text=True)
    result = run('prepare')
    assert result.returncode == 0, result.stderr
    directory = repo / '.fullops-squad/docs/evaluations/qa-reports/REVIEW-1-review'
    path = directory / 'result.json'
    preview = json.loads((directory / 'preview.json').read_text())
    assert {f['path'] for f in preview['reviewable_files']} == {'sample.py', 'guide.md', 'sample.test.ts', '.fullops-squad/docs/evaluations/qa-reports/K-evidence/manifest.json'}
    assert sorted(f['path'] for f in preview['excluded_files']) == [
        '.fullops-squad/docs/evaluations/qa-reports/K-evidence/frame.png', 'scene.tscn']  # 증거 이미지는 기본 exclude
    before = path.read_bytes()
    assert run('prepare').returncode != 0 and path.read_bytes() == before
    assert run('check').returncode != 0  # pending
    data = json.loads(path.read_text())
    assert len(data['files']) == 6  # OCR 제외 파일도 최종 체크리스트에 포함한다.
    status = {f['path'].split('/')[-1]: f['review_status'] for f in data['files']}
    assert status['frame.png'] == 'skipped' and status['scene.tscn'] == 'pending'  # 제외된 증거만 미리 채운다
    assert status['manifest.json'] == 'pending'  # 증거 요약은 리뷰 대상
    for item in data['files']:
        item.update(review_status='reviewed', reason='diff와 관련 요구사항 확인')
    data.update(reviewer='test reviewer', conclusion='verified')
    def save():
        path.write_text(json.dumps(data))
    save()
    assert 'lint' in run('check').stderr  # lint 결과 누락
    (directory / 'lint.json').write_bytes(lint_out.read_bytes())
    assert run('check').returncode == 0
    removed = data['files'].pop()
    save()
    assert run('check').returncode != 0  # missing
    data['files'].append(removed)
    data['findings'] = [{'path': 'sample.py', 'content': 'test', 'severity': 'high', 'resolved': False}]
    save()
    assert run('check').returncode != 0
    data['findings'][0]['resolved'] = True
    save()
    assert run('check').returncode == 0
    rule = repo / '.fullops-squad/review/rule.json'
    original = rule.read_bytes()
    rule.write_bytes(original + b'\n')
    assert run('check').returncode != 0
    rule.write_bytes(original)
    commit()
    assert run('check').returncode != 0  # new head
    print('PASS: real OCR prepare, document/test inclusion, record preservation, pending/missing/high/rule/SHA/lint gates')
