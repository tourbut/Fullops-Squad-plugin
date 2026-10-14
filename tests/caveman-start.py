#!/usr/bin/env python3
"""Check packaged session hooks without touching real user settings."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'dist/native/fullops-squad'
sys.path.insert(0, str(ROOT / 'plugins/fullops-squad/scripts'))
import hook_runtime
import storage


def target(command):
    assert 'CLAUDE_PLUGIN_ROOT' not in command and '/cache/' not in command
    assert '.fullops-squad/runtime/fullops-squad/scripts/hook_runtime.py' in command
    return shlex.split(command)[3:]


for host in ('codex', 'claude'):
    manifest = json.loads((PACKAGE / f'.{host}-plugin/plugin.json').read_text())
    config = json.loads((PACKAGE / manifest['hooks']).read_text())
    assert set(config['hooks']) == {'SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop', 'SessionEnd'}
    group, gate, flow = config['hooks']['SessionStart']
    assert group['matcher'] == 'startup|clear'  # Resume/compact must preserve an opt-out.
    hook, = group['hooks']
    assert target(hook['command']) == ['caveman_start']
    assert 'matcher' not in gate  # done-gate는 resume·compact에도 시작 지점을 확인한다
    assert target(gate['hooks'][0]['command']) == ['done_gate', 'start']
    assert flow['matcher'] == 'startup|clear'
    assert target(flow['hooks'][0]['command']) == ['flow_gate', 'start']
    stop, flow_stop = config['hooks']['Stop']
    assert target(stop['hooks'][0]['command']) == ['done_gate', 'stop']
    assert target(flow_stop['hooks'][0]['command']) == ['flow_gate', 'stop']
    for event, mode in (('UserPromptSubmit', 'prompt'), ('PreToolUse', 'tool'), ('PostToolUse', 'post')):
        entry, = config['hooks'][event]
        assert target(entry['hooks'][0]['command']) == ['flow_gate', mode]

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

# An already-loaded hook command must survive deletion of both old and new caches.
with tempfile.TemporaryDirectory(prefix='fullops hook ') as directory:
    home = Path(directory)
    env = {**os.environ, 'HOME': directory, 'USERPROFILE': directory}
    source = home / 'cache/1.4.2'
    shutil.copytree(PACKAGE, source)
    root = home / '.fullops-squad/runtime/fullops-squad'
    commands = [h['command'] for groups in config['hooks'].values() for g in groups for h in g['hooks']]
    def invoke(command):
        result = subprocess.run([sys.executable, *shlex.split(command)[1:]], input='{}',
                                text=True, capture_output=True, env=env, cwd=home)
        assert result.returncode == 0, (command, result.stderr)
        return result.stdout
    with patch.object(hook_runtime, 'runtime_root', return_value=root):
        subprocess.run([sys.executable, str(source / 'scripts/deps.py'), '--runtime-only'],
                       env=env, check=True, capture_output=True)
        assert not hook_runtime.problems(source)
        previous = (root / 'current.json').read_bytes()
        first = json.loads(previous)['package']
        source.rename(home / 'old-cache-removed')
        for command in commands:
            invoke(command)
        shutil.copytree(PACKAGE, source)
        (source / 'scripts/caveman_start.py').write_text("print('updated runtime')", encoding='utf-8')
        with patch.object(storage, 'write_json', side_effect=OSError('disk failure')):
            try:
                hook_runtime.install(source)
                raise AssertionError('Expected update failure')
            except OSError:
                pass
        assert (root / 'current.json').read_bytes() == previous
        for command in commands:
            invoke(command)
        hook_runtime.install(source)
        source.rename(home / 'new-cache-removed')
        assert invoke(commands[0]).strip() == 'updated runtime'
        assert (root / 'packages' / first / 'scripts/done_gate.py').is_file()
        for command in commands:
            invoke(command)
print('PASS: stable hook commands survive cache removal, updates and failed publication')
