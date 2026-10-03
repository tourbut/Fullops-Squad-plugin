"""coor 실세션의 오차단·완료 수집 실패를 외부 세션 변경 없이 재현한다."""
import hashlib
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

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import flow_gate
import integration


class SessionRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fullops-session-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.fullops-squad').mkdir()
        (self.root / '.fullops-squad/fullops.json').write_text(json.dumps({
            'roles': {'dev': 'fullops/dev'}, 'git': {'remote': 'origin', 'base': 'main'}}))

    def gate(self, command):
        with patch.object(flow_gate, 'context', return_value=('coordinator', None)):
            return flow_gate.tool_denial(self.root, {'tool_input': {'cmd': command}}, {})

    def test_help_batch_and_real_dispatch(self):
        self.assertIsNone(self.gate('orca orchestration worker-start --help; git status --short'))
        self.assertIn('--run', self.gate('orca orchestration worker-start --help; orca orchestration worker-start --spec K1'))
        self.assertIn('--run', self.gate('orca orchestration worker-start --spec "Read --help first"'))
        self.assertIn('작업 지시', self.gate('orca orchestration worker-start --help; orca terminal send --terminal term_dev --text "Please implement this follow-up feature and report all results"'))

    def test_powershell_spec_variable_keeps_task_key(self):
        routes = self.root / '.fullops-squad/docs/evaluations/jev'
        routes.mkdir(parents=True)
        (routes / 'K1-route.json').write_text('{"route":"simple"}')
        with patch.object(integration, 'denial', return_value=None), \
             patch.object(integration, 'baseline_denial', return_value=None):
            self.assertIsNone(self.gate('$spec=\'Task key: K1. Read inbox\'; orca orchestration worker-start --spec $spec --run run_live --worktree path:dev'))
            self.assertIsNone(self.gate('$spec = @\'\nTask key: K1. Read inbox\n\'@\n orca orchestration worker-start --spec $spec --run run_live --worktree path:dev'))

    def test_route_sentence_punctuation_and_distinct_keys(self):
        routes = self.root / '.fullops-squad/docs/evaluations/jev'
        routes.mkdir(parents=True)
        (routes / 'K1-route.json').write_text('{"route":"simple"}')
        self.assertIsNone(flow_gate.route_key_denial(self.root, '--spec "Task key: K1. Read inbox"'))
        for key in ('K1.2', 'K1-other', 'K10'):
            self.assertIsNotNone(flow_gate.route_key_denial(self.root, f'--spec "Task key: {key}"'))

    def test_path_and_id_selector_keep_baseline_check(self):
        def git(root, *args):
            if Path(root) != self.root:
                raise subprocess.CalledProcessError(1, ['git'])
            return 'fullops/dev'
        with patch.object(integration, 'git', side_effect=git), \
             patch.object(integration, 'directory', return_value=self.root), \
             patch.object(integration, 'ancestor', return_value=False) as check:
            for selector in (f'path:{self.root}', f'id:repo::{self.root}'):
                self.assertIn('동기화', integration.baseline_denial(self.root, f'worker-start --worktree "{selector}"'))
                check.assert_called()

    def test_check_preserves_terminal_and_run(self):
        with patch.object(flow_gate, 'orca', return_value={'messages': []}) as cli:
            self.gate('orca orchestration check --terminal term_coor --run run_live --wait')
            self.assertIn('--terminal', cli.call_args.args)
            self.assertIn('term_coor', cli.call_args.args)
            self.assertIn('run_live', cli.call_args.args)

    def test_actual_worker_prose_task_metadata_and_redelivery(self):
        sha = '42e8c9f1d39b77e70e0c9ce3b3d0f58660de0e87'
        message = {'id': 'msg_live', 'type': 'worker_done', 'run_id': 'run_live',
                   'body': f'기준 SHA aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, 최종 로컬 SHA는 {sha}이고 인박스는 비었습니다.',
                   'payload': json.dumps({'taskId': 'task_live', 'outcome': 'succeeded'})}
        with patch.object(integration, 'directory', return_value=self.root), \
             patch.object(integration, 'orca', return_value={'tasks': [{'id': 'task_live', 'spec': 'Task key: K1. Refer to K0.'}]}):
            routes = self.root / '.fullops-squad/docs/evaluations/jev'
            routes.mkdir(parents=True)
            (routes / 'K1-route.json').write_text('{}')
            (routes / 'K0-route.json').write_text('{}')
            path = self.root / (hashlib.sha256(b'msg_live').hexdigest() + '.json')
            path.write_text(json.dumps({'message': 'msg_live', 'key': '', 'sha': None, 'hold': {'reason': 'review'}}))
            integration.record(self.root, [message])
            saved = json.loads(path.read_text())
            self.assertEqual(saved['sha'], sha)
            self.assertEqual(saved['key'], 'K1')
            self.assertEqual(saved['hold'], {'reason': 'review'})

    def test_hold_recovers_message_from_explicit_terminal(self):
        message = {'id': 'msg_recovered', 'type': 'worker_done', 'body': '[완료] K1 | SHA abcdef0123456789'}
        args = ['integration.py', '--repo', str(self.root), 'hold', '--message', 'msg_recovered',
                '--run', 'run_live', '--terminal', 'term_coor', '--reason', 'review', '--owner', 'dev', '--resume', 'pass']
        with patch.object(integration, 'git', return_value=str(self.root)), \
             patch.object(integration, 'directory', return_value=self.root), \
             patch.object(integration, 'orca', return_value={'messages': [message]}) as cli, \
             patch.object(sys, 'argv', args), redirect_stdout(io.StringIO()):
            integration.main()
        self.assertIn('term_coor', cli.call_args.args)
        self.assertIn('run_live', cli.call_args.args)
        saved = json.loads((self.root / (hashlib.sha256(b'msg_recovered').hexdigest() + '.json')).read_text())
        self.assertEqual(saved['hold']['reason'], 'review')
        self.assertEqual(saved['sha'], 'abcdef0123456789')

    def test_latest_local_commit_report_and_ambiguous_refs(self):
        sha = '7a8dac866dee2e647d034ca276365c1d0cf29820'
        reports = [
            ('latest', f'git diff --check exit 0; work.py finish archived the full report. Local commit {sha} on fullops/dev, not pushed; main db815ff not merged.', sha),
            ('with-base', f'Baseline SHA aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa. Local commit {sha} on fullops/dev.', sha),
            ('ambiguous', 'Review commit aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa and commit bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.', None),
        ]
        with patch.object(integration, 'directory', return_value=self.root):
            for message_id, body, expected in reports:
                integration.record(self.root, [{'id': message_id, 'type': 'worker_done', 'body': body}])
                path = self.root / (hashlib.sha256(message_id.encode()).hexdigest() + '.json')
                self.assertEqual(json.loads(path.read_text())['sha'], expected, body)

    def test_handled_reads_nested_logs_and_primary_base(self):
        nested = self.root / '.fullops-squad/handovers/logs/2026-10-03/report.md'
        nested.parent.mkdir(parents=True)
        nested.write_text('# K1 — completed\n')
        self.assertTrue(flow_gate.handled(self.root, 'K1'))
        self.assertFalse(flow_gate.handled(self.root, 'K10'))
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.root)], check=True)
        def git(*args):
            subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)
        git('add', '.')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'setup')
        git('checkout', '-qb', 'fullops/coor')
        nested.unlink()
        git('add', '.')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'old coor checkout')
        head = subprocess.check_output(['git', '-C', str(self.root), 'rev-parse', 'HEAD'])
        self.assertTrue(flow_gate.handled(self.root, 'K1'))
        self.assertFalse(flow_gate.handled(self.root, 'K10'))
        self.assertEqual(subprocess.check_output(['git', '-C', str(self.root), 'rev-parse', 'HEAD']), head)
        self.assertFalse(nested.exists())

    def test_unknown_hold_has_actionable_error(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'integration.py'), '--repo', str(self.root),
                                 'hold', '--message', 'unknown', '--reason', 'review', '--owner', 'dev',
                                 '--resume', 'review passed'], capture_output=True, text=True, encoding='utf-8',
                                env={**os.environ, 'FULLOPS_ORCA_CLI': str(self.root / 'missing-orca')})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Traceback', result.stderr)
        self.assertIn('--terminal', result.stderr)


if __name__ == '__main__':
    unittest.main()
