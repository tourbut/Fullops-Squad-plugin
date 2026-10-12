"""웹 실행기의 안전 경계·관측 범위·독립 판정을 유료 API 없이 검증한다."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/fullops-squad/scripts'))
import jev_test_web as web
import web_contract as contract
import web_playwright
import web_analysis
import web_poc

spec = importlib.util.spec_from_file_location('web_fixture', ROOT / 'tests/jev-test-web.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class Engine(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sequence = 0

    def execute(self, scenario=None, browser=None, call=None, **options):
        self.sequence += 1
        return web.run(scenario or self.scenario(), browser or fixture.FakeBrowser(), call,
                       Path(self.temp.name) / str(self.sequence), log=lambda _: None, **options)

    def scenario(self, **changes):
        return {'url': 'http://127.0.0.1/todo', 'goal': 'Add milk', 'covers': ['TODO-1'],
                'values': {'milk': 'milk'}, 'checks': [{'text': 'milk'}], 'max_steps': 3,
                'safety': {'fixture': 'isolated-todo', 'allowed_operations': ['fill_submit', 'check', 'click']}, **changes}

    def test_budget_exhaustion_is_not_complete_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            result = web.run(self.scenario(max_steps=1), fixture.FakeBrowser(),
                             fixture.jev([('fill_submit', 'e3', 'milk')]), Path(temp), log=lambda _: None)
        self.assertFalse(result['passed'], 'budget exhaustion cannot prove exploration completed')
        self.assertTrue(all(c['passed'] for c in result['checks']))

    def test_orca_snapshot_reports_all_candidates(self):
        browser = web.Browser('orca', 'path:test')
        refs = {f'e{i}': {'role': 'button', 'name': f'Button {i} '} for i in range(300)}
        with patch.object(browser, 'run', return_value={'ok': True, 'result': {'origin': 'https://example.test', 'refs': refs, 'snapshot': 'state'}}), \
             patch.object(browser, 'evaluate', return_value={'url': 'https://example.test', 'digest': 'state', 'unsupported': []}):
            snapshot = browser.snapshot()
        self.assertEqual(len(snapshot['elements']), 300, '80-element truncation hides valid targets')
        self.assertEqual(snapshot['elements'][0]['name'], 'Button 0')

    def test_one_enter_has_one_submit_path(self):
        script = """
