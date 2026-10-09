"""Git 캐시 증분 정합성, 작업 트리 격리, 장애 fallback과 외부 호출 차단을 확인한다."""
from concurrent.futures import ThreadPoolExecutor
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
sys.path.insert(0, str(ROOT / 'plugins/fullops-squad/scripts'))
import jev_context
import jev_find
import jev_observe as jev
import jev_packet
import jev_route
import search_index as index
import setup
import storage
import work


class SearchIndex(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fullops-search-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repo'
        self.repo.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'test')
        self.git('config', 'user.email', 'test@example.test')
        self.git('config', 'core.autocrlf', 'false')
        self.write('api.py', '# Account lookup.\ndef fetch_user(user_id):\n    """Return account details."""\n    return user_id\n')
        self.write('guide.md', '---\ntitle: 계약\nsummary: 사용자 API\nstatus: approved\nstatuses: {"D05": "review", "D06": "approved"}\n---\n# 응답\n[코드](api.py)\n')
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.DEVNULL, encoding='utf-8').strip()

    def write(self, name, value):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8', newline='\n')

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'fixture')
        return self.git('rev-parse', 'HEAD')

    def active(self):
        with redirect_stdout(io.StringIO()):
            setup.setup(self.repo, roles=['architecture', 'dev'], local_only=True)
            work.new(self.repo, 'dev', 'S-1', 'Change `api.py` and fetch_user; preserve account response.', 'HEAD')
        self.commit()

    def test_incremental_matches_rebuild_and_preserves_metadata(self):
        first = index.metadata(self.repo, self.base)
        api = next(item for item in first if item['path'] == 'api.py')
        self.assertEqual(api['definitions'][0]['signature'], 'fetch_user(user_id)')
        self.assertEqual(api['definitions'][0]['line_start'], 2)
        doc = next(item for item in first if item['path'] == 'guide.md')
        self.assertEqual(doc['status'], 'approved')
        self.assertEqual(doc['statuses'], {'D05': 'review', 'D06': 'approved'})
        self.assertEqual(doc['links'], ['api.py'])
        path = index.cache_path(self.repo, 'code')
        before = path.stat().st_mtime_ns
        with patch.object(index, 'prefix_blob', side_effect=AssertionError('unchanged blob parsed')):
            self.assertEqual(index.metadata(self.repo, self.base), first)
        self.assertEqual(path.stat().st_mtime_ns, before)
        self.write('copy.py', (self.repo / 'api.py').read_text())
        self.git('mv', 'guide.md', 'renamed.md')
        self.write('api.py', '# Changed account API.\ndef lookup_user(uid):\n    return uid\n')
        head = self.commit()
        with patch.object(index, 'prefix_blob', wraps=index.prefix_blob) as read:
            incremental = index.metadata(self.repo, head)
        self.assertEqual(read.call_count, 3)
        self.assertEqual(incremental, index.metadata(self.repo, head, use_cache=False))
        self.assertEqual({x['path'] for x in incremental}, {'api.py', 'copy.py', 'renamed.md'})
        self.assertEqual(index.metadata(self.repo, self.base), first)
        self.git('switch', '-qc', 'alternate', self.base)
        self.assertEqual(index.metadata(self.repo, 'HEAD'), first)

    def test_dirty_and_untracked_never_enter_head_map(self):
        baseline = index.metadata(self.repo, self.base)
        self.write('api.py', '# dirty unique content\n')
        self.write('untracked.py', '# never automatically transmit\n')
        self.assertEqual(index.metadata(self.repo, self.base), baseline)

    def test_corrupt_lock_and_replace_failures_use_direct_read(self):
        expected = index.metadata(self.repo, self.base, use_cache=False)
        index.metadata(self.repo, self.base)
        path = index.cache_path(self.repo, 'code')
        for invalid in ('{', '[]', '{"schema_version": 9}'):
            path.write_text(invalid)
            self.assertEqual(index.metadata(self.repo, self.base), expected)
        malformed = json.loads(path.read_text())
        malformed['files'][0]['headings'] = [42]
        malformed['files_sha256'] = jev.digest(json.dumps(malformed['files'], sort_keys=True, ensure_ascii=False).encode())
        path.write_text(json.dumps(malformed), encoding='utf-8')
        self.assertEqual(index.metadata(self.repo, self.base), expected)
        lock = path.parent / 'writer.lock'
        lock.touch()
        with patch.object(index, 'write_json', side_effect=AssertionError('write under another lock')):
            self.assertEqual(index.metadata(self.repo, self.base), expected)
        lock.unlink()
        path.unlink()
        with patch.object(index, 'write_json', side_effect=PermissionError('Windows sharing violation')) as write, patch.object(index.time, 'sleep'):
            self.assertEqual(index.metadata(self.repo, self.base), expected)
            self.assertEqual(write.call_count, 3)
        self.assertFalse(lock.exists())
        self.assertFalse(path.exists())

    def test_policy_and_parser_changes_invalidate(self):
        index.metadata(self.repo, self.base)
        with patch.object(index, 'PARSER_VERSION', 'changed'), patch.object(index, 'prefix_blob', wraps=index.prefix_blob) as read:
            index.metadata(self.repo, self.base)
            self.assertEqual(read.call_count, 2)
        self.write('.fullops-squad/lint/lint.json', json.dumps({'exclude': ['api.py']}))
        self.assertNotIn('api.py', dict(index.code_map(self.repo, self.commit())))

    def test_same_blob_paths_worktrees_and_concurrent_writers(self):
        self.write('copy.py', (self.repo / 'api.py').read_text())
        self.commit()
        expected = index.metadata(self.repo, 'HEAD', use_cache=False)
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: index.metadata(self.repo, 'HEAD'), range(3)))
        self.assertTrue(all(result == expected for result in results))
        other = self.repo.parent / 'linked'
        self.git('worktree', 'add', '-q', '--detach', str(other), self.base)
        self.assertNotEqual(index.cache_path(self.repo, 'code'), index.cache_path(other, 'code'))
        self.assertEqual({item['path'] for item in index.metadata(other, self.base)}, {'api.py', 'guide.md'})

    def test_secret_binary_symlink_unsupported_and_large(self):
        self.write('.env', 'API_KEY=example\n')
        self.write('secret-body.py', '# Account lookup\npassword = "sensitive-value"\n')
        self.write('unsupported.rs', '// Header only\nfn example() {}\n')
        self.write('invalid.py', '# Safe header\ndef broken(\n')
        self.write('invalid.md', '---\nstatuses: {"D05": NaN}\n---\n# Invalid approval metadata\n')
        (self.repo / 'image').write_bytes(b'\0binary')
        self.write('large.py', '# Large\n' + '#' * index.MAX_BLOB)
        (self.repo / 'link.py').symlink_to('api.py')
        head = self.commit()
        entries = index.metadata(self.repo, head)
        mapped = {x['path']: x for x in entries if x['searchable']}
        self.assertFalse({'.env', 'secret-body.py', 'image', 'link.py'} & set(mapped))
        self.assertEqual(mapped['unsupported.rs']['parser'], 'header')
        self.assertEqual(mapped['invalid.py']['parser'], 'header')
        self.assertTrue(mapped['invalid.md']['partial'])
        self.assertIsNone(mapped['invalid.md']['statuses'])
        self.assertTrue(mapped['large.py']['partial'])
        self.assertNotIn('sensitive-value', index.cache_path(self.repo, 'code').read_text())

    def test_head_move_during_parse_keeps_fixed_commit(self):
        self.write('later.py', '# Later commit\n')
        newer = self.commit()
        self.git('reset', '--soft', self.base)
        original = index.prefix_blob
        def move(*args):
            self.git('reset', '--soft', newer)
            return original(*args)
        with patch.object(index, 'prefix_blob', side_effect=move):
            entries = index.metadata(self.repo, 'HEAD')
        self.assertEqual({x['path'] for x in entries}, {'api.py', 'guide.md'})
        self.assertEqual(json.loads(index.cache_path(self.repo, 'code').read_text())['head'], self.base)

    def test_shared_state_bounded_payload_and_invalid_ids(self):
        captured = []
        def call(payload):
            captured.append(payload)
            return {'model': 'typesafe/jev-test', 'answers': {
                'where': {'type': 'choice', 'choice': 'invalid', 'confidence': 1, 'probabilities': {'invalid': 1}},
                'exists': {'type': 'noul', 'noul': 0.01}},
                'usage': {'input_tokens': 10, 'output_tokens': 10, 'cost': 0.001}}, 0.01
        with self.assertRaises(ValueError):
            jev_find.ask(call, 'account response', {'F000': 'api.py — Account API'}, True)
        payload = captured[0]
        self.assertEqual(payload['state']['entries'], {'F000': 'api.py — Account API'})
        self.assertEqual(payload['questions']['where']['criteria'], {'F000': None})
        self.assertEqual(payload['questions']['exists']['type'], 'noul')
        entries = [(str(n), 'description ' * 70) for n in range(600)]
        pools = list(jev_find.batches(entries, 'task'))
        self.assertEqual(sum(map(len, pools)), 600)
        self.assertTrue(all(len(pool) <= 255 for pool in pools))

    def test_explicit_symbol_seeds_and_zero_probability_folder_expansion(self):
        self.active()
        seeds, error = jev_find.explicit_seeds(self.repo, self.git('rev-parse', 'HEAD'), 'Change `fetch_user`', {'api.py', 'guide.md'})
        self.assertEqual(seeds, ['api.py'])
        self.assertIsNone(error)
        entries = [(f'group{n}/file{n}.py', '') for n in range(260)]
        def call(payload):
            labels = list(payload['questions']['where']['criteria'])
            answers = {'where': {'type': 'choice', 'choice': labels[0], 'confidence': 1,
                                'probabilities': {cid: float(cid == labels[0]) for cid in labels}}}
            if 'exists' in payload['questions']:
                answers['exists'] = {'type': 'noul', 'noul': 0.01}
            return {'model': 'typesafe/jev-test', 'answers': answers,
                    'usage': {'input_tokens': 1, 'output_tokens': 1, 'cost': 0}}, 0
        with patch.object(jev_find, 'code_map', return_value=entries):
            found = jev_find.find(self.repo, 'dev', 'S-1', call, limit=2, strategy='hierarchical')
        self.assertEqual(found['presented_files'], 260)
        self.assertEqual(found['existence']['status'], 'not_confirmed')
        self.assertEqual(len(found['unselected_files']), 258)

    def test_offline_missing_promisor_blob_never_fetches_and_retries_later(self):
        sha = self.git('rev-parse', self.base + ':api.py')
        object_path = self.repo / '.git/objects' / sha[:2] / sha[2:]
        saved = object_path.read_bytes()
        object_path.chmod(0o600)  # Windows의 Git loose object는 읽기 전용이다.
        object_path.unlink()
        self.git('config', 'remote.origin.promisor', 'true')
        self.git('config', 'remote.origin.url', 'http://127.0.0.1:9/never-fetch')
        trace = self.repo.parent / 'git-trace.log'
        with patch.dict(os.environ, {'FULLOPS_OFFLINE': '1', 'GIT_TRACE': str(trace)}):
            items = index.metadata(self.repo, self.base)
        self.assertTrue(next(x for x in items if x['path'] == 'api.py')['read_error'])
        self.assertNotIn('fetch ', trace.read_text())
        object_path.write_bytes(saved)
        items = index.metadata(self.repo, self.base)
        self.assertTrue(next(x for x in items if x['path'] == 'api.py')['searchable'])

    def test_offline_all_entrypoints_and_fresh_packet(self):
        self.active()
        explicit_document = '.fullops-squad/docs/design-docs/seed-only.md'
        self.write(explicit_document, '# Explicit task contract\n')
        self.commit()
        with patch.dict(os.environ, {'FULLOPS_OFFLINE': '1'}), patch.object(jev.subprocess, 'run', wraps=subprocess.run) as run:
            call = unittest.mock.Mock(side_effect=AssertionError('external callback'))
            found = jev_find.find(self.repo, 'dev', 'S-1', call)
            self.assertFalse(found['semantic_search'])
            self.assertEqual(found['ranking_status'], 'local_only')
            self.assertTrue(found['candidates'])
            self.assertIn('api.py', found['seed_paths'])
            jev_route.route(self.repo, 'S-1', 'change API', call)
            classified = jev_context.context(self.repo, 'dev', 'S-1', ['api.py'], call)
            self.assertFalse(classified['semantic_search'])
            call.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, 'offline'):
                jev.request({'model': 'm'}, 'key')
            self.assertFalse(any('curl' in str(c.args[0][0]) for c in run.call_args_list))
            self.assertEqual(jev.git_env()['GIT_ALLOW_PROTOCOL'], '')
        storage.write_json(jev_find.result_path(self.repo, 'S-1', 'documents-find'), {
            **work.input_identity(self.repo, 'dev', 'S-1', {}), 'candidates': [], 'seed_paths': [explicit_document]})
        packet = jev_packet.packet(self.repo, 'dev', 'S-1', seeds=['api.py'])
        self.assertIn(explicit_document, packet['categories']['document_read'])
        self.assertNotIn(explicit_document, packet['categories']['document_update'])
        output = jev_find.result_path(self.repo, 'S-1', 'packet')
        storage.write_json(output, packet)
        jev_packet.check(self.repo, 'dev', 'S-1')
        self.write('api.py', '# changed after packet\n')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            jev_packet.check(self.repo, 'dev', 'S-1')
        overlay = jev_packet.packet(self.repo, 'dev', 'S-1', seeds=['api.py'])
        self.assertEqual(next(x for x in overlay['items'] if x['path'] == 'api.py')['source_basis'], 'tracked_worktree_overlay')


if __name__ == '__main__':
    unittest.main()
