#!/usr/bin/env python3
"""산출물 인덱스의 원천 경로와 조립 문서의 로컬 링크를 검사한다."""
import argparse
from pathlib import Path
import re
import subprocess


def check(repo, selected=None):
    repo = Path(repo).expanduser().resolve(strict=True)
    root = Path(subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"], text=True).strip()).resolve()
    base = repo / ".fullops-squad"
    if root != repo or not (base / "fullops.json").is_file():
        raise ValueError("활성화된 Git 레포 루트를 지정하세요")
    index = base / "docs/deliverables/README.md"
    rows = {}
    for line in index.read_text().splitlines():
        if line.startswith("| D"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 5 and re.fullmatch(r"D\d{2}", cells[0]):
                rows[cells[0]] = (re.findall(r"`([^`]+)`", cells[3]), cells[4])
    if set(rows) != {f"D{number:02d}" for number in range(1, 14)}:
        raise ValueError("산출물 인덱스의 D01–D13 행을 확인하세요")
    if selected and selected not in rows:
        raise ValueError(f"없는 산출물 ID: {selected}")
    issues = []
    errors = []
    unwritten = 0
    for doc_id, (sources, status) in rows.items():
        if selected and doc_id != selected:
            continue
        if selected:
            print(f"{doc_id}: {status} / 원천: {', '.join(sources)}")
        missing = [source for source in sources if not (base / source).exists()]
        if status == "미작성":
            unwritten += 1
        elif missing:
            issue = f"{doc_id} 원천 없음: {', '.join(missing)}"
            issues.append(issue)
            errors.append(issue)
        for document in (base / "docs/deliverables").glob(f"{doc_id}_*.md"):
            for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
                path = target.split("#", 1)[0]
                if path and not re.match(r"[a-z]+://", path) and not (document.parent / path).exists():
                    issue = f"{document.name} 링크 없음: {target}"
                    issues.append(issue)
                    errors.append(issue)
    for issue in issues:
        print(issue)
    print(f"검사: {selected or len(rows)} / 미작성: {unwritten} / 문제: {len(issues)}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--id")
    args = parser.parse_args()
    try:
        if check(args.repo, args.id):
            parser.exit(1)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"산출물 검사 실패: {error}\n")


if __name__ == "__main__":
    main()
