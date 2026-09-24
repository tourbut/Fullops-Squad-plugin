"""임시 Git 레포로 setup·핸드오버·산출물 검사·설치 계획을 확인한다."""
from datetime import date
import importlib.util
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and '.git' not in p.relative_to(root).parts}


def main():
    setup = load('setup', 'plugins/fullops-squad/scripts/setup.py')
    work = load('work', 'plugins/fullops-squad/scripts/work.py')
    deliverables = load('deliverables', 'plugins/fullops-squad/scripts/deliverables.py')
    install = load('install', 'scripts/install.py')
    build = load('build', 'scripts/build.py')
    dependencies = __import__('json').loads((ROOT / 'dependencies.json').read_text())
    assert set(dependencies['mcp']) == {'context7'}  # codebase-memory-mcp는 0.4.1에서 제거했다
    assert dependencies['mcp']['context7']['package'] == '@upstash/context7-mcp@4.1.1'
    mcp = __import__('json').loads((ROOT / 'plugins/fullops-squad/mcp.json').read_text())
    assert mcp['mcpServers']['context7'] == {'type': 'stdio', 'command': dependencies['mcp']['context7']['command'], 'args': []}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        source_before = snapshot(build.SOURCE)
        native = build.build(root / 'native')
        native_mcp = __import__('json').loads((native / '.mcp.json').read_text())
        assert native_mcp == __import__('json').loads((native / 'mcp_config.json').read_text())
        assert native_mcp['mcpServers'] == {name: {k: v for k, v in server.items() if k != 'type'} for name, server in mcp['mcpServers'].items()}
        assert not (native / 'mcp.json').exists()
        (native / 'obsolete.txt').write_text('old build')
        build.build(native)
        assert not (native / 'obsolete.txt').exists() and snapshot(build.SOURCE) == source_before
        protected = root / 'user-files'
        protected.mkdir()
        (protected / 'note').write_text('keep')
        try:
            build.build(protected)
        except ValueError:
            pass
        else:
            raise AssertionError('사용자 디렉터리 빌드 덮어쓰기')
        assert (protected / 'note').read_text() == 'keep'
        packaged = root / 'packaged-service'
        packaged.mkdir()
        subprocess.run(['git', 'init', '-q', str(packaged)], check=True)
        subprocess.run(['python3', str(native / 'scripts/setup.py'), '--repo', str(packaged), '--roles', 'gameplay', '--local-only'], check=True, capture_output=True)
        assert (packaged / '.fullops-squad/FULLOPS.md').is_file()
        repo = root / 'service with spaces'
        other = root / 'other'
        for p in (repo, other):
            p.mkdir()
            subprocess.run(['git', 'init', '-q', str(p)], check=True)
        original = '# 기존 사용자 규칙\r\n한글·공백을 그대로 보존한다.\r\n'
        (repo / 'AGENTS.md').write_bytes(original.encode())
        (repo / 'CLAUDE.md').write_bytes(original.encode())
        (repo / 'GEMINI.md').write_bytes(original.encode())
        existing_agents = repo / '.agents'
        existing_agents.mkdir()
        (existing_agents / 'FULLOPS.md').write_text('다른 하네스의 기존 규칙')
        (existing_agents / 'fullops.json').write_text('{"schema_version": 1}')
        (existing_agents / 'notes.md').write_text('보존할 작업 기록')
        agents_before = snapshot(existing_agents)
        old_pointer = setup.POINTER.replace('.fullops-squad/', '.agents/')
        (repo / 'CLAUDE.md').write_bytes((original + old_pointer + '추가 사용자 규칙\r\n').encode())
        before = snapshot(repo)
        assert setup.setup(repo, dry_run=True, roles=['backend_dev'], local_only=True)
        assert snapshot(repo) == before and snapshot(other) == {}
        setup.setup(repo, roles=['backend_dev'], local_only=True)
        assert not (repo / '.fullops-squad/workflows').exists()
        assert (repo / 'AGENTS.md').read_bytes().startswith(original.encode())
        assert (repo / 'CLAUDE.md').read_bytes().startswith(original.encode())
        assert (repo / 'GEMINI.md').read_bytes().startswith(original.encode())
        assert snapshot(existing_agents) == agents_before
        assert (repo / 'CLAUDE.md').read_bytes().endswith('추가 사용자 규칙\r\n'.encode())
        assert '.agents/' not in (repo / 'CLAUDE.md').read_text()
        assert (repo / setup.MARKER).exists()
        work.new(repo, 'backend_dev', 'TEST-1', '기록 검증')
        inbox = repo / '.fullops-squad/handovers/to_backend_dev.md'
        assert inbox.read_text().startswith('# TEST-1 — 기록 검증')
        try:
            work.new(repo, 'backend_dev', 'TEST-2', '덮어쓰기 검증')
        except ValueError:
            pass
        else:
            raise AssertionError('진행 중 지시서 덮어쓰기')
        try:
            work.finish(repo, 'backend_dev', 'TEST-1')
        except ValueError:
            pass
        else:
            raise AssertionError('빈 완료 보고 아카이브')
        placeholder = work.TEMPLATE.read_text().partition('## 완료 보고\n')[2]
        inbox.write_text(inbox.read_text().replace(placeholder, '브랜치 main / SHA 미커밋 / 검증 통과 / 로그 보존.\n'))
        completed = inbox.read_text()
        work.finish(repo, 'backend_dev', 'TEST-1')
        assert inbox.read_bytes() == b''
        assert 'TEST-1' in (repo / f'.fullops-squad/handovers/logs/{date.today()}_to_backend_dev.md').read_text()
        inbox.write_text(completed)
        try:
            work.finish(repo, 'backend_dev', 'TEST-1')
        except ValueError:
            pass
        else:
            raise AssertionError('완료 지시서 중복 아카이브')
        assert inbox.read_text() == completed
        inbox.write_bytes(b'')
        assert not deliverables.check(repo, 'D01')  # 미작성 원천은 실패가 아니다.
        deliverable = repo / '.fullops-squad/docs/deliverables/D01_business-plan.md'
        deliverable.write_text('[원천](없는-파일.md)')
        assert deliverables.check(repo, 'D01')
        deliverable.unlink()
        log = repo / '.fullops-squad/handovers/logs/existing.md'
        log.write_text('작업 기록')
        inbox.write_text('진행 중 과제')
        state = snapshot(repo)
        assert setup.setup(repo, local_only=True) == []
        assert snapshot(repo) == state and snapshot(other) == {}
        assert snapshot(existing_agents) == agents_before
        try:
            setup.setup(repo / '.fullops-squad')
        except ValueError:
            pass
        else:
            raise AssertionError('하위 디렉터리 setup 허용')
        (other / '.fullops-squad').mkdir()
        (other / '.fullops-squad/FULLOPS.md').write_text('기존 하네스')
        state = snapshot(other)
        try:
            setup.setup(other, roles=['backend_dev'])
        except ValueError:
            pass
        else:
            raise AssertionError('충돌 덮어쓰기')
        assert snapshot(other) == state
        # Exercise real Git remote creation without touching GitHub/user repositories.
        service, remote = root / 'dynamic-service', root / 'remote.git'
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(service)], check=True)
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(remote)], check=True)
        def git(*args):
            return setup.git(service, *args)
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.com',
            'commit', '--allow-empty', '-m', 'initial')
        git('remote', 'add', 'origin', str(remote))
        git('push', 'origin', 'main')
        refs_before = git('ls-remote', 'origin')
        setup.setup(service, roles=['gameplay', 'engine'], remote='origin', dry_run=True)
        assert not (service / setup.MARKER).exists()
        assert git('ls-remote', 'origin') == refs_before
        setup.setup(service, roles=['gameplay', 'engine'], remote='origin')
        config = __import__('json').loads((service / setup.MARKER).read_text())
        assert config['roles'] == {'gameplay': 'fullops/gameplay', 'engine': 'fullops/engine'}
        assert config['git'] == {'remote': 'origin', 'base': 'main'}
        assert not (service / '.fullops-squad/contexts/backend_dev.md').exists()
        work.new(service, 'gameplay', 'GAME-1', '게임 구현')
        try:
            work.new(service, 'backend_dev', 'NO-1', '미등록 역할')
        except ValueError:
            pass
        else:
            raise AssertionError('미등록 역할 허용')
        before = snapshot(service)
        assert setup.setup(service, remote='origin') == []
        assert snapshot(service) == before
        # Advance the base; old roles must retain their commits, new roles use new base.
        old_sha = git('rev-parse', 'HEAD')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.com',
            'commit', '--allow-empty', '-m', 'new base')
        git('push', 'origin', 'main')
        setup.setup(service, roles=['mobile'], remote='origin')
        assert git('ls-remote', 'origin', 'refs/heads/fullops/gameplay').split()[0] == old_sha
        assert git('ls-remote', 'origin', 'refs/heads/fullops/mobile').split()[0] == git('rev-parse', 'HEAD')
        assert (service / '.fullops-squad/handovers/to_gameplay.md').read_text().startswith('# GAME-1')
        # A later CLI invocation must reuse the saved non-default remote/base.
        git('branch', 'release', old_sha)
        git('push', 'origin', 'release')
        git('remote', 'rename', 'origin', 'upstream')
        setup.setup(service, remote='upstream', base='release')
        cli = ['python3', str(ROOT / 'plugins/fullops-squad/scripts/setup.py'), '--repo', str(service)]
        before, refs_before = snapshot(service), git('ls-remote', 'upstream')
        subprocess.run([*cli, '--roles', 'renderer', '--dry-run'], check=True, capture_output=True)
        assert snapshot(service) == before and git('ls-remote', 'upstream') == refs_before
        subprocess.run([*cli, '--roles', 'renderer'], check=True, capture_output=True)
        config = __import__('json').loads((service / setup.MARKER).read_text())
        assert config['git'] == {'remote': 'upstream', 'base': 'release'}
        assert git('ls-remote', 'upstream', 'refs/heads/fullops/renderer').split()[0] == old_sha
        assert setup.setup(service) == []  # shared API follows the same default resolution
        before, refs_before = snapshot(service), git('ls-remote', 'upstream')
        for extra in (['--roles', 'localworker', '--local-only'],
                      ['--roles', 'localworker', '--local-only', '--dry-run'],
                      ['--local-only', '--remote', 'upstream']):
            result = subprocess.run([*cli, *extra], capture_output=True, text=True)
            assert result.returncode != 0
            assert snapshot(service) == before and git('ls-remote', 'upstream') == refs_before
        assert setup.setup(service, local_only=True) == []  # existing roles/docs can be maintained offline
        # Explicit options still override saved values.
        git('remote', 'rename', 'upstream', 'origin')
        subprocess.run([*cli, '--roles', 'explicitworker', '--remote', 'origin', '--base', 'main'],
                       check=True, capture_output=True)
        config = __import__('json').loads((service / setup.MARKER).read_text())
        assert config['git'] == {'remote': 'origin', 'base': 'main'}
        assert git('ls-remote', 'origin', 'refs/heads/fullops/explicitworker').split()[0] == git('rev-parse', 'HEAD')
        before, refs_before = snapshot(service), git('ls-remote', 'origin')
        for kwargs in ({'roles': ['../escape']}, {'roles': ['newrole'], 'base': 'missing'}):
            try:
                setup.setup(service, remote='origin', **kwargs)
            except ValueError:
                pass
            else:
                raise AssertionError('잘못된 역할/기준 브랜치 허용')
            assert snapshot(service) == before and git('ls-remote', 'origin') == refs_before
        hook = remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o755)
        try:
            setup.setup(service, roles=['rejected'], remote='origin')
        except subprocess.CalledProcessError:
            pass
        else:
            raise AssertionError('원격 거절을 성공으로 처리')
        assert snapshot(service) == before and git('ls-remote', 'origin') == refs_before
        # Explicit migration preserves old fixed-role documents.
        marker = service / setup.MARKER
        marker.write_text('{"schema_version": 1, "plugin_version": "0.1.0"}\n')
        handover = service / '.fullops-squad/handovers/to_gameplay.md'
        old_content = handover.read_bytes()
        setup.setup(service, roles=['gameplay'], local_only=True)
        assert handover.read_bytes() == old_content
        (other / '.fullops-squad/FULLOPS.md').unlink()
        (other / 'AGENTS.md').symlink_to(repo / 'AGENTS.md')
        try:
            setup.setup(other, roles=['backend_dev'])
        except ValueError:
            pass
        else:
            raise AssertionError('심볼릭 링크 쓰기')
        (other / 'AGENTS.md').unlink()
        (other / setup.MARKER).write_text('[]')
        state = snapshot(other)
        try:
            setup.setup(other, roles=['backend_dev'])
        except ValueError:
            pass
        else:
            raise AssertionError('잘못된 활성화 설정 허용')
        assert snapshot(other) == state
    for host in ('codex', 'claude-code', 'grok', 'agy', 'both', 'all'):
        plan = list(install.commands(host))
        assert all('setup.py' not in ' '.join(cmd) for cmd in plan)
        skills = [cmd for cmd in plan if cmd[0] == 'npx']
        assert skills and all('--global' in cmd and '--agent' in cmd for cmd in skills)
        assert all('universal' not in cmd for cmd in skills)
        hosts = {cmd[0] for cmd in plan} - {'npx'}
        assert hosts == {'all': {'npm', 'codex', 'claude', 'grok', 'agy'},
                         'both': {'npm', 'codex', 'claude'}}.get(host, {'npm', 'claude' if host == 'claude-code' else host})
        assert plan[0] == ['npm', 'install', '--global', '@upstash/context7-mcp@4.1.1', '@alibaba-group/open-code-review@latest']
        assert any(cmd[4] == 'alibaba/open-code-review' and 'open-code-review-delegate' in cmd for cmd in skills)
        for source, name in (('JuliusBrussee/caveman', 'caveman'), ('typesafe-ai/skills', 'typesafe-ai')):
            targets = {cmd[cmd.index('--agent') + 1] for cmd in skills
                       if cmd[4] == source and cmd[5:7] == ['--skill', name]}
            assert targets == {'all': {'codex', 'claude-code', 'grok', 'antigravity-cli'},
                               'both': {'codex', 'claude-code'},
                               'agy': {'antigravity-cli'}}.get(host, {host})
        if host in ('grok', 'agy'):
            target = 'antigravity-cli' if host == 'agy' else 'grok'
            assert all(cmd[cmd.index('--agent') + 1] == target for cmd in skills)
            assert {cmd[4] for cmd in skills} == {'cathrynlavery/diagram-design',
                                                'mattpocock/skills', 'DietrichGebert/ponytail', 'alibaba/open-code-review',
                                                'JuliusBrussee/caveman', 'typesafe-ai/skills'}
            assert plan[-1] == [host, 'plugin', 'install', str(install.PLUGIN)] + (['--trust'] if host == 'grok' else [])
    registered = {'codex': {'fullops-squad': str(ROOT), 'ponytail': 'https://github.com/DietrichGebert/ponytail.git'}}
    assert not any(cmd[2:4] == ['marketplace', 'add'] for cmd in install.commands('codex', registered))
    try:
        list(install.commands('codex', {'codex': {'fullops-squad': '/wrong/source'}}))
    except ValueError:
        pass
    else:
        raise AssertionError('다른 출처의 같은 이름 마켓플레이스 허용')
    print('PASS: 동적 역할·원격 브랜치 생성/보존/실패, setup 재실행, 핸드오버, 산출물, 설치 계획')


if __name__ == '__main__':
    main()
