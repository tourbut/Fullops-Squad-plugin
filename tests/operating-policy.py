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
        self.repo = Path(self.temp.name).resolve()
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
        self.assertEqual(policy.load(self.repo)['subagent_level'], 'lite')
        self.assertEqual(jev_route.coordinator_role(self.repo), 'coor')
        self.assertEqual(jev_route.marked_role(self.repo, 'tester'), 'tester')
        path = self.repo / '.fullops-squad/fullops.json'
        old = self.config()
        for key in ('mode', 'primary_role', 'test_level', 'subagent_level'):
            old.pop(key, None)
        storage.write_json(path, old)
        self.assertEqual((policy.load(self.repo)['mode'], policy.load(self.repo)['test_level']), ('coor', 'standard'))
        self.assertEqual(policy.load(self.repo)['subagent_level'], 'off')
        # An ordinary setup update must not opt a legacy repository into delegation.
        self.apply(local_only=True)
        self.assertEqual(policy.load(self.repo)['subagent_level'], 'off')
        for key in ('mode', 'test_level', 'subagent_level'):
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
        options = {'local_only': True, 'mode': 'dev', 'test_level': 'minimal', 'subagent_level': 'standard'}
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
        self.assertEqual(policy.load(self.repo)['test_level'], 'minimal')
        self.assertEqual(policy.load(self.repo)['subagent_level'], 'standard')
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
        self.assertEqual(policy.LEVELS, ('minimal', 'lite', 'standard', 'full', 'exhaustive'))
        commands = [{'name': level, 'kind': 'test', 'level': level, 'run': [sys.executable, '-c', 'print("ok")']}
                    for level in policy.LEVELS]
        commands += [{'name': 'security', 'kind': 'test', 'level': 'exhaustive', 'required': True,
                      'run': [sys.executable, '-c', 'print("security")']},
                     {'name': 'existing', 'kind': 'test', 'run': [sys.executable, '-c', 'print("existing")']}]
        for index, level in enumerate(policy.LEVELS):
            with self.subTest(level=level):
                self.assertEqual([policy.command_selected(command, level) for command in commands],
                                 [i <= index for i in range(5)] + [True, True])
                self.assertIn(level, policy.test_brief(level))
        config_path = self.repo / lint.CONFIG
        settings = json.loads(config_path.read_text())
        storage.write_json(config_path, {**settings, 'commands': commands})
        base = self.commit()
        self.config(test_level='exhaustive')
        (self.repo / 'app.py').write_text('value = 1\n')
        head = self.commit()
        result = lint.lint(self.repo, base)
        self.assertEqual(result['head'], head)
        self.assertEqual(result['test_level'], 'lite')
        self.assertEqual([c['status'] for c in result['commands']],
                         ['passed', 'passed', 'skipped', 'skipped', 'skipped', 'passed', 'passed'])
        (self.repo / 'NOTES.md').write_text('docs only\n')
        docs = self.commit()
        result = lint.lint(self.repo, head)
        # 문서만 바뀌면 required 검사만 실행하고 check도 같은 생략을 허용한다.
        self.assertEqual([c['status'] for c in result['commands']], ['skipped'] * 5 + ['passed', 'skipped'])
        self.assertEqual(result['commands'][0]['reason'], lint.NO_CODE)
        review.check_lint(self.repo, {'base': head, 'head': docs}, result)
        forged = json.loads(json.dumps(lint.lint(self.repo, base)))
        forged['commands'][0].update(status='skipped', reason=lint.NO_CODE)
        with self.assertRaisesRegex(ValueError, '실행되지'):
            review.check_lint(self.repo, {'base': base, 'head': docs}, forged)
        self.assertTrue(policy.command_selected({'kind': 'test'}, 'lite'))
        with self.assertRaises(policy.PolicyError):
            policy.command_selected({'kind': 'lint', 'level': 'full'}, 'lite')
        with self.assertRaises(policy.PolicyError):
            policy.command_selected({'kind': 'test', 'required': 'false'}, 'lite')

    def test_subagent_update_and_handover_inherit_independent_levels(self):
        self.assertEqual(policy.SUBAGENT_LEVELS, ('off', 'lite', 'standard', 'full'))
        for level in policy.SUBAGENT_LEVELS:
            self.assertIn(level, policy.subagent_brief(level))
        with self.assertRaises(policy.PolicyError):
            policy.subagent_brief('unknown')
        guide = self.repo / '.fullops-squad/FULLOPS.md'
        guide.write_text(guide.read_text(encoding='utf-8') + '\nUSER WORKFLOW\n', encoding='utf-8')
        before = self.snapshot()
        self.apply(local_only=True, test_level='exhaustive', subagent_level='off', dry_run=True)
        self.assertEqual(before, self.snapshot())
        self.apply(local_only=True, test_level='exhaustive', subagent_level='off')
        operating = policy.load(self.repo)
        self.assertEqual((operating['test_level'], operating['subagent_level']), ('exhaustive', 'off'))
        self.assertIn('USER WORKFLOW', guide.read_text(encoding='utf-8'))
        self.assertIn('rules/delegation.md', guide.read_text(encoding='utf-8'))
        with redirect_stdout(io.StringIO()):
            work.new(self.repo, 'dev', 'INHERIT', 'use configured levels')
        meta = work.deliverables.front_matter((self.repo / '.fullops-squad/handovers/to_dev.md').read_text(encoding='utf-8'))
        self.assertEqual((meta['test_level'], meta['subagent_level']), ('exhaustive', 'off'))

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
        # 설정·에셋만 바뀐 소규모 변경은 독립 리뷰를 요구하지 않는다.
        self.assertFalse(review.need(self.repo, base, head)['required'])
        with patch.object(review, 'direct_check') as check:
            self.assertEqual(hook('stop'), {})
            check.assert_not_called()
        large = patch.object(review, 'need', return_value={'required': True})
        large.start()
        self.addCleanup(large.stop)
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

    def test_review_need_uses_base_policy_size_and_always_paths(self):
        (self.repo / 'notes.md').write_text('docs\n')
        docs = self.commit()
        self.assertEqual(review.need(self.repo, self.base, docs)['action'], 'skip')
        (self.repo / 'big.py').write_text(''.join(f'value_{i} = {i}\n' for i in range(400)))
        big = self.commit()
        decision = review.need(self.repo, docs, big)
        # 대규모여도 기본값은 사용자에게 먼저 묻는다.
        self.assertEqual((decision['action'], decision['code_files'], decision['code_lines']), ('ask', 1, 400))
        with self.assertRaisesRegex(ValueError, 'user'):
            review.waive(self.repo, 'BIG', docs, big, 'skip it', 'coordinator')
        with patch.object(review, 'check') as check:
            with self.assertRaisesRegex(ValueError, '면제'):
                review.direct_check(self.repo, docs, big, 'author')
            with redirect_stdout(io.StringIO()):
                review.waive(self.repo, 'BIG', docs, big, '사용자: 이번 리팩터링은 리뷰 생략', 'user')
            review.direct_check(self.repo, docs, big, 'author')
            check.assert_not_called()
        with self.assertRaisesRegex(ValueError, '보존'):
            review.waive(self.repo, 'BIG', docs, big, 'again', 'user')
        self.config(review_policy={'min_code_lines': 400, 'min_code_files': 15, 'always': ['auth/**'], 'auto': True})
        configured = self.commit()
        (self.repo / 'auth').mkdir()
        (self.repo / 'auth/token.py').write_text('value = 1\n')
        self.config(review_policy={'min_code_lines': 100000, 'min_code_files': 1000, 'always': []})
        weakened = self.commit()
        # 작업 브랜치의 정책 완화는 기준 시점 판정을 바꾸지 못한다.
        self.assertEqual(review.need(self.repo, configured, weakened)['always'], ['auth/token.py'])
        self.assertEqual(review.need(self.repo, configured, weakened)['action'], 'review')  # 기준 설정 auto=true
        with self.assertRaises(policy.PolicyError):
            policy.validate({'schema_version': 1, 'review_policy': {'min_code_lines': -1}})

    def test_review_reports_and_specs_do_not_trip_integration_or_inbox_gates(self):
        import hashlib
        listing = {'tasks': [{'id': 'task_r', 'spec': 'Task key: K; Purpose: review; Review SHA: ' + 'a' * 40}]}
        with patch.object(integration, 'orca', return_value=listing):
            integration.record(self.repo, [{'id': 'msg_review', 'type': 'worker_done', 'body': '[리뷰] K 수락 가능',
                                            'payload': {'taskId': 'task_r'}, 'run_id': 'run_1'}])
        saved = integration.directory(self.repo) / (hashlib.sha256(b'msg_review').hexdigest() + '.json')
        self.assertFalse(saved.exists())  # 읽기 전용 리뷰 보고는 미병합 결과가 아니다.
        log = 'read .fullops-squad/handovers/logs/2026-10-16_to_dev.md'
        self.assertIsNone(flow_gate.dispatch_inbox_denial(f'worker-start --spec "Task key: K; Purpose: review; {log}"'))
        self.assertIsNotNone(flow_gate.dispatch_inbox_denial(f'worker-start --spec "Task key: K; {log}"'))

    def test_abandoned_review_closes_pending_folder_without_acceptance(self):
        folder = self.repo / '.fullops-squad/docs/evaluations/qa-reports/STOP-review'
        storage.write_json(folder / 'result.json', {'base': self.base, 'head': self.base, 'conclusion': '',
                                                    'files': [{'review_status': 'pending'}]})
        self.assertFalse(review.abandoned(self.repo, 'STOP'))
        with self.assertRaisesRegex(ValueError, 'reason'):
            review.abandon(self.repo, 'STOP', ' ')
        review.abandon(self.repo, 'STOP', 'user waived small change')
        self.assertTrue(review.abandoned(self.repo, 'STOP'))
        storage.write_json(folder / 'result.json', {'conclusion': 'tampered'})
        self.assertFalse(review.abandoned(self.repo, 'STOP'))

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
