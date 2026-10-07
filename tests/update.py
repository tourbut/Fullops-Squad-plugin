"""업데이트 계획의 버전 선택·보존과 배포 패키지의 릴리스 접근을 검증한다."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


update = load('fullops_update', ROOT / 'plugins/fullops-squad/scripts/update.py')
build = load('fullops_update_build', ROOT / 'scripts/build.py')


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fullops-update-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'service with spaces'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.marker = self.repo / '.fullops-squad/fullops.json'
        self.marker.parent.mkdir()
        self.set_applied('0.9.8')
        self.plugin = self.root / 'plugin'
        self.plugin.mkdir()
        (self.plugin / 'plugin.json').write_text(json.dumps({'version': '0.9.10'}))
        notes = self.plugin / 'releases'
        notes.mkdir()
        for release in ('0.9.7', '0.9.8', '0.9.9', '0.9.10', '0.10.0'):
            (notes / f'{release}.md').write_text(f'# {release}\n\n## 기존 레포 적용\n반영 {release}\n', encoding='utf-8')

    def set_applied(self, release):
        self.marker.write_text(json.dumps({'schema_version': 1, 'plugin_version': release,
                                          'roles': {'dev': 'fullops/dev'}}))

    def test_oldest_baseline_numeric_order_and_target_bound(self):
        result = update.plan(self.repo, '0.9.9', self.plugin)
        self.assertEqual(result['baseline'], '0.9.8')
        self.assertEqual([n['version'] for n in result['releases']], ['0.9.9', '0.9.10'])
        self.assertIn('반영 0.9.10', result['releases'][-1]['content'])
        self.assertEqual(result['installed_version'], '0.9.10')
        self.set_applied('0.9.10')
        self.assertEqual(update.plan(self.repo, '0.9.8', self.plugin)['baseline'], '0.9.8')

    def test_plan_preserves_user_changes_and_existing_config(self):
        note = self.marker.parent / 'handovers/to_dev.md'
        note.parent.mkdir()
        note.write_bytes(b'ongoing user work\r\n')
        before = {str(p): p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}
        update.plan(self.repo, None, self.plugin)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.repo.rglob('*') if p.is_file()})

    def test_same_version_has_no_new_releases(self):
        self.set_applied('0.9.10')
        self.assertEqual(update.plan(self.repo, '0.9.10', self.plugin)['releases'], [])

    def test_invalid_unknown_downgrade_and_missing_notes_fail(self):
        for release in (None, 'unknown', '0.10.0'):
            self.set_applied(release)
            with self.assertRaises(ValueError):
                update.plan(self.repo, None, self.plugin)
        self.set_applied('0.9.8')
        with self.assertRaises(ValueError):
            update.plan(self.repo, '0.10.0', self.plugin)
        (self.plugin / 'releases/0.9.10.md').unlink()
        with self.assertRaises(ValueError):
            update.plan(self.repo, None, self.plugin)

    def test_new_repo_and_subdirectory_are_rejected(self):
        with self.assertRaises(ValueError):
            update.plan(self.marker.parent, None, self.plugin)
        self.marker.unlink()
        with self.assertRaises(ValueError):
            update.plan(self.repo, None, self.plugin)

    def test_packaged_cli_reads_bundled_notes_without_checkout(self):
        package = build.build(self.root / 'native')
        self.assertEqual((package / 'INSTALL.md').read_bytes(), (ROOT / 'README.md').read_bytes())
        for note in (ROOT / 'docs/releases').glob('*.md'):
            self.assertEqual((package / 'releases' / note.name).read_bytes(), note.read_bytes())
        result = subprocess.run(['python3', str(package / 'scripts/update.py'), '--repo', str(self.repo),
                                 '--from', '0.9.9', '--json'], capture_output=True, text=True,
                                encoding='utf-8', check=True)
        report = json.loads(result.stdout)
        self.assertEqual([n['version'] for n in report['releases']], ['0.9.9', '0.9.10', '0.9.11', '0.9.12', '0.9.13', '0.9.14', '1.0.0'])
        self.assertTrue(report['steps'])
        self.assertIn('담당과 반복 범위', (package / 'assets/repository/.fullops-squad/rules/common/testing.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
