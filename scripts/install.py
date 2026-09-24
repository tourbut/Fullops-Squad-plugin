#!/usr/bin/env python3
"""개발 체크아웃에서 플러그인과 외부 의존성을 함께 설치한다. 레포 setup은 실행하지 않는다.

일반 사용자는 GitHub 마켓플레이스로 설치하고 플러그인 안의 scripts/deps.py로 의존성을 채운다.
이 설치기는 개발 중인 체크아웃을 로컬 마켓플레이스로 등록해 바로 시험할 때 쓴다. 의존성 목록은 deps.py와 같다.
"""
import argparse
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "dist/native/fullops-squad"
sys.path.insert(0, str(ROOT / "plugins/fullops-squad/scripts"))
import deps  # noqa: E402

normalize_source = deps.normalize_source


def commands(host, registered=None):
    return deps.commands(host, registered, plugin={"source": str(ROOT), "package": PLUGIN})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", choices=["all", "both", *deps.HOSTS], default="all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print(shlex.join(["python3", str(ROOT / "scripts/build.py")]))
    else:
        subprocess.run([sys.executable, str(ROOT / "scripts/build.py")], check=True, cwd=ROOT)
    try:
        clis = {"all": ["codex", "claude"], "both": ["codex", "claude"], "codex": ["codex"], "claude-code": ["claude"]}.get(args.host, [])
        registered = {} if args.dry_run else {cli: deps.registered_marketplaces(cli) for cli in clis}
        deps.run(commands(args.host, registered), args.dry_run)
    except (ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    print("설치 계획 확인 완료" if args.dry_run else "설치 완료. 새 에이전트 세션에서 setup-fullops를 실행하세요.")


if __name__ == "__main__":
    main()
