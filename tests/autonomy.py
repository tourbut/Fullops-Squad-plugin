#!/usr/bin/env python3
"""섀도 자동 승인 판정: 등급 규칙, 기준 시점 정책, 입력 누락·차단, 상태 불변 기록, 결정의 SHA·만료·응답자·중복 답."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'


def run(script, *args, ok=True):
    done = subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True, encoding='utf-8')
    assert (done.returncode == 0) == ok, (script, args, done.stdout, done.stderr)
    return json.loads(done.stdout) if ok else done.stderr


with tempfile.TemporaryDirectory(prefix='fullops-autonomy-') as tmp:
    repo, saved = Path(tmp) / 'repo', Path(tmp) / 'lint'
    repo.mkdir()
    saved.mkdir()

    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True, encoding='utf-8').strip()

    def commit(message):
        git('add', '-A')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', message)
        return git('rev-parse', 'HEAD')

    git('init', '-q', '-b', 'main')
    subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', str(repo), '--roles', 'dev', '--local-only'],
                   check=True, capture_output=True)
    (repo / 'src').mkdir()
    (repo / 'src/app.py').write_text('"""앱 진입점."""\n', encoding='utf-8')
    base = commit('base')

    def change(branch, files, lint=True):
        git('checkout', '-q', '-B', branch, base)
        for name, text in files.items():
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            (repo / name).write_text(text, encoding='utf-8')
        head = commit(branch)
        if lint:
            subprocess.run([sys.executable, str(SCRIPTS / 'lint.py'), '--repo', str(repo), '--from', base], check=True,
                           capture_output=True)
            shutil.copyfile(repo / '.git/fullops-gate/lint-result.json', saved / f'{branch}.json')
        return head

    def judge(head, *extra):
        return run('autonomy.py', 'judge', '--repo', str(repo), '--from', base, '--to', head, *extra)

    docs = change('docs', {'docs/guide.md': '# 안내\n'})
    result = judge(docs)  # 등록된 워크트리에서 같은 base·head lint 결과를 찾는다
    assert (result['grade'], result['blocked'], result['merge_allowed'], result['mode']) == ('auto', False, False, 'shadow'), result
    assert result['version'] == 1 and result['inputs']['lint']['passed'] and result['head'] == docs

    code = change('code', {'src/app.py': '"""앱 진입점."""\nVALUE = 1\n'})
    assert judge(code)['grade'] == 'delay'
    ci = change('ci', {'.github/workflows/ci.yml': 'on: push\n'})
    result = judge(ci, '--lint', str(saved / 'ci.json'))
    assert result['grade'] == 'ask' and '.github/workflows/ci.yml' in result['reasons'][0], result
    big = change('big', {f'src/m{i}.py': f'"""모듈 {i}."""\nVALUE = {i}\n' for i in range(16)})
    result = judge(big, '--lint', str(saved / 'big.json'))
    assert result['grade'] == 'ask' and result['inputs']['need']['required'], result

    # 작업 브랜치가 정책을 낮춰도 기준 시점 정책으로 판정한다
    config = json.loads((repo / '.fullops-squad/fullops.json').read_text(encoding='utf-8'))
    lowered = json.dumps({**config, 'autonomy_policy': {'auto': ['**'], 'ask': []}}, ensure_ascii=False)
    lower = change('lower', {'.fullops-squad/fullops.json': lowered, 'src/app.py': '"""앱 진입점."""\nVALUE = 2\n'})
    result = judge(lower, '--lint', str(saved / 'lower.json'))
    assert result['grade'] == 'ask' and result['policy']['auto'] == ['**/*.md', 'docs/**', 'tests/**'], result

    # 입력 누락·판정 불가는 ask, lint ERROR·미해결 high는 등급과 관계없이 blocked
    missing = change('missing', {'src/app.py': '"""앱 진입점."""\nVALUE = 3\n'}, lint=False)
    result = judge(missing)
    assert result['grade'] == 'ask' and result['blocked'] and 'lint' in result['blockers'][0], result
    failing = json.loads((saved / 'code.json').read_text(encoding='utf-8'))
    failing['violations'].append({'rule': 'X-001', 'severity': 'ERROR', 'path': 'src/app.py', 'message': 'x'})
    (saved / 'error.json').write_text(json.dumps(failing), encoding='utf-8')
    result = judge(code, '--lint', str(saved / 'error.json'))
    assert (result['grade'], result['blocked'], result['blockers']) == ('delay', True, ['lint ERROR 1건']), result
    review = repo / '.fullops-squad/docs/evaluations/qa-reports/R1-review'
    review.mkdir(parents=True)
    (review / 'result.json').write_text(json.dumps({'findings': [
        {'path': 'docs/guide.md', 'content': '근거 없는 링크', 'severity': 'high', 'resolved': False},
        {'path': 'docs/guide.md', 'content': '오타', 'severity': 'low', 'resolved': False}]}), encoding='utf-8')
    result = judge(docs, '--lint', str(saved / 'docs.json'), '--review-key', 'R1')
    assert (result['grade'], result['blocked'], result['blockers']) == ('auto', True, ['미해결 critical/high 1건']), result
    shutil.rmtree(review.parent)
    result = judge('no-such-ref')
    assert result['grade'] == 'ask' and result['reasons'][0].startswith('입력을 읽지 못했습니다'), result
    assert judge(docs, '--lint', str(saved / 'missing.json'))['grade'] == 'ask'

    # 섀도 기록은 ref·인덱스·작업 트리·다른 하네스 기록을 바꾸지 않는다
    git('checkout', '-q', 'code')
    state = lambda: (git('for-each-ref'), git('status', '--porcelain', '--ignored'), git('rev-parse', 'HEAD'),
                     sorted(p.name for p in (repo / '.git').iterdir()))
    before = state()
    result = judge(code, '--lint', str(saved / 'code.json'), '--key', 'K1', '--record')
    after = state()
    assert after[:3] == before[:3] and set(after[3]) - set(before[3]) <= {'fullops-autonomy'}, (before, after)
    assert Path(result['recorded']).parent.name == 'fullops-autonomy' and not result['merge_allowed']
    run('autonomy.py', 'judge', '--repo', str(repo), '--from', base, '--to', '../x', '--record')  # 읽지 못한 ref는 경로에 쓰지 않는다
    assert not (repo / '.git/x').exists() and (repo / '.git/fullops-autonomy/nokey-unresolved.json').is_file()

    # 결정은 SHA·유효 기간·허용 응답자에 묶이고, 늦은 답은 이미 처리됐다고 알린다
    asked = run('decision.py', 'add', '--repo', str(repo), '--question', '병합할까요?', '--key', 'K1', '--sha', code,
                '--risk', 'CI 변경', '--allow', 'alice', '--origin', 'bot')
    assert asked['sha'] == code and asked['expires_at'] and asked['origin'] == 'bot' and asked['version'] == 1
    rows = run('autonomy.py', 'compare', '--repo', str(repo))['judgments']
    assert [r['decision']['id'] for r in rows if r['key'] == 'K1'] == [asked['id']], rows
    answer = ['decision.py', 'answer', '--repo', str(repo), '--id', asked['id'], '--answer', '예']
    assert '다시 물어야' in run(*answer, '--by', 'alice', '--sha', docs, ok=False)
    assert '다시 물어야' in run(*answer, '--by', 'alice', ok=False)
    assert '답할 수 없습니다' in run(*answer, '--by', 'bob', '--sha', code, ok=False)
    closed = run(*answer, '--by', 'alice', '--sha', code, '--via', 'bot')
    assert (closed['status'], closed['via'], closed['decided_by']) == ('answered', 'bot', 'alice')
    late = run('decision.py', 'answer', '--repo', str(repo), '--id', asked['id'], '--answer', '아니오', '--by', 'alice', '--sha', code)
    assert late['already'] and late['answer'] == '예', late
    expiring = run('decision.py', 'add', '--repo', str(repo), '--question', '만료될 결정', '--sha', code, '--expires-hours', '1')
    path = repo / '.git/fullops-decisions' / f"{expiring['id']}.json"
    path.write_text(json.dumps({**expiring, 'expires_at': '2000-01-01T00:00:00+00:00'}), encoding='utf-8')
    assert '만료' in run('decision.py', 'answer', '--repo', str(repo), '--id', expiring['id'], '--answer', '예', '--sha', code, ok=False)
    assert '40자리' in run('decision.py', 'add', '--repo', str(repo), '--question', 'q', '--sha', 'main', ok=False)
    old = {'id': 'D090', 'status': 'open', 'key': 'K0', 'question': '옛 결정', 'options': [], 'blocks': None,
           'asked_at': '2026-10-01T00:00:00+00:00'}
    (repo / '.git/fullops-decisions/D090.json').write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
    assert 'D090' in [d['id'] for d in run('decision.py', 'list', '--repo', str(repo))['decisions']]
    assert run('decision.py', 'answer', '--repo', str(repo), '--id', 'D090', '--answer', '예')['status'] == 'answered'

print('PASS: shadow grades, merge-base policy, missing input and blockers, side-effect-free record, decision SHA/expiry/responder/late answer')
