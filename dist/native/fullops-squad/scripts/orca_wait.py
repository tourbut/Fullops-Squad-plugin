#!/usr/bin/env python3
"""coordinator 대기: heartbeat·status 묶음은 모델을 깨우지 않고 ack하고, 처리할 메시지가 오면 반환한다.

`--types` 없는 `check --wait`가 걸려 있으면 Orca는 PTY 알림("You have N orchestration message")을
보내지 않는다. 대신 모든 메시지에 깨어나므로, 조용한 타입만 있는 묶음은 여기서 흡수한다.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time


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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--orca', default='orca', help='skills get에 사용한 Orca 실행 파일')
    parser.add_argument('--run')
    parser.add_argument('--terminal')
    parser.add_argument('--ack', help='처리를 마친 이전 delivery id')
    parser.add_argument('--quiet-types', default='heartbeat,status', help='모델을 깨우지 않고 흡수할 타입')
    parser.add_argument('--wait-ms', type=int, default=900000)
    parser.add_argument('--max-minutes', type=float, default=45, help='이 시간 동안 처리할 메시지가 없으면 반환한다')
    args = parser.parse_args()
    quiet = {t.strip() for t in args.quiet_types.split(',') if t.strip()}
    deadline = time.monotonic() + args.max_minutes * 60
    absorbed, ack = [], args.ack
    try:
        while True:
            result = check(args, ack)
            ack = None  # 전달한 ack는 이번 호출에서 처리됐다
            messages = result.get('messages') or []
            if messages and not all(m.get('type') in quiet for m in messages):
                print(json.dumps({'status': 'actionable', 'deliveryId': result.get('deliveryId'),
                                  'messages': messages, 'absorbed': summarize(absorbed)}, ensure_ascii=False, indent=1))
                return 0
            if messages:
                absorbed += messages
                ack = result.get('deliveryId')
            if time.monotonic() >= deadline:
                if ack:
                    check(argparse.Namespace(**{**vars(args), 'wait_ms': 1}), ack)  # 흡수한 마지막 묶음을 ack
                print(json.dumps({'status': 'idle_timeout', 'absorbed': summarize(absorbed)}, ensure_ascii=False, indent=1))
                return 0
    except (OSError, RuntimeError, KeyError) as error:
        print(json.dumps({'status': 'error', 'error': str(error), 'pending_ack': ack,
                          'absorbed': summarize(absorbed)}, ensure_ascii=False, indent=1))
        return 2


if __name__ == '__main__':
    sys.exit(main())
