"""현재 지시서는 역할 인박스 하나를 쓰고, 완료 후 로그 보존과 다음 과제 착수를 확인한다."""
import json
from datetime import date
from pathlib import Path
import subprocess
import sys
import tempfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import work


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-handover-') as tmp:
        repo = Path(tmp)
        subprocess.run(['git', 'init', '-q', '-b', 'main', tmp], check=True)
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp,
                        '--roles', 'architecture', 'dev', '--local-only'], check=True, capture_output=True)
        work.new(repo, 'dev', 'K1', '현재 작업')
        inbox = repo / '.fullops-squad/handovers/to_dev.md'
        original = inbox.read_bytes()
        side = repo / '.fullops-squad/handovers/K2.md'
        side.write_text('# K2 — 별도 과제\n', encoding='utf-8')
        try:
            work.instruction(repo, 'dev', 'K2', '.fullops-squad/handovers/K2.md')
        except ValueError as error:
            assert '역할 인박스' in str(error)
        else:
            raise AssertionError('과제명 파일을 현재 지시서로 허용함')
        assert work.instruction(repo, 'dev', 'K1', '.fullops-squad/handovers/to_dev.md')[0] == inbox

        def hook(tool):
            output = subprocess.check_output([sys.executable, str(SCRIPTS / 'flow_gate.py'), 'tool'],
                input=json.dumps({'cwd': tmp, 'session_id': 'rules', 'tool_input': tool}), text=True)
            return json.loads(output).get('hookSpecificOutput', {}).get('permissionDecisionReason', '')

        assert '역할 인박스' in hook({'file_path': str(side), 'content': '# K2 — 별도 과제\n'})
        assert '진행 중' in hook({'file_path': str(inbox), 'content': '# K2 — 새 과제\n'})
        assert 'work.py finish' in hook({'file_path': str(inbox), 'content': ''})
        assert inbox.read_bytes() == original
        patch = '*** Begin Patch\n*** Add File: .fullops-squad/handovers/K3.md\n+# K3 — 별도 과제\n*** End Patch\n'
        assert '역할 인박스' in hook({'command': patch})
        move = ('*** Begin Patch\n*** Update File: .fullops-squad/handovers/to_dev.md\n'
                '*** Move to: .fullops-squad/handovers/K1.md\n@@\n-a\n+b\n*** End Patch\n')
        assert '역할 인박스' in hook({'command': move})
        archive = move.replace('Update File: .fullops-squad/handovers/to_dev.md',
                               'Update File: .fullops-squad/handovers/K1.md').replace(
                               'Move to: .fullops-squad/handovers/K1.md',
                               'Move to: .fullops-squad/handovers/logs/K1.md')
        assert not hook({'command': archive})
        assert not hook({'file_path': '.fullops-squad/handovers/pending/K2.md', 'content': '# K2 — 대기 자료\n'})
        assert not hook({'file_path': '.fullops-squad/handovers/logs/K0.md', 'content': '# K0 — 이전 기록\n'})
        assert not hook({'command': 'python3 work.py new --help'})
        command = 'orca orchestration worker-start --run r1 --spec "K2 .fullops-squad/handovers/K2.md"'
        assert '역할 인박스' in hook({'command': command})
        assert '역할 인박스' in hook({'command': command.replace('handovers/K2.md', 'handovers/pending/K2.md')})
        # 설계 역할도 과제명 파일을 생성하지 않는다.
        subprocess.run(['git', '-C', tmp, 'checkout', '-qb', 'fullops/architecture'], check=True)
        assert '역할 인박스' in hook({'file_path': str(side), 'content': '# K2 — 별도 과제\n'})

        # 현재 과제의 후속은 같은 인박스를 고친다. 완료 후 전문을 보존하고 다음 과제를 만든다.
        route = repo / '.fullops-squad/docs/evaluations/jev/K1-route.json'
        route.parent.mkdir(parents=True, exist_ok=True)
        route.write_text(json.dumps({'route': 'simple', 'role': 'dev'}))
        assert not hook({'file_path': str(inbox), 'content': '# K1 — 같은 과제 후속\n'})
        remove_line = ('*** Begin Patch\n*** Update File: .fullops-squad/handovers/to_dev.md\n'
                       '@@\n-이전 후속 설명\n*** End Patch\n')
        assert not hook({'command': remove_line})  # 일부 줄 삭제를 인박스 전체 비우기로 오인하지 않는다.
        inbox.write_text(inbox.read_text(encoding='utf-8').partition('## 완료 보고\n')[0]
                         + '## 완료 보고\n현재 작업 완료. 검증 통과.\n', encoding='utf-8')
        finished = inbox.read_text(encoding='utf-8')
        work.finish(repo, 'dev', 'K1')
        assert inbox.read_bytes() == b''
        log = repo / f'.fullops-squad/handovers/logs/{date.today()}_to_dev.md'
        assert finished.rstrip() in log.read_text(encoding='utf-8')
        work.new(repo, 'dev', 'K2', '다음 작업')
        assert '# K2 — 다음 작업' in inbox.read_text(encoding='utf-8')
    print('PASS: canonical inbox, alternate file/dispatch denials, active task preservation, archive then next task')


if __name__ == '__main__':
    main()
