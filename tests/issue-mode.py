"""격리 Git 저장소에서 이슈 수집→동일 coor claim→질문→답변→새 attempt와 안전 경계를 검증한다."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/fullops-squad/scripts'))
import issue_mode as mode
from issue_github import APIError, GitHub, SafeRedirect, iso
import urllib.request
import urllib.error


def fails(call, text=''):
    try:
        call()
    except (ValueError, APIError) as error:
        assert text in str(error), (text, str(error))
    else:
        raise AssertionError('fail-closed 검사가 통과했습니다')


class API:
    def __init__(self):
        self.issues, self.comments, self.posts, self.fail_post = [], [], 0, False
        self.failure = None
        self.allow_push = True
        self.checks, self.reviews = [], []

    def get(self, path):
        if '/check-runs' in path:
            return {'check_runs': deepcopy(self.checks)}
        if '/reviews' in path:
            return deepcopy(self.reviews)
        if path.startswith('/repos/') and '/pulls/' not in path:
            return {'id': 7, 'full_name': path.removeprefix('/repos/'), 'permissions': {'push': self.allow_push}}
        if '/pulls/' in path:
            return self.pr
        return {'id': 42, 'login': 'author', 'type': 'User'}

    def pages(self, path, cache):
        if self.failure:
            raise self.failure
        return deepcopy(self.comments if '/comments?' in path else self.issues), dict(cache)

    def issue(self, repository, number):
        return deepcopy(next(i for i in self.issues if i['number'] == number))

    def comment(self, repository, number, body):
        self.posts += 1
        result = {'id': 900 + self.posts, 'body': body, 'user': {'id': 42, 'login': 'author'},
                  'created_at': iso(time.time()), 'updated_at': iso(time.time()), 'html_url': 'https://github.com/comment'}
        self.comments.append(result)
        if self.fail_post:
            raise APIError('lost response')
        return result


class Orca:
    executable = 'orca'

    def identity(self, *args):
        return 'incarnation'


def orca_answers(caller, pane, run='run'):
    """Orca 1.4.251처럼 run은 --full일 때만 준다. 기본 응답은 runId뿐이다."""
    def call(*args):
        if args[0] == 'status':
            return caller
        if args[0] == 'terminal':
            return pane
        return {'run': {'id': run}} if '--full' in args else {'runId': run, 'objective': 'x'}
    return call


def issue(number, author=42, **changes):
    return {'id': 100 + number, 'repository_id': 7, 'number': number,
            'title': 'work ' + str(number), 'body': 'requirement', 'created_at': iso(time.time()),
            'updated_at': iso(time.time()), 'state': 'open', 'html_url': f'https://github.com/owner/service/issues/{number}',
            'user': {'id': author, 'login': 'author'}, 'edit_verified': True, **changes}


def repository(root):
    """origin remote와 FullOps git 설정이 있는 격리 저장소. 없는 폴더는 git init이 만든다."""
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), 'remote', 'add', 'origin', 'https://github.com/owner/service.git'], check=True)
    (root / '.fullops-squad').mkdir()
    (root / '.fullops-squad/fullops.json').write_text(json.dumps({'git': {'remote': 'origin', 'base': 'main'}}))
    return root


def handover():
    """인계 뒤 fencing, 잠금 밖 GitHub 조회, 시작되지 않은 dispatch intent, 무관한 worker의 Orca 조회."""
    with tempfile.TemporaryDirectory(prefix='fullops-issue-') as temporary:
        root = repository(Path(temporary))
        store, api = mode.Store(root), API()
        mode.configure(store, api, 'owner/service', ['author'], interval=60, approved=True)
        for session in ('first', 'second', 'third'):
            receipt = mode.hook_path(root, session)
            receipt.parent.mkdir(exist_ok=True)
            receipt.write_text(json.dumps({'provider_session': session}))
        token = mode.activate(store, Orca(), 'coor', 'run', 'term', 'first')['token']
        api.issues = [issue(1), issue(2)]
        mode.poll(store, api, token)
        assert mode.claim(store, api, token)['issue_id'] == '101'
        mode.checkpoint(store, api, token, 101, 'running', received=True)
        post = api.comment

        def set_status(identifier, status):
            with store.edit() as state:
                state['jobs'][identifier]['status'] = status

        def unlocked(call):
            def wrapped(*args, **kwargs):  # GitHub 응답을 기다리는 동안 hook이 쓸 수 있어야 한다.
                db = sqlite3.connect(store.path, timeout=0)
                try:
                    db.execute('BEGIN IMMEDIATE')
                finally:
                    db.close()
                return call(*args, **kwargs)
            return wrapped

        # 게시 직전 조회 중 취소되면 예전 판단으로 게시하지 않는다.
        def cancelled(path, cache):
            set_status('101', 'cancelled')
            return [], {}
        with patch.object(api, 'pages', side_effect=cancelled):
            fails(lambda: mode.question(store, api, token, 101, '크기는?'), '게시')
        assert api.posts == 0
        set_status('101', 'running')

        # 답변 확인 조회는 잠금 밖에서 하고, 조회 뒤 바뀐 상태를 덮어쓰지 않는다.
        mode.question(store, api, token, 101, '크기는?')
        api.comments.append({'id': 1001, 'body': '128px', 'user': {'id': 42, 'login': 'author'}, 'html_url': 'https://github.com/answer',
                             'created_at': iso(time.time()), 'updated_at': iso(time.time())})
        mode.poll_answers(store, api, token)
        assert mode.answer_delivery(store, token)['issue_id'] == '101'
        def edited(path, cache):
            set_status('101', 'changed')
            return deepcopy(api.comments), {}
        with patch.object(api, 'pages', side_effect=edited):
            fails(lambda: mode.resolve_answers(store, api, token, 101, 'sufficient', '규격 확정'), 'claimed')
        assert store.read()['jobs']['101']['status'] == 'changed'
        set_status('101', 'claimed')
        with patch.object(api, 'issue', side_effect=unlocked(api.issue)), patch.object(api, 'pages', side_effect=unlocked(api.pages)):
            assert mode.resolve_answers(store, api, token, 101, 'sufficient', '규격 확정') == 'queued'

        # 완료 직전 재확인도 잠금 밖에서 한다.
        assert mode.claim(store, api, token)['attempt'] == 2
        mode.checkpoint(store, api, token, 101, 'running', received=True)
        mode.checkpoint(store, api, token, 101, 'reviewing', received=True)
        subprocess.run(['git', '-C', str(root), 'add', '.fullops-squad'], check=True)
        subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'setup'], check=True)
        head = mode.integration.git(root, 'rev-parse', 'HEAD')
        api.pr = {'draft': True, 'state': 'open', 'merged': False, 'html_url': 'https://github.com/owner/service/pull/1',
                  'head': {'sha': head, 'ref': 'fullops/issue-1-a2', 'repo': {'id': 7}}, 'base': {'ref': 'main', 'repo': {'id': 7}}}
        rechecks = []
        real_issue = api.issue
        def flip(*args):
            rechecks.append(args)
            if len(rechecks) == 2:
                set_status('101', 'changed')
            return real_issue(*args)
        with patch('review.check'):
            with patch.object(api, 'issue', side_effect=flip):
                fails(lambda: mode.complete(store, api, token, 101, root, 'key', head, head, 1), 'attempt')
            assert store.read()['jobs']['101']['status'] == 'changed'
            set_status('101', 'reviewing')
        # 수락 후 snapshot까지 정리한 리뷰는 live 검사 대신 보존 증거·SHA·규칙으로 완료한다.
        import review
        folder = root / '.fullops-squad/docs/evaluations/qa-reports/cleaned-review'
        folder.mkdir(parents=True)
        rule = root / '.fullops-squad/review/rule.json'
        rule.parent.mkdir(parents=True, exist_ok=True)
        rule.write_text('{}')
        independence = {'implementer_session': 'a', 'reviewer_session': 'b'}
        (folder / 'result.json').write_text(json.dumps({'base': head, 'head': head, 'rule_sha256': review.rule_hash(rule), 'independence': independence}))
        for name in ('preview.json', 'rules.json', 'lint.json', 'report.md'):
            (folder / name).write_text('{}')
        (folder / 'snapshot-cleanup.json').write_text(json.dumps({'state': 'removed', 'live_check': 'passed', 'base': head, 'head': head,
            'independence': independence, 'evidence_sha256': review.evidence_hashes(root, 'cleaned')}))
        with patch('review.check', side_effect=AssertionError('live check')):
            rule.write_text('{"changed": 1}')
            fails(lambda: mode.complete(store, api, token, 101, root, 'cleaned', head, head, 1), '규칙')
            rule.write_text('{}')
            with patch.object(api, 'issue', side_effect=unlocked(real_issue)):
                mode.complete(store, api, token, 101, root, 'cleaned', head, head, 1)
        assert store.read()['jobs']['101']['status'] == 'completed'

        # 끝난 이슈만 남으면 worker hook은 Orca를 부르지 않는다.
        build = ['python3', 'build.py']
        context = {'dispatch': 'other', 'task': 'other-task'}
        with patch.object(mode.integration, 'orca', side_effect=AssertionError('Orca queried')):
            assert mode.boundary(root, 'plain', ' '.join(build), [], [build], context) is None
        work = mode.claim(store, api, token)
        assert work['issue_id'] == '102'
        mode.checkpoint(store, api, token, 102, 'running', received=True)
        # 진행 중 이슈가 있어도 무관한 worker는 한 번만 확인한다.
        show = {'dispatchId': 'other', 'taskId': 'other-task', 'runId': 'other-run', 'terminal': 'x', 'workspace': 'repo::' + str(root)}
        unrelated = {'tasks': [{'id': 'other-task', 'spec': 'unrelated'}]}
        with patch.object(mode.integration, 'orca', side_effect=[show]) as lookup:  # 이슈의 Run이 아니면 task를 읽지 않는다
            assert mode.boundary(root, 'plain', ' '.join(build), [], [build], context) is None
        assert lookup.call_count == 1
        with patch.object(mode.integration, 'orca', side_effect=AssertionError('Orca queried again')):
            assert mode.boundary(root, 'plain', ' '.join(build), [], [build], context) is None
        # 그 Run이 이슈의 하위 Run으로 등록되면 생략 기록을 믿지 않고 다시 확인한다.
        with store.edit() as state:
            state['jobs']['102']['child_runs'] = {'other-run': {'task_key': work['task_key'], 'epoch': state['owner']['epoch']}}
        with patch.object(mode.integration, 'orca', side_effect=[show, unrelated]):
            assert mode.boundary(root, 'plain', ' '.join(build), [], [build], context)
        # 이슈의 Run에서 spec을 읽지 못하면(--full 없는 Orca 기본 응답) 무관한 worker로 기록하지 않고 막는다.
        concise = {'tasks': [{'id': 'other-task', 'status': 'ready', 'title': 'x'}]}
        with patch.object(mode.integration, 'orca', side_effect=[show, concise]) as lookup:
            assert 'task spec' in mode.boundary(root, 'plain', ' '.join(build), [], [build], context)
        assert '--full' in lookup.call_args_list[1].args
        with patch.object(mode.integration, 'orca', side_effect=[show, concise]) as again:  # 생략 기록을 남기지 않아 다시 묻는다
            assert mode.boundary(root, 'plain', ' '.join(build), [], [build], context)
        assert again.call_count == 2
        with store.edit() as state:
            state['jobs']['102'].pop('child_runs')

        # worker-start가 실행되지 않은 intent는 큐를 영구히 막지 않고, 같은 task key로 재배정하지도 않는다.
        start = ['orca', 'orchestration', 'worker-start', '--run', 'run', '--spec', work['task_key']]
        mode.reserve_dispatch(root, 'first', [start])
        class Listing(Orca):
            tasks, page = [{'id': 'other', 'spec': 'unrelated'}], {'hasMore': False}
            def call(self, *args):  # Orca 1.4.251: spec·count·page는 --full일 때만 온다
                if '--full' not in args:
                    return {'tasks': [{'id': t['id'], 'status': 'ready', 'title': 'x'} for t in self.tasks]} if 'task-list' in args else {'scope': 'run', 'workers': []}
                if 'task-list' in args:
                    return {'tasks': self.tasks, 'count': len(self.tasks), 'page': self.page}
                return {'workers': [], 'page': {'total': 0, 'hasMore': False}}
        runtime = Listing()
        fails(lambda: mode.reconcile(store, runtime, token, 102, '부재 확인', syncing=True), '부재')
        fails(lambda: mode.reconcile(store, runtime, token, 102, '방금 예약', not_dispatched=True), '유예')
        with store.edit() as state:
            state['jobs']['102']['dispatch_intents'][-1]['at'] = iso(time.time() - mode.INTENT_GRACE - 1)
        runtime.page = {'hasMore': True}
        fails(lambda: mode.reconcile(store, runtime, token, 102, '잘린 목록', not_dispatched=True), '전체')
        runtime.page = {'hasMore': False}
        runtime.tasks = [{'id': 'task', 'spec': 'Task key: ' + work['task_key']}]
        fails(lambda: mode.reconcile(store, runtime, token, 102, '실제 시작됨', not_dispatched=True), 'sync')
        assert not store.read()['jobs']['102']['settled']
        runtime.tasks = [{'id': 'other', 'spec': 'unrelated'}]
        mode.reconcile(store, runtime, token, 102, 'worker-start 실패를 터미널에서 확인', not_dispatched=True)
        stuck = store.read()['jobs']['102']
        assert stuck['status'] == 'held' and stuck['settled'] and not mode.occupies(stuck)
        assert mode.checkpoint(store, api, token, 102, 'queued', reason='worker-start 미실행') == 'queued'
        retry = mode.claim(store, api, token)
        assert retry['attempt'] == 2 and retry['task_key'] != work['task_key']
        mode.checkpoint(store, api, token, 102, 'running', received=True)

        # POST 중 lease가 넘어가면 게시 사실만 남기고 작업 상태는 새 소유자에게 둔다.
        taken = []
        def takeover(*args):
            with store.edit() as state:
                state['owner']['expires'] = 0
            taken.append(mode.activate(store, Orca(), 'new-coor', 'new-run', 'term', 'second'))
            return post(*args)
        posts = api.posts
        with patch.object(api, 'comment', side_effect=takeover):
            fails(lambda: mode.question(store, api, token, 102, '높이는?'), 'lease')
        saved = store.read()
        sent = next(e for e in saved['outbox'].values() if e['issue_id'] == '102')
        assert sent['status'] == 'sent' and sent['comment_id'] and api.posts == posts + 1
        assert saved['jobs']['102']['status'] == 'reconciling' and sent['question_id'] in saved['jobs']['102']['questions']
        api.comments.append({'id': 1002, 'body': '64px', 'user': {'id': 42, 'login': 'author'}, 'html_url': 'https://github.com/answer',
                             'created_at': iso(time.time()), 'updated_at': iso(time.time())})
        mode.poll_answers(store, api, taken[0]['token'])
        assert [a['comment_id'] for a in store.read()['jobs']['102']['answers']] == [1002]
        # 이전 coor의 진행 중 턴은 현재 소유자의 이슈에 외부 효과를 내지 못한다. 이슈 밖 작업은 그대로다.
        late = ['orca', 'orchestration', 'worker-start', '--run', 'run', '--spec', retry['task_key']]
        for words in (late, ['git', 'push', 'origin', 'HEAD:refs/heads/fullops/issue-2-a2'],
                      ['gh', 'pr', 'create', '--draft', '--head', 'fullops/issue-2-a2']):
            assert '인계' in mode.boundary(root, 'first', ' '.join(words), [], [words]), words
        for words in (build, ['gh', 'issue', 'list'], ['git', 'push', 'origin', 'other']):
            assert mode.boundary(root, 'first', ' '.join(words), [], [words]) is None, words
        # 이전 attempt의 intent만 남은 채 배정 전에 인계된 작업도 reconciling에 갇히지 않는다.
        mode.reconcile(store, runtime, taken[0]['token'], 102, '현재 attempt는 배정 전 인계', not_dispatched=True)
        assert store.read()['jobs']['102']['status'] == 'held'
        mode.stop(store, 'second')
        assert mode.boundary(root, 'first', ' '.join(late), [], [late]) is None  # 소유 lease가 없으면 직접 운영
        # 거부된 POST의 결과도 outbox에 남아 새 coor가 다시 보낼 수 있다.
        third = mode.activate(store, Orca(), 'third-coor', 'third-run', 'term', 'third')
        with store.edit() as state:
            state['jobs']['102'].update(status='running', epoch=third['epoch'])
        def denied(*args):
            with store.edit() as state:
                state['owner']['expires'] = 0
            raise APIError(403)
        with patch.object(api, 'comment', side_effect=denied):
            fails(lambda: mode.question(store, api, third['token'], 102, '권한은?'))
        saved = store.read()
        assert list(saved['outbox'].values())[-1]['status'] == 'failed' and saved['jobs']['102']['status'] == 'running'


def inert_when_off():
    """모드 OFF의 보류 job은 무관한 worker를 조회·차단하지 않는다. 점유 job과 모드 ON은 그대로 확인한다."""
    with tempfile.TemporaryDirectory(prefix='fullops-issue-off-') as temporary:
        root = repository(Path(temporary))
        store, api = mode.Store(root), API()
        mode.configure(store, api, 'owner/service', ['author'], interval=60, approved=True)
        receipt = mode.hook_path(root, 'first')
        receipt.parent.mkdir(exist_ok=True)
        receipt.write_text(json.dumps({'provider_session': 'first'}))
        token = mode.activate(store, Orca(), 'coor', 'run', 'term', 'first')['token']
        api.issues = [issue(1)]
        mode.poll(store, api, token)
        mode.claim(store, api, token)
        build, context = ['python3', 'build.py'], {'dispatch': 'other', 'task': 'other-task'}
        def boundary():
            return mode.boundary(root, 'plain', ' '.join(build), [], [build], context)
        with store.edit() as state:
            state['jobs']['101']['status'] = 'awaiting_author'
            state['owner']['enabled'] = False
        with patch.object(mode.integration, 'orca', side_effect=AssertionError('Orca queried')):
            assert boundary() is None
        with store.edit() as state:
            state['jobs']['101']['dispatch_intents'] = [{'at': iso(time.time())}]
            state['jobs']['101']['settled'] = False
        with patch.object(mode.integration, 'orca', return_value=None) as lookup:
            assert 'Orca' in boundary()
        assert lookup.call_count == 1
        with store.edit() as state:
            state['jobs']['101'].pop('dispatch_intents')
            state['owner']['enabled'] = True
        with patch.object(mode.integration, 'orca', return_value=None) as lookup:
            assert 'Orca' in boundary()
        assert lookup.call_count == 1


def main():
    # 화면에서 선택된 다른 pane은 소유 identity 검증에 사용하지 않는다.
    adapter = mode.Orca('orca')
    caller = {'caller': {'orcaSessionId': 'coor', 'live': True}}
    pane = {'terminal': {'handle': 'term', 'connected': True, 'incarnationId': 'incarnation'}}
    with patch.object(adapter, 'call', side_effect=orca_answers(caller, pane)) as call:
        assert adapter.identity('coor', 'run', 'term') == 'incarnation'
        assert call.call_args_list[1].args == ('terminal', 'show', '--terminal', 'term')
        assert call.call_args_list[2].args == ('orchestration', 'run-current', '--from', 'term', '--full')
    for status in ({}, {'caller': {'orcaSessionId': 'coor', 'live': False}}):
        with patch.object(adapter, 'call', return_value=status) as call:
            fails(lambda: adapter.identity('coor', 'run', 'term'), 'identity')
            assert call.call_count == 1
    native = {'provider_session': 'host', 'orca_terminal': 'term'}
    with patch.dict('os.environ', {'ORCA_TERMINAL_HANDLE': 'term', 'ORCA_AGENT_SESSION_ID': ''}):
        with patch.object(adapter, 'call', side_effect=orca_answers({}, pane)):
            assert adapter.identity('provider_session:host', 'run', 'term', 'host', native) == 'incarnation'
        for session, terminal, receipt in (('provider_session:other', 'term', native),
                                           ('provider_session:host', 'other', native),
                                           ('provider_session:host', 'term', {})):
            with patch.object(adapter, 'call', return_value={}):
                fails(lambda: adapter.identity(session, 'run', terminal, 'host', receipt), 'identity')
        for status in ({'caller': {'live': False}}, {'caller': {'orcaSessionId': 'other', 'live': True}}):
            with patch.object(adapter, 'call', return_value=status):
                fails(lambda: adapter.identity('provider_session:host', 'run', 'term', 'host', native), 'identity')
        with patch.dict('os.environ', {'ORCA_AGENT_SESSION_ID': 'structured'}), patch.object(adapter, 'call', return_value={}):
            fails(lambda: adapter.identity('provider_session:host', 'run', 'term', 'host', native), 'identity')
    with tempfile.TemporaryDirectory(prefix='fullops-issue-') as temporary:
        root = repository(Path(temporary))
        store, api = mode.Store(root), API()
        assert store.read()['owner'] is None and store.read()['config'] is None
        fails(lambda: mode.configure(store, api, 'owner/service', ['author']), '사용자')
        for interval in (0, -1, 59, True, '60'):
            fails(lambda: mode.configure(store, api, 'owner/service', ['author'], interval, approved=True))
        fails(lambda: mode.configure(store, api, 'owner/service', [], approved=True))
        fails(lambda: mode.configure(store, api, 'other/repo', ['author'], approved=True), 'remote')
        api.allow_push = False
        fails(lambda: mode.configure(store, api, 'owner/service', ['author'], approved=True), 'push')
        api.allow_push = True
        mode.configure(store, api, 'owner/service', ['author'], interval=60, approved=True)
        assert store.read()['owner'] is None
        fails(lambda: mode.activate(store, Orca(), 'coor', 'run', 'term', 'provider'), 'SessionStart')
        receipt = mode.hook_path(root, 'provider')
        receipt.parent.mkdir()
        receipt.write_text(json.dumps({'provider_session': 'provider'}))
        binding = mode.hook_path(root, 'terminal-term')
        binding.write_text(json.dumps({'provider_session': 'old', 'orca_terminal': 'term'}))
        tui_owner = {'session': 'provider_session:provider', 'provider_session': 'provider', 'run': 'run', 'terminal': 'term'}
        fails(lambda: mode.owner_identity(store, Orca(), tui_owner), 'binding')
        binding.write_text(json.dumps({'provider_session': 'provider', 'orca_terminal': 'term'}))
        assert mode.owner_identity(store, Orca(), tui_owner) == 'incarnation'
        owner = mode.activate(store, Orca(), 'coor', 'run', 'term', 'provider')
        token = owner['token']
        # 실제 CLI 입력 경로: inline interpreter/argv secret 없이 같은 fencing을 적용한다.
        private = root / '.fullops-squad/.env.issue-mode-lease.json'
        (root / '.fullops-squad/.gitignore').write_text('.env*\n')
        private.write_text(json.dumps(owner))
        private.chmod(0o600)
        arguments = ['issue_mode.py', '--repo', str(root), 'wait', '--token-file', str(private)]
        output = io.StringIO()
        with patch.object(sys, 'argv', arguments), patch.object(mode, 'GitHub', return_value=api), \
                patch.object(mode, 'Orca', return_value=Orca()), \
                patch.object(mode, 'wait', return_value={'status': 'test_wait'}) as waiting, redirect_stdout(output):
            assert mode.main() == 0
            assert waiting.call_args.args[-2:] == (token, None)
        assert token not in output.getvalue()
        public = root / 'public-token.json'
        public.write_text(json.dumps(owner))
        public.chmod(0o600)
        fails(lambda: mode.lease_token(store, str(public)), 'Git')
        if os.name == 'posix':
            private.chmod(0o644)
            fails(lambda: mode.lease_token(store, str(private)), '0600')
            private.chmod(0o600)
        private.write_text('{"token":"invalid"}')
        fails(lambda: mode.lease_token(store, str(private)), 'token')
        private.write_text(json.dumps({'token': '0' * 48}))
        with patch.object(sys, 'argv', arguments), patch.object(mode, 'GitHub', return_value=api), redirect_stdout(io.StringIO()):
            assert mode.main() == 2  # 파일 입력도 다른 coor의 capability를 수락하지 않는다.
        private.write_text(json.dumps(owner))
        fails(lambda: mode.activate(store, Orca(), 'other', 'run', 'term', 'provider'), 'lease')
        fails(lambda: mode.guard(store.read(), 'foreign'))

        # 중복·PR·close·비허용 ID·과거 backlog는 모델에 전달하지 않는다.
        api.issues = [issue(1), issue(2), issue(3, author=99), issue(4, pull_request={}),
                      issue(5, created_at='2000-01-01T00:00:00Z'), issue(6, state='closed')]
        mode.poll(store, api, token)
        mode.poll(store, api, token)
        state = store.read()
        assert set(state['jobs']) == {'101', '102', '103', '106'}
        assert state['jobs']['103']['status'] == 'rejected'
        assert state['jobs']['106']['status'] == 'cancelled'
        cursor = state['cursor']
        api.failure = APIError(429, 120)
        fails(lambda: mode.poll(store, api, token))
        assert store.read()['cursor'] == cursor
        api.failure = None
        with ThreadPoolExecutor(max_workers=2) as threads:
            claims = list(threads.map(lambda _: mode.claim(store, api, token), range(2)))
        assert sum(c is not None for c in claims) == 1
        job = next(c for c in claims if c)
        assert job['issue_id'] == '101' and job['attempt'] == 1
        received = {'task_key': job['task_key'], 'session': 'coor', 'received': True}
        fails(lambda: mode.checkpoint(store, api, token, 101, 'running'), 'receipt')
        fails(lambda: mode.checkpoint(store, api, token, 101, 'reviewing', receipt=received), '실행')
        mode.checkpoint(store, api, token, 101, 'running', received=True)  # receipt 파일 없이 lease로 수신 기록
        assert store.read()['jobs']['101']['receipt'] == received
        from flow_gate import shell_commands
        assert shell_commands('git push origin HEAD:refs/heads/x 2>&1 | tail -3') == [
            ['git', 'push', 'origin', 'HEAD:refs/heads/x'], ['tail', '-3']]  # fd 복제가 push 인자를 바꾸지 않는다
        # 처리한 orchestration delivery는 다음 wait의 --ack로 넘겨 Orca에 직접 ack하지 않아도 된다.
        acks = []
        def check(args, ack):
            acks.append(ack)
            return {'deliveryId': 'd2', 'messages': [{'type': 'question', 'id': 'm1'}]}
        with patch.object(mode, 'renew'), patch.object(mode.orca_wait, 'check', side_effect=check),                 patch.object(mode.integration, 'record'):
            assert mode.wait(store, api, Orca(), token, 'd1')['deliveryId'] == 'd2'
        assert acks == ['d1']
        with patch.object(mode, 'renew'), patch.object(mode.orca_wait, 'check', side_effect=check), \
                patch.object(mode.integration, 'record', side_effect=OSError('disk')):
            kept = mode.wait(store, api, Orca(), token, 'd1')  # 기록이 실패해도 이미 소비한 묶음은 돌려준다
        assert kept['deliveryId'] == 'd2' and kept['messages'] and kept['record_error'] == 'disk', kept
        assert mode.claim(store, api, token) is None  # busy: enqueue만, 다른 issue dispatch 없음
        # 실사용에서 coor를 멈춘 조회 명령은 통과하고, 비밀정보·다른 저장소·다른 체크아웃 변경은 막는다.
        for words in (['rg', 'def', str(Path.home() / '.codex/plugins/cache/fullops-squad/scripts/issue_mode.py')],
                      ['git', '-C', '../dev', 'status', '--short'], ['git', '-C', '../dev', 'branch', '--show-current'],
                      ['gh', 'issue', 'view', '1', '--repo', 'owner/service'],
                      ['orca', 'orchestration', 'worker-start', '--help'], ['git', 'switch', '-c', 'fullops/issue-1-a1', 'abc123'],
                      ['python3', str(Path.home() / '.claude/plugins/cache/fullops-squad/1.11.0/scripts/work.py'), 'new']):
            assert mode.boundary(root, 'provider', ' '.join(words), [], [words]) is None, words
        for words in (['Get-Content', '.fullops-squad/.env'], ['git', '-C', '../dev', 'commit', '-m', 'x'],
                      ['git', '-C', '../dev', 'branch', '-D', 'x'], ['gh', 'issue', 'view', '1', '--repo', 'other/repo'],
                      ['git', '-c', 'core.sshCommand=x', 'status'],
                      ['Set-Content', str(Path.home() / '.codex/config.toml'), 'x'],
                      ['python3', str(Path.home() / '.claude/plugins/cache/x/run.py'), str(Path.home() / '.claude/settings.json')],
                      ['Set-Content', str(Path.home() / '.claude/plugins/cache/fullops-squad/1.11.0/scripts/work.py'), 'x']):
            assert mode.boundary(root, 'provider', ' '.join(words), [], [words]), words
        # PowerShell처럼 변수 대입과 함께 쓴 제어 명령도 lease 파일 경로로 막지 않는다. 같은 줄의 다른 명령은 검사한다.
        lease = '.fullops-squad/.env.issue-mode-lease.json'
        line = [['$s=x'], ['python3', 'issue_mode.py', 'checkpoint', '--token-file', lease, '--received'], ['echo', 'done']]
        assert mode.boundary(root, 'provider', '', [], line) is None
        assert mode.boundary(root, 'provider', '', [], line[:2] + [['Get-Content', lease]])
        with store.edit() as state:
            state['jobs']['101']['started'] -= state['config']['max_seconds'] + 1
        assert mode.boundary(root, 'provider', 'orca terminal list', [], [['orca', 'terminal', 'list']]) is None
        start = ['orca', 'orchestration', 'worker-start', '--run', 'run', '--spec', job['task_key']]
        assert '한도' in mode.boundary(root, 'provider', ' '.join(start), [], [start])
        # 한도 초과는 실행 단계만 막는다. 보류 사유를 보존하고 확정 종료 뒤 재시도·취소할 수 있다.
        before_limit = store.read()
        assert mode.checkpoint(store, api, token, 101, 'running', received=True) == 'held'
        assert mode.checkpoint(store, api, token, 101, 'held', reason='tests fail', resume='owner:coor') == 'held'
        assert store.read()['jobs']['101']['reason'] == 'tests fail'
        with store.edit() as state:
            state['jobs']['101']['settled'] = True
        assert mode.checkpoint(store, api, token, 101, 'queued', reason='retry') == 'queued'
        assert mode.checkpoint(store, api, token, 101, 'cancelled', reason='user cancel', resume='none') == 'cancelled'
        with store.edit() as state:
            state.clear()
            state.update(before_limit)
        with store.edit() as state:
            state['jobs']['101']['started'] = time.time()

        # POST는 성공했지만 응답이 유실된다. outbox 재조정은 기존 comment를 채택한다.
        api.issues[0]['user']['login'] = 'renamed'
        api.fail_post = True
        fails(lambda: mode.question(store, api, token, 101, '정보: 규격이 필요합니다. 질문: 크기는? 재개: 규격 확정'))
        assert store.read()['jobs']['101']['status'] == 'held' and api.posts == 1
        api.fail_post = False
        q = mode.question(store, api, token, 101, '정보: 규격이 필요합니다. 질문: 크기는? 재개: 규격 확정')
        assert q['comment_id'] == 901 and api.posts == 1
        assert q['body'].startswith('@renamed\n')
        # 질문 전에 쓴 댓글의 편집은 답변 경로를 바꾸지 않는다.
        api.comments.append({'id': 950, 'body': 'typo', 'user': {'id': 42, 'login': 'renamed'}, 'html_url': 'https://github.com/early',
                             'created_at': iso(time.time() - 3600), 'updated_at': iso(time.time())})
        mode.poll_answers(store, api, token)
        assert store.read()['jobs']['101']['status'] != 'changed'
        assert mode.answer_delivery(store, token) is None  # 동일 계정의 자기 질문
        assert mode.boundary(root, 'provider', 'git push origin main', [], [['git', 'push', 'origin', 'main']])

        second = mode.claim(store, api, token)
        assert second['dependency_review_required'] and second['issue_id'] == '102'
        second_receipt = {'task_key': second['task_key'], 'session': 'coor', 'received': True}
        fails(lambda: mode.checkpoint(store, api, token, 102, 'running', receipt=second_receipt), '의존')
        fails(lambda: mode.checkpoint(store, api, token, 102, 'running', dependencies=['101'], receipt=second_receipt), '의존')
        mode.checkpoint(store, api, token, 102, 'running', dependencies=[], receipt=second_receipt)
        mode.checkpoint(store, api, token, 102, 'held', reason='test failed', resume='owner:coor; 독립 수정 후 검증')
        # 사이드바는 오래된 보류보다 답변 대기 이슈를 보인다.
        assert json.loads((store.path.parent / 'status.json').read_text(encoding='utf-8'))['job']['number'] == 1
        # 사용자 결정이 필요한 보류도 원래 이슈에 질문해 답변 대기로 옮긴다.
        mode.question(store, api, token, 102, '결정: 실패 테스트를 고칠 방향은? 재개: 방향 확정')
        assert store.read()['jobs']['102']['status'] == 'awaiting_author' and api.posts == 2
        with store.edit() as state:
            state['jobs']['102'].update(status='held', questions=[])
        answer ={'id': 1001, 'body': q['question_id'] + ' 128px', 'user': {'id': 42, 'login': 'renamed'},
                  'created_at': iso(time.time()), 'updated_at': iso(time.time()), 'html_url': 'https://github.com/answer'}
        api.comments.extend([{**answer, 'id': 1000, 'user': {'id': 99, 'login': 'author'}}, answer])
        mode.poll_answers(store, api, token)
        delivered = mode.answer_delivery(store, token)
        assert len(delivered['answer_candidates']) == 1 and delivered['issue_id'] == '101'
        assert mode.answer_delivery(store, token) is None
        assert mode.resolve_answers(store, api, token, 101, 'insufficient', '질문 ID는 맞지만 단위/높이가 빠짐') == 'awaiting_author'
        mode.question(store, api, token, 101, '높이도 알려주세요. 재개 조건: 너비/높이 확정')
        api.comments.append({**answer, 'id': 1002, 'body': '128px x 64px'})
        mode.poll_answers(store, api, token)
        assert len(mode.answer_delivery(store, token)['answer_candidates']) == 1
        assert mode.resolve_answers(store, api, token, 101, 'sufficient', '질문 연결 및 규격 확정, 권한 확대 없음') == 'queued'
        resumed = mode.claim(store, api, token)
        assert resumed['attempt'] == 2 and resumed['digest'] != job['digest']
        resumed_receipt = {'task_key': resumed['task_key'], 'session': 'coor', 'received': True}
        mode.checkpoint(store, api, token, 101, 'running', receipt=resumed_receipt, dependencies=[])
        assert store.read()['jobs']['101']['run'] == 'run'

        # 보류/취소/답변 대기는 worker 종료 증거를 대신하지 않는다.
        saved = store.read()
        mode.reserve_dispatch(root, 'provider', [['orca', 'orchestration', 'worker-start', '--run', 'run',
                                                 '--spec', resumed['task_key']]])
        for status in ('held', 'awaiting_author', 'changed', 'policy_hold', 'cancelled'):
            with store.edit() as state:
                state['jobs']['101']['status'] = status
                state['jobs']['102']['status'] = 'queued'
            assert mode.claim(store, api, token) is None, status
            assert mode.answer_delivery(store, token) is None, status
            with store.edit() as state:
                state['jobs']['102'].update(status='claimed', epoch=owner['epoch'])
            fails(lambda: mode.checkpoint(store, api, token, 102, 'running',
                                         receipt=second_receipt, dependencies=[]), '종료')
        with store.edit() as state:
            state.clear()
            state.update(saved)

        # 실제 pages 구현을 거친 이슈/댓글 원문은 SQLite에 들어가지 않는다.
        secret = 'ghp_' + 'x' * 36
        api.issues.append(issue(30, body=secret))
        client = GitHub('test-token')
        def response(path, **kwargs):
            rows = api.comments + [{**answer, 'id': 1030, 'body': secret}] if '/comments?' in path else api.issues
            return 200, {'ETag': 'test'}, deepcopy(rows)
        with patch.object(client, 'request', side_effect=response), patch.object(api, 'pages', side_effect=client.pages):
            mode.poll(store, api, token)
        assert store.read()['jobs']['130']['snapshot']['body'] == '[REDACTED]'
        assert store.read()['jobs']['130']['snapshot']['source_digest'] == mode.digest(['work 30', secret])
        assert secret not in json.dumps(store.read()) and secret.encode() not in store.path.read_bytes()
        api.issues.pop()
        with store.edit() as state:
            state.clear()
            state.update(saved)

        # 기본 remote push refspec 설정과 무관하게 대상 ref를 명시한다.
        branch = 'fullops/issue-1-a2'
        subprocess.run(['git', '-C', str(root), 'symbolic-ref', 'HEAD', 'refs/heads/' + branch], check=True)
        subprocess.run(['git', '-C', str(root), 'config', 'remote.origin.push', 'refs/heads/main:refs/heads/main'], check=True)
        for args in (['origin'], ['origin', branch]):
            assert mode.boundary(root, 'provider', 'git push ' + ' '.join(args), [], [['git', 'push', *args]])
        explicit = ['git', 'push', 'origin', 'HEAD:refs/heads/' + branch]
        assert mode.boundary(root, 'provider', ' '.join(explicit), [], [explicit]) is None
        for override in (['-c', 'remote.origin.pushurl=https://github.com/another/repo.git'],
                         ['-cremote.origin.pushurl=https://github.com/another/repo.git'],
                         ['--config-env=remote.origin.pushurl=PUSH_URL']):
            words = ['git', *override, *explicit[1:]]
            assert mode.boundary(root, 'provider', ' '.join(words), [], [words])
        subprocess.run(['git', '-C', str(root), 'symbolic-ref', 'HEAD', 'refs/heads/main'], check=True)

        # 다른 provider session의 worker도 정본 task/terminal로 연결한 뒤 같은 scope를 적용한다.
        context = {'dispatch': 'ctx_auto', 'task': 'task_auto'}
        mode.hook_path(root, 'worker').write_text(json.dumps({'provider_session': 'worker', 'orca_terminal': 'worker-term'}))
        projection = {'projection': {'dispatchId': 'ctx_auto', 'taskId': 'task_auto', 'runId': 'run'},
                      'terminal': {'handle': 'worker-term', 'worktreePath': str(root)}}
        listing = {'tasks': [{'id': 'task_auto', 'spec': 'Task key: ' + resumed['task_key']}]}
        merge = ['gh', 'pr', 'merge', '1']
        unknown = deepcopy(projection)
        unknown['terminal'].pop('worktreePath')
        previous_cwd = Path.cwd()
        try:
            os.chdir(root)  # hook의 실제 cwd에서도 빈 경로를 작업 공간 증거로 쓰지 않는다.
            with patch.object(mode.integration, 'orca', side_effect=[unknown, listing]):
                assert mode.boundary(root, 'worker', 'python3 build.py', [], [['python3', 'build.py']], context)
        finally:
            os.chdir(previous_cwd)
        # Orca 1.4.246의 worker-show는 projection 없이 평면으로 온다(#118).
        flat = {'dispatchId': 'ctx_auto', 'taskId': 'task_auto', 'runId': 'run', 'state': 'ready', 'stage': 'input_accepted',
                'liveness': 'live', 'terminal': 'worker-term', 'workspace': 'repo::' + str(root)}
        with patch.object(mode.integration, 'orca', side_effect=[flat, listing]):
            blocked = mode.boundary(root, 'worker', ' '.join(merge), [], [merge], context)
        assert blocked and 'binding' not in blocked and '정본' not in blocked, blocked
        with store.edit() as state:
            assert state['jobs']['101']['worker_sessions'].pop('worker')
        with patch.object(mode.integration, 'orca', side_effect=[projection, listing]):
            assert mode.boundary(root, 'worker', ' '.join(merge), [], [merge], context)
        # 유지한 worker의 새 dispatch는 Orca 정본으로 다시 묶는다.
        moved = deepcopy(projection)
        moved['projection'].update(dispatchId='ctx_next', taskId='task_next')
        with patch.object(mode.integration, 'orca', side_effect=[moved, {'tasks': [{**listing['tasks'][0], 'id': 'task_next'}]}]):
            assert mode.boundary(root, 'worker', 'python3 build.py', [], [['python3', 'build.py']],
                                 {'dispatch': 'ctx_next', 'task': 'task_next'}) is None
        with store.edit() as state:
            assert state['jobs']['101']['worker_sessions']['worker']['dispatch'] == 'ctx_next'
            state['jobs']['101']['worker_sessions']['worker'].update(dispatch='ctx_auto', task='task_auto')
        with patch.object(mode.integration, 'orca', side_effect=AssertionError('binding queried again')):
            assert mode.boundary(root, 'worker', 'cat .env', [], [['cat', '.env']], context)
            assert mode.boundary(root, 'worker', 'python3 build.py', [], [['python3', 'build.py']], context) is None
            with store.edit() as state:
                state['owner']['expires'] = 0
            assert mode.boundary(root, 'worker', 'python3 build.py', [], [['python3', 'build.py']], context)
            send = 'orca orchestration send --type worker_done --dispatch-id ctx_auto --task-id task_auto --outcome failed'
            assert mode.boundary(root, 'worker', send, [], [send.split()], context) is None
        with store.edit() as state:
            state['owner']['expires'] = time.time() + 90
            state['jobs']['101']['status'] = 'held'
        assert mode.boundary(root, 'worker', 'python3 build.py', [], [['python3', 'build.py']], context)
        with store.edit() as state:
            state['jobs']['101']['status'] = 'running'
            state['jobs']['101']['task_key'] += '-next'
        assert mode.boundary(root, 'worker', 'python3 build.py', [], [['python3', 'build.py']], context)
        with store.edit() as state:
            state['jobs']['101']['task_key'] = resumed['task_key']
        with patch.object(mode.integration, 'orca', return_value=None):
            assert mode.boundary(root, 'unverified-worker', ' '.join(merge), [], [merge], context)
        # 실제 부모 worker receipt와 child Run coordinator를 증명한 하위 작업만 같은 자동 이슈에 연결한다.
        before_nested = store.read()
        config_path = root / '.fullops-squad/fullops.json'
        original_config = config_path.read_bytes()
        config_path.write_text(json.dumps({'schema_version': 1, 'roles': {}, 'subagent_level': 'standard',
                                           'git': {'remote': 'origin', 'base': 'main'}}))
        nested = ['orca', 'orchestration', 'worker-start', '--run', 'child-run', '--spec', resumed['task_key']]
        authority = {'run': {'id': 'child-run', 'coordinator_handle': 'worker-term'}}
        concise = {'runId': 'child-run', 'objective': 'x', 'removedWork': False}  # Orca 1.4.251: run은 --full일 때만 온다
        with patch.object(mode.integration, 'orca', side_effect=lambda *args, **_: authority if '--full' in args else concise):
            assert mode.boundary(root, 'worker', ' '.join(nested), [], [nested], context) is None
            assert 'child-run' not in store.read()['jobs']['101'].get('child_runs', {})  # validation does not reserve
        # A fresh worker proof is saved after the reserve snapshot, then checked inside the writer.
        with store.edit() as state:
            state['jobs']['101']['worker_sessions'].pop('worker')
        with patch.object(mode.integration, 'orca', side_effect=[projection, listing, authority]):
            mode.reserve_dispatch(root, 'worker', [nested], context=context)
        parent_session_binding = deepcopy(store.read()['jobs']['101']['worker_sessions']['worker'])
        def changed_parent(*args, **kwargs):
            with store.edit() as state:
                state['jobs']['101']['worker_sessions']['worker']['dispatch'] = 'replacement-dispatch'
            return authority
        before_intents = store.read()['jobs']['101']['dispatch_intents']
        with patch.object(mode.integration, 'orca', side_effect=changed_parent):
            fails(lambda: mode.reserve_dispatch(root, 'worker', [nested], context=context), '부모 worker')
        assert store.read()['jobs']['101']['dispatch_intents'] == before_intents
        with store.edit() as state:
            state['jobs']['101']['worker_sessions']['worker'] = parent_session_binding
        parent_binding = store.read()['jobs']['101']['child_runs']['child-run']
        assert parent_binding == {'epoch': owner['epoch'], 'parent_dispatch': 'ctx_auto',
                                  'parent_session': 'worker', 'task_key': resumed['task_key']}
        assert not store.read()['jobs']['101']['settled']
        wrong_run = [*nested]
        wrong_run[wrong_run.index('--run') + 1] = 'run'
        assert mode.boundary(root, 'worker', ' '.join(wrong_run), [], [wrong_run], context)
        for status in (None, {'run': {}}, {'run': {'coordinator_handle': 'foreign'}}):
            with patch.object(mode.integration, 'orca', return_value=status):
                assert mode.boundary(root, 'worker', ' '.join(nested), [], [nested], context)
        config = json.loads(config_path.read_text())
        config_path.write_text(json.dumps({**config, 'subagent_level': 'off'}))
        assert mode.boundary(root, 'worker', ' '.join(nested), [], [nested], context)
        config_path.write_text(json.dumps(config))
        child_context = {'dispatch': 'ctx_child', 'task': 'task_child'}
        mode.hook_path(root, 'child').write_text(json.dumps({'provider_session': 'child', 'orca_terminal': 'child-term'}))
        child_projection = {'projection': {'dispatchId': 'ctx_child', 'taskId': 'task_child', 'runId': 'child-run'},
                            'terminal': {'handle': 'child-term', 'worktreePath': str(root)}}
        child_listing = {'tasks': [{'id': 'task_child', 'spec': 'Task key: ' + resumed['task_key']}]}
        with patch.object(mode.integration, 'orca', side_effect=[child_projection, child_listing]):
            assert mode.boundary(root, 'child', 'python3 build.py', [], [['python3', 'build.py']], child_context) is None
        assert mode.boundary(root, 'child', ' '.join(merge), [], [merge], child_context)
        with patch.object(mode.integration, 'orca', side_effect=[child_projection, {'tasks': [{'id': 'task_child', 'spec': 'different task'}]}]):
            assert mode.boundary(root, 'mismatched-child', 'python3 build.py', [], [['python3', 'build.py']], child_context)
        send_child = 'orca orchestration send --type worker_done --dispatch-id ctx_child --task-id task_child --outcome failed'
        for key, value in (('paused', True), ('expires', 0), ('epoch', owner['epoch'] + 1)):
            with store.edit() as state:
                previous = state['owner'][key]
                state['owner'][key] = value
            assert mode.boundary(root, 'child', 'python3 build.py', [], [['python3', 'build.py']], child_context)
            assert mode.boundary(root, 'child', send_child, [], [send_child.split()], child_context) is None
            with store.edit() as state:
                state['owner'][key] = previous
        # A newly observed child still binds the registration epoch after a new coor has reconciled its parent.
        with store.edit() as state:
            state['owner']['epoch'] += 1
            state['jobs']['101']['epoch'] = state['owner']['epoch']
            state['jobs']['101']['worker_sessions'].pop('child')
        with patch.object(mode.integration, 'orca', side_effect=[child_projection, child_listing]):
            assert mode.boundary(root, 'child', 'python3 build.py', [], [['python3', 'build.py']], child_context)
        assert store.read()['jobs']['101']['worker_sessions']['child']['epoch'] == parent_binding['epoch']
        with store.edit() as state:
            state['owner']['epoch'] = owner['epoch']
            state['jobs']['101']['epoch'] = owner['epoch']
        class NestedOrca:
            child_status = 'running'
            child_page = {'total': 1, 'hasMore': False}
            child_task_count = 1
            child_task_page = None
            extra_worker = False
            def call(self, *args):
                child = 'child-run' in args
                task_id = 'task_child' if child else 'task_auto'
                status = self.child_status if child else 'completed'
                if 'task-list' in args and '--full' not in args:  # Orca 1.4.251의 기본 응답
                    return {'tasks': [{'id': task_id, 'status': status, 'title': 'x'}]}
                if 'task-list' in args:
                    result = {'tasks': [{'id': task_id, 'status': status, 'spec': resumed['task_key']}],
                              'count': self.child_task_count if child else 1}
                    if child and self.child_task_page is not None:
                        result['page'] = self.child_task_page
                    return result
                verdict = 'live' if status == 'running' else 'exited'
                # 하위 Run은 Orca 1.4.246 평면 형식(liveness 문자열), 부모는 이전 projection 형식이다.
                workers = [{'taskId': task_id, 'liveness': verdict} if child else
                           {'taskId': task_id, 'projection': {'liveness': {'verdict': verdict}}}]
                if child and self.extra_worker:
                    workers.append({'taskId': 'new-task-after-listing', 'projection': {'liveness': {'verdict': 'live'}}})
                return {'workers': workers, 'page': self.child_page if child else {'total': 1, 'hasMore': False}}
        nested_runtime = NestedOrca()
        mode.reconcile(store, nested_runtime, token, 101, 'parent exited, child live', syncing=True)
        assert not store.read()['jobs']['101']['settled']
        fails(lambda: mode.checkpoint(store, api, token, 101, 'reviewing', receipt=resumed_receipt), '종료')
        with store.edit() as state:
            state['jobs']['101']['status'] = 'held'
        fails(lambda: mode.checkpoint(store, api, token, 101, 'queued', reason='retry'), '확정 종료')
        with store.edit() as state:
            state['jobs']['101']['status'] = 'reviewing'
        fails(lambda: mode.complete(store, api, token, 101, root, 'key', 'base', 'head', 1), '종료')
        nested_runtime.child_status = 'completed'
        for count, page in ((2, None), (None, None), (1, {'hasMore': True, 'total': 2}),
                            (1, {'hasMore': False, 'total': 2})):
            nested_runtime.child_task_count, nested_runtime.child_task_page = count, page
            fails(lambda: mode.reconcile(store, nested_runtime, token, 101, 'truncated child tasks', syncing=True), '전체')
            assert not store.read()['jobs']['101']['settled']
        nested_runtime.child_task_count, nested_runtime.child_task_page = 1, {'hasMore': False, 'total': 1}
        nested_runtime.extra_worker = True
        nested_runtime.child_page = {'total': 2, 'hasMore': False}
        fails(lambda: mode.reconcile(store, nested_runtime, token, 101, 'worker started after task listing', syncing=True), '전체')
        assert not store.read()['jobs']['101']['settled']
        nested_runtime.extra_worker = False
        for page in ({}, {'total': 1, 'hasMore': True}, {'total': 2, 'hasMore': False}):
            nested_runtime.child_page = page
            fails(lambda: mode.reconcile(store, nested_runtime, token, 101, 'unknown child fleet', syncing=True), '전체')
        assert not store.read()['jobs']['101']['settled']
        nested_runtime.child_page = {'total': 1, 'hasMore': False}
        mode.reconcile(store, nested_runtime, token, 101, 'all exited', syncing=True)
        assert store.read()['jobs']['101']['settled']
        assert store.read()['jobs']['101']['history'][-1]['child_runs']['child-run']['tasks']
        with store.edit() as state:
            state.clear()
            state.update(before_nested)
        config_path.write_bytes(original_config)
        # 현재 실행 allowlist 철회는 다음 안전 경계에서 중단한다.
        with store.edit() as state:
            allowed = state['config']['allowed']
            state['config']['allowed'] = {}
        # 보류 사유가 있어도 coor의 조회·기록은 계속되고, 배정·push·GitHub 변경만 막힌다.
        assert mode.boundary(root, 'provider', 'python3 build.py', [], [['python3', 'build.py']]) is None
        dispatch = ['orca', 'orchestration', 'worker-start', '--run', 'run']
        assert '철회' in mode.boundary(root, 'provider', ' '.join(dispatch), [], [dispatch])
        assert '철회' in mode.boundary(root, 'provider', 'gh issue comment 1', [], [['gh', 'issue', 'comment', '1']])
        assert mode.boundary(root, 'provider', 'gh issue view 1', [], [['gh', 'issue', 'view', '1']]) is None
        with store.edit() as state:
            state['config']['allowed'] = allowed
        for words in (['gh', 'pr', 'merge', '1'], ['gh', 'issue', 'close', '1'], ['curl', 'https://evil'],
                      ['git', 'push', 'origin', 'main'], ['git', 'reset', '--hard'], ['gh', 'api', 'repos/x'],
                      ['gh', 'issue', 'edit', '1', '--body', 'list']):
            assert mode.boundary(root, 'provider', ' '.join(words), [], [words]), words
        assert mode.boundary(root, 'foreign', 'git reset --hard', [], [['git', 'reset', '--hard']]) is None
        assert mode.boundary(root, 'provider', '', [('../outside', 'x')], [])
        api.issues[0]['user']['login'] = 'renamed'
        assert mode.fresh(store.read(), api, store.read()['jobs']['101']) is None  # stable ID
        # REST는 빈 본문을 null로, GraphQL은 ''로 준다.
        assert mode.snapshot(issue(9, body=None))['source_digest'] == mode.snapshot(issue(9, body=''))['source_digest']
        with patch.object(api, 'issue', return_value=None):
            assert mode.fresh(store.read(), api, store.read()['jobs']['101'])[0] == 'cancelled'
        api.issues[0]['body'] = 'edited externally'
        mode.poll(store, api, token)
        assert store.read()['jobs']['101']['status'] == 'changed'
        assert mode.boundary(root, 'provider', 'python3 build.py', [], [['python3', 'build.py']]) is None
        assert '보류' in mode.boundary(root, 'provider', ' '.join(dispatch), [], [dispatch])
        api.issues[0]['body'] = 'requirement'
        # 사용한 댓글 편집은 snapshot을 교체하지 않고 changed로 보존한다.
        old_digest = store.read()['comments']['1001']['digest']
        next(c for c in api.comments if c['id'] == 1001)['body'] = 'modified answer'
        mode.poll_answers(store, api, token)
        assert store.read()['comments']['1001']['digest'] == old_digest
        assert store.read()['comments']['1001']['changed']
        api.comments = [c for c in api.comments if c['id'] != 1002]
        mode.poll_answers(store, api, token)
        assert store.read()['jobs']['101']['status'] == 'changed'  # 답변 삭제는 정본 덮어쓰기 금지

        # native SessionEnd identity를 별도로 사용한다. queue는 유지하고 재활성화는 명시적이다.
        ended = subprocess.run([sys.executable, str(ROOT / 'plugins/fullops-squad/scripts/issue_mode.py'), 'session-end'],
                               input=json.dumps({'cwd': str(root), 'session_id': 'provider'}), text=True, capture_output=True)
        assert ended.returncode == 0, ended.stderr
        fails(lambda: mode.claim(store, api, token))
        assert not store.read()['owner']['enabled'] and len(store.read()['jobs']) == 4
        with store.edit() as state:
            state['jobs']['102']['status'] = 'running'
        newer = mode.activate(store, Orca(), 'new-coor', 'new-run', 'term', 'provider')
        assert store.read()['jobs']['102']['status'] == 'reconciling'
        fails(lambda: mode.claim(store, api, token))
        assert mode.claim(store, api, newer['token']) is None
        with store.edit() as state:
            state['owner']['expires'] = 0
        mode.heartbeat(root, 'provider')
        assert store.read()['owner']['expires'] == 0  # 만료된 lease를 hook이 부활시키지 않음
        fails(lambda: mode.guard(store.read(), newer['token']))
        fails(lambda: mode.renew(store, Orca(), newer['token']))
        script = str(ROOT / 'plugins/fullops-squad/scripts/issue_mode.py')
        for words in (['python3', script, '--repo', str(root), '--orca', 'orca', 'status'],
                      ['python3', script, 'disable', '--session', 'new-coor']):
            assert mode.boundary(root, 'provider', ' '.join(words), [], [words]) is None
        # 만료된 lease의 coor는 자동 실행 중이 아니므로 사용자가 직접 운영한다(PowerShell `&` 호출 포함).
        for words in (['&', 'python3.exe', script, '--repo', '.', 'disable', '--session', 'new-coor'],
                      ['python3', 'build.py'], ['gh', 'issue', 'list']):
            assert mode.boundary(root, 'provider', ' '.join(words), [], [words]) is None

        # 실제 review gate가 실패하면 completed가 되지 않는다.
        with store.edit() as state:
            state['owner']['expires'] = time.time() + 90
            state['jobs']['101'].update(status='reviewing', epoch=state['owner']['epoch'])
        subprocess.run(['git', '-C', str(root), 'add', '.fullops-squad'], check=True)
        subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-qm', 'setup'], check=True)
        head = mode.integration.git(root, 'rev-parse', 'HEAD')
        with patch('review.check', side_effect=ValueError('review failed')):
            fails(lambda: mode.complete(store, api, newer['token'], 101, root, 'key', head, head, 1), 'review failed')
        assert store.read()['jobs']['101']['status'] == 'reviewing'
        api.pr = {'draft': True, 'state': 'open', 'merged': False, 'html_url': 'https://github.com/owner/service/pull/1',
                  'head': {'sha': head, 'ref': 'fullops/issue-1-a2', 'repo': {'id': 7}},
                  'base': {'ref': 'main', 'repo': {'id': 7}}}
        with patch('review.check'):
            for field, value in (('ref', 'fullops/issue-999-a2'), ('sha', 'foreign-sha')):
                original = api.pr['head'][field]
                api.pr['head'][field] = value
                fails(lambda: mode.complete(store, api, newer['token'], 101, root, 'key', head, head, 1), 'draft')
                api.pr['head'][field] = original
            mode.complete(store, api, newer['token'], 101, root, 'key', head, head, 1)
        assert store.read()['jobs']['101']['status'] == 'completed'
        # 완료 뒤 draft PR의 실패 check·허용 작성자 수정 요청은 같은 이슈를 새 attempt로 되돌린다.
        api.checks = [{'name': 'ci', 'conclusion': 'success'}]
        api.reviews = [{'state': 'CHANGES_REQUESTED', 'submitted_at': iso(time.time() + 5), 'user': {'id': 99}, 'html_url': 'r1'}]
        mode.poll_prs(store, api, newer['token'])
        assert store.read()['jobs']['101']['status'] == 'completed', '통과 check·허용되지 않은 리뷰어로 되돌림'
        api.checks.append({'name': 'test', 'conclusion': 'failure', 'html_url': 'https://github.com/run'})
        mode.poll_prs(store, api, newer['token'])
        followup = store.read()['jobs']['101']
        assert followup['status'] == 'queued' and followup['pr_feedback'] == ['check test: failure https://github.com/run'], followup
        with store.edit() as state:
            state['jobs']['101'].update(status='completed', pr_feedback=[])
        api.pr = {**api.pr, 'merged': True, 'state': 'closed'}
        mode.poll_prs(store, api, newer['token'])
        merged = store.read()['jobs']['101']
        assert merged['status'] == 'completed' and merged['pr_closed'], '병합된 PR을 계속 봄'
        api.checks, api.reviews = [], []
        # 병합된 이슈 브랜치와 깨끗한 워크트리만 정리하고, 병합 안 된 브랜치와 고유 파일이 남은 워크트리는 남긴다.
        subprocess.run(['git', '-C', str(root), 'update-ref', 'refs/remotes/origin/main', head], check=True)
        for name in ('fullops/issue-1-a1', 'fullops/issue-3-a1'):
            subprocess.run(['git', '-C', str(root), 'branch', name, head], check=True)
        clean, dirty = root.parent / (root.name + '-a1'), root.parent / (root.name + '-a3')
        subprocess.run(['git', '-C', str(root), 'worktree', 'add', '-q', str(clean), 'fullops/issue-1-a1'], check=True)
        subprocess.run(['git', '-C', str(root), 'worktree', 'add', '-q', str(dirty), 'fullops/issue-3-a1'], check=True)
        (dirty / 'local.txt').write_text('keep\n')
        subprocess.run(['git', '-C', str(root), 'branch', 'fullops/issue-2-a1', head], check=True)
        subprocess.run(['git', '-C', str(root), 'commit', '-q', '--allow-empty', '-m', 'unmerged'], check=True,
                       env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com',
                            'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com'})
        subprocess.run(['git', '-C', str(root), 'branch', '-f', 'fullops/issue-2-a1', 'HEAD'], check=True)
        listed = mode.prune(store)
        assert {b['branch'] for b in listed['branches']} == {'fullops/issue-1-a1', 'fullops/issue-3-a1'}, listed
        assert clean.is_dir(), '목록만 볼 때 지움'
        pruned = {b['branch']: b for b in mode.prune(store, apply=True)['branches']}
        assert pruned['fullops/issue-1-a1'].get('removed') and not clean.exists()
        assert 'kept' in pruned['fullops/issue-3-a1'] and (dirty / 'local.txt').is_file()
        branches = mode.integration.git(root, 'branch', '--format=%(refname:short)').splitlines()
        assert 'fullops/issue-2-a1' in branches and 'fullops/issue-3-a1' in branches and 'fullops/issue-1-a1' not in branches
        subprocess.run(['git', '-C', str(root), 'reset', '-q', '--hard', head], check=True)
        subprocess.run(['git', '-C', str(root), 'worktree', 'remove', '--force', str(dirty)], check=True)  # 테스트 정리
        api.pr = {'draft': False, 'state': 'open'}
        with store.edit() as state:
            state['jobs']['101']['status'] = 'reviewing'
        with patch('review.check'):
            fails(lambda: mode.complete(store, api, newer['token'], 101, root, 'key', head, head, 1), 'draft')
        assert store.read()['jobs']['101']['status'] == 'reviewing'

        # 명시 backlog와 반복 silent poll. timer는 모델/dispatch를 호출하지 않는다.
        backlog = repository(root / 'backlog')
        bstore, bapi = mode.Store(backlog), API()
        mode.configure(bstore, bapi, 'owner/service', ['author'], interval=60, backlog=True, approved=True)
        bstart = mode.hook_path(backlog, 'backlog-provider')
        bstart.parent.mkdir()
        bstart.write_text(json.dumps({'provider_session': 'backlog-provider'}))
        bowner = mode.activate(bstore, Orca(), 'backlog-coor', 'backlog-run', 'term', 'backlog-provider')
        bapi.issues = [issue(20, created_at='2000-01-01T00:00:00Z')]
        with patch.object(bapi, 'pages', wraps=bapi.pages) as pages:
            mode.poll(bstore, bapi, bowner['token'])
            assert 'since=' not in pages.call_args_list[0].args[0], 'initial backlog must not use an epoch date filter'
            mode.poll(bstore, bapi, bowner['token'])
            assert 'since=' in pages.call_args_list[1].args[0], 'subsequent polls must preserve incremental intake'
        assert bstore.read()['jobs']['120']['status'] == 'queued'
        # 사이드바 요약은 ON과 현재 이슈를 보이고 lease token은 싣지 않는다.
        summary_path = bstore.path.parent / 'status.json'
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        assert summary['enabled'] and summary['repository'] == 'owner/service', summary
        assert summary['job'] == {'number': 20, 'status': 'queued', 'task_key': None}, summary
        assert bowner['token'] not in summary_path.read_text(encoding='utf-8')
        clock, deadlines = [time.time()], []
        def tick(_):
            deadlines.append(bstore.read()['owner']['expires'])
            clock[0] += 61
            if clock[0] > bowner['expires']:
                mode.stop(bstore, 'backlog-provider')
        with patch.object(mode.time, 'time', side_effect=lambda: clock[0]), patch.object(mode.time, 'sleep', side_effect=tick), patch.object(mode, 'claim', side_effect=AssertionError('poller dispatched')):
            mode.watch(bstore, bapi, Orca(), bowner['token'])
        assert max(deadlines) > bowner['expires'] + 60, 'busy coor must retain its lease without a foreground wait'
        assert bstore.read()['jobs']['120']['attempt'] == 0 and bapi.posts == 0
        assert not json.loads(summary_path.read_text(encoding='utf-8'))['enabled'], 'stop must show OFF in the sidebar'
        # 꺼진 모드는 남은 이슈를 현재 작업으로 보이지 않는다. SQLite 상태는 그대로다.
        assert json.loads(summary_path.read_text(encoding='utf-8'))['job'] is None and bstore.read()['jobs']['120']['status'] == 'queued'
        # 최초 backlog 수집 전에 신규 이슈 전용으로 바꾸면 과거 이슈를 실행하지 않는다.
        new_only = repository(root / 'new-only')
        nstore, napi = mode.Store(new_only), API()
        mode.configure(nstore, napi, 'owner/service', ['author'], backlog=True, approved=True)
        nstart = mode.hook_path(new_only, 'new-only-provider')
        nstart.parent.mkdir()
        nstart.write_text(json.dumps({'provider_session': 'new-only-provider'}))
        mode.activate(nstore, Orca(), 'new-only-coor', 'new-only-run', 'term', 'new-only-provider')
        mode.stop(nstore, 'new-only-provider')
        mode.configure(nstore, napi, 'owner/service', ['author'], backlog=False, approved=True)
        nowner = mode.activate(nstore, Orca(), 'new-only-coor', 'new-only-run', 'term', 'new-only-provider')
        deadline = nstore.read()['owner']['expires']
        with patch.object(mode, 'owner_identity', return_value='replacement-incarnation'):
            fails(lambda: mode.renew(nstore, Orca(), nowner['token']), 'incarnation')
        assert nstore.read()['owner']['expires'] == deadline
        now = 1791541507.000005  # ms→s 환산에서 1 ULP 차이가 발생하는 고정 시각
        with nstore.edit() as state:
            state['owner'].update(session='provider_session:new-only-provider', expires=now + 10)
        with patch.object(mode, 'owner_identity', return_value='incarnation'), patch.object(mode.time, 'time', return_value=now):
            for output in (None, (now - 100) * 1000, (now + 100) * 1000):
                with patch.object(adapter, 'call', return_value={'terminal': {'lastOutputAt': output}}):
                    mode.renew(nstore, adapter, nowner['token'], background=True)
                assert nstore.read()['owner']['expires'] == now + 10, 'stale or missing native activity must not renew a lease'
            with patch.object(adapter, 'call', return_value={'terminal': {'lastOutputAt': (now - 5) * 1000}}):
                mode.renew(nstore, adapter, nowner['token'], background=True)
            assert abs(nstore.read()['owner']['expires'] - (now + 85)) < 1e-6, 'native lease must expire within 90 seconds of activity'
        with nstore.edit() as state:
            state['owner'].update(session='new-only-coor', expires=time.time() + 90)
        napi.issues = [issue(21, created_at='2000-01-01T00:00:00Z'), issue(22)]
        with patch.object(napi, 'pages', wraps=napi.pages) as pages:
            mode.poll(nstore, napi, nowner['token'])
            assert 'since=' in pages.call_args.args[0], 'new-only mode must use a date filter after reconfiguration'
        assert '121' not in nstore.read()['jobs'], 'recent updates must not admit historical issues in new-only mode'
        assert nstore.read()['jobs']['122']['status'] == 'queued'
        pending = mode.claim(nstore, napi, nowner['token'])
        mode.checkpoint(nstore, napi, nowner['token'], 122, 'running',
                        receipt={'task_key': pending['task_key'], 'session': 'new-only-coor', 'received': True})
        mode.stop(nstore, 'new-only-provider')
        next_owner = mode.activate(nstore, Orca(), 'next-coor', 'next-run', 'term', 'new-only-provider')
        class EmptyRun(Orca):
            def call(self, *args):
                return {'tasks': [], 'count': 0, 'workers': [], 'page': {'total': 0, 'hasMore': False}}
        empty_run = EmptyRun()
        fails(lambda: mode.reconcile(nstore, empty_run, next_owner['token'], 122, 'absence alone is not proof'), '수동')
        with nstore.edit() as state:
            state['jobs']['122']['dispatch_intents'] = [{'run': 'previous-dispatch'}]
        fails(lambda: mode.reconcile(nstore, empty_run, next_owner['token'], 122, 'manual audit', not_dispatched=True), 'dispatch')
        with nstore.edit() as state:
            state['jobs']['122']['dispatch_intents'] = []
            state['jobs']['122']['child_runs'] = {'previous-child': {}}
        fails(lambda: mode.reconcile(nstore, empty_run, next_owner['token'], 122, 'manual audit', not_dispatched=True), 'dispatch')
        with nstore.edit() as state:
            state['jobs']['122'].pop('child_runs')
        with patch.object(empty_run, 'call', return_value={'tasks': [], 'count': 0, 'workers': []}):
            fails(lambda: mode.reconcile(nstore, empty_run, next_owner['token'], 122, 'manual audit', not_dispatched=True), '전체')
        with nstore.edit() as state:
            state['jobs']['122']['started'] = 0  # 이전 coor 기간은 새 coor의 실행 시간 한도에 넣지 않는다.
        mode.reconcile(nstore, empty_run, next_owner['token'], 122, 'manually verified owner stopped before dispatch', not_dispatched=True)
        resumed = nstore.read()['jobs']['122']
        assert time.time() - resumed['started'] < 60
        assert resumed['status'] == 'claimed' and resumed['epoch'] == next_owner['epoch']
        assert resumed['attempt'] == 1 and resumed['task_key'] == pending['task_key'] and resumed['receipt'] is None
        mode.checkpoint(nstore, napi, next_owner['token'], 122, 'running',
                        receipt={'task_key': pending['task_key'], 'session': 'next-coor', 'received': True})
        # 미확인 POST가 조회에 없을 때 재게시하지 않는다.
        with store.edit() as state:
            state['owner']['expires'] = time.time() + 90
            entry = next(iter(state['outbox'].values()))
            entry.pop('comment_id')
            entry['status'] = 'uncertain'
            state['jobs']['101'].update(status='running', attempt=1, epoch=state['owner']['epoch'])
        api.comments = []
        fails(lambda: mode.question(store, api, newer['token'], 101, '정보: 규격이 필요합니다. 질문: 크기는? 재개: 규격 확정'), '중복')
        assert api.posts == 3  # 앞서 서로 다른 질문 세 개만 게시했다.
        class SettledOrca:
            def call(self, *args):
                key = store.read()['jobs']['101']['task_key']
                if 'task-list' in args and '--full' not in args:  # Orca 1.4.251의 기본 응답
                    return {'tasks': [{'id': 'task', 'status': 'failed', 'title': 'x'}]}
                if 'task-list' in args:
                    return {'tasks': [{'id': 'task', 'status': 'failed', 'spec': 'Task key: ' + key}], 'count': self.count}
                return {'workers': [{'taskId': 'task', 'projection': {'liveness': {'verdict': self.verdict}}}],
                        'page': {'total': 1, 'hasMore': False}}
            verdict, count = 'unverifiable', 1
        runtime = SettledOrca()
        mode.reconcile(store, runtime, newer['token'], 101, '종료 미확인', syncing=True)
        assert not store.read()['jobs']['101']['settled']
        # 이슈 자신의 Run도 하위 Run처럼 잘린 task 목록으로는 종료를 확정하지 않는다.
        runtime.verdict, runtime.count = 'exited', 2
        fails(lambda: mode.reconcile(store, runtime, newer['token'], 101, '잘린 목록', syncing=True), '전체 task')
        assert not store.read()['jobs']['101']['settled']
        runtime.count = 1
        mode.reconcile(store, runtime, newer['token'], 101, '실제 failed task/종료 receipt', syncing=True)
        assert store.read()['jobs']['101']['status'] == 'held' and store.read()['jobs']['101']['settled']
        with store.edit() as state:
            state['jobs']['101']['status'] = 'running'
        with patch.object(api, 'comment', side_effect=APIError(403)):
            fails(lambda: mode.question(store, api, newer['token'], 101, '질문 권한 검사: 필요한 정보는?'))
        denied = list(store.read()['outbox'].values())[-1]
        assert denied['status'] == 'failed' and '403' in store.read()['jobs']['101']['reason']

    # API pagination/304에서도 이전 next Link를 따라간다. foreign endpoint/redirect는 토큰 전송 전에 거부.
    client = GitHub('secret')
    replies = [(200, {'ETag': 'a', 'Link': '<https://api.github.com/repositories/1300192/issues?page=2>; rel="next"'}, [1]),
               (200, {'ETag': 'b'}, [2])]
    with patch.object(client, 'request', side_effect=replies):
        rows, cache = client.pages('/repos/o/r/issues', {})
    assert rows == [1, 2]
    with patch.object(client, 'request', side_effect=[(304, {}, None), (304, {}, None)]):
        assert client.pages('/repos/o/r/issues', cache)[0] == [1, 2]
    fails(lambda: client.get('https://evil.test/issues'))
    for headers, minimum in (({'Retry-After': '120'}, 120), ({'Retry-After': 'invalid'}, 60),
                             ({'Retry-After': 'Infinity'}, 60), ({'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(time.time() + 180)}, 179)):
        error = urllib.error.HTTPError('https://api.github.com/repos/o/r/issues', 429, 'rate limited', headers, None)
        with patch.object(client.opener, 'open', side_effect=error):
            try: client.get('/repos/o/r/issues')
            except APIError as result:
                assert result.retry_after >= minimum and 'secret' not in str(result)
            else: raise AssertionError('rate limit ignored')
    fails(lambda: SafeRedirect().redirect_request(urllib.request.Request('https://api.github.com/x'), None, 302, '', {}, 'http://api.github.com/x'))
    with patch.object(client, 'request', return_value=(200, {'Link': '<https://api.github.com/repos/foreign/repo/issues>; rel="next"'}, [])):
        fails(lambda: client.pages('/repos/o/r/issues', {}), 'scope')
    assert mode.redact('ghp_' + 'a' * 36) == '[REDACTED]'
    assert mode.redact('API_KEY=private-value') == '[REDACTED]'
    assert mode.redact({'spec': ['GITHUB_TOKEN=abc'], 'n': 1}) == {'spec': ['[REDACTED]'], 'n': 1}
    missing = {'data': {'repository': {'databaseId': 7, 'issue': None}}, 'errors': [{'type': 'NOT_FOUND'}]}
    with patch.object(client, 'request', return_value=(200, {}, missing)):
        assert client.issue('o/r', 1) is None
    handover()
    inert_when_off()
    print('PASS: issue-mode atomic FIFO/lease, author IDs, API recovery/304, question outbox, same-author answers, boundaries, review failure and handover fencing')


if __name__ == '__main__':
    main()
