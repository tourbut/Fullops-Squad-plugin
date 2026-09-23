#!/usr/bin/env python3
"""Check packaged session hooks without touching real user settings."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'dist/native/fullops-squad'
for host in ('codex', 'claude'):
    manifest = json.loads((PACKAGE / f'.{host}-plugin/plugin.json').read_text())
    config = json.loads((PACKAGE / manifest['hooks']).read_text())
    assert set(config['hooks']) == {'SessionStart', 'Stop'}
    group, gate = config['hooks']['SessionStart']
    assert group['matcher'] == 'startup|clear'  # Resume/compact must preserve an opt-out.
    hook, = group['hooks']
    assert hook['command'] == 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/caveman_start.py"'
    assert 'matcher' not in gate  # done-gate는 resume·compact에도 시작 지점을 확인한다
    assert gate['hooks'][0]['command'] == 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py" start'
    stop, = config['hooks']['Stop']
    assert stop['hooks'][0]['command'] == 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/done_gate.py" stop'

with tempfile.TemporaryDirectory() as directory:
    env = {**os.environ, 'HOME': directory, 'USERPROFILE': directory,
           'CODEX_HOME': str(Path(directory) / 'custom-codex'),
           'CLAUDE_CONFIG_DIR': str(Path(directory) / 'custom-claude')}
    def run():
        return json.loads(subprocess.check_output(
            [sys.executable, str(PACKAGE / 'scripts/caveman_start.py')], env=env, text=True))
    assert 'hookSpecificOutput' not in run()
    for root in (Path(directory) / '.agents', Path(env['CODEX_HOME']), Path(env['CLAUDE_CONFIG_DIR'])):
        skill = root / 'skills/caveman/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\nname: caveman\n---\nFixture: preserve language and exact errors.\n')
        output = run()['hookSpecificOutput']
        assert output['hookEventName'] == 'SessionStart'
        assert 'full intensity' in output['additionalContext']
        assert 'turn it off' in output['additionalContext']
        assert 'Fixture: preserve language and exact errors.' in output['additionalContext']
        assert 'name: caveman' not in output['additionalContext']
        skill.unlink()
print('PASS: Caveman startup hooks, installed skill lookup, opt-out preservation and missing dependency')
