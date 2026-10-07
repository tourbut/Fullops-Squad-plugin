#!/usr/bin/env python3
"""활성 레포의 핸드오버 인박스를 만들고 완료 기록을 안전하게 보존한다."""
import argparse
import hashlib
import json
from datetime import date
import os
from pathlib import Path
import re
import subprocess
import uuid

import deliverables
from storage import atomic_write, write_json

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


def instruction(repo, role, key, handover=None):
    """현재 과제의 역할 인박스와 본문을 읽는다. 이력·대기 파일을 현재 지시서로 사용하지 않는다."""
    validate_role(repo, role)
    relative = (handover or f'.fullops-squad/handovers/to_{role}.md').replace('\\', '/')
    if Path(relative).as_posix() != f'.fullops-squad/handovers/to_{role}.md':
        raise ValueError(f'현재 지시서는 역할 인박스 .fullops-squad/handovers/to_{role}.md를 사용하세요. '
                         '다음 과제는 PLANS.md에 대기시키고 완료 뒤 로그를 보존한 다음 인박스를 재사용하세요')
    path = safe_file(repo, relative)
    text = path.read_text(encoding='utf-8') if path.is_file() else ''
    if not deliverables.split(text)[1].lstrip().startswith(f'# {key} — '):
        raise ValueError('지시서 본문 첫 줄을 `# <과제 키> — <목표>`로 쓰세요')
    return path, text


def archives(repo, role, key):
    return [p for p in safe_file(repo, '.fullops-squad/handovers/logs').glob(f'*_to_{role}.md')
            if f'## {key} — ' in p.read_text(encoding='utf-8')]


def new(repo, role, key, goal, base=None, rework=False):
    validate_role(repo, role)
    inbox = safe_file(repo, f".fullops-squad/handovers/to_{role}.md")
    if not inbox.is_file() or inbox.read_bytes():
        raise ValueError(f"진행 중이거나 없는 역할 인박스: {inbox}")
    if not goal.strip() or "\n" in goal:
        raise ValueError("목표는 한 줄로 지정하세요")
    previous = archives(repo, role, key)
    if previous and not rework:
        raise ValueError('완료된 과제의 수정은 work.py reopen으로 새 시도를 여세요')
    if rework and not previous:
        raise ValueError('완료 기록이 없는 과제는 work.py new로 시작하세요')
    content = TEMPLATE.read_text().replace("<과제 키>", key, 1).replace("<목표>", goal.strip(), 1)
    meta = {'title': f'{key} — {goal.strip()}', 'status': 'draft', 'updated': date.today().isoformat(),
            'owner': role, 'tasks': [key], 'summary': goal.strip(), 'attempt': uuid.uuid4().hex}
    if base:
        meta['base'] = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', '--verify', base + '^{commit}'], text=True).strip()
    if previous:
        references = '## 이전 완료 기록\n\n' + '\n'.join(f'- {p.relative_to(repo).as_posix()}' for p in sorted(previous)) + '\n\n'
        content = content.replace('## 완료 보고\n', references + '## 완료 보고\n')
    atomic_write(inbox, deliverables.render(meta) + '\n' + content)
    print(inbox.relative_to(repo))


