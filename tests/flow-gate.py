"""임시 레포에서 flow-gate hook의 역할 판정·dispatch 차단·지시서 route 확인·설계 역할 코드 차단·worker_done 종료 게이트를 확인한다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-flow-') as tmp:
        repo = Path(tmp)

        def git(*args):
            return subprocess.check_output(['git', '-C', tmp, *args], text=True).strip()

        def hook(mode, **event):
            event.setdefault('cwd', tmp)
            done = subprocess.run([sys.executable, str(SCRIPTS / 'flow_gate.py'), mode], text=True, capture_output=True,
                                  input=json.dumps(event), encoding='utf-8')
            assert done.returncode == 0, done.stderr
            return json.loads(done.stdout)

        def denied(output):
            return output.get('hookSpecificOutput', {}).get('permissionDecisionReason', '')

        def route(key, kind, role):
            path = repo / f'.fullops-squad/docs/evaluations/jev/{key}-route.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'route': kind, 'role': role}), encoding='utf-8')

        git('init', '-q', '-b', 'main')
        assert hook('start', session_id='x') == {}  # FullOps가 아닌 레포
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp,
                        '--roles', 'architecture', 'dev', 'art', '--local-only'], check=True, capture_output=True)
        git('add', '-A')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'setup')
        roles = json.loads((repo / '.fullops-squad/fullops.json').read_text(encoding='utf-8'))['roles']

        # coordinator (역할 브랜치가 아닌 main)
        assert 'jev_route.py' in hook('start', session_id='c', source='startup')['hookSpecificOutput']['additionalContext']
        bash = lambda command, **kw: hook('tool', session_id='c', tool_name='Bash', tool_input={'command': command}, **kw)
        assert 'worker-start' in denied(bash('orca terminal send --terminal t1 --text "handovers/to_dev.md 읽고 착수"'))
        assert '--run' in denied(bash('orca orchestration worker-start --spec "K1 작업" --agent codex'))
        assert '분류한 과제 키' in denied(bash('orca orchestration worker-start --run r1 --spec "K1 작업" --agent codex'))
        route('K1', 'simple', 'dev')
        assert bash('orca orchestration worker-start --run r1 --spec "K1 작업" --agent codex') == {}
        assert '분류한 과제 키' in denied(bash('orca orchestration worker-start --run r1 --spec "K10 작업" --agent codex'))

        write = lambda path, content, **kw: hook('tool', session_id='c', tool_name='Write',
                                                  tool_input={'file_path': path, 'content': content}, **kw)
        assert write(f'{tmp}/.fullops-squad/handovers/to_dev.md', '# K1 — 점프 수치\n') == {}
        assert '설계 역할' in denied(write(f'{tmp}/.fullops-squad/handovers/to_art.md', '# K1 — 점프 수치\n'))
        assert 'route 기록' in denied(write('.fullops-squad/handovers/to_dev.md', '# K2 — 없음\n'))

        # task-create + worker-start --task: 과제 spec에서 키를 찾는다(가짜 Orca task-list)
        tl = repo / '.git/fake-tasks.py'
        tl.write_text('import json\nprint(json.dumps({"ok": True, "result": {"tasks": ['
                      '{"id": "task_ok", "spec": "Task key K1 follow-up"}, {"id": "task_bad", "spec": "Task key loose-check"}]}}))\n',
                      encoding='utf-8')
        tcli = repo / '.git' / ('fake-tasks.cmd' if os.name == 'nt' else 'fake-tasks')
        if os.name == 'nt':
            tcli.write_text(f'@"{sys.executable}" "{tl}" %*\n', encoding='utf-8')
        else:
            tcli.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{tl}" "$@"\n', encoding='utf-8')
            tcli.chmod(0o755)
        os.environ['FULLOPS_ORCA_CLI'] = str(tcli)
        assert bash('orca orchestration worker-start --run r1 --task task_ok --agent codex') == {}
        bad = denied(bash('orca orchestration worker-start --run r1 --task task_bad --agent codex'))
        assert '--task task_bad' in bad and 'K1' in bad, bad  # 최근 분류된 키를 알려 준다
        assert '분류한 과제 키' in denied(bash("orca orchestration task-create --spec 'Task key loose-check'"))
        assert bash("orca orchestration task-create --spec 'Task key K1 follow-up'") == {}
        os.environ['FULLOPS_ORCA_CLI'] = str(repo / '.git/missing-orca')
        assert bash('orca orchestration worker-start --run r1 --task task_x --agent codex') == {}  # 확인 불가면 막지 않는다
        del os.environ['FULLOPS_ORCA_CLI']
        route('K3', 'design', 'architecture')
        assert '설계 역할' in denied(write('.fullops-squad/handovers/to_dev.md', '# K3 — 저장 형식\n'))
        assert write('.fullops-squad/handovers/to_architecture.md', '# K3 — 저장 형식\n') == {}
        assert '설계 역할' in denied(bash('python3 work.py new --repo . --role dev --key K3 --goal x'))
        assert bash('python3 work.py new --repo . --role dev --key K1 --goal x') == {}
        grok = hook('tool', sessionId='c', toolName='search_replace',  # grok camelCase 입력
                    toolInput={'file_path': '.fullops-squad/handovers/to_dev.md', 'content': '# K3 — 저장 형식\n'})
        assert '설계 역할' in denied(grok)

        # 설계 역할
        git('checkout', '-q', '-B', roles['architecture'])
        assert '코드는 고치지 않는다' in hook('start', session_id='a', source='startup')['hookSpecificOutput']['additionalContext']
        assert '코드를 고치지' in denied(hook('tool', session_id='a', tool_name='Write',
                                            tool_input={'file_path': f'{tmp}/src/save.py', 'content': 'x = 1\n'}))
        patch = '*** Begin Patch\n*** Update File: src/save.ts\n@@\n-a\n+b\n*** End Patch\n'
        assert '코드를 고치지' in denied(hook('tool', session_id='a', tool_name='apply_patch', tool_input={'command': patch}))
        assert hook('tool', session_id='a', tool_name='Write',
                    tool_input={'file_path': '.fullops-squad/handovers/to_dev.md', 'content': '# K3 — 저장 형식\n'}) == {}

        # dispatched worker
        git('checkout', '-q', '-B', roles['dev'])
        assert 'worker_done' in hook('start', session_id='w', source='startup')['hookSpecificOutput']['additionalContext']
        assert hook('stop', session_id='w') == {}  # preamble 없는 세션은 막지 않는다
        preamble = 'Task t-1 ... orca orchestration send --type worker_done --task-id t-1 --dispatch-id d-1 ...'
        assert hook('prompt', session_id='w', prompt=preamble) == {}
        assert hook('stop', session_id='w')['decision'] == 'block'
        assert 'systemMessage' in hook('stop', session_id='w', stop_hook_active=True)  # 두 번째는 통과
        assert hook('stop', sessionId='w', reason='shutdown') == {}  # grok 세션 종료 Stop
        hook('prompt', sessionId='g', prompt=preamble)
        assert hook('stop', sessionId='g', stopHookActive=False)['decision'] == 'block'
        hook('tool', sessionId='g', toolName='run_terminal_command', toolInput={'command':
             'orca orchestration ask --from w --question "저장 형식 A/B?"'})
        assert hook('stop', sessionId='g')['decision'] == 'block'  # ask는 완료가 아니다
        hook('tool', sessionId='g', toolName='run_terminal_command', toolInput={'command':
             'orca orchestration send --from w --type worker_done --task-id t-1 --dispatch-id d-1 --outcome succeeded'})
        assert hook('stop', sessionId='g') == {}
        assert hook('tool', session_id='w', tool_name='Bash', tool_input={'command': 'git status'}) == {}
        # 분류만 하고 배정하지 않은 과제는 종료를 한 번 막는다(대화 요약 뒤 배정을 잊는 경우)
        route_cmd = 'python3 C:/plugins/fullops-squad/scripts/jev_route.py --repo . --key WIN-1 --request "Windows 점검"'
        assert hook('tool', session_id='r', tool_name='Bash', tool_input={'command': route_cmd}) == {}
        blocked = hook('stop', session_id='r')
        assert blocked.get('decision') == 'block' and 'WIN-1' in blocked['reason'], blocked
        assert 'systemMessage' in hook('stop', session_id='r', stop_hook_active=True)  # 같은 상태로 다시 끝내면 통과
        (repo / '.fullops-squad/handovers/to_art.md').write_text('# WIN-1 — Windows 점검\n', encoding='utf-8')
        assert hook('stop', session_id='r') == {}  # 지시서에 과제 키가 있으면 배정한 것으로 본다
        hook('tool', session_id='r2', tool_name='Bash', tool_input={'command': route_cmd.replace('WIN-1', 'WIN-2')})
        assert hook('stop', session_id='r2').get('decision') == 'block'
        plans = repo / '.fullops-squad/PLANS.md'
        plans.write_text(plans.read_text(encoding='utf-8') + '| WIN-2 | Windows 점검 | ops | 보류: Editor 사용 중 | |\n', encoding='utf-8')
        assert hook('stop', session_id='r2') == {}  # PLANS.md에 보류를 적으면 통과
        (repo / '.fullops-squad/handovers/to_art.md').write_text('', encoding='utf-8')

        # worker를 띄운 세션은 결과를 받기 전에 끝내지 않는다(가짜 Orca CLI로 확인)
        fake_state = repo / '.git/fake-orca.json'
        fake = repo / '.git/fake-orca.py'
        fake.write_text('import json, os, sys\n'
                        'state = json.load(open(os.environ["FAKE_ORCA_STATE"], encoding="utf-8"))\n'
                        'key = "messages" if "check" in sys.argv else "workers"\n'
                        'print(json.dumps({"ok": True, "result": {key: state[key]}}))\n', encoding='utf-8')
        cli = repo / '.git' / ('fake-orca.cmd' if os.name == 'nt' else 'fake-orca')
        if os.name == 'nt':
            cli.write_text(f'@"{sys.executable}" "{fake}" %*\n', encoding='utf-8')
        else:
            cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n', encoding='utf-8')
            cli.chmod(0o755)
        os.environ.update({'FULLOPS_ORCA_CLI': str(cli), 'FAKE_ORCA_STATE': str(fake_state)})

        def scenario(messages, workers):
            fake_state.write_text(json.dumps({'messages': messages, 'workers': workers}), encoding='utf-8')

        live = [{'dispatchId': 'ctx_1', 'projection': {'outcome': None}}]
        done_rows = [{'dispatchId': 'ctx_1', 'projection': {'outcome': 'succeeded'}}]
        route('W-9', 'simple', 'dev')
        git('checkout', '-q', 'main')
        start = 'orca orchestration worker-start --run run_9 --spec "W-9 작업" --agent grok'
        assert hook('tool', session_id='wt', tool_name='Bash', tool_input={'command': start}) == {}
        scenario([], live)
        waiting = hook('stop', session_id='wt')
        assert waiting.get('decision') == 'block' and 'orca_wait.py' in waiting['reason'] and 'ctx_1' in waiting['reason'], waiting
        assert 'systemMessage' in hook('stop', session_id='wt', stop_hook_active=True)  # 같은 상태로 다시 끝내면 통과
        scenario([{'type': 'heartbeat'}, {'type': 'worker_done'}], done_rows)
        unread = hook('stop', session_id='wt')
        assert unread.get('decision') == 'block' and 'check --run run_9' in unread['reason'], unread
        scenario([{'type': 'heartbeat'}], done_rows)
        assert hook('stop', session_id='wt') == {}  # 결과를 받았고 실행 중인 worker가 없으면 통과
        os.environ['FULLOPS_ORCA_CLI'] = str(repo / '.git/missing-orca')
        scenario([], live)
        assert hook('stop', session_id='wt') == {}  # Orca를 확인할 수 없으면 막지 않는다
        del os.environ['FULLOPS_ORCA_CLI']

        # coordinator를 역할 워크트리에서 운영: 라우팅 기준의 coordinator 역할 줄로 판정한다
        agents = repo / '.fullops-squad/orca-agents.md'
        agents.write_text(agents.read_text(encoding='utf-8').replace('- 설계 역할: `architecture`',
                                                                      '- 설계 역할: `architecture`\n- coordinator 역할: `art`'), encoding='utf-8')
        git('checkout', '-q', '-B', roles['art'])
        assert 'jev_route.py' in hook('start', session_id='ca', source='startup')['hookSpecificOutput']['additionalContext']
        assert '분류한 과제 키' in denied(hook('tool', session_id='ca', tool_name='Bash', tool_input={
            'command': 'orca orchestration worker-start --run r1 --spec "K99 작업" --agent codex'}))
        board_data = repo / '.fullops-squad/board/board-data.js'
        board_data.unlink(missing_ok=True)
        assert hook('stop', session_id='ca') == {} and board_data.is_file()  # coordinator 역할 브랜치에서도 현황판 갱신
        git('checkout', '-q', roles['dev'])
        assert 'worker_done' in hook('start', session_id='wd', source='startup')['hookSpecificOutput']['additionalContext']

        (repo / '.fullops-squad/fullops.json').write_text('{', encoding='utf-8')
        assert hook('tool', session_id='w', tool_name='Bash', tool_input={'command': 'orca terminal send handovers/'}) == {}  # fail-open
    print('PASS: flow-gate roles, inject/run/route denials, handover route check, designer code block, worker_done stop gate, grok input')


if __name__ == '__main__':
    main()
