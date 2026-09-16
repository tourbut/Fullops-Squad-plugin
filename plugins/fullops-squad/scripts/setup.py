#!/usr/bin/env python3
"""명시한 Git 레포에만 FullOps를 활성화한다. 기존 문서는 보존한다."""
import argparse
import json
from pathlib import Path
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


def setup(repo, dry_run=False, verbose=False):
    repo = Path(repo).expanduser().resolve(strict=True)
    root = Path(subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"], text=True).strip()).resolve()
    if root != repo:
        raise ValueError(f"레포 루트를 지정하세요: {root}")
    templates = PLUGIN / "assets/repository"
    files = {str(p.relative_to(templates)): p.read_bytes()
             for p in sorted(templates.rglob("*")) if p.is_file()}
    for relative in [*files, *ENTRYPOINTS, MARKER]:
        path = repo / relative
        if any(p.is_symlink() for p in [path, *path.parents] if p != repo and repo in p.parents):
            raise ValueError(f"심볼릭 링크 대상은 수정하지 않습니다: {relative}")
        if path.exists() and not path.is_file():
            raise ValueError(f"파일이 아닌 경로: {relative}")
        if any(p.exists() and not p.is_dir() for p in path.parents if repo in p.parents):
            raise ValueError(f"상위 경로가 디렉터리가 아닙니다: {relative}")
    marker = repo / MARKER
    if marker.exists():
        config = json.loads(marker.read_text())
        if not isinstance(config, dict) or config.get("schema_version") != 1:
            raise ValueError("지원하지 않는 FullOps 설정 버전")
    else:
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
    if not marker.exists():
        version = json.loads((PLUGIN / "plugin.json").read_text())["version"]
        changes[MARKER] = (json.dumps({"schema_version": 1, "plugin_version": version}, indent=2) + "\n").encode()
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
    args = parser.parse_args()
    try:
        setup(args.repo, args.dry_run, args.verbose)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"setup 실패: {error}\n")


if __name__ == "__main__":
    main()
