"""실제 OCR delegate와 임시 레포로 준비·누락·SHA·규칙·심각도 검증을 확인한다."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'


with tempfile.TemporaryDirectory(prefix='fullops-delegate-') as tmp, tempfile.TemporaryDirectory(prefix='fullops-snapshot-') as snapshots:
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
    def run(mode, key='REVIEW-1'):
        return subprocess.run(['python3', str(SCRIPTS / 'review.py'), mode, '--repo', tmp,
                               '--key', key, '--from', base, '--to', 'HEAD'], capture_output=True, text=True)
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
    managed = subprocess.run(['python3', str(SCRIPTS / 'review.py'), 'snapshot', '--repo', tmp,
        '--key', 'REVIEW-LEGACY', '--to', 'HEAD', '--implementer-session', 'author-legacy',
        '--reviewer-session', 'reviewer-legacy', '--owner', 'coordinator'], check=True, capture_output=True, text=True)
    managed_path = managed.stdout.strip()
    try:
        prepared = run('prepare', 'REVIEW-LEGACY')
        assert prepared.returncode == 0, prepared.stderr
        legacy = json.loads((repo / '.fullops-squad/docs/evaluations/qa-reports/REVIEW-LEGACY-review/result.json').read_text())
        assert legacy['review_schema_version'] == 2 and legacy['independence']['snapshot_path'] == managed_path
        assert legacy['independence']['reviewer_session'] == 'reviewer-legacy'
    finally:
        git('worktree', 'remove', managed_path)
    agents = repo / '.fullops-squad/orca-agents.md'
    agents.write_text(agents.read_text(encoding='utf-8').replace('- 설계 역할: `implementer`',
                      '- 설계 역할: `designer`\n- 제품 기획 역할: `designer`\n- 기술 계획 역할: `implementer`'), encoding='utf-8')
    marker = repo / '.fullops-squad/fullops.json'
    config = json.loads(marker.read_text(encoding='utf-8'))
    config['roles']['designer'] = 'fullops/architecture'
    marker.write_text(json.dumps(config), encoding='utf-8')
    assert run('prepare', 'REVIEW-2').returncode == 0
    directory = repo / '.fullops-squad/docs/evaluations/qa-reports/REVIEW-2-review'
    path = directory / 'result.json'
    data = json.loads(path.read_text())
    assert data['review_schema_version'] == 2 and data['independence']['snapshot_head'] == git('rev-parse', 'HEAD')
    for item in data['files']:
        item.update(review_status='reviewed', reason='diff와 요구사항 확인')
    data.update(reviewer='independent reviewer', conclusion='verified')
    snapshot = Path(snapshots) / 'review'
    git('worktree', 'add', '--detach', str(snapshot), 'HEAD')
    lint_result = subprocess.run(['python3', str(SCRIPTS / 'lint.py'), '--repo', str(snapshot), '--from', base,
                                 '--out', str(directory / 'lint.json')], capture_output=True, text=True)
    assert (directory / 'lint.json').is_file(), lint_result.stderr
    save()
    assert '세션 ID' in run('check', 'REVIEW-2').stderr
    independence = data['independence']
    independence.update(implementer_session='author-1', reviewer_session='author-1', snapshot_path=str(snapshot))
    save()
    assert '세션 ID' in run('check', 'REVIEW-2').stderr
    independence['reviewer_session'] = 'reviewer-2'
    save()
    checked = run('check', 'REVIEW-2')
    assert checked.returncode == 0, checked.stdout + checked.stderr
    data.pop('review_schema_version')
    save()
    assert '스키마' in run('check', 'REVIEW-2').stderr
    data['review_schema_version'] = 2
    independence['snapshot_path'] = str(repo)
    save()
    assert '고정 head' in run('check', 'REVIEW-2').stderr
    independence['snapshot_path'] = str(snapshot)
    subprocess.run(['git', '-C', str(snapshot), 'checkout', '-q', '-b', 'review-branch'], check=True)
    save()
    assert 'detached' in run('check', 'REVIEW-2').stderr
    subprocess.run(['git', '-C', str(snapshot), 'checkout', '-q', '--detach'], check=True)
    (snapshot / 'unexpected.txt').write_text('change')
    assert '변경' in run('check', 'REVIEW-2').stderr
    (snapshot / 'unexpected.txt').unlink()
    independence['snapshot_head'] = base
    save()
    assert '고정 head' in run('check', 'REVIEW-2').stderr
    independence['snapshot_head'] = git('rev-parse', 'HEAD')
    save()
    checked = run('check', 'REVIEW-2')
    assert checked.returncode == 0, checked.stdout + checked.stderr
    git('worktree', 'remove', str(snapshot))
    print('PASS: real OCR prepare, document/test inclusion, record preservation, pending/missing/high/rule/SHA/lint gates')
    print('PASS: independent sessions, schema preservation, separate clean detached snapshot, fixed SHA')
    print('PASS: managed snapshot prepare records independent identity in legacy coor configuration')
