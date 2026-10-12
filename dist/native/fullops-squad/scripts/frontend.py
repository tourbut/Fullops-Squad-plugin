#!/usr/bin/env python3
"""프런트엔드 선택·준비 상태와 선택한 로컬 도구의 설치 계획을 확인한다. 모델 호출·hook/MCP 설정은 하지 않는다."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import deps
from work import active_repo, safe_file

CONFIG = '.fullops-squad/docs/agents/frontend.json'
DEFAULT = {'enabled': True, 'primary': 'frontend-design', 'review': [], 'tools': [],
           'host': None, 'model': None, 'effort': None, 'design': None, 'tokens': [], 'components': []}
PRIMARY = ('frontend-design', 'ui-ux-pro-max', 'impeccable')
REVIEW = ('impeccable', 'web-design-guidelines')


def local_file(repo, value):
    if not isinstance(value, str) or not value or Path(value).anchor or '..' in Path(value).parts or '\\' in value or ':' in value:
        raise ValueError('프로젝트 경로는 레포 안의 상대 경로로 지정하세요')
    path = safe_file(repo, value)
    if not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError('프로젝트 경로가 레포 밖으로 연결됩니다')
    return path


def selection(repo, **overrides):
    path = safe_file(repo, CONFIG)
    saved = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    if not isinstance(saved, dict) or set(saved) - set(DEFAULT):
        raise ValueError('frontend.json의 필드와 객체 형식을 확인하세요')
    config = {**DEFAULT, **saved}
    if overrides.get('host') is not None and overrides['host'] != config['host']:
        config.update(model=None, effort=None)  # 다른 제공사의 모델 tuple을 새 호스트에 넘기지 않는다.
    config.update({k: v for k, v in overrides.items() if v is not None})
    if type(config['enabled']) is not bool or config['primary'] not in PRIMARY or config['host'] not in (*deps.COMMON_HOSTS, None):
        raise ValueError('enabled·primary·host 선택을 확인하세요')
    for key, allowed in (('review', REVIEW), ('tools', deps.manifest()['frontend_tools'])):
        values = config[key]
        if not isinstance(values, list) or any(not isinstance(v, str) or v not in allowed for v in values) or len(set(values)) != len(values):
            raise ValueError(f'{key}에 알려진 도구를 중복 없이 지정하세요')
    if config['primary'] in config['review']:
        raise ValueError('주 스킬은 review에 중복 지정하지 마세요')
    import jev_route
    if config['model'] or config['effort']:
        jev_route.fixed_model('claude' if config['host'] == 'claude-code' else config['host'], config['model'], config['effort'])
    for key in ('tokens', 'components'):
        if not isinstance(config[key], list):
            raise ValueError(f'{key}는 경로 목록이어야 합니다')
        for value in config[key]:
            local_file(repo, value)
    if config['design'] is not None:
        local_file(repo, config['design'])
    elif (repo / 'DESIGN.md').is_file():
        config['design'] = 'DESIGN.md'
    if config['enabled'] and 'shadcn' in config['tools']:
        package = repo / 'package.json'
        data = json.loads(package.read_text()) if package.is_file() else {}
        if not isinstance(data, dict) or any(not isinstance(data.get(k, {}), dict) for k in ('dependencies', 'devDependencies')):
            raise ValueError('프로젝트 package.json 의존성 형식을 확인하세요')
        packages = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
        if 'react' not in packages:
            raise ValueError('shadcn은 React 호환 프로젝트에서만 선택하세요. 기존 스택을 유지합니다')
    return config


def tool_root(repo, name):
    return local_file(repo, '.fullops-squad/tools/frontend/' + name)


def install_plan(repo, config):
    if not config['enabled']:
        return []
    return [['npm', 'install', '--prefix', str(tool_root(repo, name)), '--no-save', '--package-lock=false',
             '--ignore-scripts', deps.manifest()['frontend_tools'][name]['package']] for name in config['tools']]


def tool_status(repo, name):
    item = deps.manifest()['frontend_tools'][name]
    package, version = item['package'].rsplit('@', 1)
    root = tool_root(repo, name)
    entry = root / 'node_modules' / package / 'package.json'
    binary = root / 'node_modules/.bin' / (item['command'] + ('.cmd' if os.name == 'nt' else ''))
    try:
        if json.loads(entry.read_text())['version'] != version:
            return 'version_mismatch'
        result = subprocess.run([str(binary), '--version'], capture_output=True, text=True, timeout=15)
        return 'cli_verified' if result.returncode == 0 and version in result.stdout.split() else 'execution_failed'
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return 'not_installed_or_unavailable'


def inspect(repo, config):
    result = {'selection': config, 'status': 'disabled' if not config['enabled'] else 'configuration_ready',
              'problems': [], 'skills': [], 'tools': {},
              'authentication': 'not_run', 'browser_qa': 'not_run', 'mcp_connection': 'not_run'}
    if not config['enabled']:
        return result
    problems = result['problems']
    if not config['host'] or not config['model'] or not config['effort']:
        problems.append('호스트·모델·effort를 선택하거나 기존 고정 tuple을 기록하세요 (자동 호스트 변경 없음)')
    if config['host']:
        cli = 'claude' if config['host'] == 'claude-code' else config['host']
        if not shutil.which(cli):
            problems.append('host CLI unavailable: ' + cli)
        wanted = [s for s in deps.manifest()['skills'] if any(n in [config['primary'], *config['review']] for n in s['names'])]
        result['skills'], absent = deps.skill_files(config['host'], wanted)
        problems.extend(absent)
        if config['primary'] == 'ui-ux-pro-max':
            problems.extend(deps.python_problem())
            for path in result['skills']:
                if Path(path).parent.name == 'ui-ux-pro-max' and not (Path(path).parent / 'scripts/search.py').is_file():
                    problems.append('ui-ux-pro-max search.py unavailable')
    for value in [config['design'], *config['tokens'], *config['components']]:
        if value is not None and not local_file(repo, value).exists():
            problems.append('design source missing: ' + value)
    if not config['design']:
        problems.append('기존 디자인 정본을 연결하거나 새 방향을 정한 뒤 정본 경로를 기록하세요')
    for name in config['tools']:
        result['tools'][name] = tool_status(repo, name)
        if result['tools'][name] != 'cli_verified':
            problems.append(name + ': ' + result['tools'][name])
    if problems:
        result['status'] = 'needs_attention'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--host', choices=deps.COMMON_HOSTS)
    parser.add_argument('--model')
    parser.add_argument('--effort')
    parser.add_argument('--primary', choices=PRIMARY)
    parser.add_argument('--review', nargs='*', choices=REVIEW)
    parser.add_argument('--tools', nargs='*', choices=tuple(deps.manifest()['frontend_tools']))
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--check', action='store_true')
    action.add_argument('--install', action='store_true', help='선택한 도구만 레포 내부에 설치. hook·MCP·브라우저 설치는 별도')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        repo = active_repo(args.repo)
        config = selection(repo, **{k: getattr(args, k) for k in ('host', 'model', 'effort', 'primary', 'review', 'tools')})
        if args.install and not args.dry_run:
            deps.run(install_plan(repo, config), False)
        if args.check or (args.install and not args.dry_run):
            result = inspect(repo, config)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if result['problems'] else 0
        print(json.dumps({'selection': config, 'install': install_plan(repo, config),
                          'scope': 'repo-local npm packages; no lifecycle scripts, hooks, trust, MCP config or browser download',
                          'runtime': 'not_run'}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f'프런트엔드 준비 실패: {error}\n')


if __name__ == '__main__':
    sys.exit(main())