let submitted = 0;
global.KeyboardEvent = class { constructor(type) { this.type = type; } };
global.document = {activeElement: {
  form: {requestSubmit() { submitted++; }},
  dispatchEvent(event) { if (event.type === 'keydown') submitted++; return true; }
}};
""" + web.ENTER + "; if (submitted !== 1) throw new Error('duplicate submission: ' + submitted);"
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_candidate_boundaries_and_missing_coverage(self):
        for total in (0, 254, 255, 300):
            raw = {'url': self.scenario()['url'], 'digest': 'same',
                   'elements': [{'ref': f'e{i}', 'role': 'button', 'name': f'Button {i}'} for i in range(total)]}
            page = contract.observation(raw, self.scenario(candidate_limit=254))
            seen = []
            web.ask(fixture.jev([('blocked', None, None)], seen=seen), self.scenario(), page, [], 1)
            self.assertTrue(all(len(q['criteria']) <= 255 for q in seen[0]['questions'].values() if q['type'] == 'choice'))
            self.assertEqual(page['coverage']['remaining'], max(0, total - 254))
            if total > 254:
                next_page = contract.observation(raw, self.scenario(candidate_limit=254), 254)
                self.assertEqual(next_page['elements'][0]['ref'], 'e254')
        bad = self.scenario(values={f'v{i}': str(i) for i in range(255)})
        self.assertTrue(web.problems(bad))
        for elements in ([{}], [{'ref': None}], [{'ref': 'e1'}, {'ref': 'e1'}]):
            with self.assertRaises(ValueError):
                contract.observation({'url': 'https://example.test', 'digest': 'x', 'elements': elements}, self.scenario())

    def test_noul_and_none_and_low_confidence_hold(self):
        for mode in ('noul', 'none', 'low'):
            base = fixture.jev([('fill_submit', 'e3', 'milk')])
            def call(payload):
                response, elapsed = base(payload)
                if mode == 'noul':
                    response['answers']['valid_fill_target']['noul'] = 0.0
                elif mode == 'none':
                    response['answers']['fill_target'] = fixture.answer(payload['questions']['fill_target']['criteria'], contract.NONE)
                else:
                    response['answers']['operation']['confidence'] = 0.1
                return response, elapsed
            browser = fixture.FakeBrowser()
            result = self.execute(browser=browser, call=call)
            self.assertEqual(result['result'], 'uncertain')
            self.assertEqual(browser.acts, [])

    def test_invalid_id_is_never_executed(self):
        base = fixture.jev([('fill_submit', 'e3', 'milk')])
        def call(payload):
            response, elapsed = base(payload)
            response['answers']['fill_target']['choice'] = 'e999999'
            return response, elapsed
        browser = fixture.FakeBrowser()
        with self.assertRaises(ValueError):
            self.execute(browser=browser, call=call)
        self.assertEqual(browser.acts, [])

    def test_stale_and_occluded_targets_never_act(self):
        for denial in ('stale_state', 'not_actionable', 'origin_not_allowed'):
            browser = fixture.FakeBrowser()
            with patch.object(browser, 'preflight', return_value=denial):
                result = self.execute(browser=browser, call=fixture.jev([('fill_submit', 'e3', 'milk')] * 3))
            self.assertFalse(result['passed'])
            self.assertEqual(browser.acts, [])

    def test_policy_separate_from_risk_and_origin_blocks_before_model(self):
        browser = fixture.FakeBrowser()
        result = self.execute(self.scenario(safety={}), browser, fixture.jev([('fill_submit', 'e3', 'milk')], risk=0))
        self.assertEqual(result['result'], 'blocked_policy')
        self.assertEqual(browser.acts, [])
        browser = fixture.FakeBrowser()
        original = browser.snapshot
        with patch.object(browser, 'snapshot', side_effect=lambda: {**original(), 'url': 'https://outside.test'}):
            result = self.execute(browser=browser, call=lambda _: self.fail('origin escaped before model'))
        self.assertEqual(result['result'], 'origin_not_allowed')
        target = {'ref': 'e1', 'role': 'button', 'name': 'Send', 'state': ['disabled']}
        page = {'url': self.scenario()['url'], 'elements': [target]}
        self.assertEqual(contract.action_denial(contract.policy(self.scenario()), page, 'click', 'e1'), 'disabled_or_sensitive_target')

    def test_setup_cannot_bypass_origin_or_remote_orca_policy(self):
        from unittest.mock import Mock
        for current, expected in [('https://outside.test', 'origin_not_allowed'),
                                  ('https://example.test', 'setup_request_filter_unavailable')]:
            browser = fixture.FakeBrowser()
            browser.request_filtering = False
            browser.setup = Mock()
            original = browser.snapshot
            with patch.object(browser, 'snapshot', side_effect=lambda: {**original(), 'url': current}):
                result = self.execute(self.scenario(url='https://example.test', setup_js='mutate()'), browser,
                                      call=lambda _: self.fail('unsafe setup reached a model'))
            self.assertEqual(result['result'], expected)
            browser.setup.assert_not_called()

    def test_time_cost_and_revisit_budgets(self):
        browser = fixture.FakeBrowser()
        result = self.execute(self.scenario(max_cost=0.00001), browser, fixture.jev([('fill_submit', 'e3', 'milk')]))
        self.assertEqual(result['result'], 'cost_budget')
        self.assertEqual(browser.acts, [])
        base = fixture.jev([('fill_submit', 'e3', 'milk')])
        clock = [0]
        def slow(payload):
            clock[0] = 1000
            return base(payload)
        # monotonic clock jumps past the configured whole-run budget after the API reply.
        with patch.object(web.time, 'monotonic', side_effect=lambda: clock[0]):
            result = self.execute(self.scenario(max_seconds=1), browser, slow)
        self.assertEqual(result['result'], 'time_budget')
        self.assertEqual(browser.acts, [])
        browser = fixture.FakeBrowser()
        original = browser.snapshot
        with patch.object(browser, 'snapshot', side_effect=lambda: {**original(), 'digest': 'fixed'}):
            result = self.execute(self.scenario(max_visits=1), browser, fixture.jev([('scroll_down', None, None)]))
        self.assertEqual(result['result'], 'revisit_budget')

    def test_late_assertion_cannot_pass_and_assert_only_has_no_setup(self):
        clock = [0]
        browser = fixture.FakeBrowser()
        browser.setup = lambda _: self.fail('assert-only executed setup')
        def check(condition):
            clock[0] = 2
            return {'condition': condition, 'value': True, 'passed': True}
        with patch.object(web.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(browser, 'check', side_effect=check):
            result = self.execute(self.scenario(max_seconds=1, setup_js='mutate()'), browser, assertions_only=True)
        self.assertEqual(result['result'], 'time_budget')
        self.assertFalse(result['passed'])
        for timeout in (True, 0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                web.request({}, None, timeout=timeout)

    def test_api_payload_and_evidence_redact_url_dom_and_personal_data(self):
        browser = fixture.FakeBrowser()
        original = browser.snapshot
        def snapshot():
            raw = original()
            raw['url'] += '?token=hidden-value#fragment-secret'
            raw['elements'][0]['name'] = 'API_KEY=hidden-value person@example.test'
            return raw
        seen = []
        with patch.object(browser, 'snapshot', side_effect=snapshot):
            self.execute(self.scenario(values={'milk': 'person@example.test'}), browser=browser,
                         call=fixture.jev([('blocked', None, None)], seen=seen))
        serialized = json.dumps(seen)
        self.assertNotIn('hidden-value', serialized)
        self.assertNotIn('person@example.test', serialized)
        self.assertNotIn('fragment-secret', serialized)
        self.assertIn('[REDACTED]', serialized)

    def test_model_free_replay_and_scenario_binding(self):
        scenario = self.scenario()
        plan = contract.replay_plan(scenario, [{'operation': 'fill_submit', 'target': {'role': 'textbox', 'name': 'What needs to be done?'}, 'value': 'milk'}])
        result = self.execute(scenario, call=lambda _: self.fail('replay used a model'), replay=plan)
        self.assertTrue(result['passed'])
        self.assertEqual(result['scope'], 'regression_replay')
        self.assertEqual(result['jev_calls'], 0)
        self.assertEqual(result['cost'], 0)
        with self.assertRaises(ValueError):
            self.execute(self.scenario(goal='different'), replay=plan)
        bad = contract.replay_plan(scenario, [{'operation': 'eval', 'target': {'role': 'button', 'name': 'x'}}])
        with self.assertRaises(ValueError):
            self.execute(scenario, replay=bad)

    def test_exploration_done_with_unobserved_candidates_is_not_pass(self):
        browser = fixture.FakeBrowser()
        original = browser.snapshot
        with patch.object(browser, 'snapshot', side_effect=lambda: {**original(), 'elements': original()['elements'] * 1,
                          'unsupported': ['frames']}):
            result = self.execute(self.scenario(exploration=True, max_steps=1), browser,
                                  fixture.jev([('done', None, None)]))
        self.assertFalse(result['passed'])
        self.assertFalse(result['coverage']['complete'])

    def test_optional_unavailable_does_not_switch_engine(self):
        browser = web_playwright.PlaywrightBrowser(Path(self.temp.name), contract.policy(self.scenario()))
        with self.assertRaisesRegex(RuntimeError, 'no engine fallback'):
            self.execute(browser=browser, assertions_only=True)

    def test_bridge_undefined_result_is_none(self):
        from unittest.mock import Mock
        browser = web_playwright.PlaywrightBrowser(Path(self.temp.name), contract.policy(self.scenario()))
        browser.process = Mock()
        browser.responses.put({'id': 1, 'ok': True})
        self.assertIsNone(browser.rpc('eval', expression='undefined'))

    def test_invalid_scenarios_are_rejected_before_browser_or_model(self):
        for change in ({'max_steps': True}, {'setup_js': [1]}, {'checks': [{'text': 1}]},
                       {'checks': [{'js': '', 'equals': True}]}, {'safety': {'allowed_operations': [[]]}},
                       {'safety': {'allowed_origins': ['https://example.test'], 'requests': []}},
                       {'url': None}):
            with self.subTest(change=change):
                scenario = self.scenario(**change)
                self.assertTrue(web.problems(scenario))
                with self.assertRaises(ValueError):
                    self.execute(scenario, call=lambda _: self.fail('invalid input called a model'))
        with self.assertRaises(ValueError):
            self.execute(assertions_only=True, replay=contract.replay_plan(self.scenario(), []))

    def test_shadow_is_advisory_and_promotion_binds_trace(self):
        scenario = self.scenario()
        result = self.execute(scenario, call=fixture.jev([('fill_submit', 'e3', 'milk'), ('done', None, None)]))
        record = Path(self.temp.name) / str(self.sequence)
        events = [json.loads(line) for line in (record / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
        plan = web_analysis.promote(scenario, result, events)
        self.assertEqual(plan['steps'][0]['value'], 'milk')
        replayed = self.execute(scenario, replay=plan, call=lambda _: self.fail('promoted regression called a model'))
        self.assertTrue(replayed['passed'])
        self.assertEqual(replayed['jev_calls'], 0)
        for status in ('passed', 'assertions_failed', 'max_steps', 'error'):
            summary = {**result, 'result': status, 'passed': status == 'passed'}
            original = dict(summary)
            advisory = web_analysis.shadow(summary)
            self.assertEqual(summary, original)
            self.assertTrue(advisory['advisory_only'])
            self.assertFalse(advisory['gates_changed'])
            self.assertIsNone(advisory['human_label'])
        with self.assertRaises(ValueError):
            web_analysis.promote(scenario, {**result, 'scope': 'assertions_only'}, events)
        with self.assertRaises(ValueError):
            web_analysis.promote(self.scenario(goal='changed'), result, events)
        defect = web_analysis.shadow({**result, 'passed': False, 'result': 'max_steps', 'assertions_passed': False})
        self.assertEqual(defect['suggested_category'], 'undetermined')

    def test_cuawright_is_disabled_and_prepare_does_not_execute_code(self):
        repo = Path(self.temp.name)
        with patch.object(web_poc, 'runtime') as runtime, patch.object(web_poc.deps, 'run') as install:
            result = web_poc.prepare(repo, 'W21', self.scenario(), 'codex', 'gpt-6', 'high', sys.executable, 20000)
            self.assertFalse(result['enabled'])
            self.assertEqual(list(repo.iterdir()), [])
            runtime.assert_not_called()
            install.assert_not_called()
        with patch.object(web_poc, 'runtime', return_value={'playwright': None, 'firefox_installed': False}), \
             patch.object(web_poc.deps, 'skill_files', return_value=({}, ['missing'])), patch.object(web_poc.deps, 'run') as install:
            result = web_poc.prepare(repo, 'W21', self.scenario(), 'codex', 'gpt-6', 'high', sys.executable, 20000, dry_run=False)
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertEqual(result['generation'], 'not_run')
            self.assertEqual(result['independent_assertions'], 'not_run')
            self.assertTrue((repo / result['workspace'] / 'poc.json').is_file())
            install.assert_not_called()
        with self.assertRaises(ValueError):
            web_poc.prepare(repo, 'W21', self.scenario(safety={}), 'codex', 'gpt-6', 'high', sys.executable, 20000)

    def test_portable_process_cleanup(self):
        from unittest.mock import Mock
        process = Mock(pid=12345)
        process.poll.return_value = None
        with patch.object(web_playwright.os, 'name', 'nt'), patch.object(web_playwright.subprocess, 'run') as command:
            web_playwright.stop_process(process)
        self.assertEqual(command.call_args.args[0], ['taskkill', '/PID', '12345', '/T', '/F'])
        with patch.object(web_playwright.os, 'name', 'posix'), patch.object(web_playwright.os, 'killpg', create=True) as kill:
            web_playwright.stop_process(process)
        kill.assert_called_once_with(12345, web_playwright.signal.SIGTERM)


if __name__ == '__main__':
    unittest.main()
