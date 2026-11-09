"""긴 Bash 출력 줄이기: 짧은 출력·다른 형식은 그대로, 긴 출력은 원문 보존과 오류 줄 유지, flow_gate 연결"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import output_trim  # noqa: E402

LONG = '\n'.join(f'line {i}' for i in range(1000))


def event(stdout='ok', stderr='', tool='Bash', hook='PostToolUse', **extra):
    return {'hook_event_name': hook, 'tool_name': tool,
            'tool_response': {'stdout': stdout, 'stderr': stderr, 'interrupted': False, 'isImage': False, **extra}}


with tempfile.TemporaryDirectory(prefix='fullops-trim-') as tmp:
    # 그대로 두는 경우
    assert output_trim.replacement(tmp, event()) is None
    assert output_trim.replacement(tmp, event('\n'.join(['x'] * output_trim.LIMIT))) is None
    assert output_trim.replacement(tmp, event(LONG, tool='PowerShell')) is None
    assert output_trim.replacement(tmp, event(LONG, hook='PostToolUseFailure')) is None
    assert output_trim.replacement(tmp, event(LONG, interrupted=True)) is None
    assert output_trim.replacement(tmp, {'hook_event_name': 'PostToolUse', 'tool_name': 'Bash', 'tool_response': LONG}) is None
    assert not (Path(tmp) / '.fullops-squad').exists()

    # 줄이는 경우: 앞뒤·오류 줄·안내·원문·다른 필드
    noisy = LONG.replace('line 500\n', 'Traceback in line 500\n')
    updated = output_trim.replacement(tmp, event(noisy, 'warn', returnCodeInterpretation='kept'))
    text = updated['stdout']
    assert text.startswith('[FullOps: 출력이 길어 줄였다. 종료코드 0.')
    assert 'line 0\n' in text and 'line 999' in text and '501: Traceback in line 500' in text
    assert 'line 300\n' not in text and len(text) < len(noisy) / 2
    assert updated['stderr'] == 'warn' and updated['returnCodeInterpretation'] == 'kept' and updated['interrupted'] is False
    folder = Path(tmp) / '.fullops-squad/local/outputs'
    assert folder.joinpath('output-00.txt').read_text(encoding='utf-8') == f'{noisy}\n--- stderr ---\nwarn'
    entry = json.loads(folder.joinpath('trim.jsonl').read_text(encoding='utf-8'))
    assert entry['raw'] == len(noisy) + 4 and entry['sent'] < entry['raw']

    # 오류 줄이 많아도 상한을 넘지 않는다
    errors = '\n'.join(f'error {i}' for i in range(5000))
    assert output_trim.replacement(tmp, event(errors))['stdout'].count('\n') < output_trim.HEAD + output_trim.TAIL + output_trim.KEPT + 5

    # 슬롯을 넘으면 파일이 늘지 않고 가장 오래된 슬롯을 덮어쓴다
    for number, _ in enumerate(range(output_trim.SLOTS + 3)):
        path = output_trim.slot(folder)
        path.write_text('x', encoding='utf-8')
        os.utime(path, (1000 + number, 1000 + number))
    assert len(list(folder.glob('output-*.txt'))) == output_trim.SLOTS

with tempfile.TemporaryDirectory(prefix='fullops-trim-') as tmp:
    # flow_gate post가 updatedToolOutput을 내고, 원문은 작업 트리를 더럽히지 않는다
    def git(*args):
        return subprocess.check_output(['git', '-C', tmp, *args], text=True, encoding='utf-8').strip()

    def post(data):
        done = subprocess.run([sys.executable, str(SCRIPTS / 'flow_gate.py'), 'post'], text=True, capture_output=True, encoding='utf-8',
                              input=json.dumps({**data, 'cwd': tmp, 'session_id': 's', 'tool_input': {'command': 'x'}}))
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    git('init', '-q', '-b', 'main')
    subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp, '--roles', 'dev', '--local-only'], check=True, capture_output=True)
    git('add', '-A')
    git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'setup')
    assert 'updatedToolOutput' not in post(event()).get('hookSpecificOutput', {})
    output = post(event(LONG))['hookSpecificOutput']
    assert output['hookEventName'] == 'PostToolUse' and output['updatedToolOutput']['stdout'].startswith('[FullOps:')
    assert git('status', '--porcelain') == ''
print('OK')
