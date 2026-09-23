"""임시 레포로 lint 게이트의 변경 범위·기본 검사·명령 실행·리뷰 차단을 확인한다."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
PY = sys.executable


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-lint-') as tmp:
        repo = Path(tmp)

        def git(*args):
            return subprocess.check_output(['git', '-C', tmp, *args], text=True).strip()

        def commit(message='test'):
            git('add', '-A')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-q', '--allow-empty', '-m', message)
            return git('rev-parse', 'HEAD')

        def lint(*extra):
            done = subprocess.run([PY, str(SCRIPTS / 'lint.py'), '--repo', tmp, '--from', base, *extra],
                                  capture_output=True, text=True)
            return done

        git('init', '-q', '-b', 'main')
        subprocess.run([PY, str(SCRIPTS / 'setup.py'), '--repo', tmp, '--roles', 'dev', '--local-only'],
                       check=True, capture_output=True)
        config_path = repo / '.fullops-squad/lint/lint.json'
        config = json.loads(config_path.read_text())
        assert config['commands'] == [] and config['size']['severity'] == 'WARNING'
        docstring = '"""' + 'doc\n' * 50 + '"""\n'
        (repo / 'big.py').write_text(docstring + ''.join(f'x{i} = {i}\n' for i in range(301)))
        (repo / 'legacy.py').write_text('y = 1  # type: ignore\n')
        (repo / 'moved.py').write_text('z = 1\n' * 5)
        (repo / 'short.py').write_text(docstring + 'a = 1\n')
        config['size']['max_code_lines'] = 300
        config['rules'] = [{'code': 'CUSTOM-001', 'description': 'print 금지', 'pattern': r'\bprint\(',
                            'file_extensions': ['.py'], 'severity': 'ERROR', 'exclude_patterns': [r'#\s*allow-print'],
                            'enabled': True},
                           {'code': 'CUSTOM-002', 'description': '꺼진 규칙', 'pattern': 'z', 'enabled': False}]
        config['commands'] = [{'name': 'ok', 'run': [PY, '-c', 'pass']}]
        config_path.write_text(json.dumps(config))
        base = commit('base')

        # 기존 위반 줄은 소급하지 않고, 추가된 줄·늘어난 파일만 본다.
        (repo / 'big.py').write_text((repo / 'big.py').read_text() + 'extra = 1\n')
        (repo / 'legacy.py').write_text('y = 1  # type: ignore\nw = 2\n')
        git('mv', 'moved.py', 'renamed.py')
        (repo / 'src').mkdir()
        (repo / 'src/app.py').write_text('\n'.join([
            'import os',
            'a = eval("1")',
            'session.exec(q)',
            'b = 1  # type: ignore[attr-defined]',
            'c = 1  # type: ignore',
            'd = 1  # noqa',
            'e = 1  # noqa: E501',
            'print("x")',
            'print("y")  # allow-print',
            'pass' + 'word = "hunter2"',
            'pass' + 'word = os.environ["P"]',
            'api_' + 'key = "example-key"',
        ]) + '\n')
        (repo / 'tests').mkdir()
        (repo / 'tests/test_app.py').write_text('tok' + 'en = "real-looking"\n')
        (repo / 'web.ts').write_text('// @ts-ignore\nlet v = 1; // eslint-disable-line\n// eslint-disable-next-line no-console\n')
        (repo / 'node_modules').mkdir()
        (repo / 'node_modules/dep.py').write_text('q = eval("1")\n')
        (repo / 'image.bin').write_bytes(b'\0eval(1)')
        (repo / 'src/documented.py').write_text('"""주문 합계 계산."""\ntotal = 1\n')  # 헤더가 있으면 DOC-001 없음
        (repo / 'short.py').write_text((repo / 'short.py').read_text() + 'b = 2\n')
        head = commit('work')

        out = repo / '.git/fullops-lint.json'
        done = lint('--out', str(out))
        assert done.returncode == 1, done.stdout + done.stderr
        result = json.loads(out.read_text())
        found = {(v['code'], v['path'], v['line']) for v in result['violations']}
        expected = {
            ('SIZE-001', 'big.py', None),
            ('ANTI-002', 'src/app.py', 2),
            ('ANTI-003', 'src/app.py', 5),
            ('ANTI-003', 'src/app.py', 6),
            ('CUSTOM-001', 'src/app.py', 8),
            ('SEC-001', 'src/app.py', 10),
            ('SEC-001', 'tests/test_app.py', 1),
            ('ANTI-003', 'web.ts', 1),
            ('ANTI-003', 'web.ts', 2),
            ('DOC-001', 'src/app.py', None),  # 헤더 설명 없는 새 코드 파일
            ('DOC-001', 'tests/test_app.py', None),
            ('DOC-001', 'web.ts', None),
        }
        assert found == expected, found ^ expected
        severity = {(v['code'], v['path']): v['severity'] for v in result['violations']}
        assert severity[('SIZE-001', 'big.py')] == 'WARNING'
        assert severity[('SEC-001', 'tests/test_app.py')] == 'WARNING'
        assert severity[('SEC-001', 'src/app.py')] == 'ERROR'
        assert result['head'] == head and result['base'] == base
        assert result['config_sha256'] == hashlib.sha256(config_path.read_bytes()).hexdigest()
        assert result['commands'][0]['status'] == 'passed'
        assert result['summary']['errors'] == 7 and result['summary']['warnings'] == 5

        # 명령 실패·실행 불가·레포 밖 cwd
        config['commands'] = [{'name': 'fail', 'run': [PY, '-c', 'import sys; print("bad"); sys.exit(3)']},
                              {'name': 'missing', 'run': ['fullops-no-such-linter']}]
        config['rules'] = []
        config_path.write_text(json.dumps(config))
        for name in ('src/app.py', 'web.ts', 'tests/test_app.py'):
            (repo / name).unlink()
        base = commit('fix')  # 설정은 merge-base에서 읽으므로 기준을 옮긴다
        done = lint('--out', str(out))
        result = json.loads(out.read_text())
        assert done.returncode == 1 and 'bad' in done.stdout
        assert [c['status'] for c in result['commands']] == ['failed', 'unavailable']
        assert result['commands'][0]['exit_code'] == 3

        config['commands'] = [{'name': 'escape', 'run': ['true'], 'cwd': '..'}]
        config_path.write_text(json.dumps(config))
        base = commit('escape')
        assert lint().returncode == 2
        config['commands'] = []
        config['rules'] = [{'code': 'CUSTOM-009', 'description': 'TODO 금지', 'pattern': 'TODO', 'severity': 'ERROR'}]
        config_path.write_text(json.dumps(config))
        base = commit('clean')
        gate = repo / '.git/fullops-gate/pass.json'
        done = lint()
        assert done.returncode == 0 and 'LINT-000' in done.stdout, done.stdout
        assert json.loads(gate.read_text())['head'] == base  # done-gate 통과 기록

        # 브랜치가 스스로 설정을 느슨하게 해도 merge-base 설정이 적용된다.
        config['rules'][0]['enabled'] = False
        config['exclude'].append('**')
        config_path.write_text(json.dumps(config))
        (repo / 'todo.py').write_text('x = 1  # TODO\n')
        commit('loosen')
        done = lint('--out', str(out))
        found = {(v['code'], v['path']) for v in json.loads(out.read_text())['violations']}
        assert done.returncode == 1 and ('CUSTOM-009', 'todo.py') in found and ('LINT-001', '.fullops-squad/lint/lint.json') in found, found
        assert json.loads(gate.read_text())['head'] == base  # 실패는 통과 기록을 바꾸지 않는다
        git('reset', '-q', '--hard', base)

        # 테스트 skip 추가는 ERROR, 케이스 감소·파일 삭제는 WARNING
        (repo / 'tests/test_calc.py').parent.mkdir(exist_ok=True)
        (repo / 'tests/test_calc.py').write_text('def test_a():\n    pass\n\ndef test_b():\n    pass\n')
        (repo / 'tests/test_gone.py').write_text('def test_c():\n    pass\n')
        (repo / 'app.js').write_text('list.only(x)\n')
        base = commit('tests')
        (repo / 'tests/test_calc.py').write_text('import pytest\n\n@pytest.mark.skip\ndef test_a():\n    pass\n')
        (repo / 'tests/test_gone.py').unlink()
        (repo / 'app.js').write_text('list.only(x)\nlist.only(y)\n')  # 테스트가 아닌 파일은 대상이 아니다
        commit('damage')
        done = lint('--out', str(out))
        found = {(v['code'], v['severity'], v['path'], v['line']) for v in json.loads(out.read_text())['violations']}
        assert found == {('ANTI-004', 'ERROR', 'tests/test_calc.py', 3), ('ANTI-005', 'WARNING', 'tests/test_calc.py', None),
                         ('ANTI-005', 'WARNING', 'tests/test_gone.py', None),
                         ('LINT-000', 'WARNING', '.fullops-squad/lint/lint.json', None)}, found
        git('reset', '-q', '--hard', base)

        (repo / 'dirty.py').write_text('d = 1\n')
        assert lint().returncode == 2  # 커밋 전 실행 거부
        (repo / 'dirty.py').unlink()

        # review.py check의 lint 게이트 (OCR 없이 리뷰 기록을 구성한다)
        head = git('rev-parse', 'HEAD')
        directory = repo / '.fullops-squad/docs/evaluations/qa-reports/LINT-1-review'
        directory.mkdir(parents=True)
        (directory / 'preview.json').write_text(json.dumps({'from': base, 'to': head, 'reviewable_files': [],
                                                            'excluded_files': []}))
        rule = repo / '.fullops-squad/review/rule.json'
        (directory / 'result.json').write_text(json.dumps({
            'base': base, 'head': head, 'rule_sha256': hashlib.sha256(rule.read_bytes()).hexdigest(),
            'reviewer': 'tester', 'conclusion': 'ok', 'files': [], 'findings': []}))
        git('stash', '-u', '-q')  # lint는 깨끗한 체크아웃에서 실행한다

        def review():
            return subprocess.run([PY, str(SCRIPTS / 'review.py'), 'check', '--repo', tmp, '--key', 'LINT-1',
                                   '--from', base, '--to', head], capture_output=True, text=True)

        lint_json = repo / '.git/fullops-review-lint.json'
        assert lint('--out', str(lint_json)).returncode == 0
        git('stash', 'pop', '-q')
        assert 'lint' in review().stderr  # lint.json 없음
        data = json.loads(lint_json.read_text())

        def save(value):
            (directory / 'lint.json').write_text(json.dumps(value))

        save(data)
        assert review().returncode == 0, review().stderr
        save({**data, 'violations': data['violations'] + [
            {'code': 'ANTI-002', 'severity': 'ERROR', 'line': 1, 'path': 'x.py', 'message': ''}]})
        assert 'ERROR' in review().stderr
        save({**data, 'commands': [{'name': 'missing', 'status': 'unavailable', 'reason': ''}]})
        assert 'reason' in review().stderr
        save({**data, 'commands': [{'name': 'missing', 'status': 'unavailable', 'reason': '폐쇄망'}]})
        assert review().returncode == 0
        save({**data, 'commands': [{'name': 'x', 'status': 'timeout'}]})
        assert review().returncode != 0
        save({**data, 'head': '0' * 40})
        assert review().returncode != 0
        save({**data, 'config_sha256': 'changed'})
        assert '설정' in review().stderr

        # find.json이 있으면 check가 적중률을 자동으로 남기고, 계산 실패는 check를 막지 않는다.
        save(data)
        find = repo / '.fullops-squad/docs/evaluations/jev/TASK-1-find.json'
        find.parent.mkdir(parents=True, exist_ok=True)
        find.write_text(json.dumps({'head': base, 'candidates': [{'path': 'todo.py'}], 'existence': {'status': 'found'}}))
        done = subprocess.run([PY, str(SCRIPTS / 'review.py'), 'check', '--repo', tmp, '--key', 'LINT-1', '--task-key', 'TASK-1',
                               '--from', base, '--to', head], capture_output=True, text=True)
        assert done.returncode == 0 and 'jev_find score' in done.stdout, done.stdout + done.stderr
        scored = json.loads((directory / 'jev-find-score.json').read_text())
        assert scored['task_key'] == 'TASK-1' and scored['head'] == head
        find.write_text('broken')
        done = subprocess.run([PY, str(SCRIPTS / 'review.py'), 'check', '--repo', tmp, '--key', 'LINT-1', '--task-key', 'TASK-1',
                               '--from', base, '--to', head], capture_output=True, text=True)
        assert done.returncode == 0 and '생략' in done.stdout, done.stdout + done.stderr
        assert review().returncode == 0  # 리뷰 키로는 find.json이 없어 기록하지 않는다
    print('PASS: changed-only scope, size growth, suppressions, eval, secrets, custom rules, commands, review lint gate')


if __name__ == '__main__':
    main()
