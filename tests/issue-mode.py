"""격리 Git 저장소에서 이슈 수집→동일 coor claim→질문→답변→새 attempt와 안전 경계를 검증한다."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
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

    def get(self, path):
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
    def identity(self, *args):
        return 'incarnation'


def issue(number, author=42, **changes):
    return {'id': 100 + number, 'repository_id': 7, 'number': number,
            'title': 'work ' + str(number), 'body': 'requirement', 'created_at': iso(time.time()),
            'updated_at': iso(time.time()), 'state': 'open', 'html_url': f'https://github.com/owner/service/issues/{number}',
            'user': {'id': author, 'login': 'author'}, 'edit_verified': True, **changes}


def main():
    # 화면에서 선택된 다른 pane은 소유 identity 검증에 사용하지 않는다.
    adapter = mode.Orca('orca')
    caller = {'caller': {'orcaSessionId': 'coor', 'live': True}}
    pane = {'terminal': {'handle': 'term', 'connected': True, 'incarnationId': 'incarnation'}}
    with patch.object(adapter, 'call', side_effect=[caller, pane, {'run': {'id': 'run'}}]) as call:
        assert adapter.identity('coor', 'run', 'term') == 'incarnation'
        assert call.call_args_list[1].args == ('terminal', 'show', '--terminal', 'term')
        assert call.call_args_list[2].args == ('orchestration', 'run-current', '--from', 'term')
    for status in ({}, {'caller': {'orcaSessionId': 'coor', 'live': False}}):
        with patch.object(adapter, 'call', return_value=status) as call:
            fails(lambda: adapter.identity('coor', 'run', 'term'), 'identity')
            assert call.call_count == 1
    native = {'provider_session': 'host', 'orca_terminal': 'term'}
    with patch.dict('os.environ', {'ORCA_TERMINAL_HANDLE': 'term', 'ORCA_AGENT_SESSION_ID': ''}):
        with patch.object(adapter, 'call', side_effect=[{}, pane, {'run': {'id': 'run'}}]):
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
        root = Path(temporary)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(root)], check=True)
        subprocess.run(['git', '-C', str(root), 'remote', 'add', 'origin', 'https://github.com/owner/service.git'], check=True)
        (root / '.fullops-squad').mkdir()
        (root / '.fullops-squad/fullops.json').write_text(json.dumps({'git': {'remote': 'origin', 'base': 'main'}}))
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
            assert waiting.call_args.args[-1] == token
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
        mode.checkpoint(store, api, token, 101, 'running', receipt=received)
        assert mode.claim(store, api, token) is None  # busy: enqueue만, 다른 issue dispatch 없음

        # POST는 성공했지만 응답이 유실된다. outbox 재조정은 기존 comment를 채택한다.
        api.issues[0]['user']['login'] = 'renamed'
        api.fail_post = True
        fails(lambda: mode.question(store, api, token, 101, '정보: 규격이 필요합니다. 질문: 크기는? 재개: 규격 확정'))
        assert store.read()['jobs']['101']['status'] == 'held' and api.posts == 1
        api.fail_post = False
        q = mode.question(store, api, token, 101, '정보: 규격이 필요합니다. 질문: 크기는? 재개: 규격 확정')
        assert q['comment_id'] == 901 and api.posts == 1
        assert q['body'].startswith('@renamed\n')
        mode.poll_answers(store, api, token)
        assert mode.answer_delivery(store, token) is None  # 동일 계정의 자기 질문
        assert mode.boundary(root, 'provider', 'git push origin main', [], [['git', 'push', 'origin', 'main']])

        second = mode.claim(store, api, token)
        assert second['dependency_review_required'] and second['issue_id'] == '102'
        second_receipt = {'task_key': second['task_key'], 'session': 'coor', 'received': True}
        fails(lambda: mode.checkpoint(store, api, token, 102, 'running', receipt=second_receipt), '의존')
        fails(lambda: mode.checkpoint(store, api, token, 102, 'running', dependencies=['101'], receipt=second_receipt), '의존')
        mode.checkpoint(store, api, token, 102, 'running', dependencies=[], receipt=second_receipt)
        mode.checkpoint(store, api, token, 102, 'held', reason='test failed', resume='owner:coor; 독립 수정 후 검증')
        answer = {'id': 1001, 'body': q['question_id'] + ' 128px', 'user': {'id': 42, 'login': 'renamed'},
                  'created_at': iso(time.time()), 'updated_at': iso(time.time()), 'html_url': 'https://github.com/answer'}
        api.comments.extend([{**answer, 'id': 1000, 'user': {'id': 99, 'login': 'author'}}, answer])
        mode.poll_answers(store, api, token)
        delivered = mode.answer_delivery(store, token)
        assert len(delivered['answer_candidates']) == 1 and delivered['issue_id'] == '101'
        assert mode.answer_delivery(store, token) is None
        mode.resolve_answers(store, api, token, 101, 'insufficient', '질문 ID는 맞지만 단위/높이가 빠짐')
        mode.question(store, api, token, 101, '높이도 알려주세요. 재개 조건: 너비/높이 확정')
        api.comments.append({**answer, 'id': 1002, 'body': '128px x 64px'})
        mode.poll_answers(store, api, token)
        assert len(mode.answer_delivery(store, token)['answer_candidates']) == 1
        mode.resolve_answers(store, api, token, 101, 'sufficient', '질문 연결 및 규격 확정, 권한 확대 없음')
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
        with patch.object(mode.integration, 'orca', side_effect=[projection, listing]):
            assert mode.boundary(root, 'worker', ' '.join(merge), [], [merge], context)
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
        with patch.object(mode.integration, 'orca', return_value=authority):
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
                child = args[-1] == 'child-run'
                task_id = 'task_child' if child else 'task_auto'
                status = self.child_status if child else 'completed'
                if 'task-list' in args:
                    result = {'tasks': [{'id': task_id, 'status': status, 'spec': resumed['task_key']}],
                              'count': self.child_task_count if child else 1}
                    if child and self.child_task_page is not None:
                        result['page'] = self.child_task_page
                    return result
                workers = [{'taskId': task_id, 'projection': {'liveness': {'verdict': 'live' if status == 'running' else 'exited'}}}]
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
            fails(lambda: mode.reconcile(store, nested_runtime, token, 101, 'truncated child tasks', syncing=True), '하위')
            assert not store.read()['jobs']['101']['settled']
        nested_runtime.child_task_count, nested_runtime.child_task_page = 1, {'hasMore': False, 'total': 1}
        nested_runtime.extra_worker = True
        nested_runtime.child_page = {'total': 2, 'hasMore': False}
        fails(lambda: mode.reconcile(store, nested_runtime, token, 101, 'worker started after task listing', syncing=True), '하위')
        assert not store.read()['jobs']['101']['settled']
        nested_runtime.extra_worker = False
        for page in ({}, {'total': 1, 'hasMore': True}, {'total': 2, 'hasMore': False}):
            nested_runtime.child_page = page
            fails(lambda: mode.reconcile(store, nested_runtime, token, 101, 'unknown child fleet', syncing=True), '하위')
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
        assert mode.boundary(root, 'provider', 'python3 build.py', [], [['python3', 'build.py']])
        with store.edit() as state:
            state['config']['allowed'] = allowed
        for words in (['gh', 'pr', 'merge', '1'], ['gh', 'issue', 'close', '1'], ['curl', 'https://evil'],
                      ['git', 'push', 'origin', 'main'], ['git', 'reset', '--hard'], ['gh', 'api', 'repos/x']):
            assert mode.boundary(root, 'provider', ' '.join(words), [], [words]), words
        assert mode.boundary(root, 'foreign', 'git reset --hard', [], [['git', 'reset', '--hard']]) is None
        assert mode.boundary(root, 'provider', '', [('../outside', 'x')], [])
        api.issues[0]['user']['login'] = 'renamed'
        assert mode.fresh(store.read(), api, store.read()['jobs']['101']) is None  # stable ID
        api.issues[0]['body'] = 'edited externally'
        mode.poll(store, api, token)
        assert store.read()['jobs']['101']['status'] == 'changed'
        assert mode.boundary(root, 'provider', 'python3 build.py', [], [['python3', 'build.py']])
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
        for words in (['python3', 'build.py', script, 'status'], ['python3', '-c', 'product_change()', script, 'status'],
                      ['python3', script, '--repo', str(root / 'foreign'), 'status'],
                      ['python3', script, 'disable', '--session', 'foreign']):
            assert mode.boundary(root, 'provider', ' '.join(words), [], [words])
        assert mode.boundary(root, 'provider', 'python3 build.py', [], [['python3', 'build.py']])

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
        api.pr = {'draft': False, 'state': 'open'}
        with store.edit() as state:
            state['jobs']['101']['status'] = 'reviewing'
        with patch('review.check'):
            fails(lambda: mode.complete(store, api, newer['token'], 101, root, 'key', head, head, 1), 'draft')
        assert store.read()['jobs']['101']['status'] == 'reviewing'

        # 명시 backlog와 반복 silent poll. timer는 모델/dispatch를 호출하지 않는다.
        backlog = root / 'backlog'
        backlog.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(backlog)], check=True)
        subprocess.run(['git', '-C', str(backlog), 'remote', 'add', 'origin', 'https://github.com/owner/service.git'], check=True)
        (backlog / '.fullops-squad').mkdir()
        (backlog / '.fullops-squad/fullops.json').write_text((root / '.fullops-squad/fullops.json').read_text())
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
        # 최초 backlog 수집 전에 신규 이슈 전용으로 바꾸면 과거 이슈를 실행하지 않는다.
        new_only = root / 'new-only'
        new_only.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(new_only)], check=True)
        subprocess.run(['git', '-C', str(new_only), 'remote', 'add', 'origin', 'https://github.com/owner/service.git'], check=True)
        (new_only / '.fullops-squad').mkdir()
        (new_only / '.fullops-squad/fullops.json').write_text((root / '.fullops-squad/fullops.json').read_text())
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
        now = time.time()
        with nstore.edit() as state:
            state['owner'].update(session='provider_session:new-only-provider', expires=now + 10)
        with patch.object(mode, 'owner_identity', return_value='incarnation'), patch.object(mode.time, 'time', return_value=now):
            for output in (None, (now - 100) * 1000, (now + 100) * 1000):
                with patch.object(adapter, 'call', return_value={'terminal': {'lastOutputAt': output}}):
                    mode.renew(nstore, adapter, nowner['token'], background=True)
                assert nstore.read()['owner']['expires'] == now + 10, 'stale or missing native activity must not renew a lease'
            with patch.object(adapter, 'call', return_value={'terminal': {'lastOutputAt': (now - 5) * 1000}}):
                mode.renew(nstore, adapter, nowner['token'], background=True)
            assert nstore.read()['owner']['expires'] == now + 85, 'native lease must expire within 90 seconds of activity'
        with nstore.edit() as state:
            state['owner']['session'] = 'new-only-coor'
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
            fails(lambda: mode.reconcile(nstore, empty_run, next_owner['token'], 122, 'manual audit', not_dispatched=True), 'dispatch')
        mode.reconcile(nstore, empty_run, next_owner['token'], 122, 'manually verified owner stopped before dispatch', not_dispatched=True)
        resumed = nstore.read()['jobs']['122']
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
        assert api.posts == 2  # 앞서 서로 다른 질문 두 개만 게시했다.
        class SettledOrca:
            def call(self, *args):
                key = store.read()['jobs']['101']['task_key']
                if 'task-list' in args:
                    return {'tasks': [{'id': 'task', 'status': 'failed', 'spec': 'Task key: ' + key}]}
                return {'workers': [{'taskId': 'task', 'projection': {'liveness': {'verdict': self.verdict}}}]}
            verdict = 'unverifiable'
        runtime = SettledOrca()
        mode.reconcile(store, runtime, newer['token'], 101, '종료 미확인', syncing=True)
        assert not store.read()['jobs']['101']['settled']
        runtime.verdict = 'exited'
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
    replies = [(200, {'ETag': 'a', 'Link': '<https://api.github.com/repos/o/r/issues?page=2>; rel="next"'}, [1]),
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
    print('PASS: issue-mode atomic FIFO/lease, author IDs, API recovery/304, question outbox, same-author answers, boundaries and review failure')


if __name__ == '__main__':
    main()
