"""프런트엔드 선택·격리·실패 상태와 고정 모델 보존. 실제 호스트·유료 API·전역 설치는 사용하지 않는다."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import deps
import frontend
import jev_route
import setup
from storage import write_json


class Frontend(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fullops-frontend-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'service with spaces'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.repo)], check=True)
        with redirect_stdout(io.StringIO()):
            setup.setup(self.repo, roles=['dev'], local_only=True)
        self.config = self.repo / frontend.CONFIG

    def save(self, **changes):
        data = {**frontend.DEFAULT, **changes}
        write_json(self.config, data)
        return data

    def snapshot(self):
        return {p.relative_to(self.repo).as_posix(): p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}

    def test_defaults_and_setup_preserve_selection(self):
        self.assertEqual(frontend.selection(self.repo)['tools'], [])
        self.save(host='grok', model='grok-fixed', effort='high', design='brand.md')
        before = self.config.read_bytes()
        with redirect_stdout(io.StringIO()):
            setup.setup(self.repo, roles=['dev'], local_only=True)
        self.assertEqual(self.config.read_bytes(), before)
        config = frontend.selection(self.repo, primary='ui-ux-pro-max')
        self.assertEqual((config['host'], config['model'], config['effort']), ('grok', 'grok-fixed', 'high'))
        self.assertIsNone(frontend.selection(self.repo, host='codex')['model'])
        self.assertEqual(self.config.read_bytes(), before)

    def test_dry_run_all_hosts_is_read_only_and_has_no_optional_default(self):
        before = self.snapshot()
        for host in deps.COMMON_HOSTS:
            args = [sys.executable, str(SCRIPTS / 'frontend.py'), '--repo', str(self.repo), '--host', host,
                    '--model', 'fixed-model', '--effort', 'medium', '--install', '--dry-run']
            result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                                    env={**os.environ, 'FULLOPS_OFFLINE': '1'})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['install'], [])
        self.assertEqual(self.snapshot(), before)

    def test_optional_plan_is_local_and_react_only(self):
        with self.assertRaises(ValueError):
            frontend.selection(self.repo, tools=['shadcn'])
        write_json(self.repo / 'package.json', {'dependencies': {'react': 'test'}})
        config = frontend.selection(self.repo, tools=['playwright', 'shadcn', 'impeccable-engine'])
        plan = frontend.install_plan(self.repo, config)
        self.assertEqual(len(plan), 3)
        for command in plan:
            self.assertIn('--ignore-scripts', command)
            self.assertNotIn('--global', command)
            self.assertNotIn('--trust', command)
            self.assertTrue(Path(command[command.index('--prefix') + 1]).is_relative_to(self.repo / '.fullops-squad/tools/frontend'))
        self.save(enabled=False, tools=['shadcn'])
        (self.repo / 'package.json').unlink()
        disabled = frontend.selection(self.repo)
        self.assertEqual(frontend.install_plan(self.repo, disabled), [])
        with patch.object(deps, 'skill_files', side_effect=AssertionError('disabled check')):
            self.assertEqual(frontend.inspect(self.repo, disabled)['status'], 'disabled')

    def test_malformed_and_escaping_inputs_are_rejected(self):
        for changes in ({'design': '../secret'}, {'tokens': ['/outside']}, {'components': 'src'},
                        {'tools': ['unknown']}, {'review': ['impeccable', 'impeccable']},
                        {'primary': 'impeccable', 'review': ['impeccable']},
                        {'host': 'grok', 'model': 'm'}, {'host': 'wrapper'}, {'enabled': 'false'}):
            with self.subTest(changes=changes):
                self.save(**changes)
                with self.assertRaises(ValueError):
                    frontend.selection(self.repo)
        for value in ([], {'unknown': True}):
            write_json(self.config, value)
            with self.assertRaises(ValueError):
                frontend.selection(self.repo)

    def test_check_only_selected_skills_and_tools_and_no_false_qa(self):
        (self.repo / 'DESIGN.md').write_text('existing visual truth')
        for host in deps.COMMON_HOSTS:
            config = frontend.selection(self.repo, host=host, model='fixed', effort='low', tools=['playwright'])
            with patch.object(deps, 'skill_files', return_value=(['skill/SKILL.md'], [])) as skills, \
                 patch.object(frontend.shutil, 'which', return_value='host'), \
                 patch.object(frontend, 'tool_status', return_value='cli_verified') as tools:
                result = frontend.inspect(self.repo, config)
                self.assertEqual(result['status'], 'configuration_ready')
                self.assertEqual(skills.call_args.args[0], host)
                self.assertEqual([s['names'] for s in skills.call_args.args[1]], [['frontend-design']])
                tools.assert_called_once_with(self.repo, 'playwright')
                self.assertEqual({result[k] for k in ('authentication', 'browser_qa', 'mcp_connection')}, {'not_run'})
        with patch.object(deps, 'skill_files', return_value=([], ['missing skill'])), \
             patch.object(frontend.shutil, 'which', return_value=None), \
             patch.object(frontend, 'tool_status', return_value='execution_failed'):
            result = frontend.inspect(self.repo, config)
            self.assertEqual(result['status'], 'needs_attention')
            self.assertGreaterEqual(len(result['problems']), 3)

    def test_tool_version_failure_and_execution(self):
        self.assertEqual(frontend.tool_status(self.repo, 'playwright'), 'not_installed_or_unavailable')
        root = frontend.tool_root(self.repo, 'playwright') / 'node_modules'
        write_json(root / '@playwright/cli/package.json', {'name': 'other-cli', 'version': '9.2.0'})
        self.assertEqual(frontend.tool_status(self.repo, 'playwright'), 'package_identity_mismatch')
        write_json(root / '@playwright/cli/package.json', {'name': '@playwright/cli', 'version': '9.2.0'})
        with patch.object(frontend.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '9.2.0\n', '')):
            self.assertEqual(frontend.tool_status(self.repo, 'playwright'), 'cli_verified')
        with patch.object(frontend.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '8.0.0\n', '')):
            self.assertEqual(frontend.tool_status(self.repo, 'playwright'), 'execution_failed')
        with patch.object(frontend.subprocess, 'run', return_value=subprocess.CompletedProcess([], 3221226505, '9.2.0\n', 'assertion failed')):
            self.assertEqual(frontend.tool_status(self.repo, 'playwright'), 'execution_failed')
        with patch.object(frontend.subprocess, 'run', side_effect=subprocess.TimeoutExpired('test', 15)):
            self.assertEqual(frontend.tool_status(self.repo, 'playwright'), 'not_installed_or_unavailable')

    def test_common_skill_checks_other_hosts_and_preserves_latest_content(self):
        home = Path(self.temp.name) / 'home'
        raw = b'---\nname: x\n---\nLatest instructions\n'
        item = {'source': 'official/skills', 'names': ['x']}
        data = {'skills': [item], 'codex': {'skills': []}, 'portable_skills': []}
        write_json(home / '.agents/.skill-lock.json', {'skills': {'x': {'source': item['source']}}})
        common = home / '.agents/skills/x/SKILL.md'
        common.parent.mkdir(parents=True)
        common.write_bytes(raw)
        with patch.object(deps.Path, 'home', return_value=home), patch.object(deps, 'manifest', return_value=data), \
             patch.dict('os.environ', {'CODEX_HOME': str(home / '.codex'), 'CLAUDE_CONFIG_DIR': str(home / '.claude')}):
            command = deps.skill_command(item, list(deps.COMMON_HOSTS))
            self.assertTrue(deps.command_skill_problems('codex', command))  # Claude runtime link is missing.
            claude = home / '.claude/skills/x/SKILL.md'
            claude.parent.mkdir(parents=True)
            claude.write_bytes(raw.replace(b'\n', b'\r\n'))
            self.assertEqual(deps.command_skill_problems('codex', command), [])
            extra = common.parent / 'references/local.md'
            extra.parent.mkdir()
            extra.write_text('locally changed reference')
            with redirect_stdout(io.StringIO()):
                deps.backup_skills('codex', command)
            backups = list((home / '.codex/fullops-skill-backups').glob('*/x/references/local.md'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), 'locally changed reference')
            claude.write_text('locally changed')
            self.assertEqual(deps.required_skills('codex')[1], [])
            with redirect_stdout(io.StringIO()):
                deps.backup_skills('codex', command)
            backups = list((home / '.claude/fullops-skill-backups').glob('*/x/SKILL.md'))
            self.assertEqual(len(backups), 2)
            self.assertIn('locally changed', [p.read_text() for p in backups])
            self.assertEqual(claude.read_text(), 'locally changed')
            write_json(home / '.agents/.skill-lock.json', {'skills': {'x': {'source': 'other/skills'}}})
            self.assertTrue(any('source unverified' in p for p in deps.skill_files('codex')[1]))

    def test_skill_backup_preserves_unverified_and_shadowed_folders(self):
        home = Path(self.temp.name) / 'backup-home'
        item = {'source': 'official/skills', 'names': ['research']}
        write_json(home / '.agents/.skill-lock.json', {'skills': {'research': {'source': 'local/skills'}}})
        for relative, content in (('.agents', 'canonical edit'), ('.codex', 'codex edit'), ('.claude', 'claude edit'), ('.grok', 'grok edit')):
            folder = home / relative / 'skills/research'
            folder.mkdir(parents=True)
            (folder / 'SKILL.md').write_text(content)
            (folder / 'local.txt').write_text(content)
        with patch.object(deps.Path, 'home', return_value=home), \
             patch.dict('os.environ', {'CODEX_HOME': str(home / '.codex'), 'CLAUDE_CONFIG_DIR': str(home / '.claude')}):
            for host in deps.COMMON_HOSTS:
                for names in (['research'], ['*']):
                    selected = {**item, 'names': names}
                    data = {'skills': [selected], 'codex': {'skills': []}, 'portable_skills': []}
                    with self.subTest(host=host, names=names), redirect_stdout(io.StringIO()), \
                         patch.object(deps, 'manifest', return_value=data):
                        deps.backup_skills(host, deps.skill_command(selected, [host]))
                backups = list((deps.receipt_path(host).parent / 'fullops-skill-backups').glob('*/research/local.txt'))
                self.assertEqual(len(backups), 2)  # 같은 내용은 두 번째 호출에서 다시 복사하지 않는다
                self.assertEqual({p.read_text() for p in backups}, {'canonical edit', host.split('-')[0] + ' edit'})

    def test_skill_backup_rejects_destination_inside_source(self):
        folder = Path(self.temp.name) / 'x'
        folder.mkdir()
        (folder / 'SKILL.md').write_text('local edit')
        item = {'source': 'official/skills', 'names': ['x']}
        with patch.object(deps, 'command_skills', return_value=[('codex', item)]), \
             patch.object(deps, 'receipt_path', return_value=folder / 'deps.json'), \
             patch.object(deps, 'skill_roots', return_value=[folder.parent]):
            with self.assertRaisesRegex(ValueError, '원본 폴더 밖'):
                deps.backup_skills('codex', [])
        self.assertFalse((folder / 'fullops-skill-backups').exists())

    def test_fixed_tuple_is_recorded_offline(self):
        for host in deps.COMMON_HOSTS:
            result = jev_route.model_only(self.repo, 'UI', 'dev', host, 'user-model', 'low')
            self.assertEqual(result['model']['model'], 'user-model')
            self.assertEqual(result['model']['source'], 'user')
        args = [sys.executable, str(SCRIPTS / 'jev_route.py'), '--repo', str(self.repo), '--key', 'UI',
                '--model-only', '--role', 'dev', '--agent', 'grok',
                '--model', 'user-model', '--effort', 'high', '--strict']
        done = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                              env={**os.environ, 'FULLOPS_OFFLINE': '1', 'OPENROUTER_API_KEY': '', 'TYPESAFE_API_KEY': ''})
        self.assertEqual(done.returncode, 0, done.stderr)
        with self.assertRaises(ValueError):
            jev_route.fixed_model('grok', 'm', None)
        with self.assertRaises(ValueError):
            jev_route.model_only(self.repo, 'UI', '../secret', 'grok', 'm', 'high')

if __name__ == '__main__':
    unittest.main()
