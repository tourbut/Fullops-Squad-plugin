#!/usr/bin/env python3
"""산출물 인덱스의 원천 경로·조립 문서 링크·원천 문서 front matter를 검사하고, front matter를 정해진 형식으로 쓴다(--stamp).

front matter는 모델이 손으로 쓰지 않고 --stamp로만 쓴다. 필드 순서와 목록 표기가 고정돼 문서마다 같고,
lint의 DOC-002 규칙이 바뀐 원천 문서의 형식을 이 스크립트의 출력과 글자 그대로 비교한다.
"""
import argparse
from datetime import date
from pathlib import Path
import re
import subprocess

STATUSES = ("draft", "review", "approved")
REQUIRED = ("id", "title", "status", "updated", "owner", "summary")
LISTS = ("tasks", "upstream", "downstream")
ORDER = ("id", "title", "status", "updated", "owner", "tasks", "upstream", "downstream", "summary")
INDEX = "docs/deliverables/README.md"


def split(text):
    """(meta, 본문). 맨 위 `---` 블록이 없거나 닫히지 않으면 (None, 원문)."""
    lines = text.lstrip("﻿").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    meta = {}
    for n, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return meta, "".join(lines[n + 1:])
        match = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*?)\s*(?:\s#.*)?$", line.rstrip("\r\n"))
        if match:
            key, value = match.groups()
            if value.startswith("[") and value.endswith("]"):
                meta[key] = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
            else:
                meta[key] = value.strip("'\"")
    return None, text


def front_matter(text):
    return split(text)[0]


def render(meta):
    """정해진 필드 순서와 표기로 front matter를 만든다. 알 수 없는 키는 뒤에 이름순으로 둔다."""
    keys = [k for k in ORDER if k in meta] + sorted(k for k in meta if k not in ORDER)
    lines = []
    for key in keys:
        value = meta[key]
        if key in LISTS or isinstance(value, list):
            items = value if isinstance(value, list) else [value]
            lines.append(f"{key}: [{', '.join(items)}]")
        else:
            lines.append(f"{key}: {value}")
    return "---\n" + "\n".join(lines) + "\n---\n"


def problems(text, doc_id, index_status=None):
    """원천 문서 front matter의 규칙 위반 목록. 빈 목록이면 통과."""
    meta, _ = split(text)
    if meta is None:
        return ["front matter 없음"]
    found = [f"필수 필드 없음: {k}" for k in REQUIRED if not str(meta.get(k, "")).strip()]
    if meta.get("id") and meta["id"] != doc_id:
        found.append(f"id가 {doc_id}가 아님: {meta['id']}")
    if meta.get("status") and meta["status"] not in STATUSES:
        found.append(f"status는 {'/'.join(STATUSES)} 중 하나: {meta['status']}")
    if meta.get("updated") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["updated"]):
        found.append(f"updated는 YYYY-MM-DD: {meta['updated']}")
    found += [f"{k}는 [a, b] 목록" for k in LISTS if k in meta and not isinstance(meta[k], list)]
    if index_status in STATUSES and meta.get("status") in STATUSES and meta["status"] != index_status:
        found.append(f"인덱스 상태({index_status})와 문서 상태({meta['status']})가 다름")
    lines = text.lstrip("﻿").splitlines(keepends=True)
    block = "".join(lines[:next(n for n, l in enumerate(lines[1:], 2) if l.strip() == "---")])
    if not found and block.replace("\r\n", "\n") != render(meta):
        found.append("정해진 형식과 다름(필드 순서·목록 표기·주석)")
    return found


