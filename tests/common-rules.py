"""공통 규칙의 배포·연결·보존을 검증한다. LLM의 규칙 준수를 판정하지 않는다."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/fullops-squad'
ASSETS = PLUGIN / 'assets/repository/.fullops-squad'
RULES = Path('.fullops-squad/rules/common')
RULE_NAMES = {'coding-style.md', 'testing.md', 'security.md'}
BUNDLE_NAMES = RULE_NAMES | {'README.md', 'ECC-LICENSE.txt'}


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


setup = load('fullops_setup_test', 'plugins/fullops-squad/scripts/setup.py')
work = load('fullops_work_test', 'plugins/fullops-squad/scripts/work.py')
build = load('fullops_build_test', 'scripts/build.py')


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and not p.is_symlink()
            and '.git' not in p.relative_to(root).parts and '__pycache__' not in p.parts}


class CommonRulesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fullops-rules-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.env = patch.dict(os.environ, {
            'HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.home / '.config'),
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': str(self.home / '.gitconfig'),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.repo = self.root / 'service with spaces'
        self.repo.mkdir()
        self.git('init', '-q', '-b', 'main')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True).strip()

    def activate(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return setup.setup(self.repo, local_only=True, **kwargs)

    def assert_bundle(self, root):
        directory = root / RULES
        self.assertEqual({p.name for p in directory.iterdir()}, BUNDLE_NAMES)
        for name in BUNDLE_NAMES:
            self.assertEqual((directory / name).read_bytes(),
                             (ASSETS / 'rules/common' / name).read_bytes())

    def test_rules_have_bounded_scope_provenance_and_local_links(self):
        directory = ASSETS / 'rules/common'
        self.assertEqual({p.name for p in directory.iterdir()}, BUNDLE_NAMES)
        readme = (directory / 'README.md').read_text()
        self.assertIn('fullops-common-0.3.1', readme)
        self.assertIn('934195f955cf0da847d59fcd6f68856bce112d8b', readme)
        license_text = (directory / 'ECC-LICENSE.txt').read_text()
        self.assertIn('Copyright (c) 2026 Affaan Mustafa', license_text)
        self.assertIn('The above copyright notice and this permission notice', license_text)
        for file in directory.glob('*.md'):
            for target in re.findall(r'\]\(([^)]+)\)', file.read_text()):
                if '://' not in target and not target.startswith('#'):
                    self.assertTrue((file.parent / target.split('#', 1)[0]).is_file(), target)
        for name in RULE_NAMES:
            content = (directory / name).read_text()
            self.assertLessEqual(len(content.splitlines()), 60)
            self.assertNotRegex(content, r'ecc:|tdd-guide|security-reviewer|TodoWrite|~/.claude')
        for name in ('FULLOPS.md', 'project.md', 'handovers/_TEMPLATE.md'):
            self.assertIn('rules/common/README.md', (ASSETS / name).read_text())
        for name in ('setup-fullops', 'fullops-work', 'fullops-review', 'fullops-orca'):
            self.assertIn('.fullops-squad/rules/common/README.md',
                          (PLUGIN / 'skills' / name / 'SKILL.md').read_text())

    def test_dry_run_is_local_and_activation_copies_rules(self):
        before = snapshot(self.root)
        self.assertTrue(self.activate(roles=['implementer'], dry_run=True))
        self.assertEqual(snapshot(self.root), before)
        self.activate(roles=['implementer'])
        self.assert_bundle(self.repo)
        self.assertEqual(snapshot(self.home), {})
        self.assertFalse((self.repo / '.claude/rules').exists())
        state = snapshot(self.repo)
        self.assertEqual(self.activate(), [])
        self.assertEqual(snapshot(self.repo), state)

    def test_setup_preserves_user_rules_and_project_documents(self):
        self.activate(roles=['implementer'])
        for name in ['rules/common/coding-style.md', 'FULLOPS.md', 'project.md',
                     'handovers/_TEMPLATE.md', 'handovers/to_implementer.md']:
            (self.repo / '.fullops-squad' / name).write_text('# 사용자 수정본\n보존해야 한다.\n')
        before = snapshot(self.repo)
        self.assertEqual(self.activate(), [])
        self.assertEqual(snapshot(self.repo), before)

    def test_existing_030_repo_receives_only_missing_rule_files(self):
        self.activate(roles=['implementer'])
        shutil.rmtree(self.repo / RULES)
        marker = self.repo / '.fullops-squad/fullops.json'
        config = json.loads(marker.read_text())
        config['plugin_version'] = '0.3.0'
        marker.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', newline='\n')
        for name in ['FULLOPS.md', 'project.md', 'handovers/_TEMPLATE.md']:
            (self.repo / '.fullops-squad' / name).write_text('# 기존 레포 정본\n자동 교체 금지\n')
        before = snapshot(self.repo)
        planned = self.activate(dry_run=True)
        self.assertEqual(snapshot(self.repo), before)
        self.assertEqual(set(planned), {(RULES / name).as_posix() for name in BUNDLE_NAMES})
        self.activate()
        self.assert_bundle(self.repo)
        for name, content in before.items():
            self.assertEqual((self.repo / name).read_bytes(), content, name)
        self.assertEqual(json.loads(marker.read_text())['plugin_version'], '0.3.0')

    def test_symlink_rule_destination_is_rejected_before_writes(self):
        self.activate(roles=['implementer'])
        shutil.rmtree(self.repo / RULES)
        external = self.root / 'external'
        external.mkdir()
        (external / 'keep.md').write_text('수정 금지\n')
        try:
            (self.repo / RULES).symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('심볼릭 링크 생성 권한이 없는 환경')
        before, external_before = snapshot(self.repo), snapshot(external)
        with self.assertRaises(ValueError):
            self.activate()
        self.assertEqual(snapshot(self.repo), before)
        self.assertEqual(snapshot(external), external_before)

    def test_native_package_contains_rules_notice_and_consistent_version(self):
        before = snapshot(PLUGIN)
        native = build.build(self.root / 'native')
        self.assert_bundle(native / 'assets/repository')
        version = json.loads((PLUGIN / 'plugin.json').read_text())['version']
        for name in ('plugin.json', '.claude-plugin/plugin.json', '.codex-plugin/plugin.json'):
            self.assertEqual(json.loads((native / name).read_text())['version'], version)
        packaged_repo = self.root / 'packaged service'
        packaged_repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(packaged_repo)], check=True)
        subprocess.run(['python3', str(native / 'scripts/setup.py'), '--repo', str(packaged_repo),
                        '--roles', 'implementer', '--local-only'], check=True, capture_output=True)
        self.assert_bundle(packaged_repo)
        self.assertEqual(snapshot(PLUGIN), before)

    def test_preparation_commit_exposes_same_rules_and_handover_to_worker(self):
        self.activate(roles=['implementer'])
        with contextlib.redirect_stdout(io.StringIO()):
            work.new(self.repo, 'implementer', 'RULES-1', '공통 기준으로 구현')
        inbox = Path('.fullops-squad/handovers/to_implementer.md')
        self.assertIn('## 적용 기준과 예외', (self.repo / inbox).read_text())
        self.git('add', '.')
        self.git('-c', 'user.name=FullOps Test', '-c', 'user.email=test@example.com',
                 'commit', '-q', '-m', 'test: prepare common rules and handover')
        worker = self.root / 'worker'
        self.git('worktree', 'add', '-q', '-b', 'fullops/implementer', str(worker))
        self.assert_bundle(worker)
        self.assertEqual((worker / inbox).read_bytes(), (self.repo / inbox).read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
