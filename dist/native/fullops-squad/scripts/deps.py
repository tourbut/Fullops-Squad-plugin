#!/usr/bin/env python3
"""FullOps의 외부 의존성(npm 도구·MCP, 사용자 범위 스킬, 의존 플러그인)을 확인(--check)하거나 설치한다.

마켓플레이스로 플러그인만 설치하면 npm 도구와 사용자 범위 스킬은 설치되지 않는다. 설치된 플러그인 안에서
이 스크립트를 실행해 채운다. 출처는 패키지에 함께 들어 있는 dependencies.json이다.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from storage import write_json

HERE = Path(__file__).resolve().parents[1]
HOSTS = ("codex", "claude-code", "grok", "agy")


def manifest():
    """설치된 패키지에서는 패키지 루트, 개발 체크아웃에서는 레포 루트의 dependencies.json."""
    for path in (HERE / 'dependencies.json', HERE.parents[1] / 'dependencies.json'):
        if path.is_file():
            return json.loads(path.read_text(encoding='utf-8'))
    raise FileNotFoundError('dependencies.json을 찾을 수 없습니다')


def normalize_source(source):
    return source.removeprefix("https://github.com/").removesuffix(".git").rstrip("/")


def commands(host, registered=None, plugin=None):
    """설치 명령 목록. plugin이 있으면 FullOps 자신의 마켓플레이스 등록·설치도 넣는다({'source', 'package'}).

    registered는 {cli: {마켓플레이스 이름: 출처}}이며 이미 등록된 마켓플레이스는 건너뛰고 출처가 다르면 멈춘다.
    """
    deps = manifest()
    agents = {"all": list(HOSTS), "both": ["codex", "claude-code"]}.get(host, [host])
    yield ["npm", "install", "--global", *[server["package"] for server in deps["mcp"].values()],
           *[tool["package"] for tool in deps["tools"]]]
    for agent in agents:
        cli = "claude" if agent == "claude-code" else agent
        if agent in ("grok", "agy"):
            for skill in deps["skills"] + deps["codex"]["skills"] + deps["portable_skills"]:
                yield ["npx", "--yes", "skills@latest", "add", skill["source"],
                       "--skill", *skill["names"], "--global", "--agent",
                       "antigravity-cli" if agent == "agy" else agent, "--yes"]
            if plugin:
                yield [cli, "plugin", "install", str(plugin["package"])] + (["--trust"] if agent == "grok" else [])
            continue
        markets = dict(deps["marketplaces"]) if cli == "claude" else {"ponytail": deps["marketplaces"]["ponytail"]}
        if plugin:
            markets["fullops-squad"] = str(plugin["source"])
        for name, source in markets.items():
            current = (registered or {}).get(cli, {}).get(name)
            if current is not None:
                if normalize_source(current) != normalize_source(source):
                    raise ValueError(f"{cli}: {name} 마켓플레이스 출처 충돌: {current} != {source}")
            else:
                yield [cli, "plugin", "marketplace", "add", source]
        for name in dependency_plugins(agent):
            yield [cli, "plugin", "install" if cli == "claude" else "add", name]
        for skill in deps["skills"] + (deps["codex"]["skills"] if cli == "codex" else []):
            yield ["npx", "--yes", "skills@latest", "add", skill["source"],
                   "--skill", *skill["names"], "--global", "--agent", agent, "--yes"]
        if plugin:
            yield [cli, "plugin", "install" if cli == "claude" else "add", "fullops-squad@fullops-squad"]


def registered_marketplaces(cli):
    result = json.loads(subprocess.check_output([shutil.which(cli) or cli, "plugin", "marketplace", "list", "--json"], text=True))
    if cli == "codex":
        return {m["name"]: m.get("marketplaceSource", {}).get("source", m["root"])
                for m in result["marketplaces"]}
    return {m["name"]: m.get("repo") or m.get("url") or m.get("path") or m["installLocation"]
            for m in result}


def missing_tools():
    """PATH에 없는 필수 CLI(OCR·Context7 MCP). 스킬은 호스트마다 경로가 달라 설치 명령으로 채운다."""
    deps = manifest()
    names = [tool["command"] for tool in deps["tools"]] + [server["command"] for server in deps["mcp"].values()]
    return [name for name in names if not shutil.which(name)]


def receipt_path(host):
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) if host == 'codex' else \
        Path(os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home() / '.claude'))) if host == 'claude-code' else Path.home() / ('.' + host)
    return home / 'fullops-deps.json'


def read_receipt(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) and all(isinstance(data.get(key, []), list) and
            all(isinstance(item, str) for item in data.get(key, [])) for key in ('completed', 'skill_files')) else {}
    except (OSError, ValueError):
        return {}


def skill_files(host, wanted=None):
    """호스트 설치 목록의 실제 SKILL.md를 확인한다. wildcard는 skills 설치기의 source 기록을 사용한다."""
    data = manifest()
    wanted = wanted if wanted is not None else data['skills'] + (data['codex']['skills'] if host in ('codex', 'grok', 'agy') else []) + (data['portable_skills'] if host in ('grok', 'agy') else [])
    lock = Path.home() / '.agents/.skill-lock.json'
    try:
        installed = json.loads(lock.read_text()).get('skills', {}) if lock.is_file() else {}
        if not isinstance(installed, dict) or any(not isinstance(entry, dict) or not isinstance(entry.get('source', ''), str) for entry in installed.values()):
            installed = {}
    except (OSError, ValueError, AttributeError):
        installed = {}
    roots = [receipt_path(host).parent / 'skills']
    if host != 'claude-code':
        roots.insert(0, Path.home() / '.agents/skills')
    paths, absent = [], []
    for item in wanted:
        names = item['names']
        if '*' in names:
            names = [name for name, entry in installed.items() if normalize_source(entry.get('source', '')) == normalize_source(item['source'])]
            if not names:
                absent.append('skills source: ' + item['source'])
        for name in names:
            path = next((root / name / 'SKILL.md' for root in roots if (root / name / 'SKILL.md').is_file()), None)
            if path:
                paths.append(str(path))
            else:
                absent.append('skill: ' + name)
    return paths, absent


def tool_problems():
    absent = missing_tools()
    if absent:
        return absent
    try:
        root = Path(subprocess.check_output([shutil.which('npm') or 'npm', 'root', '--global'], text=True).strip())
        for item in [*manifest()['tools'], *manifest()['mcp'].values()]:
            package, version = item['package'].rsplit('@', 1)
            installed = json.loads((root / package / 'package.json').read_text())['version']
            if version != 'latest' and installed != version:
                absent.append(f"{item['command']}: version {installed} != {version}")
        subprocess.run([shutil.which('ocr') or 'ocr', '--version'], check=True, capture_output=True, timeout=15)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        absent.append('tool package/version/execution verification unavailable')
    return absent


def dependency_plugins(host):
    return manifest()['codex']['plugins'] if host == 'codex' else ['ponytail@ponytail', 'mattpocock-skills@claude-plugins-official'] if host == 'claude-code' else []


def package_identity(root):
    root = Path(root)
    files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts}
    return {'version': json.loads((root / 'plugin.json').read_text())['version'],
            'sha256': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}


def plugin_problems(host, expected=None, target=None):
    expected = dependency_plugins(host) if expected is None else expected
    if not expected:
        return []
    cli = 'claude' if host == 'claude-code' else host
    try:
        data = json.loads(subprocess.check_output([shutil.which(cli) or cli, 'plugin', 'list', '--json'], text=True))
        rows = data.get('installed', []) if host == 'codex' else data
        installed = {row.get('id') or row.get('pluginId') or f"{row.get('name')}@{row.get('marketplaceName') or row.get('marketplace')}": row
                     for row in rows if row.get('installed', True) and row.get('enabled', True)}
        absent = ['plugin: ' + name for name in expected if name not in installed]
        if target and not absent:
            row = installed['fullops-squad@fullops-squad']
            folder = row.get('readFromFolder') if host == 'claude-code' else None
            version = row.get('folderVersion') if folder else row.get('version')
            if version != target['version']:
                return ['FullOps version differs from development target']
            root = receipt_path(host).parent / 'plugins/cache/fullops-squad/fullops-squad' / version if host == 'codex' else Path(folder or row['installPath'])
            if package_identity(root) != {k: target[k] for k in ('version', 'sha256')}:
                absent.append('FullOps package version/content differs from development target')
            source = registered_marketplaces(cli).get('fullops-squad', '')
            if normalize_source(source) != normalize_source(target['source']):
                absent.append('FullOps marketplace source differs from development target')
        return absent
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.CalledProcessError):
        return ['host plugin verification unavailable']


def python_problem():
    try:
        subprocess.run([shutil.which('python3') or 'python3', '-c', 'import sys; assert sys.version_info >= (3, 10)'],
                       check=True, capture_output=True, timeout=10)
        return []
    except (OSError, subprocess.SubprocessError):
        return ['hooks require python3 3.10+ on PATH']


def fingerprint():
    return hashlib.sha256(json.dumps(manifest(), sort_keys=True).encode()).hexdigest()


def check_host(host):
    paths, absent = skill_files(host)
    absent += python_problem() + tool_problems() + plugin_problems(host)
    path = receipt_path(host)
    receipt = read_receipt(path)
    if receipt.get('plugin'):
        absent += plugin_problems(host, ['fullops-squad@fullops-squad'], receipt['plugin'])
    if receipt.get('manifest_sha256') != fingerprint() or receipt.get('host') != host or receipt.get('home') != str(path.parent.resolve()) or receipt.get('complete') is not True:
        absent.append('host dependency installation incomplete; rerun --host ' + host)
    absent += ['removed skill: ' + p for p in receipt.get('skill_files', []) if not Path(p).is_file()]
    return absent


def install_host(host, plan, plugin=None):
    absent = python_problem()
    if absent:
        raise ValueError('; '.join(absent))
    path = receipt_path(host)
    old = read_receipt(path)
    identity = {'manifest_sha256': fingerprint(), 'host': host, 'home': str(path.parent.resolve()), 'plugin': None}
    if plugin and host in ('codex', 'claude-code'):
        identity['plugin'] = {**package_identity(plugin['package']), 'source': str(plugin['source'])}
    receipt = old if all(old.get(k) == identity[k] for k in ('manifest_sha256', 'host', 'home')) else {'completed': []}
    receipt.update(identity)
    receipt['complete'] = False
    write_json(path, receipt)
    for command in plan:
        token = hashlib.sha256(json.dumps(command).encode()).hexdigest()
        valid = not tool_problems() if command[:3] == ['npm', 'install', '--global'] else \
            not skill_files(host, [{'source': command[4], 'names': command[command.index('--skill') + 1:command.index('--global')]}])[1] \
            if command[0] == 'npx' else not plugin_problems(host, [command[3]], identity.get('plugin') if command[3] == 'fullops-squad@fullops-squad' else None) \
            if command[1:3] in (['plugin', 'add'], ['plugin', 'install']) and host in ('codex', 'claude-code') else False
        if token not in receipt['completed'] or not valid:
            run([command], False)
            if command[:4] == ['claude', 'plugin', 'install', 'fullops-squad@fullops-squad'] and plugin_problems(host, [command[3]], identity.get('plugin')):
                run([['claude', 'plugin', 'update', command[3], '--scope', 'user']], False)
        if token not in receipt['completed']:
            receipt['completed'].append(token)
        write_json(path, receipt)
    paths, absent = skill_files(host)
    absent += tool_problems() + plugin_problems(host)
    if identity.get('plugin'):
        absent += plugin_problems(host, ['fullops-squad@fullops-squad'], identity['plugin'])
    if absent:
        raise ValueError('; '.join(absent))
    receipt.update(complete=True, skill_files=paths)
    write_json(path, receipt)


def run(plan, dry_run):
    plan = list(plan)
    if not dry_run:
        absent = sorted({cmd[0] for cmd in plan if not shutil.which(cmd[0])})
        if absent:
            raise SystemExit("먼저 설치할 실행 파일: " + ", ".join(absent))
    for cmd in plan:
        print(shlex.join(cmd), flush=True)
        if not dry_run:
            subprocess.run([shutil.which(cmd[0]) or cmd[0], *cmd[1:]], check=True)  # Windows의 .cmd


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", choices=["all", "both", *HOSTS], help="의존성을 설치할 CLI")
    parser.add_argument("--dry-run", action="store_true", help="실행할 명령만 출력한다")
    parser.add_argument("--check", action="store_true", help="--host와 함께 전체 구성·설치 완료를 검사. 단독 사용은 CLI 존재만 확인")
    args = parser.parse_args()
    if args.check:
        hosts = {'all': HOSTS, 'both': ('codex', 'claude-code')}.get(args.host, [args.host])
        absent = [f'{host}: {problem}' for host in hosts for problem in check_host(host)] if args.host else missing_tools()
        print(('호스트 의존성 검증 완료' if args.host else '필수 CLI 존재 확인 (skill/plugin/version 검사는 --host 필요)') if not absent else '의존성 미완료: ' + ', '.join(absent))
        raise SystemExit(1 if absent else 0)
    if not args.host:
        parser.error("--host가 필요합니다")
    cli = {"claude-code": "claude"}.get(args.host, args.host)
    try:
        registered = {} if args.dry_run or args.host in ("all", "both", "grok", "agy") else {cli: registered_marketplaces(cli)}
        if args.dry_run:
            run(commands(args.host, registered), True)
        else:
            for host in {'all': HOSTS, 'both': ('codex', 'claude-code')}.get(args.host, [args.host]):
                install_host(host, list(commands(host, registered)))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"의존성 설치 실패: {error}\n")
    print("의존성 확인 완료" if args.dry_run else "의존성 설치 완료. 새 에이전트 세션을 여세요.")


if __name__ == "__main__":
    sys.exit(main())
