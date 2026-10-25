"""탐색 패킷의 전달 범위·노이즈 필터·완료 검사, finish의 후속 등재, 끊긴 세션 recover를 임시 레포로 확인한다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import jev_packet
import work

KEY = 'DEMO-APP-1'


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-packet-') as tmp:
        repo = Path(tmp)

        def git(*args):
            return subprocess.check_output(['git', '-C', tmp, *args], text=True).strip()
        git('init', '-q', '-b', 'main')
        git('config', 'user.name', 'Test')
        git('config', 'user.email', 'test@example.com')
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp, '--roles', 'dev', 'tester', '--local-only'],
                       check=True, capture_output=True)
        (repo / 'src').mkdir()
        (repo / 'src/app.py').write_text('"""DEMO widget app"""\ndef state():\n    return 1\n\n\ndef render_widget():\n    return state()\n', encoding='utf-8')
        (repo / 'src/view.py').write_text('"""view"""\nfrom app import render_widget\n', encoding='utf-8')
        for i in range(30):  # `state`는 레포 전체에 깔린 이름이다
            (repo / f'src/m{i}.py').write_text(f'"""module {i}"""\nstate = {i}\n', encoding='utf-8')
        (repo / 'artifacts').mkdir()
        (repo / 'artifacts/old.py').write_text('"""old artifact"""\nrender_widget()\n', encoding='utf-8')
        git('add', '.')
        git('commit', '-q', '-m', 'init')
        git('checkout', '-qb', 'fullops/dev')
        work.new(repo, 'dev', KEY, 'DEMO 위젯 렌더를 고친다')
        inbox = repo / '.fullops-squad/handovers/to_dev.md'

        result, output = jev_packet.build(repo, 'dev', KEY, seeds=['src/app.py'], write_inbox=True)
        paths = {i['path']: i for i in result['items']}
        assert 'direct_edit' in paths['src/app.py']['categories']
        assert 'artifacts/old.py' not in paths, 'artifacts/는 문자열 검색 대상이 아니다'
        assert 'src/view.py' in paths and any(e.get('symbol') == 'render_widget' for e in paths['src/view.py']['evidence'])
        assert 'state' in result['ubiquitous_terms'] and not any(  # seed 정의 근거만 남고 문자열 일치는 없다
            e.get('symbol') == 'state' and e.get('method') == 'string-search' for i in result['items'] for e in i['evidence'])
        assert not any(e.get('symbol') == 'DEMO' for i in result['items'] for e in i['evidence']), '과제 키 조각은 검색어가 아니다'
        assert '.fullops-squad/handovers/to_dev.md' not in result['required_paths']
        shown = jev_packet.delivered(result)
        block = inbox.read_text(encoding='utf-8').split('<!-- fullops-packet:start -->')[1].split('<!-- fullops-packet:end -->')[0]
        assert block.count('\n- `') == len(shown) and '나머지 참조 후보' in block
        assert len(shown) <= len(result['required_paths']) + 20 + len(result['categories']['direct_edit']) + len(result['categories']['document_update'])

        # 끊긴 세션 복구: 미커밋 변경을 WIP 커밋으로 보존하고 기본 브랜치를 merge한 뒤 패킷을 다시 만든다.
        git('add', '.')
        git('commit', '-q', '-m', 'dispatch')
        git('checkout', '-q', 'main')
        (repo / 'README.md').write_text('base moved\n', encoding='utf-8')
        git('add', 'README.md')
        git('commit', '-q', '-m', 'main moves')
        git('checkout', '-q', 'fullops/dev')
        (repo / 'src/app.py').write_text((repo / 'src/app.py').read_text(encoding='utf-8') + '\n\ndef extra():\n    return 2\n', encoding='utf-8')
        work.recover(repo, 'dev', KEY)
        assert git('log', '-1', '--format=%s', 'HEAD^1').startswith('wip(dev): DEMO-APP-1'), git('log', '--oneline', '-3')
        assert git('merge-base', '--is-ancestor', 'main', 'HEAD') == ''
        result = json.loads(output.read_text(encoding='utf-8'))
        assert result['head'] == git('rev-parse', 'HEAD') and 'src/app.py' in result['options']['seeds']
        assert '<!-- fullops-packet:start -->' in inbox.read_text(encoding='utf-8')

        # 완료 검사는 지시서에 실린 항목만 요구한다.
        outcomes = jev_packet.result_path(repo, KEY, 'packet-outcomes')
        rows = [{'path': i['path'], 'category': c, 'status': 'completed', 'reason': '읽고 반영했다'}
                for i in jev_packet.delivered(result) for c in i['categories']]
        data = {'packet_input_sha256': result['input_sha256'], 'attempt': result['attempt'], 'items': rows, 'uncertainty_review': '미확인 후보 확인'}
        outcomes.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        text = inbox.read_text(encoding='utf-8')
        jev_packet.check(repo, 'dev', KEY, completion=True, text=text)
        outcomes.write_text(json.dumps({**data, 'items': rows[1:]}, ensure_ascii=False), encoding='utf-8')
        try:
            jev_packet.check(repo, 'dev', KEY, completion=True, text=text)
        except ValueError as error:
            assert 'incomplete' in str(error)
        else:
            raise AssertionError('전달 항목 누락을 통과시킴')
        outcomes.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        edited = text.replace('status: draft', 'status: done', 1)
        assert edited != text
        try:  # 어느 값이 다른지 말한다(#94)
            jev_packet.check(repo, 'dev', KEY, completion=True, text=edited)
        except ValueError as error:
            assert 'packet instruction identity differs' in str(error) and 'status' in str(error), error
        else:
            raise AssertionError('지시서 변경을 통과시킴')

        # finish는 완료 보고의 `남은 일`에서 다른 역할 요청을 PLANS.md에 등재한다.
        inbox.write_text(text.partition('## 완료 보고\n')[0] + '## 완료 보고\n브랜치 fullops/dev / SHA ' + result['head'][:12]
                         + '\n검증: 통과.\n남은 일: coor 병합, tester 독립 QA(시나리오 S1), 문서 정리\n', encoding='utf-8')
        work.finish(repo, 'dev', KEY)
        plans = (repo / '.fullops-squad/PLANS.md').read_text(encoding='utf-8')
        assert work.FOLLOWUPS in plans and f'- [ ] {KEY} → tester: tester 독립 QA(시나리오 S1) (완료 보고 자동 등재' in plans, plans
        assert '문서 정리' not in plans and plans.count(KEY) == 1
        work.queue_followups(repo, work.followups(repo, 'dev', KEY, '남은 일: tester 독립 QA(시나리오 S1)'))
        guide = work.TEMPLATE.read_text(encoding='utf-8').partition('## 완료 보고\n')[2]
        assert work.followups(repo, 'dev', KEY, guide) == [], '남겨 둔 템플릿 안내 문장은 후속 요청이 아니다'
        assert len(work.followups(repo, 'dev', KEY, guide + '\n- **남은 일**: tester 회귀 확인\n')) == 1
        assert (repo / '.fullops-squad/PLANS.md').read_text(encoding='utf-8').count('시나리오 S1') == 1, '같은 요청은 한 번만 등재한다'
    print('PASS: delivered subset, noise filters, recover, completion contract, followup queue')


if __name__ == '__main__':
    main()
