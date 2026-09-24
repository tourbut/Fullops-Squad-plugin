#!/usr/bin/env python3
"""FullOps의 외부 의존성(npm 도구·MCP, 사용자 범위 스킬, 의존 플러그인)을 확인(--check)하거나 설치한다.

마켓플레이스로 플러그인만 설치하면 npm 도구와 사용자 범위 스킬은 설치되지 않는다. 설치된 플러그인 안에서
이 스크립트를 실행해 채운다. 출처는 패키지에 함께 들어 있는 dependencies.json이다.
"""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

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
        if cli == "codex":
            for name in deps["codex"]["plugins"]:
                yield [cli, "plugin", "add", name]
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
    parser.add_argument("--check", action="store_true", help="빠진 필수 CLI만 확인한다. 빠진 것이 있으면 종료코드 1")
    args = parser.parse_args()
    if args.check:
        absent = missing_tools()
        print("필수 CLI 모두 있음" if not absent else "없는 CLI: " + ", ".join(absent))
        raise SystemExit(1 if absent else 0)
    if not args.host:
        parser.error("--host가 필요합니다")
    cli = {"claude-code": "claude"}.get(args.host, args.host)
    try:
        registered = {} if args.dry_run or args.host in ("all", "both", "grok", "agy") else {cli: registered_marketplaces(cli)}
        run(commands(args.host, registered), args.dry_run)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"의존성 설치 실패: {error}\n")
    print("의존성 확인 완료" if args.dry_run else "의존성 설치 완료. 새 에이전트 세션을 여세요.")


if __name__ == "__main__":
    sys.exit(main())
