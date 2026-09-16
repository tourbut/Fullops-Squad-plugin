#!/usr/bin/env python3
"""플러그인과 외부 의존성을 함께 설치한다. 레포 setup은 실행하지 않는다."""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "dist/native/fullops-squad"


def commands(host, registered=None):
    deps = json.loads((ROOT / "dependencies.json").read_text())
    agents = {"all": ["codex", "claude-code", "grok", "agy"],
              "both": ["codex", "claude-code"]}.get(host, [host])
    yield ["npm", "install", "--global", *[server["package"] for server in deps["mcp"].values()]]
    for agent in agents:
        cli = "claude" if agent == "claude-code" else agent
        if agent in ("grok", "agy"):
            for skill in deps["skills"] + deps["codex"]["skills"] + deps["portable_skills"]:
                yield ["npx", "--yes", "skills@latest", "add", skill["source"],
                       "--skill", *skill["names"], "--global", "--agent",
                       "antigravity-cli" if agent == "agy" else agent, "--yes"]
            yield [cli, "plugin", "install", str(PLUGIN)] + (["--trust"] if agent == "grok" else [])
            continue
        markets = deps["marketplaces"] if cli == "claude" else {"ponytail": deps["marketplaces"]["ponytail"]}
        for name, source in {**markets, "fullops-squad": str(ROOT)}.items():
            current = (registered or {}).get(cli, {}).get(name)
            if current is not None:
                if normalize_source(current) != normalize_source(source):
                    raise ValueError(f"{cli}: {name} 마켓플레이스 출처 충돌: {current} != {source}")
            else:
                yield [cli, "plugin", "marketplace", "add", source]
        if cli == "codex":
            for plugin in deps["codex"]["plugins"]:
                yield [cli, "plugin", "add", plugin]
        for skill in deps["skills"] + (deps["codex"]["skills"] if cli == "codex" else []):
            yield ["npx", "--yes", "skills@latest", "add", skill["source"],
                   "--skill", *skill["names"], "--global", "--agent", agent, "--yes"]
        yield [cli, "plugin", "install" if cli == "claude" else "add", "fullops-squad@fullops-squad"]


def normalize_source(source):
    return source.removeprefix("https://github.com/").removesuffix(".git").rstrip("/")


def registered_marketplaces(cli):
    result = json.loads(subprocess.check_output([cli, "plugin", "marketplace", "list", "--json"], text=True))
    if cli == "codex":
        return {m["name"]: m.get("marketplaceSource", {}).get("source", m["root"])
                for m in result["marketplaces"]}
    return {m["name"]: m.get("repo") or m.get("url") or m.get("path") or m["installLocation"]
            for m in result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=["all", "both", "codex", "claude-code", "grok", "agy"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print(shlex.join(["python3", str(ROOT / "scripts/build.py")]))
    else:
        subprocess.run(["python3", str(ROOT / "scripts/build.py")], check=True, cwd=ROOT)
    plan = list(commands(args.host))
    if not args.dry_run:
        missing = sorted({cmd[0] for cmd in plan if not shutil.which(cmd[0])})
        if missing:
            parser.error("먼저 설치할 실행 파일: " + ", ".join(missing))
        try:
            registered = {cli: registered_marketplaces(cli) for cli in sorted({cmd[0] for cmd in plan} & {"codex", "claude"})}
            plan = list(commands(args.host, registered))
        except (ValueError, subprocess.CalledProcessError) as error:
            parser.error(str(error))
    for cmd in plan:
        print(shlex.join(cmd), flush=True)
        if not args.dry_run:
            subprocess.run(cmd, check=True, cwd=ROOT)
    print("설치 계획 확인 완료" if args.dry_run else "설치 완료. 새 에이전트 세션에서 setup-fullops를 실행하세요.")


if __name__ == "__main__":
    main()
