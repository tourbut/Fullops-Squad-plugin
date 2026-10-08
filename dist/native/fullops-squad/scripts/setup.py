#!/usr/bin/env python3
"""명시한 Git 레포에만 FullOps를 활성화한다. 기존 문서는 보존한다."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

from datetime import date
import deliverables
import policy
from storage import atomic_write, write_json


def apply_plan(repo, journal, plan, dry_run=False, verbose=False, rollback=False):
    """최초 계획의 원본/작성 바이트를 확인해 중단된 setup을 재개한다. 사용자 변경은 보존한다."""
    pending = []
    for item in plan['files']:
        name = Path(item['path'])
        if not name.parts or name.is_absolute() or '..' in name.parts or name.parts[0] == '.git':
            raise ValueError('잘못된 setup 복구 경로')
        path = repo / name
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if repo in p.parents):
            raise ValueError('setup 복구 경로에 symlink가 있습니다')
        current = path.read_bytes() if path.exists() else None
        before = base64.b64decode(item['before'], validate=True) if item['before'] is not None else None
        after = base64.b64decode(item['after'], validate=True)
        if current not in (before, after):
            raise ValueError(f"setup 중 사용자 변경을 보존합니다. 복구 충돌: {item['path']}")
        target = before if rollback else after
        if current != target:
            pending.append((path, target))
    for path, content in pending:
        if verbose:
            print(('생성 예정: ' if dry_run else '작성: ') + path.relative_to(repo).as_posix())
        if not dry_run:
            if content is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, content)
    if not dry_run:
        journal.unlink(missing_ok=True)
    print(f"{'생성 예정' if dry_run else '작성'}: {len(pending)}개")
    return [path.relative_to(repo).as_posix() for path, _ in pending]

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


def lint_commands(repo):
    """신규 설정에 기존 package scripts만 연결한다. 스택별 규칙 구성은 setup 스킬이 맡는다."""
    manifest = repo / 'package.json'
    if not manifest.is_file():
        return []
    package = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(package, dict) or not isinstance(package.get('scripts', {}), dict) or not isinstance(package.get('packageManager', ''), str):
        raise ValueError('package.json의 scripts·packageManager 형식을 확인하세요')
    scripts = package.get('scripts', {})
    manager = re.match(r'^(npm|pnpm|yarn|bun)(?:@|$)', package.get('packageManager', ''))
    command = manager[1] if manager else next((name for file, name in (
        ('pnpm-lock.yaml', 'pnpm'), ('yarn.lock', 'yarn'), ('bun.lock', 'bun'), ('bun.lockb', 'bun'))
        if (repo / file).is_file()), 'npm')
    # ponytail: 루트의 대표 스크립트만 연결한다. 모노레포·다른 스택은 스킬이 실제 실행 범위를 확인한다.
    names = ['lint' if scripts.get('lint') else 'lint:design', 'typecheck', 'test']
    return [{'name': name, 'kind': 'test' if name == 'test' else 'lint',
             'run': [command, 'run', name]} for name in names
            if isinstance(scripts.get(name), str) and scripts[name].strip()
            and 'no test specified' not in scripts[name]]


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


def transition_preflight(repo):
    if git(repo, 'status', '--porcelain'):
        raise ValueError('운영 모드 전환 전에 현재 변경을 커밋하거나 보존하세요. dirty 작업은 수정하지 않습니다')
    import flow_gate
    import integration
    for entry in git(repo, 'worktree', 'list', '--porcelain').split('\n\n'):
        worktree = next((line[9:] for line in entry.splitlines() if line.startswith('worktree ')), None)
        if not worktree or not Path(worktree).is_dir():
            continue
        if git(worktree, 'status', '--porcelain'):
            raise ValueError(f'다른 작업 공간의 변경을 보존한 뒤 전환하세요: {worktree}')
        directory = Path(git(worktree, 'rev-parse', '--absolute-git-dir')) / 'fullops-gate'
        for path in directory.glob('flow-*.json'):
            state = json.loads(path.read_text(encoding='utf-8'))
            if state.get('dispatch') and not state.get('settled'):
                raise ValueError('미완료 dispatch가 있습니다. worker 결과를 처리한 작업 경계에서 전환하세요')
            for run in state.get('runs', []):
                status = flow_gate.run_state(run)
                if status is None or status[0] or status[1]:
                    raise ValueError(f'Run {run}의 활성 worker·미처리 메시지·상태를 확인하세요')
    if integration.pending(repo):
        raise ValueError('기본 브랜치에 미통합 완료 결과가 있습니다. 리뷰·통합 후 전환하세요')
    if any(json.loads(path.read_text(encoding='utf-8')).get('hold')
           for path in integration.directory(repo).glob('*.json')):
        raise ValueError('보류된 통합 결과가 있습니다. 원본 기록을 해결한 뒤 전환하세요')
    for path in (repo / '.fullops-squad/docs/evaluations/qa-reports').glob('*-review/result.json'):
        result = json.loads(path.read_text(encoding='utf-8'))
        if not result.get('conclusion') or any(item.get('review_status') == 'pending' for item in result.get('files', [])):
            import review
            if review.superseded_check(repo, path.parent.name[:-7]):
                continue
            raise ValueError('진행 중인 리뷰를 완료한 뒤 전환하세요')


def operating_block(content, name):
    start, end = '<!-- fullops-mode:start -->', '<!-- fullops-mode:end -->'
    if content.count(start) != content.count(end) or content.count(start) > 1:
        raise ValueError(f'손상된 운영 모드 관리 블록: {name}')
    if name.endswith('FULLOPS.md'):
        body = ('## 운영 모드와 테스트 범위\n\n'
                '`fullops.json`의 mode·primary_role·primary_branch·test_level이 정본이다. mode 누락은 coor, 테스트 레벨 누락은 standard다.\n'
                'coor에서는 기존 조율·배정 책임을 유지한다. dev에서는 주 담당자가 직접 기술 계획·구현·검증을 수행하고 필요한 전문가를 배정·통합한다.\n'
                'dev 주 담당자는 제품 범위 판단을 사용자/기획 담당과 확인하고, 작성자와 다른 세션의 고정 SHA 리뷰를 받는다. 부모 dispatch나 가짜 worker_done은 만들지 않는다.\n'
                '아래 coor 전용 배정/직접 설계 제한은 dev 주 담당자의 직접 개발에 적용하지 않는다. 라우팅·인박스·독립 리뷰·통합·산출물 보존은 두 모드에서 유지한다.\n'
                '테스트 범위는 rules/common/testing.md의 레벨을 따르고, 모드 전환 뒤에는 새 세션을 시작한다. 기존 worker 공간과 기록은 보존하며 다음 배정 전에 동기화한다.\n')
    elif name.endswith('testing.md'):
        template = (PLUGIN / 'assets/repository' / name).read_text(encoding='utf-8')
        body = template.split(start + '\n', 1)[1].split(end, 1)[0]
    else:
        body = ('## 운영 책임\n\n'
                '현재 모드·주 담당자·테스트 레벨은 fullops.json을 읽는다. FULLOPS.md의 운영 모드 절을 우선 적용한다.\n'
                'dev 주 담당자는 직접 구현과 전문가 배정·통합을 맡는다. dispatched dev-worker는 기존 worker 권한과 worker_done 계약을 따른다.\n')
    block = f'{start}\n{body}{end}'
    if start in content:
        left, right = content.index(start), content.index(end)
        if left > right:
            raise ValueError(f'손상된 운영 모드 관리 블록: {name}')
        return content[:left] + block + content[right + len(end):]
    meta, body = deliverables.split(content)
    prefix = deliverables.render(meta) + '\n' if meta else ''
    return prefix + block + '\n\n' + body


def setup(repo, dry_run=False, verbose=False, roles=None, remote=None, base=None, local_only=False,
          mode=None, primary_role=None, test_level=None, rollback=False):
    repo = Path(repo).expanduser().resolve(strict=True)
    root = Path(subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"], text=True).strip()).resolve()
    if root != repo:
        raise ValueError(f"레포 루트를 지정하세요: {root}")
    local_journal = Path(git(repo, 'rev-parse', '--absolute-git-dir')) / 'fullops-setup.json'
    mode_journal = policy.transition_path(repo)
    journal = mode_journal if mode_journal.exists() else local_journal
    invocation = {'roles': roles, 'remote': remote, 'base': base, 'local_only': local_only}
    for name, value in (('mode', mode), ('primary_role', primary_role), ('test_level', test_level)):
        if value is not None:
            invocation[name] = value
    if journal.is_file():
        if journal.is_symlink():
            raise ValueError('symlink 복구 기록은 사용하지 않습니다')
        plan = json.loads(journal.read_text(encoding='utf-8'))
        if plan.get('repo', str(repo)) != str(repo):
            raise ValueError('전환을 시작한 체크아웃에서 같은 명령으로 복구하세요')
        if rollback and journal != mode_journal:
            raise ValueError('모드 전환 복구 기록만 --rollback으로 되돌릴 수 있습니다')
        if not rollback and plan.get('invocation') != invocation:
            raise ValueError('중단된 setup이 있습니다. 이전과 같은 옵션으로 재시도하세요')
        return apply_plan(repo, journal, plan, dry_run, verbose, rollback)
    if rollback:
        raise ValueError('중단된 모드 전환 기록이 없습니다')
    marker = repo / MARKER
    if marker.is_symlink() or marker.parent.is_symlink():
        raise ValueError("심볼릭 링크 설정은 사용하지 않습니다")
    config = json.loads(marker.read_text()) if marker.exists() else {"schema_version": 1}
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("지원하지 않는 FullOps 설정 버전")
    connection = config.get("git", {})
    if not isinstance(connection, dict) or any(
        not isinstance(connection.get(key), str) or not connection[key]
        for key in ("remote", "base") if connection):
        raise ValueError("잘못된 원격 설정: git.remote와 git.base를 확인하세요")
    if local_only and (remote is not None or base is not None):
        raise ValueError("--local-only와 --remote/--base는 함께 사용할 수 없습니다")
    assigned = config.get("roles", {})
    if not isinstance(assigned, dict):
        raise ValueError("roles는 역할과 브랜치의 객체여야 합니다")
    assigned = dict(assigned)
    if local_only and connection and any(role not in assigned for role in roles or []):
        raise ValueError("원격 연결된 레포의 역할 추가에는 원격 setup을 사용하세요")
    for role in roles or []:
        assigned.setdefault(role, f"fullops/{role}")
    if not assigned:
        raise ValueError("레포에 필요한 역할을 --roles로 지정하세요")
    for role, branch in assigned.items():
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", role) or not isinstance(branch, str) or not re.fullmatch(r"fullops/[a-z][a-z0-9_-]{0,63}", branch):
            raise ValueError(f"잘못된 역할/브랜치: {role}")
    if len(set(assigned.values())) != len(assigned):
        raise ValueError("역할별 브랜치는 중복될 수 없습니다")
    old_mode = config.get('mode', 'coor')
    old_primary = config.get('primary_role')
    config['roles'] = assigned
    if mode is not None:
        config['mode'] = mode
    elif not marker.exists():
        config['mode'] = 'coor'
    if test_level is not None:
        config['test_level'] = test_level
    elif not marker.exists():
        config['test_level'] = 'lite'
    if primary_role is not None:
        config['primary_role'] = primary_role
    elif config.get('mode') == 'dev' and old_mode != 'dev':
        config['primary_role'] = 'dev'
    elif not marker.exists() and 'coor' in assigned:
        config['primary_role'] = 'coor'
    if config.get('mode') == 'dev':
        config.setdefault('primary_branch', git(repo, 'symbolic-ref', '--short', 'HEAD'))
    policy.validate(config)
    transition = marker.exists() and (old_mode != config.get('mode', 'coor') or old_primary != config.get('primary_role'))
    if transition:
        if old_mode == 'dev' and config.get('mode') == 'coor':
            raise ValueError('일반 dev → coor 전환은 지원하지 않습니다. 중단 복구는 --rollback을 사용하세요')
        transition_preflight(repo)
        journal = mode_journal
    print(f"운영 모드: {config.get('mode', 'coor')} / 주 담당: {config.get('primary_role') or '기존 coordinator'} / 테스트: {config.get('test_level', 'standard')}")
    templates = PLUGIN / "assets/repository"
    files = {p.relative_to(templates).as_posix(): p.read_bytes()
             for p in sorted(templates.rglob("*")) if p.is_file()}
    if not marker.exists():
        name = '.fullops-squad/orca-agents.md'
        text = files[name].decode('utf-8')
        designer = 'designer' if 'designer' in assigned else next(iter(assigned))
        markers = f'- 설계 역할: `{designer}`'
        if config.get('mode') == 'coor' and config.get('primary_role'):
            markers += f'\n- coordinator 역할: `{config["primary_role"]}`'
        if 'tester' in assigned:
            markers += '\n- tester 역할: `tester`'
        text = text.replace('- 설계 역할: `architecture`', markers)
        files[name] = text.encode('utf-8')
    lint_path = '.fullops-squad/lint/lint.json'
    if not (repo / lint_path).exists():
        lint_config = json.loads(files[lint_path])
        lint_config['commands'] = lint_commands(repo)
        files[lint_path] = (json.dumps(lint_config, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    for role in assigned:
        files[f".fullops-squad/handovers/to_{role}.md"] = b""
        files[f".fullops-squad/contexts/{role}.md"] = f"# {role} 컨텍스트\n\n결정·교훈을 항목당 3줄 이내로 기록한다.\n".encode()
    for name, content in files.items():
        if name.endswith('.md') and content and '/rules/common/' not in name and '/_' not in name:
            body = content.decode('utf-8')
            title = next((line[2:].strip() for line in body.splitlines() if line.startswith('# ')), Path(name).stem)
            files[name] = (deliverables.render({'title': title, 'status': 'draft', 'updated': date.today().isoformat(),
                           'owner': Path(name).stem if '/contexts/' in name else config.get('primary_role', 'coordinator'), 'summary': title}) + '\n' + body).encode('utf-8')
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
    if mode is not None or test_level is not None or not marker.exists():
        for name in ('.fullops-squad/FULLOPS.md', '.fullops-squad/orca-agents.md',
                     '.fullops-squad/rules/common/testing.md'):
            current = (repo / name).read_bytes() if (repo / name).exists() else changes[name]
            updated = operating_block(current.decode('utf-8'), name).encode('utf-8')
            if updated != current:
                changes[name] = updated
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
    if not local_only:
        remote = remote if remote is not None else connection.get("remote", "origin")
        base = base if base is not None else connection.get("base")
        config["git"] = remote_branches(repo, remote, base, assigned, dry_run)
    updated = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode()
    if not marker.exists() or marker.read_bytes() != updated:
        changes[MARKER] = updated
    plan = {'repo': str(repo), 'invocation': invocation, 'files': [{'path': name,
            'before': base64.b64encode((repo / name).read_bytes()).decode() if (repo / name).exists() else None,
            'after': base64.b64encode(content).decode()} for name, content in changes.items()]}
    if not dry_run:
        if transition:
            backup = journal.parent / 'fullops-mode-backups' / f'{uuid.uuid4().hex}.json'
            write_json(backup, plan)
            print(f'전환 원본 백업: {backup}')
            # Exclusive publication keeps a concurrent transition from replacing the recovery plan.
            os.link(backup, journal)
        else:
            write_json(journal, plan)
    return apply_plan(repo, journal, plan, dry_run, verbose)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="개별 파일 경로 출력")
    parser.add_argument("--roles", nargs="+", help="레포별 역할 ID. 재실행 시 기존 역할에 추가")
    parser.add_argument("--remote", help="역할 브랜치를 생성할 remote (저장값 또는 최초 origin)")
    parser.add_argument("--local-only", action="store_true", help="원격 생성 없이 로컬 역할만 구성")
    parser.add_argument("--base", help="원격 기준 브랜치 (저장값 또는 최초 원격 HEAD)")
    parser.add_argument('--mode', choices=['coor', 'dev'], help='신규 운영 모드 또는 기존 coor → dev 전환')
    parser.add_argument('--primary-role', help='주 담당 등록 역할. dev 모드 기본 dev')
    parser.add_argument('--test-level', choices=policy.LEVELS, help='개발 검증 범위. 신규 기본 lite, 기존 누락 standard')
    parser.add_argument('--rollback', action='store_true', help='중단된 운영 모드 전환의 원본 복구')
    args = parser.parse_args()
    try:
        setup(args.repo, args.dry_run, args.verbose, args.roles,
              args.remote, args.base, args.local_only, args.mode, args.primary_role, args.test_level, args.rollback)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"setup 실패: {error}\n")


if __name__ == "__main__":
    main()
