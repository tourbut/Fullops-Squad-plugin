"""운영 모드 전환·주 담당 권한·검사 레벨의 핵심 실패 경계를 임시 Git 레포로 확인한다."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/fullops-squad/scripts'))
import done_gate
import flow_gate
import integration
import jev_route
import lint
import policy
import review
import setup
import storage
import work


class OperatingPolicy(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fullops-mode-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'core.autocrlf', 'false')
        self.apply(roles=['coor', 'designer', 'dev', 'tester'], local_only=True)
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True).strip()

    def apply(self, **options):
        with redirect_stdout(io.StringIO()):
            return setup.setup(self.repo, **options)

    def commit(self):
        self.git('add', '-A')
        self.git('-c', 'user.name=test', '-c', 'user.email=test@example.test', 'commit', '-qm', 'fixture')
        return self.git('rev-parse', 'HEAD')

    def config(self, **changes):
        path = self.repo / '.fullops-squad/fullops.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data.update(changes)
        storage.write_json(path, data)
        return data

    def snapshot(self):
        return {p.relative_to(self.repo).as_posix(): p.read_bytes() for p in self.repo.rglob('*')
                if p.is_file() and '.git' not in p.relative_to(self.repo).parts}

    def test_defaults_legacy_and_invalid_values(self):
        self.assertEqual(policy.load(self.repo)['test_level'], 'lite')
        self.assertEqual(jev_route.coordinator_role(self.repo), 'coor')
        self.assertEqual(jev_route.marked_role(self.repo, 'tester'), 'tester')
        path = self.repo / '.fullops-squad/fullops.json'
        old = self.config()
        for key in ('mode', 'primary_role', 'test_level'):
            old.pop(key, None)
        storage.write_json(path, old)
        self.assertEqual((policy.load(self.repo)['mode'], policy.load(self.repo)['test_level']), ('coor', 'standard'))
        for key in ('mode', 'test_level'):
            storage.write_json(path, {**old, key: 'unknown'})
            with self.assertRaises(policy.PolicyError):
                work.active_repo(self.repo)

    def test_preview_preservation_retry_and_rollback(self):
        header = '\ufeff---\r\nowner: "user" # preserve comment\r\ncustom:\r\n  nested: true\r\n---\r\n'
        body = '\r\n# User guide\r\nUSER MODEL CHOICE\r\n'
        updated = setup.operating_block(header + body, '.fullops-squad/orca-agents.md')
        self.assertTrue(updated.startswith(header))
        self.assertTrue(updated.endswith(body))
        self.assertEqual(setup.operating_block(updated, '.fullops-squad/orca-agents.md'), updated)
        with self.assertRaisesRegex(ValueError, '메타데이터'):
            setup.operating_block('---\nowner: user', '.fullops-squad/orca-agents.md')
        with self.assertRaisesRegex(ValueError, '메타데이터'):
            setup.operating_block('---\nowner: user\n<!-- fullops-mode:start -->\nold\n<!-- fullops-mode:end -->', '.fullops-squad/orca-agents.md')
        agents = self.repo / '.fullops-squad/orca-agents.md'
        content = agents.read_text(encoding='utf-8')
        start, end = '<!-- fullops-mode:start -->', '<!-- fullops-mode:end -->'
        # A legacy guide guarantees two planned writes, independently of host line endings.
        content = content[:content.index(start)] + content[content.index(end) + len(end):]
        agents.write_text(content + '\nUSER MODEL CHOICE\n', encoding='utf-8')
        self.commit()
        before = self.snapshot()
        options = {'local_only': True, 'mode': 'dev', 'test_level': 'lite'}
        self.apply(dry_run=True, verbose=True, **options)
        self.assertEqual(before, self.snapshot())
        original = setup.atomic_write
        count = 0
        def interrupt(path, content):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected write interruption')
            original(path, content)
        with patch.object(setup, 'atomic_write', side_effect=interrupt):
            with self.assertRaises(OSError):
                self.apply(**options)
        with self.assertRaises(policy.PolicyError):
            work.active_repo(self.repo)
        command = f'python3 "{setup.__file__}" --repo "{self.repo}" --rollback'
        event = {'cwd': str(self.repo), 'tool_input': {'command': command}}
        with patch.object(sys, 'argv', ['flow_gate.py', 'tool']), patch.object(sys, 'stdin', io.StringIO(json.dumps(event))):
            self.assertEqual(flow_gate.main(), {})
        self.apply(rollback=True)
        self.assertEqual(before, self.snapshot())
        with patch.object(setup, 'atomic_write', side_effect=interrupt):
            count = 0
            with self.assertRaises(OSError):
                self.apply(**options)
        self.apply(**options)
        self.assertEqual(policy.load(self.repo)['mode'], 'dev')
        self.assertIn('USER MODEL CHOICE', agents.read_text(encoding='utf-8'))
        self.assertEqual(json.loads(before['.fullops-squad/fullops.json'])['roles'], policy.load(self.repo)['roles'])
        self.assertEqual(self.apply(**options), [])

    def test_primary_role_only_interruption_retry(self):
        with patch.object(setup, 'atomic_write', side_effect=OSError('interruption')):
            with self.assertRaises(OSError):
                self.apply(local_only=True, primary_role='dev')
        command = f'python3 "{setup.__file__}" --repo "{self.repo}" --local-only --primary-role dev'
        event = {'cwd': str(self.repo), 'tool_input': {'command': command}}
        with patch.object(sys, 'argv', ['flow_gate.py', 'tool']), patch.object(sys, 'stdin', io.StringIO(json.dumps(event))):
            self.assertEqual(flow_gate.main(), {})
        self.apply(local_only=True, primary_role='dev')
        self.assertEqual(policy.load(self.repo)['primary_role'], 'dev')

    def test_single_dev_role_can_write_code(self):
        single = self.repo / 'single'
        single.mkdir()
        subprocess.run(['git', '-C', str(single), 'init', '-q', '-b', 'main'], check=True)
        with redirect_stdout(io.StringIO()):
            setup.setup(single, roles=['dev'], local_only=True)
        subprocess.run(['git', '-C', str(single), 'checkout', '-qb', 'fullops/dev'], check=True)
        self.assertEqual(flow_gate.context(single), ('dev', 'architecture'))
        event = {'tool_input': {'file_path': str(single / 'app.py'), 'content': 'print("ok")'}}
        self.assertIsNone(flow_gate.tool_denial(single, event, {}))

    def test_dirty_dispatch_hold_and_review_block_transition(self):
        options = {'local_only': True, 'mode': 'dev'}
        extra = self.repo / 'user-note.txt'
        extra.write_text('preserve')
        with self.assertRaisesRegex(ValueError, 'dirty'):
            self.apply(**options)
        extra.unlink()
        gate = Path(self.git('rev-parse', '--absolute-git-dir')) / 'fullops-gate/flow-worker.json'
        storage.write_json(gate, {'dispatch': 'active', 'settled': False})
        with self.assertRaisesRegex(ValueError, 'dispatch'):
            self.apply(**options)
        storage.write_json(gate, {'runs': ['run1']})
        with patch.object(flow_gate, 'run_state', return_value=(1, [])) as peek:
            with self.assertRaisesRegex(ValueError, 'Run'):
                self.apply(**options)
            peek.assert_called_once_with('run1')
        gate.unlink()
        storage.write_json(integration.directory(self.repo) / 'held.json', {'hold': True})
        with self.assertRaisesRegex(ValueError, '보류'):
            self.apply(**options)

    def test_primary_alias_dispatch_and_routing_candidate(self):
        self.apply(local_only=True, mode='dev')
        self.commit()
        config = policy.load(self.repo)
        self.assertEqual(policy.identity(self.repo, config), ('dev', True))
        self.git('checkout', '-qb', 'fullops/dev')
        self.assertEqual(policy.identity(self.repo, config), ('dev', True))
        self.assertEqual(policy.identity(self.repo, config, dispatched=True), ('dev', False))
        self.assertTrue(flow_gate.primary(self.repo, {}))
        self.assertFalse(flow_gate.primary(self.repo, {'dispatch': 'worker'}))
        event = {'tool_input': {'command': 'python3 work.py new --role dev --key DIRECT --goal fix'}}
        self.assertIsNone(flow_gate.tool_denial(self.repo, event, {}))
        event['tool_input']['command'] = 'python3 work.py new --role tester --key EXPERT --goal verify'
        self.assertIn('route', flow_gate.tool_denial(self.repo, event, {}))
        agents = self.repo / '.fullops-squad/orca-agents.md'
        agents.write_text(agents.read_text(encoding='utf-8').replace('- coordinator 역할: `coor`', '- coordinator 역할: `dev`'), encoding='utf-8')
        self.assertIsNone(jev_route.coordinator_role(self.repo))
        def classify(payload):
            self.assertIn('dev', payload['questions']['role']['criteria'])
            raise RuntimeError('no network required')
        jev_route.classify(self.repo, 'K', 'implement existing requirement', classify)

    def test_levels_run_required_and_reject_branch_weakening(self):
        commands = [{'name': level, 'kind': 'test', 'level': level, 'run': [sys.executable, '-c', 'print("ok")']}
                    for level in policy.LEVELS]
        commands += [{'name': 'security', 'kind': 'test', 'level': 'full', 'required': True,
                      'run': [sys.executable, '-c', 'print("security")']}]
        config_path = self.repo / lint.CONFIG
        settings = json.loads(config_path.read_text())
        storage.write_json(config_path, {**settings, 'commands': commands})
        base = self.commit()
        self.config(test_level='full')
        head = self.commit()
        result = lint.lint(self.repo, base)
        self.assertEqual(result['head'], head)
        self.assertEqual(result['test_level'], 'lite')
        self.assertEqual([c['status'] for c in result['commands']], ['passed', 'skipped', 'skipped', 'passed'])
        self.assertTrue(policy.command_selected({'kind': 'test'}, 'lite'))
        with self.assertRaises(policy.PolicyError):
            policy.command_selected({'kind': 'lint', 'level': 'full'}, 'lite')
        with self.assertRaises(policy.PolicyError):
            policy.command_selected({'kind': 'test', 'required': 'false'}, 'lite')

    def test_direct_review_requires_current_author_and_independent_session(self):
        path = self.repo / '.fullops-squad/docs/evaluations/qa-reports/K-review/result.json'
        head = self.git('rev-parse', 'HEAD')
        result = {'base': head, 'head': head, 'review_schema_version': 2,
                  'independence': {'implementer_session': 'author'}}
        storage.write_json(path, result)
        with self.assertRaises(ValueError):
            review.direct_check(self.repo, head, head, 'other-author')
        with patch.object(review, 'check') as check:
            review.direct_check(self.repo, head, head, 'author')
            check.assert_called_once_with(self.repo, 'K', head, head)
        storage.write_json(path.with_name('snapshot-cleanup.json'), {'state': 'removed'})
        with patch.object(review, 'historical') as historical, patch.object(review, 'check') as check:
            review.direct_check(self.repo, head, head, 'author')
            historical.assert_called_once_with(self.repo, 'K')
            check.assert_not_called()
        with patch.object(review, 'historical', side_effect=ValueError('changed evidence')):
            with self.assertRaisesRegex(ValueError, 'changed evidence'):
                review.direct_check(self.repo, head, head, 'author')
        result['independence'].update(reviewer_session='author', read_only=True, snapshot_path=str(self.repo))
        with self.assertRaisesRegex(ValueError, '서로 다른'):
            review.check_independence(self.repo, result)

    def test_direct_stop_cannot_skip_lint_or_independent_review(self):
        self.apply(local_only=True, mode='dev')
        base = self.commit()
        event = {'cwd': str(self.repo), 'sessionId': 'author'}
        def hook(mode, **extra):
            with patch.object(sys, 'argv', ['done_gate.py', mode]), patch.object(
                    sys, 'stdin', io.StringIO(json.dumps({**event, **extra}))):
                return done_gate.main()
        self.assertIn('설정·에셋', hook('start')['hookSpecificOutput']['additionalContext'])
        for name, content in (('package.json', '{"private":true}'), ('app.toml', 'enabled = true'),
                              ('scene.tscn', '[gd_scene format=3]')):
            with self.subTest(name=name):
                (self.repo / name).write_text(content)
                self.assertEqual(hook('stop')['decision'], 'block')
        head = self.commit()
        self.assertEqual(hook('stop')['decision'], 'block')
        self.assertEqual(hook('stop', stopHookActive=True)['decision'], 'block')
        gate = Path(self.git('rev-parse', '--absolute-git-dir')) / 'fullops-gate'
        storage.write_json(gate / 'pass.json', {'head': head, 'base': base})
        self.assertEqual(hook('stop')['decision'], 'block')
        invalid = self.repo / '.fullops-squad/docs/evaluations/qa-reports/BAD-review/result.json'
        storage.write_json(invalid, {'base': base, 'head': head, 'review_schema_version': 2, 'independence': []})
        self.assertEqual(hook('stop')['decision'], 'block')
        invalid.unlink()
        with patch.object(review, 'direct_check') as check:
            self.assertEqual(hook('stop'), {})
            check.assert_called_once_with(self.repo, base, head, 'author')
        storage.write_json(gate / 'flow-author.json', {'dispatch': 'worker'})
        with patch.object(review, 'direct_check') as check:
            self.assertEqual(hook('stop'), {})
            check.assert_not_called()

    def test_superseded_pending_review_preserves_original(self):
        (self.repo / 'app.py').write_text('"""behavior needing review"""\nprint("changed")\n')
        implementation = self.commit()
        qa = self.repo / '.fullops-squad/docs/evaluations/qa-reports'
        old = qa / 'OLD-review/result.json'
        independent = {'review_schema_version': 2, 'independence': {'implementer_session': 'author'}}
        storage.write_json(old, {'base': self.base, 'head': implementation, 'conclusion': '',
                                'files': [{'review_status': 'pending'}], **independent})
        replacement = qa / 'NEW-review'
        result = {'base': implementation, 'head': implementation, 'conclusion': 'accepted', 'files': [], **independent}
        storage.write_json(replacement / 'result.json', result)
        with self.assertRaisesRegex(ValueError, '미검토 변경'):
            review.supersede(self.repo, 'OLD', 'NEW')
        result['base'] = self.base
        storage.write_json(replacement / 'result.json', result)
        for name in ('preview', 'rules', 'lint'):
            storage.write_json(replacement / f'{name}.json', {})
        (replacement / 'report.md').write_text('Independent accepted review')
        original = old.read_bytes()
        self.commit()
        with self.assertRaisesRegex(ValueError, '리뷰'):
            self.apply(local_only=True, mode='dev', dry_run=True)
        with patch.object(review, 'check') as check:
            review.supersede(self.repo, 'OLD', 'NEW')
            check.assert_called_once_with(self.repo, 'NEW', self.base, implementation)
        self.assertEqual(old.read_bytes(), original)
        with patch.object(review, 'check') as check:
            review.direct_check(self.repo, self.base, implementation, 'author')
            check.assert_called_once_with(self.repo, 'NEW', self.base, implementation)
        self.commit()
        self.apply(local_only=True, mode='dev', dry_run=True)
        (replacement / 'report.md').write_text('changed evidence')
        with self.assertRaisesRegex(ValueError, '증거'):
            review.superseded_check(self.repo, 'OLD')


if __name__ == '__main__':
    unittest.main()
