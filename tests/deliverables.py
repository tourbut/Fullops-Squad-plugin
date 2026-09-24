"""임시 레포에서 산출물 front matter의 --stamp 작성·인덱스 동기화·검사(--strict)와 lint DOC-002 관문을 확인한다."""
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
import deliverables  # noqa: E402


def main():
    today = date.today().isoformat()
    with tempfile.TemporaryDirectory(prefix='fullops-deliv-') as tmp:
        repo = Path(tmp)
        fo = repo / '.fullops-squad'

        def git(*args):
            return subprocess.check_output(['git', '-C', tmp, *args], text=True, encoding='utf-8').strip()

        def commit(message):
            git('add', '-A')
            git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', message)
            return git('rev-parse', 'HEAD')

        def cli(*args):
            return subprocess.run([sys.executable, str(SCRIPTS / 'deliverables.py'), '--repo', tmp, *args],
                                  capture_output=True, text=True, encoding='utf-8')

        git('init', '-q', '-b', 'main')
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp, '--roles', 'arch', 'dev', '--local-only'],
                       check=True, capture_output=True)
        base = commit('setup')

        # 처음 쓰는 front matter는 owner·summary가 필요하다
        missing = cli('--id', 'D03', '--stamp', '--task', 'T-1')
        assert missing.returncode == 1 and '--owner' in missing.stderr and '--summary' in missing.stderr, missing.stderr

        done = cli('--id', 'D03', '--stamp', '--task', 'T-1', '--owner', 'arch', '--summary', '점프 시스템 구조',
                   '--downstream', 'D05, D10')
        assert done.returncode == 0 and done.stdout.strip() == '.fullops-squad/docs/design-docs/architecture.md', done.stderr
        doc = fo / 'docs/design-docs/architecture.md'
        assert doc.read_text(encoding='utf-8') == (
            f'---\nid: D03\ntitle: 아키텍처설계서\nstatus: draft\nupdated: {today}\nowner: arch\ntasks: [T-1]\n'
            'downstream: [D05, D10]\nsummary: 점프 시스템 구조\n---\n\n# 아키텍처설계서\n'), doc.read_text(encoding='utf-8')
        index = (fo / 'docs/deliverables/README.md').read_text(encoding='utf-8')
        assert '| D03 | 설계 | 아키텍처설계서 | `docs/design-docs/architecture.md`, `docs/design-docs/tech-stack.md` | draft |' in index

        # 다시 쓰면 본문·기존 값을 보존하고 과제·상태·날짜만 바뀐다
        doc.write_text(doc.read_text(encoding='utf-8') + '\n## 구조\n\n본문\n', encoding='utf-8')
        assert cli('--id', 'D03', '--stamp', '--task', 'T-2', '--status', 'review').returncode == 0
        meta, body = deliverables.split(doc.read_text(encoding='utf-8'))
        assert (meta['tasks'], meta['status'], meta['owner'], meta['downstream']) == (['T-1', 'T-2'], 'review', 'arch', ['D05', 'D10'])
        assert '## 구조\n\n본문' in body and body.count('# 아키텍처설계서') == 1
        assert '| review |' in (fo / 'docs/deliverables/README.md').read_text(encoding='utf-8').split('| D03 |')[1].split('\n')[0]

        # 원천이 여러 파일이면 --path로 고르고, 원천이 아닌 경로는 거부한다
        assert cli('--id', 'D03', '--stamp', '--path', 'docs/design-docs/tech-stack.md', '--owner', 'arch',
                   '--summary', '기술 스택').returncode == 0
        assert '다름' not in cli('--id', 'D03', '--strict').stdout
        wrong = cli('--id', 'D03', '--stamp', '--path', 'docs/planning/business-plan.md', '--owner', 'a', '--summary', 'b')
        assert wrong.returncode == 1 and '원천 경로가 아닙니다' in wrong.stderr
        folder = cli('--id', 'D02', '--stamp', '--owner', 'arch', '--summary', 'x')
        assert folder.returncode == 1 and '--path' in folder.stderr  # D02 원천은 폴더

        # 검사: 손으로 고친 형식 차이는 경고, --strict면 오류
        assert deliverables.problems(doc.read_text(encoding='utf-8'), 'D03', 'review') == []
        hand = doc.read_text(encoding='utf-8').replace('owner: arch\n', 'owner: arch   # 담당\n')
        assert deliverables.problems(hand, 'D03', 'review') == ['정해진 형식과 다름(필드 순서·목록 표기·주석)']
        swapped = doc.read_text(encoding='utf-8').replace('status: review\nupdated', 'updated').replace('owner: arch', 'status: review\nowner: arch')
        assert deliverables.problems(swapped, 'D03', 'review') == ['정해진 형식과 다름(필드 순서·목록 표기·주석)']
        bad = deliverables.problems('---\nid: D04\nstatus: done\nupdated: 9/24\ntasks: T-1\n---\n', 'D03', 'review')
        assert set(bad) >= {'필수 필드 없음: title', 'id가 D03가 아님: D04', 'status는 draft/review/approved 중 하나: done',
                            'updated는 YYYY-MM-DD: 9/24', 'tasks는 [a, b] 목록'}, bad
        assert deliverables.problems('# 제목\n', 'D03') == ['front matter 없음']
        assert deliverables.problems(doc.read_text(encoding='utf-8'), 'D03', 'approved') == ['인덱스 상태(approved)와 문서 상태(review)가 다름']
        doc.write_text(hand, encoding='utf-8')
        loose, strict = cli('--id', 'D03'), cli('--id', 'D03', '--strict')
        assert loose.returncode == 0 and '경고: D03' in loose.stdout
        assert strict.returncode == 1 and '정해진 형식과 다름' in strict.stdout

        # lint DOC-002: 바뀐 원천 문서만 검사하고, --stamp로 다시 쓰면 통과한다
        commit('hand edit')
        lint_out = subprocess.run([sys.executable, str(SCRIPTS / 'lint.py'), '--repo', tmp, '--from', base,
                                   '--out', str(repo / 'lint.json')], capture_output=True, text=True, encoding='utf-8')
        report = json.loads((repo / 'lint.json').read_text(encoding='utf-8'))
        doc_errors = [v for v in report['violations'] if v['code'] == 'DOC-002']
        assert lint_out.returncode == 1 and len(doc_errors) == 1, (lint_out.stdout, doc_errors)
        assert doc_errors[0]['path'] == '.fullops-squad/docs/design-docs/architecture.md' and 'D03' in doc_errors[0]['message']
        (repo / 'lint.json').unlink()
        assert cli('--id', 'D03', '--stamp').returncode == 0
        commit('restamp')
        fixed = subprocess.run([sys.executable, str(SCRIPTS / 'lint.py'), '--repo', tmp, '--from', base, '--out', str(repo / 'lint.json')],
                               capture_output=True, text=True, encoding='utf-8')
        report = json.loads((repo / 'lint.json').read_text(encoding='utf-8'))
        assert not [v for v in report['violations'] if v['code'] == 'DOC-002'], report['violations']
        (repo / 'lint.json').unlink()
    print('PASS: deliverables stamp format/index sync/body keep/path guard, strict check, lint DOC-002 gate')


if __name__ == '__main__':
    main()
