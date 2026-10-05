"""설치된 shadcn·ESLint로 임시 Tailwind 레포의 setup 연결과 종료코드 게이트를 확인한다."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools', type=Path, required=True, help='검사용 npm 개발 의존성이 설치된 폴더')
    parser.add_argument('--out', type=Path, help='실제 명령 결과를 보존할 JSON 파일')
    args = parser.parse_args()
    tools = args.tools.resolve(strict=True)
    cli = tools / 'node_modules/eslint/bin/eslint.js'
    assert cli.is_file(), 'ESLint 검사용 의존성이 필요합니다'
    versions = {name: json.loads((tools / 'node_modules' / name / 'package.json').read_text())['version']
                for name in ('@shadcn/lint', 'eslint', '@typescript-eslint/parser', 'tailwindcss')}
    evidence = {'versions': versions}
    # Parent node_modules supplies the tools without adding dependencies to FullOps.
    with tempfile.TemporaryDirectory(prefix='sample-', dir=tools) as tmp:
        repo = Path(tmp)
        def git(*args):
            return subprocess.check_output(['git', '-C', tmp, *args], text=True).strip()
        def commit():
            git('add', '-A')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'sample')
        git('init', '-q', '-b', 'main')
        (repo / 'package.json').write_text(json.dumps({'private': True, 'type': 'module', 'scripts': {
            'lint:design': f'node "{cli.as_posix()}" src/page.tsx'}}), encoding='utf-8')
        (repo / 'eslint.config.mjs').write_text('''import { plugin as shadcn } from "@shadcn/lint";
import parser from "@typescript-eslint/parser";
export default [{
  files: ["src/**/*.tsx"],
  languageOptions: { parser, parserOptions: { ecmaFeatures: { jsx: true } } },
  plugins: { shadcn },
  rules: { "shadcn/no-arbitrary-values": "error" },
}];
''', encoding='utf-8')
        (repo / 'src').mkdir()
        (repo / 'src/theme.css').write_text('@import "tailwindcss";\n@theme { --color-brand: #336699; }\n')
        page = repo / 'src/page.tsx'
        page.write_text('// UI.\nexport const Page = () => <div className="p-4" />;\n')
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp, '--roles', 'dev', '--local-only'],
                       check=True, capture_output=True)
        config = json.loads((repo / '.fullops-squad/lint/lint.json').read_text())
        assert config['commands'] == [{'name': 'lint:design', 'kind': 'lint', 'run': ['npm', 'run', 'lint:design']}]
        commit()
        base = git('rev-parse', 'HEAD')
        for key, value, exit_code in [('invalid', 'p-[13px]', 1), ('valid', 'p-6', 0)]:
            page.write_text(f'// UI.\nexport const Page = () => <div className="{value}" />;\n')
            commit()
            out = repo / '.git/design-lint.json'
            done = subprocess.run([sys.executable, str(SCRIPTS / 'lint.py'), '--repo', tmp,
                                   '--from', base, '--out', str(out)], capture_output=True, text=True)
            assert done.returncode == exit_code, done.stdout + done.stderr
            result = json.loads(out.read_text(encoding='utf-8'))
            record = result['commands'][0]
            assert record['name'] == 'lint:design' and record['exit_code'] == exit_code, record
            assert record['status'] == ('failed' if exit_code else 'passed'), record
            if exit_code:
                assert 'shadcn/no-arbitrary-values' in record['output_tail'], record
                assert result['summary']['errors'] == 1
            else:
                assert result['summary']['errors'] == 0
                stamp = json.loads((repo / '.git/fullops-gate/pass.json').read_text())
                assert stamp['head'] == git('rev-parse', 'HEAD')
            evidence[key] = result
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS: real @shadcn/lint, setup script registration, invalid/valid exit codes and HEAD gate')
    print(json.dumps(versions))


if __name__ == '__main__':
    main()
