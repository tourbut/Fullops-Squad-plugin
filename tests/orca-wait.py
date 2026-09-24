"""가짜 Orca CLI로 coordinator 대기의 흡수·ack·반환·타임아웃·오류를 확인한다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/fullops-squad/scripts/orca_wait.py'
FAKE = '''#!/usr/bin/env python3
import json, os, sys
state = os.environ['FAKE_STATE']
calls = json.load(open(state)) if os.path.exists(state) else []
calls.append(sys.argv[1:])
json.dump(calls, open(state, 'w'))
responses = json.load(open(os.environ['FAKE_RESPONSES']))
print(json.dumps(responses[min(len(calls), len(responses)) - 1]))
'''


def ok(result):
    return {'id': 'x', 'ok': True, 'result': result}


def batch(delivery, *types):
    return ok({'deliveryId': delivery, 'count': len(types), 'timedOut': False,
               'messages': [{'id': f'{delivery}-{i}', 'type': t, 'from_handle': 'term_w1', 'subject': t,
                             'created_at': f'2026-09-23 10:0{i}', 'payload': '{"phase":"implementing"}'}
                            for i, t in enumerate(types)]})


def run(tmp, responses, *extra):
    state = Path(tmp) / 'state.json'
    state.unlink(missing_ok=True)
    (Path(tmp) / 'responses.json').write_text(json.dumps(responses))
    env = dict(os.environ, FAKE_STATE=str(state), FAKE_RESPONSES=str(Path(tmp) / 'responses.json'))
    orca = Path(tmp) / ('orca.cmd' if os.name == 'nt' else 'orca')
    done = subprocess.run([sys.executable, str(SCRIPT), '--orca', str(orca), '--run', 'run_1', *extra],
                          capture_output=True, text=True, env=env)
    return done.returncode, json.loads(done.stdout), json.loads(state.read_text())


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-orca-wait-') as tmp:
        fake = Path(tmp) / 'orca'
        fake.write_text(FAKE)
        fake.chmod(0o755)
        if os.name == 'nt':  # shebang을 실행할 수 없으므로 실제 Orca처럼 orca.cmd로 감싼다
            (Path(tmp) / 'orca.cmd').write_text(f'@"{sys.executable}" "%~dp0orca" %*\n')
        empty = ok({'deliveryId': None, 'count': 0, 'messages': [], 'timedOut': True})

        # heartbeat·status 묶음은 흡수해서 다음 대기에 ack하고, worker_done이 오면 ack 없이 반환한다.
        code, out, calls = run(tmp, [batch('d1', 'heartbeat'), batch('d2', 'status', 'heartbeat'),
                                     batch('d3', 'heartbeat', 'worker_done')], '--ack', 'd0')
        assert code == 0 and out['status'] == 'actionable' and out['deliveryId'] == 'd3', out
        assert [m['type'] for m in out['messages']] == ['heartbeat', 'worker_done']
        assert out['absorbed']['heartbeats']['term_w1']['at'] == '2026-09-23 10:01'
        assert [m['type'] for m in out['absorbed']['others']] == ['status']
        acks = [c[c.index('--ack') + 1] if '--ack' in c else None for c in calls]
        assert acks == ['d0', 'd1', 'd2'], acks
        assert all('--types' not in c and '--wait' in c and c[c.index('--run') + 1] == 'run_1' for c in calls)

        # 조용한 묶음만 오다가 시간이 다 되면 마지막 묶음을 ack하고 idle_timeout으로 반환한다.
        code, out, calls = run(tmp, [batch('d1', 'heartbeat'), empty], '--max-minutes', '0')
        assert code == 0 and out['status'] == 'idle_timeout', out
        assert calls[-1][calls[-1].index('--ack') + 1] == 'd1' and len(calls) == 2
        code, out, calls = run(tmp, [empty], '--max-minutes', '0')
        assert out['status'] == 'idle_timeout' and len(calls) == 1 and '--ack' not in calls[0]

        # quiet 타입은 바꿀 수 있다: status를 빼면 status가 곧바로 반환된다.
        code, out, _ = run(tmp, [batch('d1', 'status')], '--quiet-types', 'heartbeat')
        assert out['status'] == 'actionable'

        # Orca 오류는 보류 중인 ack와 함께 보고한다.
        code, out, _ = run(tmp, [batch('d1', 'heartbeat'),
                                 {'id': 'x', 'ok': False, 'error': {'code': 'consumer_fenced', 'message': 'no'}}])
        assert code == 2 and out['status'] == 'error' and 'consumer_fenced' in out['error'] and out['pending_ack'] == 'd1', out
    print('PASS: orca wait absorbs heartbeat/status, acks in order, returns actionable, idle timeout, errors')


if __name__ == '__main__':
    main()