def index_rows(text):
    """{산출물 ID: (이름, 원천 경로들, 상태)}"""
    rows = {}
    for line in text.splitlines():
        if line.startswith("| D"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 5 and re.fullmatch(r"D\d{2}", cells[0]):
                rows[cells[0]] = (cells[2], re.findall(r"`([^`]+)`", cells[3]), cells[4])
    return rows


def owner_of(sources, relative):
    """.fullops-squad 기준 경로가 어느 원천에 속하는지. 파일이면 같은 경로, 폴더면 그 안의 Markdown."""
    for source in sources:
        source = source.split(" ")[0]
        if relative == source or (source.endswith("/") and relative.startswith(source) and relative.endswith(".md")):
            return True
    return False


def source_files(base, source):
    """인덱스의 원천 경로가 파일이면 그 파일, 폴더면 안의 Markdown 파일들."""
    path = base / source.split(" ")[0]
    if path.is_dir():
        return sorted(p for p in path.rglob("*.md") if p.is_file())
    return [path] if path.is_file() else []


def meta_for(base, doc_id, sources):
    """원천 파일 중 id가 맞는 front matter를 찾는다. (경로, meta) 또는 (첫 파일, None)."""
    files = [f for source in sources for f in source_files(base, source)]
    for path in files:
        meta = front_matter(path.read_text(encoding="utf-8", errors="replace"))
        if meta and meta.get("id") == doc_id:
            return path, meta
    return (files[0], None) if files else (None, None)


def active_base(repo):
    repo = Path(repo).expanduser().resolve(strict=True)
    root = Path(subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"], text=True).strip()).resolve()
    base = repo / ".fullops-squad"
    if root != repo or not (base / "fullops.json").is_file():
        raise ValueError("활성화된 Git 레포 루트를 지정하세요")
    return base


def stamp(repo, doc_id, task=None, status=None, owner=None, summary=None, title=None,
          upstream=None, downstream=None, path=None, today=None):
    """원천 문서에 front matter를 정해진 형식으로 쓰고, 인덱스 표의 상태를 같은 값으로 맞춘다."""
    base = active_base(repo)
    index = base / INDEX
    rows = index_rows(index.read_text(encoding="utf-8"))
    if doc_id not in rows:
        raise ValueError(f"없는 산출물 ID: {doc_id}")
    name, sources, index_status = rows[doc_id]
    if path:
        target = (base / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        relative = target.relative_to(base.resolve()).as_posix()
        if not owner_of(sources, relative):
            raise ValueError(f"{relative}은 {doc_id}의 원천 경로가 아닙니다: {', '.join(sources)}")
    else:
        files = [f for s in sources for f in source_files(base, s)]
        candidates = [s.split(" ")[0] for s in sources if not s.split(" ")[0].endswith("/")]
        if files:
            target = meta_for(base, doc_id, sources)[0]
        elif candidates:
            target = base / candidates[0]
        else:
            raise ValueError(f"{doc_id} 원천이 폴더입니다. --path로 문서를 지정하세요")
    text = target.read_text(encoding="utf-8") if target.is_file() else ""
    meta, body = split(text)
    meta = dict(meta or {})
    for key, value in (("title", title), ("owner", owner), ("summary", summary)):
        if value:
            meta[key] = value.strip()
    meta["id"] = doc_id
    meta.setdefault("title", name)
    meta["status"] = status or (meta.get("status") if meta.get("status") in STATUSES else None) or \
        (index_status if index_status in STATUSES else "draft")
    meta["updated"] = (today or date.today()).isoformat()
    tasks = meta.get("tasks") if isinstance(meta.get("tasks"), list) else ([meta["tasks"]] if meta.get("tasks") else [])
    if task and task not in tasks:
        tasks.append(task)
    if tasks:
        meta["tasks"] = tasks
    for key, value in (("upstream", upstream), ("downstream", downstream)):
        if value is not None:
            meta[key] = value
    missing = [k for k in ("owner", "summary") if not str(meta.get(k, "")).strip()]
    if missing:
        raise ValueError("처음 쓰는 front matter에는 " + ", ".join(f"--{k}" for k in missing) + "가 필요합니다")
    if meta["status"] not in STATUSES:
        raise ValueError(f"status는 {'/'.join(STATUSES)} 중 하나")
    body = body if body.strip() else f"\n# {meta['title']}\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(meta) + (body if body.startswith("\n") else "\n" + body), encoding="utf-8", newline="\n")
    if index_status != meta["status"]:
        lines = index.read_text(encoding="utf-8").splitlines(keepends=True)
        for n, line in enumerate(lines):
            if line.startswith(f"| {doc_id} |"):
                cells = line.rstrip("\r\n").rstrip("|").split("|")
                cells[-1] = f" {meta['status']} "
                lines[n] = "|".join(cells) + "|\n"
        index.write_text("".join(lines), encoding="utf-8", newline="\n")
    return target


def check(repo, selected=None, strict=False):
    base = active_base(repo)
    rows = index_rows((base / INDEX).read_text(encoding="utf-8"))
    if set(rows) != {f"D{number:02d}" for number in range(1, 14)}:
        raise ValueError("산출물 인덱스의 D01–D13 행을 확인하세요")
    if selected and selected not in rows:
        raise ValueError(f"없는 산출물 ID: {selected}")
    issues, errors, warnings = [], [], []
    unwritten = 0
    for doc_id, (_, sources, status) in rows.items():
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
        if status not in ("미작성", "범위 밖"):
            for path in [f for s in sources for f in source_files(base, s)]:
                for problem in problems(path.read_text(encoding="utf-8", errors="replace"), doc_id, status):
                    message = f"{doc_id} {path.relative_to(base).as_posix()}: {problem}"
                    (errors if strict else warnings).append(message)
                    if strict:
                        issues.append(message)
        for document in (base / "docs/deliverables").glob(f"{doc_id}_*.md"):
            for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
                path = target.split("#", 1)[0]
                if path and not re.match(r"[a-z]+://", path) and not (document.parent / path).exists():
                    issue = f"{document.name} 링크 없음: {target}"
                    issues.append(issue)
                    errors.append(issue)
    for issue in issues:
        print(issue)
    for warning in warnings:
        print(f"경고: {warning}")
    print(f"검사: {selected or len(rows)} / 미작성: {unwritten} / 문제: {len(issues)} / 경고: {len(warnings)}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--id", help="산출물 ID (D01–D13)")
    parser.add_argument("--strict", action="store_true", help="front matter 문제도 오류로 처리")
    parser.add_argument("--stamp", action="store_true", help="--id 산출물의 원천 문서에 front matter를 쓴다")
    parser.add_argument("--task", help="--stamp: 이 문서를 바꾼 과제 키 (tasks에 추가)")
    parser.add_argument("--status", choices=STATUSES)
    parser.add_argument("--owner", help="담당 역할")
    parser.add_argument("--summary", help="한 줄 요약")
    parser.add_argument("--title")
    parser.add_argument("--upstream", help="쉼표로 구분한 상위 산출물 ID")
    parser.add_argument("--downstream", help="쉼표로 구분한 하위 산출물 ID")
    parser.add_argument("--path", help="원천이 폴더이거나 여러 파일일 때 쓸 문서 (.fullops-squad 기준)")
    args = parser.parse_args()
    ids = lambda v: None if v is None else [x.strip() for x in v.split(",") if x.strip()]
    try:
        if args.stamp:
            if not args.id:
                raise ValueError("--stamp에는 --id가 필요합니다")
            target = stamp(args.repo, args.id, args.task, args.status, args.owner, args.summary, args.title,
                           ids(args.upstream), ids(args.downstream), args.path)
            print(target.relative_to(active_base(args.repo).parent).as_posix())
        elif check(args.repo, args.id, args.strict):
            parser.exit(1)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"산출물 처리 실패: {error}\n")


if __name__ == "__main__":
    main()
