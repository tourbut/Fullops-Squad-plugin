#!/usr/bin/env python3
"""grok worker가 워크트리에서 멈추지 않게 원본 레포의 grok 폴더 신뢰를 확인(--check)하거나 추가(--add)한다.

grok은 신뢰하지 않은 폴더의 hook·MCP·프로젝트 지시문을 실행하기 전에 확인을 요청하고, 워크트리는 git 공용 폴더가 있는
원본 체크아웃 경로로 신뢰를 요구한다. 신뢰는 보안 결정이라 사용자가 승인한 뒤에만 --add를 실행한다.
신뢰 목록은 ~/.grok/trusted_folders.toml이며 FULLOPS_GROK_TRUST_FILE로 바꿀 수 있다(테스트용).
"""
import argparse
import os
from pathlib import Path
import re
import time

from env_link import main_checkout


def store():
    return Path(os.environ.get('FULLOPS_GROK_TRUST_FILE') or Path.home() / '.grok/trusted_folders.toml')


def project(path):
    """grok이 신뢰를 요구하는 경로: 워크트리면 원본 체크아웃, 아니면 그 경로."""
    path = Path(path).resolve()
    return main_checkout(path) or path


def same(a, b):
    a, b = os.path.normpath(a), os.path.normpath(b)
    return a.lower() == b.lower() if os.name == 'nt' else a == b


def trusted(path, text=None):
    """신뢰 목록에 이 경로(또는 상위 폴더)가 trusted = true로 있는지."""
    text = store().read_text(encoding='utf-8') if text is None and store().is_file() else (text or '')
    target = str(path)
    for folder, body in re.findall(r"^\[folders\.'([^']+)'\]\s*\n((?:(?!^\[).*\n?)*)", text, re.M):
        if re.search(r'^\s*trusted\s*=\s*true\s*$', body, re.M):
            if same(folder, target) or os.path.normpath(target).lower().startswith(os.path.normpath(folder).lower() + os.sep):
                return True
    return False


def add(path):
    """신뢰 목록 끝에 항목을 덧붙인다. 이미 신뢰돼 있으면 바꾸지 않고 False."""
    if trusted(path):
        return False
    target = store()
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding='utf-8') if target.is_file() else ''
    entry = f"[folders.'{path}']\ntrusted = true\ndecided_at = {int(time.time())}\n"
    target.write_text(existing + ('\n' if existing and not existing.endswith('\n') else '') + entry,
                      encoding='utf-8', newline='\n')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', required=True, help='레포 체크아웃 또는 워크트리 경로')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check', action='store_true', help='신뢰 여부만 확인한다. 신뢰되지 않았으면 종료코드 1')
    action.add_argument('--add', action='store_true', help='사용자 승인 뒤 신뢰 목록에 추가한다')
    args = parser.parse_args()
    path = project(args.repo)
    if args.check:
        ok = trusted(path)
        print(f"grok 신뢰 {'됨' if ok else '안 됨'}: {path}")
        raise SystemExit(0 if ok else 1)
    print(f"grok 신뢰 {'추가' if add(path) else '이미 됨'}: {path} ({store()})")


if __name__ == '__main__':
    main()
