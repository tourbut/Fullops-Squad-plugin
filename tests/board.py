"""임시 레포에서 현황판 데이터 수집·JS 출력·변경 없을 때 재작성 생략·coordinator Stop hook 자동 갱신·git 무시를 확인한다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'


def data(repo):
    text = (repo / '.fullops-squad/board/board-data.js').read_text(encoding='utf-8')
    assert text.startswith('window.FULLOPS_BOARD = ') and text.rstrip().endswith(';')
    return json.loads(text[len('window.FULLOPS_BOARD = '):].rstrip().rstrip(';'))


def main():
    with tempfile.TemporaryDirectory(prefix='fullops-board-') as tmp:
        repo = Path(tmp)
        fo = repo / '.fullops-squad'

        def git(*args):
            return subprocess.check_output(['git', '-C', tmp, *args], text=True).strip()

        def run():
            done = subprocess.run([sys.executable, str(SCRIPTS / 'board.py'), '--repo', tmp],
                                  capture_output=True, text=True, encoding='utf-8')
            assert done.returncode == 0, done.stderr
            return done.stdout.strip()

        git('init', '-q', '-b', 'main')
        failed = subprocess.run([sys.executable, str(SCRIPTS / 'board.py'), '--repo', tmp], capture_output=True, text=True)
        assert failed.returncode == 1  # setup 전 레포
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp, '--roles', 'architecture', 'dev', 'art',
                        '--local-only'], check=True, capture_output=True)
        assert (fo / 'board/index.html').is_file() and (fo / 'board/board.json').is_file()
        git('add', '-A')
        git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'setup')

        assert run() == '.fullops-squad/board/board-data.js'
        empty = data(repo)
        assert [p['name'] for p in empty['phases']] == ['기획', '설계', '구현', 'QA', '이행']
        assert {r['role']: r['task'] for r in empty['roles']} == {'architecture': None, 'dev': None, 'art': None}
        assert len(empty['deliverables']) == 13 and empty['deliverables'][0]['id'] == 'D01'
        assert empty['branch'] == 'main' and empty['board_error'] is None
        assert empty['notes'] == []  # 템플릿 안내 문장은 요약으로 보이지 않는다

        # coordinator가 단계를 갱신하고 레포에 기록이 쌓인다
        (fo / 'board/board.json').write_text(json.dumps({'title': '점프 게임', 'phases': [
            {'name': '기획', 'status': 'done', 'deliverables': ['D01', 'D02']},
            {'name': '구현', 'status': 'active', 'note': '1차'},
            {'name': '출시 준비', 'status': 'weird'}]}, ensure_ascii=False), encoding='utf-8')
        subprocess.run([sys.executable, str(SCRIPTS / 'work.py'), 'new', '--repo', tmp, '--role', 'dev', '--key', 'JUMP-1',
                        '--goal', '점프 높이 조정'], check=True, capture_output=True)
        inbox = fo / 'handovers/to_dev.md'
        inbox.write_text(inbox.read_text(encoding='utf-8').replace('- 상태: ready / running / blocked', '- 상태: running'),
                         encoding='utf-8')
        (fo / 'handovers/logs').mkdir(parents=True, exist_ok=True)
        (fo / 'handovers/logs/2026-09-20_to_art.md').write_text(
            '\n## ART-1 — 2026-09-20\n\n# ART-1 — 캐릭터 교체\n\n본문\n\n## ART-2 — 2026-09-22\n\n# ART-2 — UI 아이콘\n', encoding='utf-8')
        (fo / 'docs/evaluations/jev').mkdir(parents=True, exist_ok=True)
        (fo / 'docs/evaluations/jev/JUMP-1-route.json').write_text(json.dumps({'route': 'simple', 'role': 'dev', 'deliverables': ['D03'],
            'model': {'agent': 'claude', 'model': 'claude-sonnet-5', 'effort': 'medium', 'source': 'jev', 'usage': {}}}), encoding='utf-8')
        (fo / 'docs/evaluations/jev/ART-9-model-art.json').write_text(json.dumps({'task_key': 'ART-9', 'role': 'art',
            'model': {'agent': 'codex', 'model': 'gpt-6-sol', 'effort': 'low', 'source': 'only'}}), encoding='utf-8')
        review = fo / 'docs/evaluations/qa-reports/ART-2-review'
        review.mkdir(parents=True)
        (review / 'result.json').write_text(json.dumps({'head': 'a' * 40, 'reviewer': 'coordinator', 'conclusion': '수락',
            'findings': [{'severity': 'high', 'resolved': True}, {'severity': 'critical', 'resolved': False},
                         {'severity': 'low', 'resolved': False}]}), encoding='utf-8')
        for folder_name, passed in (('web-20260924-101010', False), ('web-20260925-090000', True), ('unity-20260925-080000', False)):
            folder = fo / f'docs/evaluations/qa-reports/JUMP-1-test/{folder_name}'
            folder.mkdir(parents=True)
            scenario = 'scenarios/unity/jump.json' if folder_name.startswith('unity') else 'scenarios/web/login.json'
            (folder / 'result.json').write_text(json.dumps({'result': 'passed' if passed else 'stalled', 'passed': passed, 'steps': 4,
                'cost': 0.0002, 'scenario': scenario, 'covers': ['REQ-1']}), encoding='utf-8')
        (fo / 'docs/evaluations/qa-reports/JUMP-1-test/web-20260925-090000/report.md').write_text('# r', encoding='utf-8')
        (review / 'lint.json').write_text(json.dumps({'summary': {'errors': 0, 'warnings': 2}}), encoding='utf-8')
        index = fo / 'docs/deliverables/README.md'
        index.write_text(index.read_text(encoding='utf-8').replace('| D01 | 착수 | 사업계획서 | `docs/planning/business-plan.md` | 미작성 |',
                                                                  '| D01 | 착수 | 사업계획서 | `docs/planning/business-plan.md` | approved |'), encoding='utf-8')
        (fo / 'docs/planning').mkdir(parents=True, exist_ok=True)
        (fo / 'docs/planning/business-plan.md').write_text(
            '---\nid: D01\ntitle: 점프 게임 사업계획서\nstatus: review   # 재검토 중\nupdated: 2026-09-24\nowner: arch\n'
            'tasks: [JUMP-1, JUMP-2]\ndownstream: [D02, D03]\nsummary: 1차 빌드 범위와 일정\n---\n\n# 사업계획서\n', encoding='utf-8')
        plans = fo / 'PLANS.md'
        text = plans.read_text(encoding='utf-8').replace('# 현재 작업\n', '# 현재 작업\n\n최신 착수: **JUMP-1** [지시서](handovers/to_dev.md)\n', 1)
        plans.write_text(text + '| JUMP-1 | 점프 높이 조정 | dev | 진행 중 | handovers/to_dev.md |\n'
                         '\n## 후속 — 2026-09-24\n\n| 과제 키 | 다음 확인 | 예정 책임 | 상태 |\n|---|---|---|---|\n| ART-9 | 배경 교체 | art | 예정 |\n',
                         encoding='utf-8')

        run()
        full = data(repo)
        assert full['title'] == '점프 게임'
        assert [(p['name'], p['status']) for p in full['phases']] == [('기획', 'done'), ('구현', 'active'), ('출시 준비', 'todo')]
        dev = next(r for r in full['roles'] if r['role'] == 'dev')
        assert dev['task'] == {'key': 'JUMP-1', 'goal': '점프 높이 조정', 'status': 'running'}, dev
        assert [(e['key'], e['role']) for e in full['history']] == [('ART-2', 'art'), ('ART-1', 'art')]
        assert full['history'][0]['goal'] == 'UI 아이콘'
        assert full['routes'] == {'JUMP-1': {'route': 'simple', 'role': 'dev', 'deliverables': ['D03'],
            'model': {'agent': 'claude', 'provider': None, 'model': 'claude-sonnet-5', 'effort': 'medium', 'source': 'jev'}}}
        assert full['models'] == {'ART-9|art': {'agent': 'codex', 'provider': None, 'model': 'gpt-6-sol', 'effort': 'low', 'source': 'only'}}
        rv, = full['reviews']
        web_test, unity_test = full['tests']  # 과제·시나리오마다 최신 실행 하나
        assert (web_test['kind'], web_test['passed'], web_test['runs'], web_test['date']) == ('web', True, 2, '2026-09-25'), web_test
        assert web_test['report'].endswith('web-20260925-090000/report.md') and web_test['covers'] == ['REQ-1']
        assert (unity_test['kind'], unity_test['result'], unity_test['report']) == ('unity', 'stalled', '')
        assert (rv['key'], rv['blocking'], rv['findings'], rv['lint_errors'], rv['lint_warnings'], rv['head']) == ('ART-2', 1, 3, 0, 2, 'a' * 12)
        d01 = full['deliverables'][0]
        assert (d01['status'], d01['index_status'], d01['name'], d01['updated'], d01['owner'], d01['has_meta']) == (
            'review', 'approved', '점프 게임 사업계획서', '2026-09-24', 'arch', True), d01  # 문서가 표보다 우선
        assert d01['source_exists'] and not full['deliverables'][1]['source_exists'] and not full['deliverables'][1]['has_meta']
        sys.path.insert(0, str(SCRIPTS))
        import deliverables
        meta = deliverables.front_matter((fo / 'docs/planning/business-plan.md').read_text(encoding='utf-8'))
        assert meta['tasks'] == ['JUMP-1', 'JUMP-2'] and meta['status'] == 'review' and meta['summary'] == '1차 빌드 범위와 일정'
        assert deliverables.front_matter('---\nid: D01\n') is None and deliverables.front_matter('# 제목\n') is None
        checked = subprocess.run([sys.executable, str(SCRIPTS / 'deliverables.py'), '--repo', tmp, '--id', 'D01'],
                                 capture_output=True, text=True, encoding='utf-8')
        assert checked.returncode == 0 and '경고: D01 docs/planning/business-plan.md: 인덱스 상태(approved)와 문서 상태(review)가 다름' in checked.stdout, checked.stdout
        assert [(p['key'], p['goal'], p['owner'], p['status'], p['group']) for p in full['plans']] == [
            ('ART-9', '배경 교체', 'art', '예정', '후속 — 2026-09-24'), ('JUMP-1', '점프 높이 조정', 'dev', '진행 중', '현재 작업')]
        assert full['notes'] == ['최신 착수: JUMP-1 지시서']

        # 내용이 같으면 다시 쓰지 않는다
        output = fo / 'board/board-data.js'
        before = output.stat().st_mtime_ns
        run()
        assert output.stat().st_mtime_ns == before

        # 깨진 board.json은 오류를 표시하고 나머지는 계속 보여 준다
        (fo / 'board/board.json').write_text('{', encoding='utf-8')
        run()
        broken = data(repo)
        assert broken['board_error'] and broken['phases'] == [] and broken['roles']

        # coordinator Stop hook이 자동 갱신하고, 생성 파일은 git이 무시한다
        output.unlink()
        hook = subprocess.run([sys.executable, str(SCRIPTS / 'flow_gate.py'), 'stop'], input=json.dumps(
            {'session_id': 'c', 'cwd': tmp}), capture_output=True, text=True, encoding='utf-8')
        assert hook.returncode == 0 and json.loads(hook.stdout) == {}
        assert output.is_file()
        assert 'board-data.js' not in git('status', '--porcelain', '--untracked-files=all')
        git('checkout', '-q', '-b', 'fullops/dev')
        output.unlink()
        subprocess.run([sys.executable, str(SCRIPTS / 'flow_gate.py'), 'stop'], input=json.dumps(
            {'session_id': 'w', 'cwd': tmp}), capture_output=True, text=True, encoding='utf-8')
        assert not output.exists()  # worker 브랜치에서는 만들지 않는다
    print('PASS: board collects phases/roles/plans/history/routes/reviews/deliverables, skips unchanged writes, '
          'shows board.json errors, refreshes on coordinator Stop, stays git-ignored')


if __name__ == '__main__':
    main()
