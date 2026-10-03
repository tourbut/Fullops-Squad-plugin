#!/usr/bin/env python3
"""coordinator 대기: heartbeat·status 묶음은 모델을 깨우지 않고 ack하고, 처리할 메시지가 오면 반환한다.

`--types` 없는 `check --wait`가 걸려 있으면 Orca는 PTY 알림("You have N orchestration message")을
보내지 않는다. 대신 모든 메시지에 깨어나므로, 조용한 타입만 있는 묶음은 여기서 흡수한다.
"""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import time

import integration


def find_orca():
    """Orca CLI 경로: ORCA_CLI_COMMAND → PATH(orca, orca-ide) → OS별 기본 설치 위치. 못 찾으면 None.

    Windows 샌드박스 셸처럼 사용자 PATH를 물려받지 않는 환경에서도 설치 위치로 찾는다."""
    for name in (os.environ.get('ORCA_CLI_COMMAND'), 'orca', 'orca-ide'):
        if name and shutil.which(name):
            return shutil.which(name)
    home = Path.home()
    for path in (Path(os.environ.get('LOCALAPPDATA') or home / 'AppData/Local') / 'Programs/orca/resources/bin/orca.exe',
                 Path('/Applications/Orca.app/Contents/Resources/bin/orca'),
                 home / 'Applications/Orca.app/Contents/Resources/bin/orca',
                 Path('/opt/Orca/resources/bin/orca')):
        if path.is_file():
            return str(path)
    return None


def check(args, ack):
    orca = shutil.which(args.orca) or args.orca  # Windows의 orca.cmd
    command = [orca, 'orchestration', 'check', '--wait', '--timeout-ms', str(args.wait_ms), '--json']
    for flag, value in (('--run', args.run), ('--terminal', args.terminal), ('--ack', ack)):
        if value:
            command += [flag, value]
    done = subprocess.run(command, capture_output=True, text=True)  # stderr는 keepalive 줄이다
    try:
        response = json.loads(done.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f'check 출력 해석 실패 (exit {done.returncode}): {done.stdout[-500:]}')
    if not response.get('ok'):
        raise RuntimeError(json.dumps(response.get('error'), ensure_ascii=False))
    return response['result']


def summarize(absorbed):
    heartbeats = {}
    for message in absorbed:
        if message.get('type') == 'heartbeat':
            heartbeats[message.get('from_handle')] = {'at': message.get('created_at'), 'payload': message.get('payload')}
    return {'heartbeats': heartbeats,
            'others': [{k: m.get(k) for k in ('id', 'type', 'from_handle', 'subject', 'body', 'created_at')}
                       for m in absorbed if m.get('type') != 'heartbeat']}


def settings(repo, check_override=None):
    """운영 설정 세 개만 읽는다. 프로세스 환경 변수 → 레포 .env → 기본값."""
    defaults = {'check_minutes': 60, 'ready_timeout_seconds': 90, 'log_limit': 30}
    names = {f'FULLOPS_WORKER_{key.upper()}': key for key in defaults}
    values = {}
    path = Path(repo) / '.fullops-squad/.env'
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            key, separator, raw = line.partition('=')
            key = key.strip().removeprefix('export ').strip()
            if separator and key in names:
                if key in os.environ or (names[key] == 'check_minutes' and check_override is not None):
                    continue
                try:
                    tokens = shlex.split(raw, comments=True)
                except ValueError:
                    raise ValueError(f'{key}: 설정값의 따옴표를 확인하세요') from None
                values[key] = tokens[0] if len(tokens) == 1 else ''
    result = {}
    for name, key in names.items():
        try:
            number = float(check_override if key == 'check_minutes' and check_override is not None else
                           os.environ.get(name, values.get(name, defaults[key])))
            if not math.isfinite(number) or number <= 0:
                if not (key == 'check_minutes' and check_override == 0):
                    raise ValueError()
            if key != 'check_minutes' and not number.is_integer():
                raise ValueError()
            result[key] = number if key == 'check_minutes' else int(number)
        except ValueError:
            raise ValueError(f'{name}: 양의 유한한 {"숫자" if key == "check_minutes" else "정수"}를 설정하세요') from None
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--orca', default=None, help='skills get에 사용한 Orca 실행 파일. 없으면 자동으로 찾는다')
    parser.add_argument('--run')
    parser.add_argument('--repo', default='.', help='설정 파일을 읽을 레포 루트. 기본은 현재 디렉터리')
    parser.add_argument('--settings', action='store_true', help='비밀값 없이 운영 설정만 JSON으로 출력하고 종료한다')
    parser.add_argument('--terminal')
    parser.add_argument('--ack', help='처리를 마친 이전 delivery id')
    parser.add_argument('--quiet-types', default='heartbeat,status', help='모델을 깨우지 않고 흡수할 타입')
    parser.add_argument('--wait-ms', type=int, default=900000)
    parser.add_argument('--max-minutes', type=float, help='설정된 확인 주기를 이번 실행에서 덮어쓴다(분)')
    args = parser.parse_args()
    try:
        configured = settings(args.repo, args.max_minutes)
    except OSError:
        parser.error('.fullops-squad/.env 설정 파일을 읽을 수 없습니다')
    except ValueError as error:
        parser.error(str(error))
    args.max_minutes = configured['check_minutes']
    if args.settings:
        print(json.dumps(configured))
        return 0
    args.orca = args.orca or find_orca() or 'orca'
    quiet = {t.strip() for t in args.quiet_types.split(',') if t.strip()}
    quiet -= {'worker_done', 'question', 'escalation'}
    deadline = time.monotonic() + args.max_minutes * 60
    absorbed, ack = [], args.ack
    try:
        while True:
            result = check(args, ack)
            ack = None  # 전달한 ack는 이번 호출에서 처리됐다
            messages = result.get('messages') or []
            if messages and not all(m.get('type') in quiet for m in messages):
                integration.record(Path(args.repo).resolve(), messages)
                print(json.dumps({'status': 'actionable', 'deliveryId': result.get('deliveryId'),
                                  'messages': messages, 'absorbed': summarize(absorbed),
                                  'integration': integration.pending(Path(args.repo).resolve())}, ensure_ascii=False, indent=1))
                return 0
            if messages:
                absorbed += messages
                ack = result.get('deliveryId')
            if time.monotonic() >= deadline:
                if ack:
                    check(argparse.Namespace(**{**vars(args), 'wait_ms': 1}), ack)  # 흡수한 마지막 묶음을 ack
                print(json.dumps({'status': 'idle_timeout', 'check_minutes': args.max_minutes,
                                  'absorbed': summarize(absorbed)}, ensure_ascii=False, indent=1))
                return 0
    except (OSError, RuntimeError, KeyError) as error:
        print(json.dumps({'status': 'error', 'error': str(error), 'pending_ack': ack,
                          'absorbed': summarize(absorbed)}, ensure_ascii=False, indent=1))
        return 2


if __name__ == '__main__':
    sys.exit(main())
