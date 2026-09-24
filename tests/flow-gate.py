"""임시 레포에서 flow-gate hook의 역할 판정·dispatch 차단·지시서 route 확인·설계 역할 코드 차단·worker_done 종료 게이트를 확인한다."""
import json
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
        assert 'route 기록' in denied(bash('orca orchestration worker-start --run r1 --spec "K1 작업" --agent codex'))
        route('K1', 'simple', 'dev')
        assert bash('orca orchestration worker-start --run r1 --spec "K1 작업" --agent codex') == {}
        assert 'route 기록' in denied(bash('orca orchestration worker-start --run r1 --spec "K10 작업" --agent codex'))

        write = lambda path, content, **kw: hook('tool', session_id='c', tool_name='Write',
                                                  tool_input={'file_path': path, 'content': content}, **kw)
        assert write(f'{tmp}/.fullops-squad/handovers/to_dev.md', '# K1 — 점프 수치\n') == {}
        assert '설계 역할' in denied(write(f'{tmp}/.fullops-squad/handovers/to_art.md', '# K1 — 점프 수치\n'))
        assert 'route 기록' in denied(write('.fullops-squad/handovers/to_dev.md', '# K2 — 없음\n'))
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
        # coordinator를 역할 워크트리에서 운영: 라우팅 기준의 coordinator 역할 줄로 판정한다
        agents = repo / '.fullops-squad/orca-agents.md'
        agents.write_text(agents.read_text(encoding='utf-8').replace('- 설계 역할: `architecture`',
                                                                      '- 설계 역할: `architecture`\n- coordinator 역할: `art`'), encoding='utf-8')
        git('checkout', '-q', '-B', roles['art'])
        assert 'jev_route.py' in hook('start', session_id='ca', source='startup')['hookSpecificOutput']['additionalContext']
        assert 'route 기록' in denied(hook('tool', session_id='ca', tool_name='Bash', tool_input={
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
