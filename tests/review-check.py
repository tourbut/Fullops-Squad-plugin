"""실제 OCR delegate와 임시 레포로 준비·누락·SHA·규칙·심각도 검증을 확인한다.
줄끝이 다른 체크아웃의 기록 검증과 Windows 경로(os.name == 'nt'에서만, 아니면 SKIP 출력)도 확인한다."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import review


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
    def run(mode, key='REVIEW-1', extra=()):
        return subprocess.run(['python3', str(SCRIPTS / 'review.py'), mode, '--repo', tmp,
                               '--key', key, '--from', base, '--to', 'HEAD', *extra], capture_output=True, text=True)
    reusable = repo / '.git/fullops-gate/lint-result.json'
    assert reusable.read_bytes() == lint_out.read_bytes()
    reused = run('prepare', 'REUSED', ('--lint', str(reusable)))
    assert reused.returncode == 0, reused.stderr
    assert (repo / '.fullops-squad/docs/evaluations/qa-reports/REUSED-review/lint.json').read_bytes() == reusable.read_bytes()
    invalid = json.loads(reusable.read_text())
    invalid['head'] = base
    bad = repo / '.git/bad-lint.json'
    bad.write_text(json.dumps(invalid))
    assert run('prepare', 'BAD-REUSE', ('--lint', str(bad))).returncode != 0
    result = run('prepare')
    assert result.returncode == 0, result.stderr
    assert '재사용' in result.stdout, result.stdout  # 같은 SHA의 worker lint 결과를 자동 채택한다.
    directory = repo / '.fullops-squad/docs/evaluations/qa-reports/REVIEW-1-review'
    assert (directory / 'lint.json').read_bytes() == reusable.read_bytes()
    assert (directory / 'report.md').read_text(encoding='utf-8').startswith('---\ntitle: REVIEW-1 리뷰\n')
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
    (directory / 'lint.json').unlink()
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
    rule.write_bytes(original.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
    crlf_rule = run('check')
    assert crlf_rule.returncode == 0, crlf_rule.stderr  # autocrlf 체크아웃의 같은 규칙
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
    agents.write_text(agents.read_text(encoding='utf-8').replace('- 설계 역할: `architecture`',
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


def hashed(data):
    return hashlib.sha256(data).hexdigest()


def refused(key, checkout):
    try:
        review.historical(checkout, key)
    except ValueError:
        return True
    return False


with tempfile.TemporaryDirectory(prefix='fullops-eol-', ignore_cleanup_errors=True) as tmp:
    # 커밋된 기록을 autocrlf=true 체크아웃과 LF 체크아웃에서 검증한다.
    origin, crlf, lf = Path(tmp) / 'origin', Path(tmp) / 'crlf', Path(tmp) / 'lf'
    qa = '.fullops-squad/docs/evaluations/qa-reports'
    def git(*args):
        subprocess.run(['git', *map(str, args)], check=True, capture_output=True)
    git('init', '-q', '-b', 'main', origin)
    git('-C', origin, 'config', 'core.autocrlf', 'false')
    independence = {'implementer_session': 'a', 'reviewer_session': 'b'}
    text, windows, binary = b'line one\nline two\n', b'kept one\r\nkept two\r\n', b'\0png\r\ndata\n'
    def record(key, recorded):
        """보존 파일을 쓰고 recorded(이름, 원본)가 정한 바이트의 해시로 영수증을 남긴다."""
        folder = origin / f'{qa}/{key}-review'
        folder.mkdir(parents=True)
        files = {'preview.json': windows, 'rules.json': b'{}\n', 'lint.json': b'{}\n', 'report.md': text, 'frame.png': binary,
                 'result.json': json.dumps({'base': 'b', 'head': 'h', 'independence': independence}).encode() + b'\n'}
        for name, raw in files.items():
            (folder / name).write_bytes(raw)
        hashes = {name: hashed(recorded(name, raw)) for name, raw in files.items()}
        (folder / 'snapshot-cleanup.json').write_text(json.dumps({
            'state': 'removed', 'live_check': 'passed', 'base': 'b', 'head': 'h', 'independence': independence,
            'evidence_sha256': hashes}), encoding='utf-8')
        return hashes
    # 새 기록(LF 정규화), 기존 기록(원본 바이트), autocrlf 작업 트리에서 만든 기존 기록(CRLF).
    record('NEW', lambda name, raw: raw if name == 'frame.png' else raw.replace(b'\r\n', b'\n'))
    raw_hashes = record('RAW', lambda name, raw: raw)
    record('CRLF-MADE', lambda name, raw: raw if name == 'frame.png' else raw.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
    stopped = origin / f'{qa}/STOP-review'
    stopped.mkdir()
    (stopped / 'result.json').write_bytes(text)
    (stopped / 'abandoned.json').write_text(json.dumps({'state': 'abandoned', 'result_sha256': hashed(text)}), encoding='utf-8')
    replaced = origin / f'{qa}/OLD-review'
    replaced.mkdir()
    (replaced / 'result.json').write_bytes(text)
    (replaced / 'superseded.json').write_text(json.dumps({'state': 'superseded', 'replacement': 'RAW', 'original_sha256': hashed(text),
                                                          'replacement_evidence_sha256': raw_hashes}), encoding='utf-8')
    git('-C', origin, 'add', '.')
    git('-C', origin, '-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-q', '-m', 'records')
    git('clone', '-q', '-c', 'core.autocrlf=true', origin, crlf)
    git('clone', '-q', '-c', 'core.autocrlf=false', origin, lf)
    raw_folder = crlf / f'{qa}/RAW-review'
    assert (raw_folder / 'report.md').read_bytes() == text.replace(b'\n', b'\r\n')  # 재현 전제: LF 커밋이 CRLF로 체크아웃된다.
    assert (raw_folder / 'preview.json').read_bytes() == windows and (raw_folder / 'frame.png').read_bytes() == binary
    for checkout in (crlf, lf):
        for key in ('NEW', 'RAW', 'CRLF-MADE'):
            assert not refused(key, checkout), (checkout, key)
        assert review.abandoned(checkout, 'STOP') and review.superseded_check(checkout, 'OLD')
    assert review.evidence_hashes(crlf, 'RAW') == review.evidence_hashes(lf, 'RAW')  # 새 영수증은 체크아웃과 무관하다.
    report, picture = raw_folder / 'report.md', raw_folder / 'frame.png'
    original = report.read_bytes()
    report.write_bytes(original + b'tampered\r\n')
    assert refused('RAW', crlf)
    report.write_bytes(original)
    picture.write_bytes(binary.replace(b'\r\n', b'\n'))  # 이진 파일은 줄끝도 내용이다.
    assert refused('RAW', crlf)
    picture.write_bytes(binary)
    (raw_folder / 'extra.md').write_bytes(b'added\n')
    assert refused('RAW', crlf)
    (raw_folder / 'extra.md').unlink()
    assert not refused('RAW', crlf)
    (crlf / f'{qa}/STOP-review/result.json').write_bytes(b'tampered\r\n')
    assert not review.abandoned(crlf, 'STOP')
    print('PASS: review records verify across autocrlf and LF checkouts, old receipts stay valid, text/binary/added-file tampering is refused')


def windows_paths():
    """역슬래시·슬래시·드라이브 대소문자로 같은 레포를 가리켜도 리뷰 정체성이 같고, core.longpaths 없는 긴 경로는 깨끗이 실패한다."""
    # 시스템·전역 설정을 빼서 사용자 환경과 무관하게 core.longpaths가 없는 상태로 시험한다. 이 파일의 마지막 블록이라 되돌리지 않는다.
    os.environ.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    with tempfile.TemporaryDirectory(prefix='fullops-winpath-', ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp).resolve() / '리뷰 경로' / 'r'  # 사용자 프로필 폴더에 흔한 한글·공백
        repo.mkdir(parents=True)
        def git(*args):
            return subprocess.check_output(['git', '-C', str(repo), *args], text=True, encoding='utf-8', stderr=subprocess.STDOUT).strip()
        def commit(message):
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-q', '-m', message)
            return git('rev-parse', 'HEAD')
        def cli(mode, form, *args):
            done = subprocess.run(['python3', str(SCRIPTS / 'review.py'), mode, '--repo', form, *args], capture_output=True, text=True, encoding='utf-8')
            assert 'Traceback' not in done.stderr, done.stderr
            return done
        def snapshot_of(form, key, head):
            return cli('snapshot', form, '--key', key, '--to', head, '--implementer-session', 'a', '--reviewer-session', 'b', '--owner', 'c')
        def spell(path):
            return path.as_posix()[0].swapcase() + path.as_posix()[1:]  # 같은 경로의 슬래시·반대 대소문자 드라이브 표기
        git('init', '-q', '-b', 'main')
        subprocess.run(['python3', str(SCRIPTS / 'setup.py'), '--repo', str(repo), '--roles', 'implementer', '--local-only'],
                       check=True, capture_output=True)
        base = commit('init')
        (repo / 'sample.py').write_text('sample\n')
        head = commit('sample')
        assert subprocess.run(['git', '-C', str(repo), 'config', 'core.longpaths'], capture_output=True).returncode == 1
        assert str(repo)[1:3] == ':\\', repo
        forms = [str(repo), repo.as_posix(), str(repo)[0].swapcase() + str(repo)[1:], str(repo) + '\\']
        for form in forms:
            done = cli('need', form, '--from', base, '--to', head)
            assert done.returncode == 0 and json.loads(done.stdout)['head'] == head, (form, done.stderr)
        # 슬래시로 만든 snapshot을 다른 드라이브 표기로 준비하고 정리한다.
        made = snapshot_of(forms[1], 'WIN', head)
        assert made.returncode == 0, made.stderr
        snapshot = Path(made.stdout.strip())
        assert '\\' in made.stdout and snapshot.is_dir()
        prepared = cli('prepare', forms[2], '--key', 'WIN', '--from', base, '--to', head)
        assert prepared.returncode == 0, prepared.stderr
        folder = repo / '.fullops-squad/docs/evaluations/qa-reports/WIN-review'
        result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
        assert result['independence']['snapshot_path'] == str(snapshot)
        # 리뷰어가 슬래시·드라이브 표기를 바꿔 적어도 같은 snapshot이다.
        result['independence']['snapshot_path'] = spell(snapshot)
        review.check_independence(repo, result)
        (folder / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        (folder / 'lint.json').write_text('{}', encoding='utf-8')
        # Orca는 workspace를 '<repo>::<경로>'로 준다. 드라이브 콜론과 표기가 달라도 같은 경로다.
        def orca(*args, **kwargs):
            return ({'terminals': []} if args[:2] == ('terminal', 'list') else
                    {'dispatchId': 'd1', 'state': 'succeeded', 'workspace': 'repo::' + spell(snapshot)})
        with patch('integration.orca', side_effect=orca), patch.object(review, 'check'):
            review.cleanup(repo, 'WIN', 'd1', True)
        assert not snapshot.exists()
        done = cli('check', forms[3], '--key', 'WIN', '--historical')
        assert done.returncode == 0, done.stderr
        # 경로만 사라지고 Git 등록이 남으면 porcelain의 슬래시 표기와 맞춰 live로 보고한다.
        made = snapshot_of(forms[0], 'GONE', head)
        assert made.returncode == 0, made.stderr
        shutil.rmtree(made.stdout.strip())
        pruned = json.loads(cli('prune', forms[1]).stdout)
        assert [item['key'] for item in pruned['live']] == ['GONE'] and 'Git 등록' in pruned['live'][0]['hold'], pruned
        git('worktree', 'prune')
        assert json.loads(cli('prune', forms[2]).stdout)['missing'] == ['GONE']
        # 레포에는 들어가지만 이름이 더 긴 snapshot 폴더에서는 MAX_PATH를 넘는 추적 파일.
        room = 259 - len(str(repo)) - 1
        deep = '/'.join(['x' * 50] * ((room - 20) // 51))
        target = repo / (deep + '/' + 'f' * (room - len(deep) - 1))
        assert len(str(target)) == 259
        target.parent.mkdir(parents=True)
        target.write_text('deep\n')
        failed = snapshot_of(forms[0], 'LONG', commit('deep'))
        assert failed.returncode == 1 and 'Filename too long' in failed.stderr and '리뷰 처리 실패' in failed.stderr, failed.stderr
        saved = json.loads(review.snapshot_record(repo, 'LONG').read_text(encoding='utf-8'))
        assert saved['state'] == 'creating' and not Path(saved['path']).exists() and Path(saved['path']).as_posix() not in git('worktree', 'list')
        assert json.loads(cli('prune', forms[0]).stdout)['missing'] == ['LONG']
        # 경로 한도를 넘는 리뷰 키는 traceback 없이 거부한다(cli가 traceback을 검사).
        assert snapshot_of(forms[0], 'K' * 300, head).returncode == 1
        # npm ocr.cmd는 cmd.exe를 거친다. 레포 경로의 &가 명령을 나누기 전에 거부한다.
        if review.ocr_command().lower().endswith(('.cmd', '.bat')):
            metachar = repo.with_name('a&b')
            repo.rename(metachar)
            done = cli('prepare', str(metachar), '--key', 'META', '--from', base, '--to', head)
            assert done.returncode == 1 and '메타문자' in done.stderr, done.stderr
            metachar.rename(repo)
    print('PASS: Windows review paths: backslash/forward/drive-case identity, Orca workspace form, prune porcelain form, long path without core.longpaths')


if os.name == 'nt':
    windows_paths()
else:
    print('SKIP: Windows review paths (os.name != nt)')
