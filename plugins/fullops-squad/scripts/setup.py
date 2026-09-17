#!/usr/bin/env python3
"""명시한 Git 레포에만 FullOps를 활성화한다. 기존 문서는 보존한다."""
import argparse
import json
from pathlib import Path
import re
import subprocess

PLUGIN = Path(__file__).resolve().parents[1]
MARKER = ".fullops-squad/fullops.json"
ENTRYPOINTS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
START = "<!-- fullops-squad:start -->"
END = "<!-- fullops-squad:end -->"
POINTER = f"""{START}
## FullOps Squad

이 레포는 `.fullops-squad/fullops.json`이 있을 때만 FullOps 하네스를 사용한다.
작업 시작 시 `.fullops-squad/FULLOPS.md`를 직접 열고 관련 규약을 따른다.
{END}
"""


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def remote_branches(repo, remote, base, roles, dry_run):
    urls = git(repo, "remote", "get-url", "--push", "--all", remote).splitlines()
    if len(urls) != 1:
        raise ValueError("push URL이 하나인 remote를 선택하세요")
    url = urls[0]
    refs = git(repo, "ls-remote", "--symref", url, "HEAD", "refs/heads/*").splitlines()
    heads = {ref: sha for line in refs for sha, ref in [line.split("\t")] if not sha.startswith("ref: ")}
    if base is None:
        base = next((line.split("\t")[0][len("ref: refs/heads/"):] for line in refs
                     if line.startswith("ref: refs/heads/") and line.endswith("\tHEAD")), None)
    if not base or f"refs/heads/{base}" not in heads:
        raise ValueError("원격 기준 브랜치가 없습니다. 첫 커밋을 push하거나 --base를 지정하세요")
    missing = [branch for branch in roles.values() if f"refs/heads/{branch}" not in heads]
    print(f"원격 {remote} / 기준 {base} / 생성: {', '.join(missing) or '없음'}")
    if missing and not dry_run:
        git(repo, "fetch", "--no-tags", url, f"refs/heads/{base}")
        sha = git(repo, "rev-parse", "FETCH_HEAD")
        # Empty leases enforce create-only even if another setup races this one.
        git(repo, "push", "--atomic", *[f"--force-with-lease=refs/heads/{b}:" for b in missing],
            url, *[f"{sha}:refs/heads/{b}" for b in missing])
    return {"remote": remote, "base": base}


def setup(repo, dry_run=False, verbose=False, roles=None, remote=None, base=None):
    repo = Path(repo).expanduser().resolve(strict=True)
    root = Path(subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"], text=True).strip()).resolve()
    if root != repo:
        raise ValueError(f"레포 루트를 지정하세요: {root}")
    marker = repo / MARKER
    if marker.is_symlink() or marker.parent.is_symlink():
        raise ValueError("심볼릭 링크 설정은 사용하지 않습니다")
    config = json.loads(marker.read_text()) if marker.exists() else {"schema_version": 1}
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("지원하지 않는 FullOps 설정 버전")
    assigned = config.get("roles", {})
    if not isinstance(assigned, dict):
        raise ValueError("roles는 역할과 브랜치의 객체여야 합니다")
    assigned = dict(assigned)
    for role in roles or []:
        assigned.setdefault(role, f"fullops/{role}")
    if not assigned:
        raise ValueError("레포에 필요한 역할을 --roles로 지정하세요")
    for role, branch in assigned.items():
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", role) or branch != f"fullops/{role}":
            raise ValueError(f"잘못된 역할/브랜치: {role}")
    templates = PLUGIN / "assets/repository"
    files = {str(p.relative_to(templates)): p.read_bytes()
             for p in sorted(templates.rglob("*")) if p.is_file()}
    for role in assigned:
        files[f".fullops-squad/handovers/to_{role}.md"] = b""
        files[f".fullops-squad/contexts/{role}.md"] = f"# {role} 컨텍스트\n\n결정·교훈을 항목당 3줄 이내로 기록한다.\n".encode()
    for relative in [*files, *ENTRYPOINTS, MARKER]:
        path = repo / relative
        if any(p.is_symlink() for p in [path, *path.parents] if p != repo and repo in p.parents):
            raise ValueError(f"심볼릭 링크 대상은 수정하지 않습니다: {relative}")
        if path.exists() and not path.is_file():
            raise ValueError(f"파일이 아닌 경로: {relative}")
        if any(p.exists() and not p.is_dir() for p in path.parents if repo in p.parents):
            raise ValueError(f"상위 경로가 디렉터리가 아닙니다: {relative}")
    if not marker.exists():
        conflicts = [name for name, content in files.items()
                     if (repo / name).exists() and (repo / name).read_bytes() != content]
        if conflicts:
            raise ValueError("기존 하네스와 충돌합니다. 먼저 수동으로 통합하세요: " + ", ".join(conflicts))
    changes = {name: content for name, content in files.items() if not (repo / name).exists()}
    for name in ENTRYPOINTS:
        path = repo / name
        content = path.read_bytes().decode() if path.exists() else ""
        if content.count(START) != content.count(END) or content.count(START) > 1:
            raise ValueError(f"손상된 FullOps 블록: {name}")
        if START in content:
            if content.index(START) > content.index(END):
                raise ValueError(f"손상된 FullOps 블록: {name}")
            start, end = content.index(START), content.index(END) + len(END)
            updated = content[:start] + POINTER.rstrip("\n") + content[end:]
            if updated != content:
                changes[name] = updated.encode()
        else:
            changes[name] = (content + ("\n\n" if content else "") + POINTER).encode()
    config.setdefault("plugin_version", json.loads((PLUGIN / "plugin.json").read_text())["version"])
    config["roles"] = assigned
    # Preflight the remote only after every local conflict has been checked.
    if remote:
        config["git"] = remote_branches(repo, remote, base, assigned, dry_run)
    updated = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode()
    if not marker.exists() or marker.read_bytes() != updated:
        changes[MARKER] = updated
    for name, content in changes.items():
        if verbose:
            print(("생성 예정: " if dry_run else "작성: ") + name)
        if not dry_run:
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    print(f"{'생성 예정' if dry_run else '작성'}: {len(changes)}개")
    return list(changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="개별 파일 경로 출력")
    parser.add_argument("--roles", nargs="+", help="레포별 역할 ID. 재실행 시 기존 역할에 추가")
    parser.add_argument("--remote", default="origin", help="역할 브랜치를 생성할 remote (기본 origin)")
    parser.add_argument("--local-only", action="store_true", help="원격 생성 없이 로컬 역할만 구성")
    parser.add_argument("--base", help="원격 기준 브랜치. 생략하면 원격 HEAD")
    args = parser.parse_args()
    try:
        if args.base and args.local_only:
            parser.error("--base와 --local-only는 함께 사용할 수 없습니다")
        setup(args.repo, args.dry_run, args.verbose, args.roles,
              None if args.local_only else args.remote, args.base)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"setup 실패: {error}\n")


if __name__ == "__main__":
    main()
