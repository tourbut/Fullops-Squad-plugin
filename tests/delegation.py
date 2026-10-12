"""하위 위임 OFF·목적 제한·오토모드 추적과 세션 지침 주입을 검증한다."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
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
        for level in policy.SUBAGENT_LEVELS:
            config['subagent_level'] = level
            self.assertIsNone(flow_gate.delegation_denial(self.repo, {}, {}, config, review, True), level)
        config['subagent_level'] = 'lite'
        self.assertIn('읽기 전용', flow_gate.delegation_denial(self.repo, {}, {'dispatch': 'd'}, config, start, False))

    def test_automatic_native_delegation_requires_supervised_orca(self):
        store = issue_mode.Store(self.repo)
        owner = {'session': 'coor', 'provider_session': 'host', 'enabled': True, 'expires': time.time() + 90,
                 'token': 'test', 'epoch': 1, 'end_marker': str(self.repo / '.git/lease-stop')}
        with store.edit() as state:
            state.update(owner=owner, epoch=1)
        self.assertIn('child Run', flow_gate.delegation_denial(
            self.repo, self.event('Agent'), {}, self.config, [], True))
        with store.edit() as state:
            state['owner']['provider_session'] = 'coor'
            state['jobs']['1'] = {'status': 'running', 'epoch': 1, 'task_key': 'K',
                                  'worker_sessions': {'host': {'dispatch': 'd', 'task': 't', 'epoch': 1, 'task_key': 'K'}}}
        self.assertIn('추적', flow_gate.delegation_denial(
            self.repo, self.event('collaboration.spawn_agent'), {'dispatch': 'd', 'task': 't'}, self.config, [], False))
        event = self.event('Agent')
        event['session_id'] = 'manual'
        self.assertIsNone(flow_gate.delegation_denial(self.repo, event, {}, self.config, [], True))

    def test_lite_requires_read_only_contract_and_rejects_write_requests(self):
        config = {**self.config, 'subagent_level': 'lite'}
        for name in ('Agent', 'Task', 'collaboration.spawn_agent', 'functions__followup_task'):
            for prompt in ('Purpose: research; inspect x.py',
                           'Purpose: review; edit x.py and implement the fix',
                           'Purpose: research; read only; edit x.py and implement the fix',
                           'Purpose: review; Read only: false; inspect x.py',
                           'Purpose: review; read only; 파일을 수정하고 보고해'):
                event = self.event(name)
                event['tool_input'] = {'prompt' if name in ('Agent', 'Task') else 'message': prompt}
                self.assertIn('읽기 전용', flow_gate.delegation_denial(self.repo, event, {}, config, [], True) or '', prompt)
            for prompt in ('Purpose: research; read only; inspect x.py and report findings',
                           'Purpose: review; Read only: true; inspect x.py; do not edit files',
                           'Purpose: research; 읽기 전용; x.py를 읽고 결과만 보고해'):
                event['tool_input'] = {'message': prompt}
                self.assertIsNone(flow_gate.delegation_denial(self.repo, event, {}, config, [], True), prompt)
        write = ['orca orchestration worker-start --run r --spec "Purpose: research; read only; edit x.py"']
        self.assertIn('읽기 전용', flow_gate.delegation_denial(self.repo, {}, {'dispatch': 'd'}, config, write, False) or '')

    def test_coor_off_blocks_optional_research_and_review(self):
        config = {**self.config, 'subagent_level': 'off'}
        for purpose in ('research', 'review'):
            start = [f'orca orchestration worker-start --run r --spec "Task key: K; Purpose: {purpose}; read only"']
            self.assertIn('off', flow_gate.delegation_denial(self.repo, {}, {}, config, start, True) or '')
        config['subagent_level'] = 'lite'
        start = ['orca orchestration worker-start --run r --spec "Task key: K; Purpose: research; read only; edit x.py"']
        self.assertIn('읽기 전용', flow_gate.delegation_denial(self.repo, {}, {}, config, start, True) or '')

    def test_inactive_automatic_records_do_not_block_native_delegation(self):
        config = {**self.config, 'subagent_level': 'standard'}
        store = issue_mode.Store(self.repo)
        owner = {'session': 'coor', 'provider_session': 'host', 'enabled': True, 'expires': time.time() + 90,
                 'token': 'test', 'epoch': 1, 'end_marker': str(self.repo / '.git/lease-stop')}
        for change in ({'enabled': False}, {'expires': 0}):
            with store.edit() as state:
                state.update(owner={**owner, **change}, epoch=1)
            self.assertIsNone(flow_gate.delegation_denial(self.repo, self.event('Agent'), {}, config, [], True), change)
            with patch.object(policy, 'load', return_value=config):
                self.assertIsNone(flow_gate.tool_denial(self.repo, self.event('Agent'), {}), change)
        with store.edit() as state:
            state.update(owner=owner, epoch=1)
        Path(owner['end_marker']).touch()
        self.assertIsNone(flow_gate.delegation_denial(self.repo, self.event('Agent'), {}, config, [], True))
        Path(owner['end_marker']).unlink()
        for status, epoch, binding_epoch, context in (
                ('completed', 1, 1, {'dispatch': 'd', 'task': 't'}),
                ('running', 0, 0, {'dispatch': 'd', 'task': 't'}),
                ('running', 1, 0, {'dispatch': 'd', 'task': 't'}),
                ('running', 1, 1, {})):
            with store.edit() as state:
                state['owner']['provider_session'] = 'coor'
                state['jobs']['1'] = {'status': status, 'epoch': epoch, 'task_key': 'K',
                                      'worker_sessions': {'host': {'dispatch': 'd', 'task': 't',
                                                                 'epoch': binding_epoch, 'task_key': 'K'}}}
            self.assertIsNone(flow_gate.delegation_denial(self.repo, self.event('Agent'), context, config, [], False))
            if status == 'completed':
                with patch.object(policy, 'load', return_value=config):
                    self.assertIsNone(flow_gate.tool_denial(self.repo, self.event('Agent'), {}))

    def test_fresh_setup_delegation_document_has_one_metadata_block(self):
        text = (self.repo / '.fullops-squad/rules/delegation.md').read_text(encoding='utf-8')
        metadata, body = text[4:].split('\n---\n', 1)
        self.assertIn('title:', metadata)
        self.assertTrue(body.lstrip().startswith('# 하위 에이전트 활용'), body[:200])

    def test_hook_blocks_optional_coor_and_lite_write_prompts(self):
        for level, event in (
                ('off', {'tool_name': 'Bash', 'tool_input': {'command':
                    'orca orchestration worker-start --run r --spec "Purpose: research; read only"'}}),
                ('lite', {'tool_name': 'Agent', 'tool_input': {'prompt':
                    'Purpose: review; read only; edit x.py and implement the fix'}})):
            write_json(self.repo / '.fullops-squad/fullops.json', {**self.config, 'subagent_level': level})
            event.update(cwd=str(self.repo), session_id='host')
            with patch.object(sys, 'argv', ['flow_gate.py', 'tool']), patch.object(
                    sys, 'stdin', io.StringIO(json.dumps(event))):
                output = flow_gate.main()['hookSpecificOutput']
            self.assertEqual(output['permissionDecision'], 'deny')
            self.assertIn(level, output['permissionDecisionReason'])

    def test_saved_task_and_variable_specs_reach_optional_policy(self):
        dispatch = 'orca orchestration worker-start --run r --spec $instructions'
        command = "$instructions = 'Task key: K; Purpose: research; read only'; " + dispatch
        spec = flow_gate.dispatch_spec(command, dispatch)
        self.assertIsNone(flow_gate.delegation_denial(self.repo, {}, {'dispatch': 'parent'}, self.config, [spec], False))
        dispatch = 'orca orchestration worker-start --run r --task task_saved'
        review = 'Task key: K; Purpose: review; Review SHA: abc; Implementer session: a; Reviewer session: b'
        with patch.object(flow_gate, 'orca', return_value={'tasks': [{'id': 'task_saved', 'spec': review}]}):
            spec = flow_gate.dispatch_spec(dispatch, dispatch)
        config = {**self.config, 'mode': 'dev', 'subagent_level': 'off'}
        self.assertIsNone(flow_gate.delegation_denial(self.repo, {}, {}, config, [spec], True))

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
