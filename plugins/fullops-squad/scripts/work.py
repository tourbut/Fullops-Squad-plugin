#!/usr/bin/env python3
"""활성 레포의 핸드오버 인박스를 만들고 완료 기록을 안전하게 보존한다."""
import argparse
import json
from datetime import date
import os
from pathlib import Path
import re
import subprocess

KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
TEMPLATE = Path(__file__).resolve().parents[1] / "assets/repository/.fullops-squad/handovers/_TEMPLATE.md"


def active_repo(path):
    repo = Path(path).expanduser().resolve(strict=True)
    root = Path(subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"], text=True).strip()).resolve()
    if root != repo or not (repo / ".fullops-squad/fullops.json").is_file():
        raise ValueError("활성화된 Git 레포 루트를 지정하세요")
    return repo


def safe_file(repo, relative):
    path = repo / relative
    if any(p.is_symlink() for p in [path, *path.parents] if p != repo and repo in p.parents):
        raise ValueError(f"심볼릭 링크 경로는 사용하지 않습니다: {relative}")
    return path


def new(repo, role, key, goal):
    validate_role(repo, role)
    inbox = safe_file(repo, f".fullops-squad/handovers/to_{role}.md")
    if not inbox.is_file() or inbox.read_bytes():
        raise ValueError(f"진행 중이거나 없는 역할 인박스: {inbox}")
    if not goal.strip() or "\n" in goal:
        raise ValueError("목표는 한 줄로 지정하세요")
    content = TEMPLATE.read_text().replace("<과제 키>", key, 1).replace("<목표>", goal.strip(), 1)
    inbox.write_text(content)
    print(inbox.relative_to(repo))


def finish(repo, role, key):
    validate_role(repo, role)
    inbox = safe_file(repo, f".fullops-squad/handovers/to_{role}.md")
    if not inbox.is_file():
        raise ValueError(f"없는 역할 인박스: {inbox}")
    content = inbox.read_text()
    if not content.startswith(f"# {key} — "):
        raise ValueError("인박스 과제 키가 다릅니다")
    report = content.partition("## 완료 보고\n")[2].strip()
    placeholder = TEMPLATE.read_text().partition("## 완료 보고\n")[2].strip()
    if not report or report == placeholder:
        raise ValueError("완료 보고 전문을 인박스에 먼저 작성하세요")
    log = safe_file(repo, f".fullops-squad/handovers/logs/{date.today()}_to_{role}.md")
    marker = f"## {key} — {date.today()}\n"
    if any(f"## {key} — " in existing.read_text()
           for existing in log.parent.glob(f"*_to_{role}.md") if existing.is_file()):
        raise ValueError("이미 아카이브된 과제입니다. 기록을 확인하세요")
    entry = ("\n" + marker + "\n" + content.rstrip() + "\n").encode()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as output:
        output.write(entry)
        output.flush()
        os.fsync(output.fileno())
    if not log.read_bytes().endswith(entry):
        raise OSError("아카이브 확인 실패: 인박스를 유지합니다")
    if inbox.read_text() != content:
        raise ValueError("아카이브 중 인박스가 변경됐습니다. 새 내용을 보존합니다")
    inbox.write_bytes(b"")
    print(log.relative_to(repo))


def validate_role(repo, role):
    config = json.loads(safe_file(repo, ".fullops-squad/fullops.json").read_text())
    if not isinstance(config, dict) or config.get("schema_version") != 1 or not isinstance(config.get("roles"), dict):
        raise ValueError("setup에서 역할 설정을 생성하거나 전환하세요")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", role) or role not in config.get("roles", {}):
        raise ValueError("등록되지 않은 역할입니다. setup에서 역할을 추가하세요")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("new", "finish"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--goal")
    args = parser.parse_args()
    if not KEY.fullmatch(args.key):
        parser.error("과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요")
    try:
        repo = active_repo(args.repo)
        if args.mode == "new":
            if args.goal is None:
                parser.error("new에는 --goal이 필요합니다")
            new(repo, args.role, args.key, args.goal)
        else:
            finish(repo, args.role, args.key)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"핸드오버 처리 실패: {error}\n")


if __name__ == "__main__":
    main()
