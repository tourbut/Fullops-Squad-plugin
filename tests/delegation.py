"""하위 위임 OFF·목적 제한·오토모드 추적과 세션 지침 주입을 검증한다."""
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
import flow_gate
import issue_mode
import policy
import setup
from storage import write_json


class Delegation(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fullops-delegation-')
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.repo)], check=True)
        with redirect_stdout(io.StringIO()):
            setup.setup(self.repo, roles=['coor', 'dev'], local_only=True)
        self.config = policy.load(self.repo)

    def event(self, name, purpose='research'):
        return {'tool_name': name, 'session_id': 'host', 'tool_input': {
            'message': f'Purpose: {purpose}; Task key: K; read only; inspect x.py and report findings'}}

    def test_native_off_and_lite_purpose_apply_to_host_tools(self):
        for name in ('Agent', 'Task', 'collaboration.spawn_agent', 'functions__followup_task'):
            self.config['subagent_level'] = 'off'
            event = self.event(name)
            self.assertIn('off', flow_gate.delegation_denial(self.repo, event, {}, self.config, [], True))
            self.config['subagent_level'] = 'lite'
            self.assertIsNone(flow_gate.delegation_denial(self.repo, event, {}, self.config, [], True))
            event = self.event(name, 'implementation')
            self.assertIn('읽기 전용', flow_gate.delegation_denial(self.repo, event, {}, self.config, [], True))
            for level in ('standard', 'full'):
                self.config['subagent_level'] = level
                self.assertIsNone(flow_gate.delegation_denial(self.repo, event, {}, self.config, [], True))
        self.assertFalse(flow_gate.native_delegation(self.event('TaskCreate')))
        self.assertFalse(flow_gate.native_delegation(self.event('collaboration.send_message')))

    def test_orca_optional_policy_preserves_coor_and_mandatory_review(self):
        config = {**self.config, 'subagent_level': 'off'}
        start = ['orca orchestration worker-start --run r --spec "Task key: K; Purpose: implementation"']
        self.assertIsNone(flow_gate.delegation_denial(self.repo, {}, {}, config, start, True))
        self.assertIn('off', flow_gate.delegation_denial(self.repo, {}, {'dispatch': 'd'}, config, start, False))
        config['mode'] = 'dev'
        self.assertIn('off', flow_gate.delegation_denial(self.repo, {}, {}, config, start, True))
        review = ['orca orchestration worker-start --run r --spec "Purpose: review; Review SHA: abc; '
                  'Implementer session: a; Reviewer session: b"']
        self.assertIsNone(flow_gate.delegation_denial(self.repo, {}, {}, config, review, True))
        config['subagent_level'] = 'lite'
        self.assertIn('읽기 전용', flow_gate.delegation_denial(self.repo, {}, {'dispatch': 'd'}, config, start, False))

    def test_automatic_native_delegation_requires_supervised_orca(self):
        store = issue_mode.Store(self.repo)
        with store.edit() as state:
            state['owner'] = {'provider_session': 'host'}
        self.assertIn('child Run', flow_gate.delegation_denial(
            self.repo, self.event('Agent'), {}, self.config, [], True))
        with store.edit() as state:
            state['owner'] = {'provider_session': 'coor'}
            state['jobs']['1'] = {'worker_sessions': {'host': {'dispatch': 'd'}}}
        self.assertIn('추적', flow_gate.delegation_denial(
            self.repo, self.event('collaboration.spawn_agent'), {'dispatch': 'd'}, self.config, [], False))
        event = self.event('Agent')
        event['session_id'] = 'manual'
        self.assertIsNone(flow_gate.delegation_denial(self.repo, event, {}, self.config, [], True))

    def test_session_and_dispatch_briefs_include_both_policies(self):
        self.config['test_level'] = 'exhaustive'
        self.config['subagent_level'] = 'standard'
        write_json(self.repo / '.fullops-squad/fullops.json', self.config)
        event = {'cwd': str(self.repo), 'session_id': 'host'}
        with patch.object(sys, 'argv', ['flow_gate.py', 'start']), patch.object(
                sys, 'stdin', io.StringIO(json.dumps(event))), patch.object(flow_gate.deps, 'missing_tools', return_value=[]):
            brief = flow_gate.main()['hookSpecificOutput']['additionalContext']
        self.assertIn('테스트 레벨 exhaustive', brief)
        self.assertIn('하위 에이전트 레벨 standard', brief)
        self.config.update(mode='dev', primary_role='dev', primary_branch='main')
        write_json(self.repo / '.fullops-squad/fullops.json', self.config)
        event.update(session_id='worker', prompt='--task-id t --dispatch-id d')
        with patch.object(sys, 'argv', ['flow_gate.py', 'prompt']), patch.object(
                sys, 'stdin', io.StringIO(json.dumps(event))):
            brief = flow_gate.main()['hookSpecificOutput']['additionalContext']
        self.assertIn('하위 에이전트 레벨 standard', brief)


    def test_failed_dispatch_reservation_blocks_launch(self):
        event = {'cwd': str(self.repo), 'session_id': 'host', 'tool_name': 'Bash',
                 'tool_input': {'command': 'orca orchestration worker-start --run r --spec "Task key: K"'}}
        with patch.object(sys, 'argv', ['flow_gate.py', 'tool']), patch.object(
                sys, 'stdin', io.StringIO(json.dumps(event))), patch.object(flow_gate, 'tool_denial', return_value=None), patch.object(
                issue_mode, 'reserve_dispatch', side_effect=ValueError('owner changed')):
            output = flow_gate.main()['hookSpecificOutput']
        self.assertEqual(output['permissionDecision'], 'deny')
        self.assertIn('owner changed', output['permissionDecisionReason'])


if __name__ == '__main__':
    unittest.main()
