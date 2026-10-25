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

        def hook(mode, native_env=None, **event):
            event.setdefault('cwd', tmp)
            done = subprocess.run([sys.executable, str(SCRIPTS / 'flow_gate.py'), mode], text=True, capture_output=True,
                                  input=json.dumps(event), encoding='utf-8', env={**os.environ, **(native_env or {})})
            assert done.returncode == 0, done.stderr
            return json.loads(done.stdout)

        def denied(output):
            return output.get('hookSpecificOutput', {}).get('permissionDecisionReason', '')

        def route(key, kind, role):
            path = repo / f'.fullops-squad/docs/evaluations/jev/{key}-route.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'version': 'jev-route-v3', 'task_key': key, 'route': kind, 'role': role}), encoding='utf-8')

        git('init', '-q', '-b', 'main')
        assert hook('start', session_id='x') == {}  # FullOps가 아닌 레포
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp,
                        '--roles', 'architecture', 'dev', 'art', '--local-only'], check=True, capture_output=True)
        git('add', '-A')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'setup')
        roles = json.loads((repo / '.fullops-squad/fullops.json').read_text(encoding='utf-8'))['roles']

        # 현황판: coordinator가 PLANS.md만 바꾸고 board.json을 그대로 두면 한 번 확인을 요청한다
        plans, phases = repo / '.fullops-squad/PLANS.md', repo / '.fullops-squad/board/board.json'
        assert hook('stop', session_id='b') == {}  # 첫 종료는 기준만 기억한다
        receipt = json.loads((repo / '.git/fullops-gate/hooks/flow-b.json').read_text())
        assert receipt['status'] == receipt['events']['stop']['status'] == 'executed'
        plans.write_text(plans.read_text(encoding='utf-8') + '\n- 진행 기록\n', encoding='utf-8')
        assert 'board.json' in hook('stop', session_id='b')['reason']
        assert hook('stop', session_id='b', stop_hook_active=True) == {}  # 두 번째는 통과
        assert hook('stop', session_id='b') == {}  # 같은 내용으로 다시 묻지 않는다
        plans.write_text(plans.read_text(encoding='utf-8') + '- 또 기록\n', encoding='utf-8')
        phases.write_text(phases.read_text(encoding='utf-8') + '\n', encoding='utf-8')
        assert hook('stop', session_id='b') == {}  # board.json도 고쳤으면 묻지 않는다
        git('checkout', '-q', '--', '.fullops-squad/PLANS.md', '.fullops-squad/board/board.json')

        # coordinator (역할 브랜치가 아닌 main)
        assert 'jev_route.py' in hook('start', session_id='c', source='startup')['hookSpecificOutput']['additionalContext']
        # 이전 세션의 열린 사용자 결정을 새 coordinator 세션이 이어받고, 닫힌 결정은 빠진다
        sys.path.insert(0, str(SCRIPTS))
        import decision
        asked = decision.add(repo, 'Postgres로 바꿀까요?', key='K9', options=['예', '아니오'])
        started = hook('start', session_id='c2', source='startup')['hookSpecificOutput']['additionalContext']
        assert f"{asked['id']}(K9): Postgres로 바꿀까요? [예 / 아니오]" in started and '사용자 결정 대기 1건' in started
        decision.close(repo, asked['id'], 'answered', answer='예', decided_by='user')
        assert '사용자 결정 대기' not in hook('start', session_id='c3', source='startup')['hookSpecificOutput']['additionalContext']
        native_env = {'ORCA_TERMINAL_HANDLE': 'term-native-test'}
        for host_session in ('native-first', 'native-next'):
            hook('start', native_env=native_env, session_id=host_session)
            receipt = json.loads((repo / f'.git/fullops-gate/flow-{host_session}.json').read_text())
            binding = json.loads((repo / '.git/fullops-gate/flow-terminal-term-native-test.json').read_text())
            assert receipt['provider_session'] == binding['provider_session'] == host_session
            assert receipt['orca_terminal'] == binding['orca_terminal'] == native_env['ORCA_TERMINAL_HANDLE']
        devtree = repo / '.git/dev-worktree'
        git('worktree', 'add', '-q', '-b', roles['dev'], str(devtree))
        bash = lambda command, **kw: hook('tool', session_id='c', tool_name='Bash',
            tool_input={'command': command + f' --worktree \"{devtree}\"' if 'worker-start' in command else command}, **kw)
        assert 'worker-start' in denied(bash('orca terminal send --terminal t1 --text "handovers/to_dev.md 읽고 착수"'))
        assert '새 세션' in denied(bash('orca terminal send --terminal t1 --text "F 버튼 겹침을 다시 판단하고 설계를 고쳐 커밋해"'))  # 경로 없는 지시도 막는다
        assert bash('orca terminal send --terminal t1 --text "y"') == {}  # 확인 프롬프트 응답은 허용
        assert bash('orca terminal send --terminal t1 --key Enter') == {}
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
        assert bash('orca orchestration worker-start --help') == {}  # 사용법 확인은 막지 않는다
        assert bash('orca orchestration task-create -h') == {}
        (repo / '.fullops-squad/handovers/to_dev.md').write_text(
            '---\ntitle: K1 지시서\nsummary: 점프 수치를 바꾼다\n---\n\n# K1 — 점프 수치\n', encoding='utf-8')
        for ref in ('.fullops-squad/handovers/to_dev.md', f'{tmp}/.fullops-squad/handovers/to_dev.md'.replace('\\', '/')):
            assert bash(f'orca orchestration worker-start --run r1 --spec "지시서 {ref}를 읽고 착수" --agent codex') == {}, ref
        (repo / '.fullops-squad/handovers/to_dev.md').write_text('', encoding='utf-8')
        del os.environ['FULLOPS_ORCA_CLI']
        route('K3', 'design', 'architecture')
        assert '설계 역할' in denied(write('.fullops-squad/handovers/to_dev.md', '# K3 — 저장 형식\n'))
        assert write('.fullops-squad/handovers/to_architecture.md', '# K3 — 저장 형식\n') == {}
        assert '설계 역할' in denied(bash('python3 work.py new --repo . --role dev --key K3 --goal x'))
        assert bash('python3 work.py new --repo . --role dev --key K1 --goal x') == {}
        assert bash('K=K1; python3 work.py new --repo . --role dev --key $K --goal x') == {}  # 같은 명령에서 대입한 셸 변수
        assert '문자 그대로' in denied(bash('python3 work.py new --repo . --role dev --key $K --goal x'))
        grok = hook('tool', sessionId='c', toolName='search_replace',  # grok camelCase 입력
                    toolInput={'file_path': '.fullops-squad/handovers/to_dev.md', 'content': '# K3 — 저장 형식\n'})
        assert '설계 역할' in denied(grok)

        git('worktree', 'remove', str(devtree))
        # 설계 역할
        git('checkout', '-q', '-B', roles['architecture'])
        assert '코드는 고치지 않는다' in hook('start', session_id='a', source='startup')['hookSpecificOutput']['additionalContext']
        assert '코드를 고치지' in denied(hook('tool', session_id='a', tool_name='Write',
                                            tool_input={'file_path': f'{tmp}/src/save.py', 'content': 'x = 1\n'}))
        patch = '*** Begin Patch\n*** Update File: src/save.ts\n@@\n-a\n+b\n*** End Patch\n'
        assert '코드를 고치지' in denied(hook('tool', session_id='a', tool_name='apply_patch', tool_input={'command': patch}))
        assert hook('tool', session_id='a', tool_name='Write',
                    tool_input={'file_path': '.fullops-squad/handovers/to_dev.md', 'content': '# K3 — 저장 형식\n'}) == {}

        # tester 역할로 지정한 역할만 검증 도구 안내를 받는다
        git('checkout', '-q', '-B', roles['art'])
        assert 'fullops-test' not in hook('start', session_id='t0', source='startup')['hookSpecificOutput']['additionalContext']
        agents_md = repo / '.fullops-squad/orca-agents.md'
        plain = agents_md.read_text(encoding='utf-8')
        marked = plain.replace('- 설계 역할: `architecture`', '- 설계 역할: `architecture`\n- tester 역할: `art`')
        agents_md.write_text(marked, encoding='utf-8')
        assert 'fullops-test' in hook('start', session_id='t', source='startup')['hookSpecificOutput']['additionalContext']
        agents_md.write_text(plain, encoding='utf-8')

        # dispatched worker
        git('checkout', '-q', '-B', roles['dev'])
        assert 'worker_done' in hook('start', session_id='w', source='startup',
                                   native_env={'ORCA_TERMINAL_HANDLE': 'term-worker'})['hookSpecificOutput']['additionalContext']
        assert hook('stop', session_id='w') == {}  # preamble 없는 세션은 막지 않는다
        preamble = 'Task t-1 ... orca orchestration send --type worker_done --task-id t-1 --dispatch-id d-1 ...'
        assert hook('prompt', session_id='w', prompt=preamble) == {}
        native = json.loads((repo / '.git/fullops-gate/flow-w.json').read_text())
        assert native['provider_session'] == 'w' and native['orca_terminal'] == 'term-worker'
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
        assert hook('stop', sessionId='g')['decision'] == 'block'  # 전송 전에는 settlement하지 않는다
        hook('post', sessionId='g', toolName='run_terminal_command', toolInput={'command':
             'orca orchestration send --from w --type worker_done --task-id t-1 --dispatch-id d-1 --outcome succeeded'},
             toolResponse={'exit_code': 0, 'stdout': json.dumps({'ok': True, 'result': {'message': {'id': 'msg1'}}})})
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
        git('worktree', 'add', '-q', str(devtree), roles['dev'])
        start = f'orca orchestration worker-start --run run_9 --spec "W-9 작업" --agent grok --worktree "{devtree}"'
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

        git('worktree', 'remove', str(devtree))
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

        # Windows의 PowerShell 도구도 셸 hook을 거친다(빠지면 모든 셸 차단이 우회된다)
        hooks = json.loads((SCRIPTS.parent / 'hooks/hooks.json').read_text(encoding='utf-8'))['hooks']
        assert all('PowerShell' in group['matcher'].split('|') for event in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure') for group in hooks[event])
        # 검증 증거: 보고서가 링크하지 않은 qa-reports 캡처의 커밋과 같은 과제의 차수 폴더를 막는다
        reports = repo / '.fullops-squad/docs/evaluations/qa-reports'
        task = reports / 'K1-DEV-test'
        (task / 'raw').mkdir(parents=True)
        (task / 'report.md').write_text('# K1\n\n| 항목 | 근거 |\n|---|---|\n| 화면 | ![](shots/a.png) |\n', encoding='utf-8')
        (task / 'shots').mkdir()
        for name in ('shots/a.png', 'shots/b.png', 'shots/c.png', 'raw/d.png'):
            (task / name).write_bytes(b'png')
        git('add', str(task / 'report.md'), str(task / 'shots/a.png'), str(task / 'shots/b.png'))
        commit = denied(hook('tool', session_id='ev', tool_name='Bash', tool_input={'command': 'git commit -m "K1 증거"'}))
        assert 'shots/b.png' in commit and 'shots/a.png' not in commit and 'c.png' not in commit and 'raw/' in commit, commit
        broad = denied(hook('tool', session_id='ev', tool_name='PowerShell', tool_input={'command': 'git add -A; git commit -m x'}))
        assert 'c.png' in broad and 'd.png' not in broad, broad  # 같은 명령의 넓은 add도 본다. raw/는 gitignore
        (task / 'report.md').write_text('# K1\n\n![](shots/a.png) ![](shots/b.png) ![](shots/c.png)\n', encoding='utf-8')
        assert not denied(hook('tool', session_id='ev', tool_name='Bash', tool_input={'command': 'git add -A && git commit -m x'}))
        assert not denied(hook('tool', session_id='ev', tool_name='Bash', tool_input={'command': 'git status'}))
        round_path = str(reports / 'K1-DEV-FIX-test/report.md')
        assert 'K1-DEV-test/report.md' in denied(hook('tool', session_id='ev', tool_name='Write', tool_input={
            'file_path': round_path, 'content': '# K1 수정'}))
        assert 'K1-DEV-test' in denied(hook('tool', session_id='ev', toolName='apply_patch', toolInput={
            'command': f'*** Begin Patch\n*** Add File: {reports / "K1-DEV-R2-test/report.md"}\n+# K1\n*** End Patch'}))
        for fine in ('K1-DEV-test/report.md', 'K2-FIX-test/report.md', 'K1-DEV-test/web-1/report.md'):
            assert not denied(hook('tool', session_id='ev', tool_name='Write', tool_input={'file_path': str(reports / fine), 'content': '#'})), fine
        git('reset', '-q')
        # 테스트 레벨 lite: 지시서의 다중 폭·테마 캡처 요구와 긴 보고서는 쓴 직후 한 번 알린다(막지 않는다)
        inbox = repo / '.fullops-squad/handovers/to_dev.md'
        saved = inbox.read_bytes()
        inbox.write_text('# K1 — 화면\n\n- KO/EN을 1440·390·320px, 라이트·다크로 캡처해 보고에 연결한다.\n', encoding='utf-8')
        note = hook('post', session_id='ad', tool_name='Write', tool_input={'file_path': str(inbox)})
        assert '1440·390·320 폭' in note['hookSpecificOutput']['additionalContext'] and '라이트·다크' in note['hookSpecificOutput']['additionalContext']
        assert hook('post', session_id='ad', tool_name='Write', tool_input={'file_path': str(inbox)}) == {}  # 같은 지적은 한 번
        (task / 'report.md').write_text('\n'.join(['| 검사 | 통과 |'] * 45), encoding='utf-8')
        assert '45줄' in hook('post', session_id='ad', tool_name='Edit', tool_input={'file_path': str(task / 'report.md')})['hookSpecificOutput']['additionalContext']
        # 커밋하지 않는 raw/를 링크한 보고서는 레벨과 무관하게 쓴 직후 알린다(#94)
        (task / 'report.md').write_text('# K1\n\n![](shots/a.png) [로그](raw/d.png) [외부](https://x.test/raw/y)\n', encoding='utf-8')
        raw = hook('post', session_id='raw', tool_name='Write', tool_input={'file_path': str(task / 'report.md')})['hookSpecificOutput']['additionalContext']
        assert 'raw/d.png' in raw and 'shots/a.png' not in raw and 'x.test' not in raw, raw
        inbox.write_bytes(saved)
        # 반복 예산(docs/flow-graph.md E15): 같은 과제의 재오픈·차수 키가 2회를 넘으면 coordinator에게 한 번 알린다
        git('checkout', '-q', 'main')
        logs = repo / '.fullops-squad/handovers/logs/2026-10-01_to_dev.md'
        logs.parent.mkdir(parents=True, exist_ok=True)
        logs.write_text('## K9 — 2026-10-01\n<!-- fullops-attempt: K9 a1 -->\n\n## K9 — 2026-10-02\n<!-- fullops-attempt: K9 a2 -->\n'
                        '## K10 — 2026-10-02\n<!-- fullops-attempt: K10 b1 -->\n', encoding='utf-8')
        inbox.write_text('---\nattempt: a3\n---\n# K9 — 수정\n', encoding='utf-8')
        reopen = {'command': 'python3 work.py reopen --repo . --role dev --key K9 --goal fix'}
        assert hook('post', session_id='rb', tool_name='Bash', tool_input=reopen) == {}  # 재오픈 2회는 예산 안
        for name in ('K9', 'K9-FIX'):
            review = reports / f'{name}-review'
            review.mkdir(parents=True, exist_ok=True)
            (review / 'result.json').write_text(json.dumps({'findings': [{'path': 'src/x.py', 'severity': 'high'}]}), encoding='utf-8')
        route('K9-FIX', 'simple', 'dev')
        route('K9-FIX-TESTER', 'simple', 'dev')  # 같은 차수를 역할로 나눈 키는 한 번만 센다
        routed = {'command': 'python3 jev_route.py --repo . --key K9-FIX --text fix'}
        note = hook('post', session_id='rb', tool_name='Bash', tool_input=routed)['hookSpecificOutput']['additionalContext']
        assert 'K9의 수정·재검증이 3회째' in note and '차수 FIX)' in note and 'src/x.py(2회)' in note, note
        assert hook('post', session_id='rb', tool_name='Bash', tool_input=routed) == {}  # 같은 권고는 한 번
        inbox.write_text('---\nattempt: a3\n---\n# K9 — 수정\n\n- 반복 예산: 3\n', encoding='utf-8')
        assert hook('post', session_id='rb2', tool_name='Bash', tool_input=routed) == {}  # 지시서 예산이 우선
        assert hook('post', session_id='rb3', tool_name='Bash', tool_input={'command': 'python3 jev_route.py --key K11'}) == {}
        inbox.write_bytes(saved)
        git('checkout', '-q', roles['dev'])

        (repo / '.fullops-squad/fullops.json').write_text('{', encoding='utf-8')
        assert hook('tool', session_id='w', tool_name='Bash', tool_input={'command': 'orca terminal send handovers/'})['hookSpecificOutput']['permissionDecision'] == 'deny'
    print('PASS: flow-gate roles, inject/run/route denials, handover route check, designer code block, worker_done stop gate, grok input')


if __name__ == '__main__':
    main()
