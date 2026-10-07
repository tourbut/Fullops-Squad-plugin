"""#6의 실패·재시도·부분 탐색 경계를 임시 저장소에서 확인한다. 유료 API/실제 세션은 사용하지 않는다."""
from contextlib import redirect_stdout
import importlib.util
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
import board
import deliverables as docs
import deps
import done_gate
import flow_gate
import integration
import jev_context
import jev_find
import jev_observe
import jev_packet
import jev_route
import jev_test_unity as unity
import jev_test_web as web
import review
import setup
import storage
import work


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


web_test = load('web_test', 'tests/jev-test-web.py')
build = load('build', 'scripts/build.py')


class Stabilization(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fullops-stable-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-q', '-b', 'main')
        with redirect_stdout(io.StringIO()):
            setup.setup(self.repo, roles=['dev'], local_only=True)
        self.base = self.commit('setup')

    def git(self, *args, cwd=None):
        return subprocess.check_output(['git', '-C', str(cwd or self.repo), *args], text=True, stderr=subprocess.DEVNULL).strip()

    def commit(self, message):
        self.git('add', '-A')
        self.git('-c', 'user.name=test', '-c', 'user.email=test@example.test', 'commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def new(self):
        with redirect_stdout(io.StringIO()):
            work.new(self.repo, 'dev', 'K1', 'rename fetch_user API', self.base)
        return self.repo / '.fullops-squad/handovers/to_dev.md'

    def test_atomic_rollback_and_build_rename_failure(self):
        a, b = self.root / 'a', self.root / 'b'
        a.write_bytes(b'old-a')
        b.write_bytes(b'old-b')
        original = storage.atomic_write
        def fail(path, data):
            if path == b and data == b'new-b':
                raise OSError('injected disk failure')
            original(path, data)
        with patch.object(storage, 'atomic_write', side_effect=fail):
            with self.assertRaises(OSError):
                storage.write_many({a: b'new-a', b: b'new-b'})
        self.assertEqual((a.read_bytes(), b.read_bytes()), (b'old-a', b'old-b'))
        output = self.root / 'native'
        output.mkdir()
        (output / build.STAMP).write_text('generated')
        (output / 'keep').write_text('old package')
        rename = Path.rename
        def failed_rename(path, target):
            if path.name == 'fullops-squad' and path.parent.name.startswith('.fullops-build-'):
                raise OSError('injected rename')
            return rename(path, target)
        with patch.object(Path, 'rename', failed_rename):
            with self.assertRaises(OSError):
                build.build(output)
        self.assertEqual((output / 'keep').read_text(), 'old package')

    def test_setup_retry_preserves_plan_and_user_conflict(self):
        fresh = self.root / 'fresh'
        fresh.mkdir()
        self.git('init', '-q', '-b', 'main', cwd=fresh)
        original, written = setup.atomic_write, []
        def fail(path, value):
            if len(written) == 2:
                raise OSError('injected setup write')
            written.append(path)
            original(path, value)
        with patch.object(setup, 'atomic_write', side_effect=fail), redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                setup.setup(fresh, roles=['dev'], local_only=True)
        journal = fresh / '.git/fullops-setup.json'
        plan = journal.read_bytes()
        before = written[0].read_bytes()
        written[0].write_bytes(b'user change')
        with self.assertRaisesRegex(ValueError, '충돌'):
            setup.setup(fresh, roles=['dev'], local_only=True)
        self.assertEqual(journal.read_bytes(), plan)
        written[0].write_bytes(before)
        with patch.object(setup, 'date') as date, redirect_stdout(io.StringIO()):
            setup.setup(fresh, roles=['dev'], local_only=True)
            date.today.assert_not_called()
        self.assertFalse(journal.exists())
        self.assertEqual(written[0].read_bytes(), before)

    def test_finish_reopen_and_archive_retry(self):
        inbox = self.new()
        def fill(sha):
            text = inbox.read_text().partition('## 완료 보고\n')[0] + f'## 완료 보고\n\nSHA {sha}\n## 근거\n검증 통과\n'
            inbox.write_text(text)
        fill('a' * 40)
        original = work.atomic_write
        def fail(path, data):
            if path == inbox and data == b'':
                raise OSError('injected inbox clear')
            return original(path, data)
        with patch.object(work, 'atomic_write', side_effect=fail), redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                work.finish(self.repo, 'dev', 'K1')
        self.assertTrue(inbox.read_bytes())
        with redirect_stdout(io.StringIO()):
            work.finish(self.repo, 'dev', 'K1')
            work.finish(self.repo, 'dev', 'K1')
            work.new(self.repo, 'dev', 'K1', 'review corrections', self.base, True)
            fill('b' * 40)
            work.finish(self.repo, 'dev', 'K1')
        log = work.archives(self.repo, 'dev', 'K1')[0].read_text()
        self.assertEqual(log.count('<!-- fullops-attempt:'), 2)
        self.assertIn('SHA ' + 'a' * 40, log)
        self.assertIn('SHA ' + 'b' * 40, log)

    def test_shared_document_and_partial_status_refusal(self):
        base = self.repo / '.fullops-squad'
        with redirect_stdout(io.StringIO()):
            for doc_id in ('D06', 'D07', 'D09'):
                docs.stamp(self.repo, doc_id=doc_id, owner='dev', summary='shared model', task='K1')
        rows = board.deliverables(base)
        for row in (d for d in rows if d['id'] in ('D06', 'D07', 'D09')):
            self.assertTrue(row['has_meta'], row)
            path, meta = docs.meta_for(base, row['id'], row['source'])
            self.assertEqual(meta['id'], row['id'])
            self.assertFalse(docs.problems(path.read_text(), row['id'], row['index_status']))
        original = path.read_text()
        for invalid in ([], ['D09', 'D09'], [None], {'invalid': 'id'}):
            broken = original.replace(original.splitlines()[1], 'id: ' + json.dumps(invalid))
            self.assertTrue(docs.problems(broken, 'D09'))
        with redirect_stdout(io.StringIO()):
            for path in ('docs/design-docs/architecture.md', 'docs/design-docs/tech-stack.md'):
                docs.stamp(self.repo, doc_id='D03', path=path, owner='dev', summary='architecture', status='draft', task='K1')
        index = base / docs.INDEX
        before = index.read_bytes()
        with self.assertRaisesRegex(ValueError, '일부만'):
            docs.stamp(self.repo, doc_id='D03', path='docs/design-docs/architecture.md', owner='dev', status='approved')
        self.assertEqual(index.read_bytes(), before)
        self.assertIn('status: draft', (base / 'docs/design-docs/architecture.md').read_text())
        docs.stamp(self.repo, doc_id='D03', path='docs/design-docs/architecture.md', status='review', task='K2', all_sources=True)
        for source in ('architecture.md', 'tech-stack.md'):
            meta = docs.front_matter((base / 'docs/design-docs' / source).read_text())
            self.assertEqual(meta['status'], 'review')
            self.assertEqual(meta['owner'], 'dev')
            self.assertIn('K1', meta['tasks'])
            self.assertIn('K2', meta['tasks'])

    def test_settlement_requires_current_delivery(self):
        command = 'orca orchestration send --type worker_done --task-id t1 --dispatch-id d1 --outcome failed --json'
        state = {'dispatch': 'd1', 'task': 't1'}
        event = {'tool_use_id': 'tool1', 'tool_input': {'command': command}}
        candidate = flow_gate.settlement_command(command, state)
        state['sending'] = {**candidate, 'tool_use_id': 'tool1'}
        response = {'exit_code': 0, 'stdout': json.dumps({'ok': True, 'result': {'message': {'id': 'msg1'}}})}
        self.assertTrue(flow_gate.delivered({**event, 'tool_response': response}, state))
        for changed in ({'tool_use_id': 'old'}, {'tool_response': {**response, 'exit_code': 1}},
                        {'tool_input': {'command': command.replace('d1', 'd2')}}):
            self.assertFalse(flow_gate.delivered({**event, 'tool_response': response, **changed}, state))
        for bad in ('echo ' + command, command + '; echo fake', command.replace('worker_done', 'ask'), command + ' --help'):
            self.assertIsNone(flow_gate.settlement_command(bad, state))
        self.assertIsNotNone(flow_gate.settlement_command(command.replace('worker_done', 'escalation'), state))
        projection = {'dispatchId': 'd1', 'taskId': 't1', 'outcome': 'succeeded', 'stage': {'dispatch': 'completed'}}
        with patch.object(flow_gate, 'orca', return_value={'projection': projection}):
            self.assertTrue(flow_gate.settled_in_runtime(state))
        for field, value in [('dispatchId', 'old'), ('taskId', 'other'), ('outcome', 'in_progress')]:
            with patch.object(flow_gate, 'orca', return_value={'projection': {**projection, field: value}}):
                self.assertFalse(flow_gate.settled_in_runtime(state))
        with patch.object(flow_gate, 'orca', return_value=None):
            self.assertFalse(flow_gate.settled_in_runtime(state))
        def status(*args):
            return {'messages': []} if args[1] == 'check' else {'workers': [
                {'dispatchId': 'live', 'projection': {'outcome': 'in_progress'}}, {'dispatchId': 'done', 'projection': projection}]}
        with patch.object(flow_gate, 'orca', side_effect=status):
            self.assertEqual(flow_gate.run_state('run1'), (0, ['live']))
        report = "python3 - <<'PY'\nreport = '''\norca orchestration worker-start\n'''\nprint(report)\nPY\n"
        self.assertEqual(flow_gate.operation_commands(report, 'worker-start'), [])
        self.assertEqual(flow_gate.operation_commands('echo orca orchestration worker-start', 'worker-start'), [])
        self.assertEqual(len(flow_gate.operation_commands(report + 'orca orchestration worker-start --run r1', 'worker-start')), 1)
        self.assertEqual(len(flow_gate.operation_commands('O=/opt/Orca/resources/bin/orca-ide; $O orchestration worker-start --run r1', 'worker-start')), 1)

    def test_dispatch_rejects_detached_unknown_and_broken_route(self):
        head = self.git('rev-parse', 'HEAD')
        path = self.root / 'snapshot'
        self.git('worktree', 'add', '-q', '--detach', str(path), head)
        self.addCleanup(lambda: subprocess.run(['git', '-C', str(self.repo), 'worktree', 'remove', str(path)], capture_output=True))
        command = f'worker-start --worktree "{path}" --spec "Task key: K1"'
        self.assertIn('implementation', integration.baseline_denial(self.repo, command))
        self.assertIsNone(integration.baseline_denial(self.repo, command + f' Purpose: review Review SHA: {head} Implementer session: a Reviewer session: b'))
        directory = self.repo / '.fullops-squad/docs/evaluations/jev'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'K1-route.json').write_text('{}')
        self.assertIn('스키마', flow_gate.route_key_denial(self.repo, command))
        self.assertIsNotNone(flow_gate.route_key_denial(self.repo, '--spec "unrelated; 참고 K1"'))

    def test_web_invalid_risk_and_midrun_exception_evidence(self):
        scenario = {'url': 'https://example.test', 'goal': 'Add milk', 'values': {'milk': 'milk'},
                    'checks': [{'text': 'milk'}], 'max_steps': 2}
        for n, risk in enumerate((None, True, float('nan'), float('inf'), -1, 1.1)):
            browser = web_test.FakeBrowser()
            out = self.root / str(n)
            with self.assertRaises(ValueError):
                web.run(scenario, browser, web_test.jev([('fill_submit', 'e3', 'milk')], risk), out, log=lambda _: None)
            self.assertEqual(browser.acts, [])
            result = json.loads((out / 'result.json').read_text())
            self.assertFalse(result['passed'])
            self.assertEqual(result['cost_status'], 'complete')
            self.assertEqual(result['known_cost'], 0.0001)
            self.assertIn('오류:', (out / 'report.md').read_text())
        browser = web_test.FakeBrowser()
        first = web_test.jev([('fill_submit', 'e3', 'milk')])
        def call(payload):
            if browser.acts:
                raise RuntimeError('original failure')
            return first(payload)
        out = self.root / 'failure'
        with self.assertRaisesRegex(RuntimeError, 'original failure'):
            web.run(scenario, browser, call, out, log=lambda _: None)
        self.assertEqual(len((out / 'events.jsonl').read_text().splitlines()), 1)
        result = json.loads((out / 'result.json').read_text())
        self.assertEqual(result['known_cost'], 0.0001)
        self.assertIsNone(result['cost'])
        out = self.root / 'maxsteps'
        passed = web.run({**scenario, 'max_steps': 1}, web_test.FakeBrowser(), web_test.jev([('fill_submit', 'e3', 'milk')]), out, log=lambda _: None)
        self.assertTrue(passed['passed'])
        self.assertEqual(passed['result'], 'max_steps')

    def test_unity_failure_keeps_first_event_and_kills_player(self):
        class Player:
            killed = False
            def wait(self, timeout=None):
                pass
            def kill(self):
                self.killed = True
        player = Player()
        play = self.root / 'play'
        play.mkdir()
        state = {'step': 1, 'actions': [{'id': 'wait', 'description': 'Wait'}]}
        answer = {'model': 'typesafe/jev-test', 'answers': {'action': web_test.answer(['wait', *unity.FINISH], 'wait')},
                  'usage': {'cost': 0.1, 'input_tokens': 1, 'output_tokens': 1}}
        out = self.root / 'unity'
        with patch.object(unity, 'wait_file', side_effect=[state, {**state, 'step': 2}]), \
             patch.object(unity, 'ask', side_effect=[{'action': answer['answers']['action'], 'cost': 0.1, 'cached': False, 'latency_s': 0.01}, RuntimeError('API failed')]):
            with self.assertRaisesRegex(RuntimeError, 'API failed'):
                unity.run({'goal': 'Wait', 'max_steps': 3, 'checks': []}, play, lambda _: player, None, out, log=lambda _: None)
        self.assertTrue(player.killed)
        self.assertEqual(len((out / 'events.jsonl').read_text().splitlines()), 1)
        self.assertFalse(json.loads((out / 'result.json').read_text())['passed'])

    def test_late_body_partial_context_and_packet_links(self):
        inbox = self.new()
        inbox.write_text(inbox.read_text() + '\n' + 'padding\n' * 600 + '\n## 완료 기준\n`fetch_user` returns version 2; update D05.\n')
        api = self.repo / 'api.py'
        api.write_text('# overview\n' * 80 + 'def fetch_user():\n    return 1\n')
        (self.repo / 'caller.py').write_text('from api import fetch_user\nvalue = fetch_user()\n')
        (self.repo / 'test_api.py').write_text('from api import fetch_user\nassert fetch_user() == 1\n')
        (self.repo / 'contract.md').write_text('[API](api.py#fetch_user)\nD05\n')
        self.commit('api')
        candidate, error = jev_context.candidate(self.repo, self.git('rev-parse', 'HEAD'), 'api.py', 0, inbox.read_text())
        self.assertIsNone(error)
        self.assertGreater(candidate['source']['span']['start_line'], 37)
        self.assertTrue(candidate['partial'])
        self.assertIn('fetch_user', work.task_excerpt(inbox.read_text()))
        result = jev_packet.packet(self.repo, 'dev', 'K1', ['api.py'], updates=['D05'])
        self.assertIn('api.py', result['categories']['direct_edit'])
        self.assertIn('caller.py', result['categories']['impact_check'])
        self.assertIn('test_api.py', result['categories']['impact_check'])
        self.assertIn('contract.md', result['categories']['document_read'])
        self.assertIn('fullops-packet', jev_packet.handover(result, 'K1-packet.json'))
        self.assertTrue(result['input_partial'])
        self.assertTrue(all(i['required'] for i in result['items'] if i['path'] in result['required_paths']))

    def test_historical_map_deleted_rename_and_utf8_prefix(self):
        (self.repo / 'old.py').write_text('# old\nvalue = 1\n')
        (self.repo / 'gone.py').write_text('# gone\nvalue = 2\n')
        (self.repo / 'big.py').write_bytes(b'#' * (jev_find.MAX_BLOB - 1) + '한글'.encode())
        head = self.commit('old sources')
        self.git('mv', 'old.py', 'new.py')
        (self.repo / 'gone.py').unlink()
        after = self.commit('move and delete')
        paths = {p for p, _ in jev_find.code_map(self.repo, head)}
        self.assertTrue({'old.py', 'gone.py', 'big.py'} <= paths)
        output = jev_find.result_path(self.repo, 'K1', 'find')
        storage.write_json(output, {'head': head, 'scope': 'code', 'candidates': [{'path': 'old.py'}, {'path': 'gone.py'}], 'existence': {'status': 'found'}})
        scored = jev_find.score(self.repo, 'K1', head, after)
        self.assertEqual(scored['new_files'], [])
        self.assertEqual(scored['renamed_files'], [['old.py', 'new.py']])
        self.assertEqual(scored['deleted_files'], ['gone.py'])

    def test_snapshot_cleanup_live_then_historical(self):
        with redirect_stdout(io.StringIO()):
            path = review.snapshot(self.repo, 'R1', self.base, 'a', 'b', 'coordinator')
        self.addCleanup(lambda: subprocess.run(['git', '-C', str(self.repo), 'worktree', 'remove', str(path)], capture_output=True))
        result = {'base': self.base, 'head': self.base, 'review_schema_version': 2, 'independence': {
            'implementer_session': 'a', 'reviewer_session': 'b', 'snapshot_path': str(path), 'snapshot_head': self.base, 'read_only': True}}
        folder = self.repo / '.fullops-squad/docs/evaluations/qa-reports/R1-review'
        folder.mkdir(parents=True)
        for name in ('preview', 'rules', 'lint'):
            storage.write_json(folder / (name + '.json'), {})
        storage.write_json(folder / 'result.json', result)
        (folder / 'report.md').write_text('Review and acceptance complete')
        if sys.platform != 'win32':
            link = folder / 'external.md'
            link.symlink_to(self.repo / 'AGENTS.md')
            with self.assertRaisesRegex(ValueError, '심볼릭'):
                review.evidence_hashes(self.repo, 'R1')
            link.unlink()
        inactive = {'archived': True, 'status': {'worker': 'released', 'liveness': 'dead'}, 'projection': {'workspace': {'id': 'repo::' + str(path)}}}
        with patch.object(integration, 'orca', return_value={'archived': False}):
            with self.assertRaisesRegex(ValueError, 'release'):
                review.cleanup(self.repo, 'R1', 'd1', True)
        (path / 'untracked.txt').write_text('keep')
        with patch.object(integration, 'orca', return_value=inactive), patch.object(review, 'check', side_effect=lambda *a: review.check_independence(self.repo, result)):
            with self.assertRaisesRegex(ValueError, '변경'):
                review.cleanup(self.repo, 'R1', 'd1', True)
            (path / 'untracked.txt').unlink()
            exclude = self.repo / '.git/info/exclude'
            exclude.write_text(exclude.read_text() + '\n*.snapshot-artifact\n')
            ignored = path / 'keep.snapshot-artifact'
            ignored.write_text('unique ignored evidence')
            with self.assertRaisesRegex(ValueError, '고유 파일'):
                review.cleanup(self.repo, 'R1', 'd1', True)
            ignored.unlink()
            review.cleanup(self.repo, 'R1', 'd1', True)
        self.assertFalse(path.exists())
        review.cleanup(self.repo, 'R1', 'd1', True)
        self.assertEqual(review.historical(self.repo, 'R1')['state'], 'removed')
        with self.assertRaises(OSError):
            review.check_independence(self.repo, result)
        (folder / 'report.md').write_text('tampered')
        with self.assertRaises(ValueError):
            review.historical(self.repo, 'R1')

    def test_host_receipt_retry_and_removed_skill(self):
        skill = self.root / 'SKILL.md'
        skill.write_text('installed')
        receipt = self.root / 'deps.json'
        for data in ({'completed': [None]}, {'skill_files': None}, {'completed': {}}, []):
            storage.write_json(receipt, data)
            self.assertEqual(deps.read_receipt(receipt), {})
        commands = [['npm', 'install', '--global', 'tool@1'], ['npx', '--yes', 'skills@latest', 'add', 'repo/skills', '--skill', 'x', '--global']]
        completed = []
        def run(plan, dry):
            completed.extend(plan)
            if len(completed) == 2:
                raise OSError('partial skill installation')
        with patch.object(deps, 'receipt_path', return_value=receipt), patch.object(deps, 'tool_problems', return_value=[]), \
             patch.object(deps, 'plugin_problems', return_value=[]), patch.object(deps, 'skill_files', return_value=([str(skill)], [])), \
             patch.object(deps, 'run', side_effect=run):
            with self.assertRaises(OSError):
                deps.install_host('codex', commands)
            deps.install_host('codex', commands)
            self.assertEqual(completed.count(commands[0]), 1)
            self.assertEqual(completed.count(commands[1]), 2)
            self.assertEqual(deps.check_host('codex'), [])
            skill.unlink()
            self.assertTrue(deps.check_host('codex'))

    def test_folder_status_requires_markdown_and_out_of_scope_does_not(self):
        base = self.repo / '.fullops-squad'
        index = base / docs.INDEX
        original = index.read_text()
        folder = base / 'docs/planning/product-specs'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / '.gitkeep').touch()
        for status in ('draft', 'review', 'approved'):
            lines = [line.rsplit('|', 2)[0] + f'| {status} |' if line.startswith('| D02 |') else line for line in original.splitlines()]
            index.write_text('\n'.join(lines) + '\n')
            with redirect_stdout(io.StringIO()):
                self.assertTrue(docs.check(self.repo, 'D02', True))
        index.write_text(original.replace('| 미작성 |', '| 범위 밖 |'))
        with redirect_stdout(io.StringIO()):
            self.assertFalse(docs.check(self.repo, 'D08', True))
        index.write_text(original)
        docs.stamp(self.repo, doc_id='D02', path='docs/planning/product-specs/nested/spec.md', owner='dev', summary='Requirements', status='draft')
        with redirect_stdout(io.StringIO()):
            self.assertFalse(docs.check(self.repo, 'D02', True))

    def test_document_sensitive_fallback_and_partial_positive_answers(self):
        row = {'id': 'D05', 'status': 'draft', 'name': 'Interface', 'stage': 'design', 'summary': 'API contract'}
        for field in ('name', 'stage', 'summary'):
            with patch.object(jev_route, 'deliverables', return_value=[{**row, field: 'API_KEY=synthetic-secret'}]):
                options = jev_route.document_options(self.repo)
            self.assertNotIn('synthetic-secret', json.dumps(options))
            self.assertIn('D05', options)
        marker = self.repo / '.fullops-squad/fullops.json'
        config = json.loads(marker.read_text())
        config['roles']['architecture'] = 'fullops/architecture'
        storage.write_json(marker, config)
        # classify needs a designer plus another worker; this fixture supplies the normal guide view.
        def response(payload):
            answers = {}
            for qid in ('scope', 'role'):
                labels = list(payload['questions'][qid]['criteria'])
                answers[qid] = web_test.answer(labels, labels[0])
            answers['doc_D05'] = {'type': 'noul', 'noul': 0.95}
            answers['doc_D10'] = {'type': 'noul', 'noul': float('nan')}
            return {'model': 'typesafe/jev-test', 'usage': {'input_tokens': 1, 'output_tokens': 1, 'cost': 0.01}, 'answers': answers}, 0.01
        with patch.object(jev_route, 'guide', return_value=('Design for structural work; dev for implementation', 'architecture', {'architecture': 'Design', 'dev': 'Implementation'})), \
             patch.object(jev_route, 'document_options', return_value={'D05': 'Interface', 'D10': 'Modules'}):
            result = jev_route.classify(self.repo, 'K1', 'update API', response)
        self.assertEqual(result['deliverables'], ['D05'])
        self.assertEqual(result['unresolved_deliverables'], ['D10'])
        self.assertEqual(result['docs_status'], 'partial')

    def test_expected_lint_base_survives_empty_inbox(self):
        self.git('checkout', '-qb', 'fullops/dev')
        inbox = self.new()
        self.commit('instruction')
        def hook(mode):
            event = {'cwd': str(self.repo), 'session_id': 'base-test'}
            with patch.object(sys, 'argv', ['done_gate.py', mode]), patch.object(sys, 'stdin', io.StringIO(json.dumps(event))):
                return done_gate.main()
        hook('start')
        (self.repo / 'change.py').write_text('# Changed sample.\nvalue = 1\n')
        self.commit('code')
        command = [sys.executable, str(ROOT / 'plugins/fullops-squad/scripts/lint.py'), '--repo', str(self.repo), '--from']
        self.assertEqual(subprocess.run([*command, 'HEAD'], capture_output=True).returncode, 0)
        self.assertEqual(hook('stop')['decision'], 'block')
        inbox.write_text('')
        self.assertEqual(hook('stop')['decision'], 'block')
        self.commit('archive instruction')
        self.assertEqual(subprocess.run([*command, self.base], capture_output=True).returncode, 0)
        self.assertEqual(hook('stop'), {})

    def test_observation_partial_cost_wall_time_and_dedup_budget(self):
        inbox = self.new()
        paths = []
        for n in range(12):
            path = f'candidate-{n}.md'
            (self.repo / path).write_text(f'# Candidate {n}\nfetch_user API context\n')
            paths.append(path)
        def response(payload):
            time.sleep(0.02)
            if payload['state']['candidate']['path'] == paths[0]:
                raise RuntimeError('one call failed')
            return {'model': 'typesafe/jev-test', 'answers': {qid: {'type': 'noul', 'noul': 0.1} for qid in payload['questions']},
                    'usage': {'cost': 0.001, 'input_tokens': 1, 'output_tokens': 1}}, 0.001
        result = jev_context.context(self.repo, 'dev', 'K1', paths + paths, response)
        self.assertTrue(result['error'])
        self.assertIsNone(result['usage']['cost'])
        self.assertAlmostEqual(result['usage']['known_cost'], 0.011)
        self.assertGreaterEqual(result['latency_seconds'], 0.03)
        self.assertEqual(len(result['context']['recommended_ids']), 19)  # 12 candidates + six rules + inbox
        self.assertIn(inbox.relative_to(self.repo).as_posix(), result['context']['required_paths'])

    def test_route_find_packet_handover_dispatch_review_identity(self):
        with redirect_stdout(io.StringIO()):
            setup.setup(self.repo, roles=['architecture', 'dev'], local_only=True)
        for name, content in {'api.py': '# User API.\ndef fetch_user():\n    return 1\n',
            'caller.py': '# User API caller.\nfrom api import fetch_user\nvalue = fetch_user()\n',
            'test_api.py': '# User API test.\nfrom api import fetch_user\nassert fetch_user() == 1\n'}.items():
            (self.repo / name).write_text(content)
        docs.stamp(self.repo, doc_id='D05', owner='dev', summary='fetch_user response contract', task='K1')
        starting = self.commit('existing API contract')
        inbox = self.new()
        def call(payload):
            answers = {}
            for qid, question in payload['questions'].items():
                if question['type'] == 'noul':
                    answers[qid] = {'type': 'noul', 'noul': 0.95 if qid in ('doc_D05', 'relevant', 'evidence') else 0.01}
                else:
                    labels = list(question['criteria'])
                    pick = next((label for label in labels if label in ('dev', 'simple', 'found')), labels[0])
                    if qid == 'where':
                        pick = next((label for label in labels if 'api.py' in question['criteria'][label] or 'interface-design.md' in question['criteria'][label]), labels[0])
                    answers[qid] = web_test.answer(labels, pick)
            return {'model': 'typesafe/jev-test', 'answers': answers, 'usage': {'cost': 0.001, 'input_tokens': 1, 'output_tokens': 1}}, 0.01
        route = jev_route.route(self.repo, 'K1', 'rename fetch_user to lookup_user and update D05', call)
        self.assertEqual(route['role'], 'dev')
        storage.write_json(jev_find.result_path(self.repo, 'K1', 'route'), route)
        for scope, suffix in [('code', 'find'), ('documents', 'documents-find')]:
            storage.write_json(jev_find.result_path(self.repo, 'K1', suffix), jev_find.find(self.repo, 'dev', 'K1', call, scope=scope))
        candidates = ['api.py', 'caller.py', 'test_api.py', '.fullops-squad/docs/design-docs/interface-design.md']
        storage.write_json(jev_find.result_path(self.repo, 'K1', 'context'), jev_context.context(self.repo, 'dev', 'K1', candidates, call))
        packet = jev_packet.packet(self.repo, 'dev', 'K1', ['api.py'])
        self.assertEqual(packet['head'], starting)
        self.assertIn('.fullops-squad/docs/design-docs/interface-design.md', packet['categories']['document_update'])
        worker = self.root / 'worker'
        self.git('worktree', 'add', '-q', '-b', 'fullops/dev', str(worker), starting)
        self.addCleanup(lambda: subprocess.run(['git', '-C', str(self.repo), 'worktree', 'remove', str(worker)], capture_output=True))
        output = jev_find.result_path(self.repo, 'K1', 'packet')
        storage.write_json(output, packet)
        text = inbox.read_text().replace('## 완료 보고', jev_packet.handover(packet, output.relative_to(self.repo)) + '\n\n## 완료 보고', 1)
        worker_inbox = worker / inbox.relative_to(self.repo)
        worker_inbox.write_text(text)
        command = f'orca orchestration worker-start --run run1 --worktree "{worker}" --spec "Task key: K1; Purpose: implementation"'
        self.assertIn('탐색 패킷', flow_gate.tool_denial(self.repo, {'tool_input': {'command': command}}, {}))
        storage.write_json(jev_find.result_path(worker, 'K1', 'packet'), packet)
        self.assertIsNone(flow_gate.tool_denial(self.repo, {'tool_input': {'command': command}}, {}))
        for name in ('api.py', 'caller.py', 'test_api.py'):
            path = worker / name
            path.write_text(path.read_text().replace('fetch_user', 'lookup_user').replace('return 1', 'return 2').replace('== 1', '== 2'))
        test = subprocess.run([sys.executable, str(worker / 'test_api.py')], cwd=worker, capture_output=True)
        self.assertEqual(test.returncode, 0)
        worker_inbox.write_text(text.partition('## 완료 보고\n')[0] + '## 완료 보고\n\n최종 API·호출자·테스트 수정. Python test_api.py exit_code=0.\n')
        with self.assertRaisesRegex(ValueError, '패킷'):
            work.finish(worker, 'dev', 'K1')
        contract = worker / '.fullops-squad/docs/design-docs/interface-design.md'
        contract.write_text(contract.read_text() + '\nlookup_user API 이름 변경; 반환 계약은 동일하다.\n')
        outcomes = {'packet_input_sha256': packet['input_sha256'], 'attempt': packet['attempt'],
                    'uncertainty_review': 'fixture의 모든 후보·잔여를 직접 검토했다', 'items': [
                        {'path': i['path'], 'category': c, 'status': 'completed' if c in ('direct_edit', 'document_update') else 'no_change',
                         'reason': 'API·계약 변경과 테스트 확인' if c in ('direct_edit', 'document_update') else '원문 읽기 및 영향 확인, 추가 변경 없음'}
                        for i in packet['items'] if not i.get('optional') for c in i['categories']]}
        storage.write_json(jev_find.result_path(worker, 'K1', 'packet-outcomes'), outcomes)
        with redirect_stdout(io.StringIO()):
            work.finish(worker, 'dev', 'K1')
        self.git('add', '-A', cwd=worker)
        self.git('-c', 'user.name=test', '-c', 'user.email=test@example.test', 'commit', '-qm', 'implementation', cwd=worker)
        head = self.git('rev-parse', 'HEAD', cwd=worker)
        folder = self.repo / '.fullops-squad/docs/evaluations/qa-reports/R-flow-review'
        folder.mkdir(parents=True)
        statuses = [line.split('\t', 1) for line in self.git('-c', 'core.quotepath=false', 'diff', '--name-status', self.base, head).splitlines()]
        files = [{'path': path, 'status': status, 'review_status': 'reviewed', 'reason': 'fixture record check'} for status, path in statuses]
        storage.write_json(folder / 'preview.json', {'from': self.base, 'to': head, 'reviewable_files': files, 'excluded_files': []})
        storage.write_json(folder / 'rules.json', {})
        storage.write_json(folder / 'result.json', {'base': self.base, 'head': head, 'rule_sha256': review.rule_hash(self.repo / '.fullops-squad/review/rule.json'),
            'files': files, 'findings': [], 'reviewer': 'fixture reviewer', 'conclusion': 'machine record check only'})
        (folder / 'report.md').write_text('Fixture machine record check; not a human code acceptance')
        lint = subprocess.run([sys.executable, str(ROOT / 'plugins/fullops-squad/scripts/lint.py'), '--repo', str(worker), '--from', self.base,
            '--out', str(folder / 'lint.json')], capture_output=True, text=True)
        self.assertEqual(lint.returncode, 0, lint.stdout)
        with redirect_stdout(io.StringIO()):
            review.check(self.repo, 'R-flow', self.base, head, 'K1')
        self.assertTrue((folder / 'jev-find-score.json').is_file())
        self.assertTrue((folder / 'jev-documents-find-score.json').is_file())
        integration.record(self.repo, [{'id': 'm-final', 'type': 'worker_done', 'body': f'[완료] K1 | 최종 SHA {head}'}])
        self.assertEqual(integration.pending(self.repo)[0]['sha'], head)

    def test_development_plugin_repair_version_and_partial_failure(self):
        target = self.root / 'package'
        target.mkdir()
        (target / 'plugin.json').write_text('{"version":"1.0.0"}')
        receipt = self.root / 'deps-repair.json'
        plugin = {'package': target, 'source': str(self.root)}
        plan = [['codex', 'plugin', 'add', 'fullops-squad@fullops-squad']]
        installed, calls = {}, []
        def problems(host, expected=None, target=None):
            return ['missing or stale FullOps'] if target and installed != target else []
        def run(commands, dry):
            calls.extend(commands)
            installed.clear()
            installed.update({**deps.package_identity(plugin['package']), 'source': plugin['source']})
        with patch.object(deps, 'receipt_path', return_value=receipt), patch.object(deps, 'tool_problems', return_value=[]), \
             patch.object(deps, 'plugin_problems', side_effect=problems), patch.object(deps, 'skill_files', side_effect=lambda *args: ([], [])), \
             patch.object(deps, 'run', side_effect=run):
            deps.install_host('codex', plan, plugin)
            deps.install_host('codex', plan, plugin)
            self.assertEqual(len(calls), 1)
            installed.clear()  # 의존성/receipt는 유지한 채 FullOps만 제거
            self.assertTrue(deps.check_host('codex'))
            deps.install_host('codex', plan, plugin)
            self.assertEqual(len(calls), 2)
            (target / 'plugin.json').write_text('{"version":"1.0.1"}')
            with patch.object(deps, 'run', side_effect=OSError('native install failed')):
                with self.assertRaises(OSError):
                    deps.install_host('codex', plan, plugin)
            self.assertFalse(deps.read_receipt(receipt)['complete'])
            deps.install_host('codex', plan, plugin)
            self.assertEqual(installed['version'], '1.0.1')
            (target / 'hook.py').write_text('new same-version hook')
            deps.install_host('codex', plan, plugin)
            self.assertEqual(len(calls), 4)
            self.assertEqual(deps.check_host('codex'), [])
            deps.install_host('codex', [], None)
            self.assertIsNone(deps.read_receipt(receipt)['plugin'])  # standalone 복구는 과거 개발 target을 재검증하지 않는다.
        claude = list(deps.commands('claude-code'))
        for name in deps.dependency_plugins('claude-code'):
            self.assertIn(['claude', 'plugin', 'install', name], claude)

    def test_packet_producer_identity_uncertainty_markdown_and_optional(self):
        (self.repo / 'ref.md').write_text('# unrelated reference\n')
        (self.repo / 'omit.md').write_text('# garden\n')
        self.commit('references')
        inbox = self.new()
        identity = work.input_identity(self.repo, 'dev', 'K1', {})
        def save(suffix, **data):
            storage.write_json(jev_find.result_path(self.repo, 'K1', suffix), {**identity, **data})
        save('find', candidates=[{'path': 'ref.md'}], partial=True, remaining_candidates=['tail.py'], error='one batch failed')
        save('route', deliverables=['D05'], docs_status='partial', unresolved_deliverables=['D10'])
        save('context', context={'candidate_paths': {'c1': 'omit.md'}, 'signals': {'c1': {'decision': 'suggest_omit'}}, 'fallback': 'API failure'}, refused_paths=[{'path': 'missing.md'}])
        packet = jev_packet.packet(self.repo, 'dev', 'K1')
        self.assertTrue(packet['partial'])
        self.assertEqual(packet['producer_status']['route']['unresolved_deliverables'], ['D10'])
        self.assertEqual(packet['producer_status']['find']['remaining_candidates'], ['tail.py'])
        self.assertIn('context_fallback', packet['producer_status']['context'])
        self.assertIn('ref.md', packet['categories']['document_read'])
        self.assertNotIn('ref.md', packet['categories']['document_update'])
        self.assertEqual(packet['optional_context_paths'], ['omit.md'])
        self.assertNotIn('omit.md', packet['context_paths'])
        self.assertNotIn('`omit.md`', jev_packet.handover(packet, Path('packet.json')))
        inbox.write_text(inbox.read_text().replace('attempt: ' + identity['attempt'], 'attempt: new-attempt'))
        stale = jev_packet.packet(self.repo, 'dev', 'K1')
        self.assertFalse(stale['producer_status'])
        self.assertEqual({v['source'] for v in stale['unknown'] if 'source' in v}, {'find', 'route', 'context'})
        self.assertNotIn('ref.md', stale['categories']['document_read'])

    def test_packet_delivery_identity_paths_and_outcomes(self):
        inbox = self.new()
        packet = jev_packet.packet(self.repo, 'dev', 'K1')
        path = jev_find.result_path(self.repo, 'K1', 'packet')
        with self.assertRaises(ValueError):
            jev_packet.check(self.repo, 'dev', 'K1', required=True)
        for field in ('attempt', 'head', 'instruction_sha256'):
            storage.write_json(path, {**packet, field: 'stale'})
            with self.assertRaises(ValueError):
                jev_packet.check(self.repo, 'dev', 'K1')
        storage.write_json(path, {**packet, 'items': [*packet['items'], {'path': 'absent.md'}]})
        with self.assertRaises(ValueError):
            jev_packet.check(self.repo, 'dev', 'K1')
        storage.write_json(path, packet)
        jev_packet.check(self.repo, 'dev', 'K1')
        result = {'attempt': packet['attempt'], 'packet_input_sha256': packet['input_sha256'], 'items': []}
        out = jev_find.result_path(self.repo, 'K1', 'packet-outcomes')
        storage.write_json(out, result)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            jev_packet.check(self.repo, 'dev', 'K1', completion=True)
        result['items'] = [{'path': i['path'], 'category': c, 'status': 'no_change', 'reason': '원문 읽기 및 영향 확인: 변경 불필요'} for i in packet['items'] for c in i['categories']]
        storage.write_json(out, result)
        jev_packet.check(self.repo, 'dev', 'K1', completion=True)
        result['items'][0]['status'] = 'unknown'
        storage.write_json(out, result)
        with self.assertRaisesRegex(ValueError, 'pending'):
            jev_packet.check(self.repo, 'dev', 'K1', completion=True)

    def test_uneven_find_batches_do_not_claim_global_probability_rank(self):
        self.new()
        entries = [(f'file-{n}.py', '') for n in range(255)] + [('tail.py', '')]
        def call(payload):
            labels = list(payload['questions']['where']['criteria'])
            probabilities = {name: 1 / len(labels) for name in labels}
            return {'model': 'typesafe/jev-test', 'usage': {'input_tokens': 1, 'output_tokens': 1, 'cost': 0.001}, 'answers': {
                'where': {'type': 'choice', 'choice': labels[0], 'confidence': probabilities[labels[0]], 'probabilities': probabilities},
                'exists': web_test.answer(list(payload['questions']['exists']['criteria']), 'found')}}, 0.01
        with patch.object(jev_find, 'code_map', return_value=entries):
            result = jev_find.find(self.repo, 'dev', 'K1', call, limit=2)
        self.assertTrue(result['partial'])
        self.assertEqual(result['ranking_status'], 'batch_only')
        self.assertEqual([c['path'] for c in result['candidates']], ['file-0.py', 'tail.py'])
        self.assertEqual(result['candidates'][1]['probability'], 1)

    def test_route_bind_records_current_instruction_without_api(self):
        self.new()
        path = jev_find.result_path(self.repo, 'K1', 'route')
        storage.write_json(path, {'task_key': 'K1', 'head': self.git('rev-parse', 'HEAD'), 'role': 'dev', 'route': 'simple'})
        command = [sys.executable, str(ROOT / 'plugins/fullops-squad/scripts/jev_route.py'), '--repo', str(self.repo), '--key', 'K1', '--role', 'dev', '--bind-inbox']
        bound = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(bound.returncode, 0, bound.stderr)
        self.assertEqual(json.loads(path.read_text())['attempt'], work.input_identity(self.repo, 'dev', 'K1', {})['attempt'])
        self.assertTrue(json.loads(path.read_text())['requires_packet'])
        inbox, content = work.instruction(self.repo, 'dev', 'K1')
        inbox.write_text(content.replace('rename fetch_user API', 'different instruction'))
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        original = '# K1 — task\n- [ ] read source\n\n## 완료 보고\n미작성.\n'
        completed = original.replace('[ ]', '[x]').replace('미작성.', '보고와 검증 기록.')
        self.assertEqual(work.instruction_digest(original), work.instruction_digest(completed))
        self.assertNotEqual(work.instruction_digest(original), work.instruction_digest(original.replace('read source', 'edit source')))


if __name__ == '__main__':
    unittest.main()