def finish(repo, role, key):
    validate_role(repo, role)
    inbox = safe_file(repo, f".fullops-squad/handovers/to_{role}.md")
    if not inbox.is_file():
        raise ValueError(f"없는 역할 인박스: {inbox}")
    content = inbox.read_text()
    if not content.strip():
        previous = archives(repo, role, key)
        if previous:
            print(sorted(previous)[-1].relative_to(repo))
            return
    if not deliverables.split(content)[1].lstrip().startswith(f"# {key} — "):
        raise ValueError("인박스 과제 키가 다릅니다")
    report = content.partition("## 완료 보고\n")[2].strip()
    placeholder = TEMPLATE.read_text().partition("## 완료 보고\n")[2].strip()
    if not report or report == placeholder:
        raise ValueError("완료 보고 전문을 인박스에 먼저 작성하세요")
    log = safe_file(repo, f".fullops-squad/handovers/logs/{date.today()}_to_{role}.md")
    meta = deliverables.front_matter(content) or {}
    attempt = meta.get('attempt') or hashlib.sha256(content.encode()).hexdigest()
    token = f'<!-- fullops-attempt: {key} {attempt} -->'
    marker = f"## {key} — {date.today()}\n{token}\n"
    entry = ("\n" + marker + "\n" + content.rstrip() + "\n").encode()
    log.parent.mkdir(parents=True, exist_ok=True)
    if not log.exists():
        log.write_text(deliverables.render({'title': f'{role} 완료 기록', 'status': 'draft',
                       'updated': date.today().isoformat(), 'owner': role, 'summary': '지시서와 완료 보고를 보존한다.'}), encoding='utf-8')
    matching = [p for p in archives(repo, role, key) if token in p.read_text(encoding='utf-8')]
    if matching:
        log = matching[0]
        saved = re.split(r'\n## [A-Za-z0-9][A-Za-z0-9._-]* — \d{4}-\d{2}-\d{2}\n<!-- fullops-attempt:',
                         log.read_text(encoding='utf-8').split(token, 1)[1], maxsplit=1)[0]
        if content.rstrip() not in saved:
            raise ValueError('같은 시도의 완료 기록이 다릅니다. 인박스를 보존하고 새 시도를 여세요')
    else:
        atomic_write(log, log.read_bytes() + entry)
    if content.rstrip().encode() not in log.read_bytes():
        raise OSError("아카이브 확인 실패: 인박스를 유지합니다")
    if inbox.read_text() != content:
        raise ValueError("아카이브 중 인박스가 변경됐습니다. 새 내용을 보존합니다")
    atomic_write(inbox, b'')
    print(log.relative_to(repo))


def validate_role(repo, role):
    config = json.loads(safe_file(repo, ".fullops-squad/fullops.json").read_text())
    if not isinstance(config, dict) or config.get("schema_version") != 1 or not isinstance(config.get("roles"), dict):
        raise ValueError("setup에서 역할 설정을 생성하거나 전환하세요")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", role) or role not in config.get("roles", {}):
        raise ValueError("등록되지 않은 역할입니다. setup에서 역할을 추가하세요")


def input_identity(repo, role, key, options):
    _, text = instruction(repo, role, key)
    text = re.sub(r'<!-- fullops-packet:start -->[\s\S]*?<!-- fullops-packet:end -->\n*', '', text)
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    meta = deliverables.front_matter(text) or {}
    value = {'task_key': key, 'role': role, 'head': head, 'attempt': meta.get('attempt'),
             'instruction_sha256': hashlib.sha256(text.encode()).hexdigest(), 'options': options}
    return {**value, 'input_sha256': hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()}


def task_excerpt(text, limit=3500):
    """긴 인박스의 뒤쪽 완료 기준도 전달한다. 전체 인박스는 worker 필수 문맥이다."""
    if len(text) <= limit:
        return text
    # ponytail: 첫/끝 구간만 보낸다. 중간 계약은 partial로 남기고 worker가 원본을 읽는다.
    return text[:limit // 2 - 40] + '\n[partial: read full inbox]\n' + text[-limit // 2:]


def previous_result(path, identity, force=False):
    if not path.is_file() or force:
        return None
    result = json.loads(path.read_text(encoding='utf-8'))
    if result.get('input_sha256') != identity['input_sha256']:
        raise ValueError('입력이 변경됐습니다. --force로 이전 결과를 보존하고 갱신하세요')
    return result


def save_result(path, result):
    if path.is_file():
        history = path.parent / 'history' / (path.stem + '-' + uuid.uuid4().hex + '.json')
        atomic_write(history, path.read_bytes())
    write_json(path, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("new", "reopen", "finish"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--goal")
    parser.add_argument('--base', help='new/reopen: 지시서의 고정 lint 기준 SHA/ref')
    args = parser.parse_args()
    if not KEY.fullmatch(args.key):
        parser.error("과제 키는 영문·숫자·점·밑줄·하이픈만 사용하세요")
    try:
        repo = active_repo(args.repo)
        if args.mode in ('new', 'reopen'):
            if args.goal is None:
                parser.error("new에는 --goal이 필요합니다")
            new(repo, args.role, args.key, args.goal, args.base, args.mode == 'reopen')
        else:
            finish(repo, args.role, args.key)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"핸드오버 처리 실패: {error}\n")


if __name__ == "__main__":
    main()
