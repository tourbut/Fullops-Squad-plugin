"""플러그인 안 의존성 설치기가 FullOps 자신은 빼고 의존성만 설치하는지, 필수 CLI 확인과 세션 시작 안내를 확인한다."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import deps  # noqa: E402


def main():
    for host in ('codex', 'claude-code', 'grok', 'agy', 'all'):
        plan = list(deps.commands(host))
        flat = [' '.join(map(str, cmd)) for cmd in plan]
        assert plan[0][:3] == ['npm', 'install', '--global'] and '@alibaba-group/open-code-review@latest' in plan[0]
        assert not any('fullops-squad' in line for line in flat), (host, flat)  # 자신은 마켓플레이스가 설치한다
        assert any('JuliusBrussee/caveman' in line for line in flat)
    codex = [' '.join(c) for c in deps.commands('codex')]
    assert 'codex plugin marketplace add DietrichGebert/ponytail' in codex and 'codex plugin add ponytail@ponytail' in codex
    assert not [c for c in deps.commands('codex', {'codex': {'ponytail': 'https://github.com/DietrichGebert/ponytail.git'}})
                if c[2:4] == ['marketplace', 'add']]  # 이미 등록된 마켓플레이스는 건너뛴다
    with_self = [' '.join(map(str, c)) for c in deps.commands('codex', plugin={'source': 'tourbut/x', 'package': '/p'})]
    assert with_self[-1] == 'codex plugin add fullops-squad@fullops-squad' and 'codex plugin marketplace add tourbut/x' in with_self

    with tempfile.TemporaryDirectory(prefix='fullops-deps-') as tmp:
        empty = {**os.environ, 'PATH': tmp}  # 필수 CLI가 없는 PATH
        env = {**os.environ, 'PATH': os.pathsep.join([tmp, os.environ.get('PATH', '')])}
        check = subprocess.run([sys.executable, str(SCRIPTS / 'deps.py'), '--check'], capture_output=True, text=True,
                               encoding='utf-8', env=empty)
        assert check.returncode == 1 and 'ocr' in check.stdout and 'context7-mcp' in check.stdout, check.stdout
        for name in ('ocr', 'context7-mcp'):
            fake = Path(tmp) / (name + ('.cmd' if os.name == 'nt' else ''))
            fake.write_text('@echo off\n' if os.name == 'nt' else '#!/bin/sh\n', encoding='utf-8')
            fake.chmod(0o755)
        ok = subprocess.run([sys.executable, str(SCRIPTS / 'deps.py'), '--check'], capture_output=True, text=True,
                            encoding='utf-8', env=env)
        assert ok.returncode == 0, ok.stdout
        dry = subprocess.run([sys.executable, str(SCRIPTS / 'deps.py'), '--host', 'grok', '--dry-run'], capture_output=True,
                             text=True, encoding='utf-8')
        assert dry.returncode == 0 and 'grok' in dry.stdout and 'plugin install' not in dry.stdout, dry.stdout

        # 필수 CLI가 없으면 세션 시작 안내에 설치 명령이 나온다
        repo = Path(tmp) / 'repo'
        repo.mkdir()
        subprocess.check_output(['git', 'init', '-q', '-b', 'main', str(repo)])
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', str(repo), '--roles', 'dev', '--local-only'],
                       check=True, capture_output=True)
        start = subprocess.run([sys.executable, str(SCRIPTS / 'flow_gate.py'), 'start'], capture_output=True, text=True,
                               encoding='utf-8', env={**empty, 'PATH': os.pathsep.join([os.path.dirname(shutil.which('git')),
                                                                                         os.path.dirname(sys.executable)])},
                               input=json.dumps({'session_id': 's', 'cwd': str(repo), 'source': 'startup'}))
        brief = json.loads(start.stdout).get('hookSpecificOutput', {}).get('additionalContext', '')
        assert 'deps.py' in brief and '필수 CLI가 없다' in brief, (brief, start.stderr)
        assert 'python3=' in brief and sys.executable.split(os.sep)[-1] in brief  # 셸 PATH가 달라도 쓸 전체 경로
    print('PASS: deps plan excludes fullops itself, skips registered marketplaces, --check, dry-run, SessionStart hint')


if __name__ == '__main__':
    main()
