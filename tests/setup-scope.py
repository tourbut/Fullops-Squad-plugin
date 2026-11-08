"""setup 템플릿 폴더, deps.py --no-refresh 범위, 호스트가 실제로 읽는 스킬 경로를 확인한다."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import deps  # noqa: E402

REMOVED = ('docs/design-docs/diagrams', 'docs/exec-plans/active', 'docs/exec-plans/completed',
           'docs/exec-plans/discarded', 'docs/exec-plans/sprint-contracts', 'docs/planning/meeting-logs')
KEPT = ('docs/design-docs/adr', 'docs/design-docs/mockups', 'docs/evaluations/qa-reports', 'docs/exec-plans/phases',
        'docs/generated', 'docs/operations', 'docs/planning/product-specs', 'handovers/logs')


def template_folders():
    with tempfile.TemporaryDirectory(prefix='fullops-setup-scope-') as tmp:
        subprocess.check_output(['git', 'init', '-q', '-b', 'main', tmp])
        setup = [sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp, '--roles', 'dev', '--local-only']
        subprocess.run(setup, check=True, capture_output=True)
        base = Path(tmp) / '.fullops-squad'
        assert not [name for name in REMOVED if (base / name).exists()]
        assert all((base / name / '.gitkeep').is_file() for name in KEPT)
        # 기존 레포에 남은 폴더의 사용자 파일은 setup 재실행이 건드리지 않는다
        kept = base / REMOVED[1] / 'plan.md'
        kept.parent.mkdir(parents=True)
        kept.write_text('mine', encoding='utf-8')
        subprocess.run(setup, check=True, capture_output=True)
        assert kept.read_text(encoding='utf-8') == 'mine'


def no_refresh_scope():
    catalog = deps.manifest()
    npm = ['npm', 'install', '--global', 'tool']
    shared = deps.skill_command(catalog['skills'][0], list(deps.COMMON_HOSTS))
    host_only = deps.skill_command(catalog['codex']['skills'][0], ['grok'])
    plan, ran = [npm, shared, host_only], []
    with tempfile.TemporaryDirectory() as tmp, \
         patch.object(deps, 'receipt_path', return_value=Path(tmp) / 'deps.json'), \
         patch.object(deps, 'tool_problems', return_value=[]), patch.object(deps, 'plugin_problems', return_value=[]), \
         patch.object(deps, 'skill_files', return_value=([], [])), patch.object(deps, 'command_skill_problems', return_value=[]), \
         patch.object(deps, 'python_problem', return_value=[]), patch.object(deps, 'backup_skills'), \
         patch.object(deps.hook_runtime, 'install'), patch.object(deps, 'run', side_effect=lambda commands, dry: ran.extend(commands)):
        deps.install_host('grok', plan)
        assert ran == plan, ran
        ran.clear()
        # 앞선 대상이 갱신한 공용 의존성만 건너뛴다. --agent grok 전용 스킬은 아직 아무도 갱신하지 않았다
        deps.install_host('grok', plan, refresh_shared=False)
        assert ran == [host_only], ran


def skill_paths():
    item = {'source': 'o/s', 'names': ['x']}
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        lock = home / '.agents/.skill-lock.json'
        lock.parent.mkdir()
        lock.write_text('{"skills": {"x": {"source": "o/s"}}}', encoding='utf-8')
        canonical = home / '.agents/skills/x/SKILL.md'
        canonical.parent.mkdir(parents=True)
        canonical.write_text('skill', encoding='utf-8')
        with patch.object(deps.Path, 'home', return_value=home), patch.dict(os.environ, {'GROK_HOME': str(home / 'custom-grok')}):
            # agy는 전역에서 ~/.agents/skills를 읽지 않는다. https://antigravity.google/docs/skills
            assert deps.skill_files('agy', [item])[1] == ['skill: x']
            for root in ('.gemini/config/skills', '.gemini/antigravity-cli/skills', '.gemini/skills'):
                assert home / root in deps.skill_roots('agy'), root
            read = home / '.gemini/config/skills/x/SKILL.md'
            read.parent.mkdir(parents=True)
            read.write_text('skill', encoding='utf-8')
            assert deps.skill_files('agy', [item]) == ([str(read)], [])
            # grok은 ~/.agents/skills와 $GROK_HOME/skills를 읽는다. ~/.grok/docs/user-guide/08-skills.md
            assert deps.skill_files('grok', [item]) == ([str(canonical)], [])
            assert deps.skill_roots('grok') == [home / '.agents/skills', home / 'custom-grok/skills']


if __name__ == '__main__':
    template_folders()
    print('PASS: template folders')
    no_refresh_scope()
    print('PASS: --no-refresh scope')
    skill_paths()
    print('PASS: host skill paths')
