#!/usr/bin/env python3
"""선택형 GitHub 이슈 intake. 동일 coor의 foreground wait만 전달 경로로 사용한다."""
import argparse
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
import time

import integration
import orca_wait
from issue_github import APIError, GitHub, iso, timestamp

ACTIVE = {'claimed', 'running', 'reviewing', 'reconciling'}
HELD = {'held', 'awaiting_author', 'reconciling', 'changed', 'policy_hold'}
FINAL = {'completed', 'cancelled', 'rejected'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def snapshot(issue):
    value = {k: issue.get(k) for k in ('id', 'repository_id', 'number', 'html_url', 'user',
                                     'title', 'body', 'created_at', 'updated_at', 'edit_verified', 'state')}
    value['source_digest'] = digest([issue.get('title'), issue.get('body')])
    for field in ('title', 'body'):
        value[field] = redact(value[field] or '')
    return value


def redact(text):
    text = re.sub(r'(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{16,}', '[REDACTED]', text)
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----', '[REDACTED]', text)
    return re.sub(r'(?im)\b(?:authorization\s*:\s*bearer|[A-Z_]*(?:API_KEY|TOKEN|PASSWORD|SECRET)\s*[=:])\s*[^\s,;]+', '[REDACTED]', text)


def safe_pages(pages):
    # 비밀값이 있는 페이지는 재조회한다. 원문 digest와 304 캐시를 혼동하지 않는다.
    return {key: value for key, value in pages.items()
            if redact(json.dumps(value, ensure_ascii=False)) == json.dumps(value, ensure_ascii=False)}


def occupies(job):
    return job['status'] in ACTIVE or bool(job.get('dispatch_intents') and not job.get('settled'))


def local_file(store, name):
    candidate = Path(name)
    candidate = candidate if candidate.is_absolute() else store.repo / candidate
    candidate = candidate.resolve()
    relative = candidate.relative_to(store.repo)
    if any(p.lower().startswith('.env') or p.lower() in ('.git', '.codex', '.claude', 'auth.json', 'credentials.json') for p in relative.parts):
        raise ValueError('credential/실행 권한 파일은 자동 이슈 입력으로 읽을 수 없습니다')
    return candidate


class Store:
    def __init__(self, repo):
        self.repo = Path(repo).resolve()
        directory = integration.directory(self.repo).parent / 'fullops-issues'
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / 'state.sqlite'
        if self.path.is_file():
            return
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO state VALUES (1,?)', (json.dumps({
                'schema': 1, 'config': None, 'owner': None, 'epoch': 0, 'jobs': {}, 'pages': {},
                'cursor': None, 'outbox': {}, 'comments': {}, 'events': []}),))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute('PRAGMA synchronous=FULL')
        return db

    @contextmanager
    def edit(self):
        # ponytail: 단일 저장소의 queue JSON을 직렬화한다. 대규모 backlog는 indexed rows로 전환한다.
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            state = json.loads(db.execute('SELECT data FROM state WHERE id=1').fetchone()[0])
            yield state
            db.execute('UPDATE state SET data=? WHERE id=1', (json.dumps(state, ensure_ascii=False),))
            db.commit()
        finally:
            db.close()  # 예외면 rollback. cursor, enqueue, claim, outbox는 같은 transaction이다.

    def read(self):
        with closing(self.connect()) as db:
            return json.loads(db.execute('SELECT data FROM state WHERE id=1').fetchone()[0])


def record(state, kind, **data):
    state['events'].append({'at': iso(time.time()), 'type': kind, **data})


def remote_identity(repo, repository):
    connection = integration.config(repo).get('git') or {}
    if not connection.get('remote') or not connection.get('base'):
        raise ValueError('remote/base가 확인된 FullOps setup이 필요합니다')
    for flags in ((), ('--push',)):
        urls = integration.git(repo, 'remote', 'get-url', *flags, '--all', connection['remote']).splitlines()
        expected = repository.lower()
        if len(urls) != 1 or urls[0].lower().removesuffix('.git').rstrip('/') not in (
                'https://github.com/' + expected, 'git@github.com:' + expected, 'ssh://git@github.com/' + expected):
            raise ValueError('fetch/push remote가 명시한 GitHub 저장소와 다릅니다')
    return connection


def configure(store, github, repository, users, interval=300, backlog=False,
              max_attempts=3, max_seconds=3600, max_tokens=100000, approved=False):
    if approved is not True:
        raise ValueError('사용자가 구현/검증/리뷰/작업 브랜치 push/draft PR/동일 이슈 질문 범위를 선택해야 합니다')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('명시적인 owner/repository가 필요합니다')
    if type(interval) is not int or interval < 60 or not users:
        raise ValueError('주기 >= 60초와 명시적인 허용 GitHub ID가 필요합니다')
    if any(type(n) is not int or n <= 0 for n in (max_attempts, max_seconds, max_tokens)):
        raise ValueError('재시도/시간/보고된 모델 토큰 한도는 양의 정수입니다')
    repository_info = github.get('/repos/' + repository)
    if not isinstance(repository_info, dict) or type(repository_info.get('id')) is not int or repository_info['id'] <= 0:
        raise ValueError('GitHub 저장소 stable ID를 확인하지 못했습니다')
    remote_identity(store.repo, repository_info['full_name'])
    if repository_info.get('permissions', {}).get('push') is not True:
        raise ValueError('초안 PR용 작업 브랜치 push 권한을 확인하지 못했습니다')
    allowed = {}
    for login in users:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:\[bot\])?', login):
            raise ValueError('GitHub login 형식 오류')
        user = github.get('/users/' + login)
        if not isinstance(user, dict) or type(user.get('id')) is not int or user['id'] <= 0 or user.get('type') not in ('User', 'Bot'):
            raise ValueError('확인되지 않은 GitHub 사용자')
        allowed[str(user['id'])] = {'id': user['id'], 'login': user['login'], 'type': user['type']}
    with store.edit() as state:
        if state['owner'] and state['owner']['enabled']:
            raise ValueError('활성 모드를 먼저 disable한 뒤 사용자가 설정을 변경하세요')
        old = state['config']
        if old and old['repository_id'] != repository_info['id']:
            raise ValueError('대기열이 있는 저장소 identity를 변경할 수 없습니다')
        state['config'] = {'repository': repository_info['full_name'], 'repository_id': repository_info['id'],
                           'allowed': allowed, 'interval': interval, 'backlog': bool(backlog),
                           'max_attempts': max_attempts, 'max_seconds': max_seconds, 'max_tokens': max_tokens,
                           'branch_prefix': 'fullops/issue-', 'scope': ['implementation', 'tests', 'review',
                           'deliverables', 'branch_push', 'draft_pr', 'author_questions']}
        for job in state['jobs'].values():
            if str(job['snapshot']['user']['id']) not in allowed and job['status'] not in FINAL:
                job.update(status='policy_hold', reason='작성자 allowlist 철회', resume='사용자의 명시적 재등록')
        record(state, 'configured', allowed_ids=list(allowed), interval=interval)


class Orca:
    def __init__(self, executable):
        if not executable:
            raise ValueError('지원되는 Orca 실행 파일을 확인하지 못했습니다')
        self.executable = executable

    def call(self, *args):
        result = subprocess.run([self.executable, *args, '--json'], capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        try:
            data = json.loads(result.stdout)
        except ValueError:
            raise ValueError('Orca 응답을 확인하지 못했습니다') from None
        if result.returncode or not isinstance(data, dict) or not data.get('ok') or not isinstance(data.get('result'), dict):
            raise ValueError('Orca 조회/전달 실패; 실행 상태는 미확인입니다')
        result = data['result']
        if data.get('caller'):
            result = {**result, 'caller': data['caller']}
        return result

    def identity(self, session, run, terminal, provider_session=None, hook=None):
        status = self.call('status')
        caller = status.get('caller')
        if caller is None and not os.getenv('ORCA_AGENT_SESSION_ID'):
            # Orca terminal agents have no Orca session ID; their native host session is the owner.
            valid = (provider_session and session == 'provider_session:' + provider_session and
                     os.getenv('ORCA_TERMINAL_HANDLE') == terminal and hook and
                     hook.get('provider_session') == provider_session and
                     hook.get('orca_terminal') == terminal)
        else:
            valid = (isinstance(caller, dict) and caller.get('orcaSessionId') == session and
                     caller.get('live') is True)
        if not valid:
            raise ValueError('Orca가 현재 coor session identity를 증명하지 못합니다; 활성화 blocked')
        pane = self.call('terminal', 'show', '--terminal', terminal)['terminal']
        info = self.call('orchestration', 'run-current', '--from', terminal).get('run') or {}
        if (pane.get('handle') != terminal or info.get('id') != run or
                not pane.get('connected') or pane.get('orphaned') or not pane.get('incarnationId')):
            raise ValueError('현재 Run 소유 coor와 살아 있는 같은 terminal을 확인하지 못했습니다')
        return pane['incarnationId']


def owner_identity(store, orca, owner):
    hook = hook_path(store.repo, owner['provider_session'])
    receipt = json.loads(hook.read_text()) if hook.is_file() else {}
    if receipt.get('provider_session') != owner['provider_session']:
        raise ValueError('현재 host SessionStart receipt가 없습니다; 활성화 blocked')
    if owner['session'].startswith('provider_session:'):
        binding = hook_path(store.repo, 'terminal-' + owner['terminal'])
        current = json.loads(binding.read_text()) if binding.is_file() else {}
        if current.get('provider_session') != owner['provider_session'] or current.get('orca_terminal') != owner['terminal']:
            raise ValueError('현재 terminal의 native SessionStart binding이 다릅니다; 활성화 blocked')
    return orca.identity(owner['session'], owner['run'], owner['terminal'], owner['provider_session'], receipt)


def activate(store, orca, session, run, terminal, provider_session, now=None):
    now = time.time() if now is None else now
    incarnation = owner_identity(store, orca, {'session': session, 'run': run, 'terminal': terminal,
                                             'provider_session': provider_session})
    with store.edit() as state:
        config = state['config']
        if not config or not config['allowed']:
            raise ValueError('사용자 설정과 API로 확인한 allowlist가 필요합니다')
        remote_identity(store.repo, config['repository'])
        old = state['owner']
        if old and old['enabled'] and old['expires'] > now and not Path(old['end_marker']).is_file():
            raise ValueError('같은 저장소에서 이미 활성 coor가 lease를 소유합니다')
        for job in state['jobs'].values():
            if occupies(job):
                job.update(status='reconciling', reason='이전 session task/worker/receipt 확인 필요',
                           resume='정본 receipt를 확인하여 checkpoint reconcile 실행')
            elif job['status'] not in FINAL and job.get('attempt'):
                job['epoch'] = state['epoch'] + 1  # 질문/보류 기록의 소유 인계. 자동 실행은 하지 않는다.
        state['epoch'] += 1
        owner = {'session': session, 'provider_session': provider_session, 'run': run, 'terminal': terminal, 'incarnation': incarnation,
                 'epoch': state['epoch'], 'token': secrets.token_hex(24), 'enabled': True, 'paused': False,
                 'expires': now + 90, 'end_marker': str(store.path.parent / f'lease-stop-{state["epoch"]}.json')}
        state['owner'] = owner
        if state['cursor'] is None:
            state['cursor'] = '1970-01-01T00:00:00Z' if config['backlog'] else iso(now)
            state['since_created'] = state['cursor']
        record(state, 'activated', session=session, run=run, epoch=owner['epoch'])
        return owner


def guard(state, token, now=None):
    owner = state['owner']
    if (not owner or not owner['enabled'] or owner['token'] != token or
            Path(owner['end_marker']).is_file() or owner['expires'] <= (time.time() if now is None else now)):
        raise ValueError('모드 OFF, 만료되거나 다른 coor의 fencing token입니다')
    return owner


def stop(store, session, action='disable'):
    owner = store.read()['owner']
    if owner and session in (owner['session'], owner['provider_session']) and action not in ('pause', 'resume'):
        from storage import write_json
        # SessionEnd deadline 중 DB writer가 바빠도 먼저 신규 실행을 fencing한다.
        write_json(Path(owner['end_marker']), {'session': session, 'epoch': owner['epoch']})
    with store.edit() as state:
        owner = state['owner']
        if owner and session in (owner['session'], owner['provider_session']):
            if action == 'pause':
                owner['paused'] = True
            elif action == 'resume':
                guard(state, owner['token'])
                owner['paused'] = False
                owner.pop('blocked', None)
            else:
                owner.update(enabled=False, expires=0)
            record(state, action, session=session)
            return True
    return False


def hook_path(repo, session):
    if not session:
        raise ValueError('host session ID가 필요합니다')
    key = re.sub(r'[^A-Za-z0-9_-]', '_', str(session))[:100]
    return Path(integration.git(repo, 'rev-parse', '--absolute-git-dir')) / 'fullops-gate' / ('flow-' + key + '.json')


def heartbeat(repo, session):
    path = integration.directory(repo).parent / 'fullops-issues/state.sqlite'
    if path.is_file():
        with Store(repo).edit() as state:
            owner = state['owner']
            if owner and owner['provider_session'] == session and owner['enabled'] and owner['expires'] > time.time():
                owner['expires'] = time.time() + 90


def fresh(state, github, job, issue=None):
    config = state['config']
    issue = issue or github.issue(config['repository'], job['snapshot']['number'])
    if issue['id'] != job['snapshot']['id'] or issue['repository_id'] != config['repository_id']:
        raise ValueError('GitHub issue/repository identity 불일치')
    if str(issue['user']['id']) not in config['allowed']:
        return 'policy_hold', '작성자 allowlist 철회'
    if issue['state'] != 'open':
        return 'cancelled', 'GitHub issue가 닫혔습니다'
    if not issue.get('edit_verified'):
        return 'changed', '본문의 편집 주체를 원래 작성자로 확인하지 못했습니다'
    original = {k: job['snapshot'][k] for k in ('title', 'body')}
    if (job['snapshot']['user']['id'] != issue['user']['id'] or job['snapshot']['source_digest'] != digest([issue.get('title'), issue.get('body')]) or
            digest(original) != digest({k: redact(issue[k] or '') for k in original})):
        return 'changed', '실행 snapshot과 이슈 본문이 다릅니다; 작성자 재확인/새 attempt 필요'
    return None


def poll(store, github, token):
    saved = store.read()
    guard(saved, token)
    if saved['owner']['paused']:
        return
    config = saved['config']
    since = iso(timestamp(saved['cursor']) - 1)  # 같은 초 경계와 오프라인 복귀를 포함한다.
    path = f"/repos/{config['repository']}/issues?state=all&sort=created&direction=asc&per_page=100&since={since}"
    issues, cache = github.pages(path, safe_pages(saved['pages']))
    # 모든 네트워크 결과가 준비된 뒤 cursor와 enqueue를 함께 commit한다.
    with store.edit() as state:
        guard(state, token)
        if state['owner']['paused']:
            return
        for issue in issues:
            if 'pull_request' in issue:
                continue
            identifier = str(issue['id'])
            if identifier in state['jobs']:
                continue  # edit/reopen/comment를 새로운 작업으로 재실행하지 않는다.
            if timestamp(issue['created_at']) < timestamp(state['since_created']):
                continue
            status, reason = 'queued', ''
            if str(issue['user']['id']) not in state['config']['allowed']:
                status, reason = 'rejected', '등록되지 않은 작성자'
            elif issue['state'] != 'open':
                status, reason = 'cancelled', '닫힌 이슈'
            item = snapshot({**issue, 'repository_id': config['repository_id']})
            state['jobs'][identifier] = {'snapshot': item, 'digest': digest(item), 'status': status,
                                        'reason': reason, 'resume': '', 'attempt': 0, 'dependencies': None,
                                        'tokens': 0, 'history': [], 'answers': [], 'questions': []}
            record(state, 'discovered', issue_id=identifier, status=status)
        if issues:
            state['cursor'] = max([state['cursor']] + [i['updated_at'] for i in issues])
        state['pages'] = {k: v for k, v in state['pages'].items() if '/comments' in k}
        state['pages'] = safe_pages({**state['pages'], **cache})
    poll_answers(store, github, token)
    saved = store.read()
    observations = {identifier: (job['digest'], fresh(saved, github, job))
                    for identifier, job in saved['jobs'].items() if job['status'] in ACTIVE and job['status'] != 'reconciling'}
    with store.edit() as state:
        guard(state, token)
        for identifier, (fingerprint, denial) in observations.items():
            job = state['jobs'][identifier]
            if denial and job['digest'] == fingerprint and job['status'] in ACTIVE:
                job.update(status=denial[0], reason=denial[1], resume='작업을 안전 경계에서 보존하고 작성자 재확인')


def claim(store, github, token):
    saved = store.read()
    owner = guard(saved, token)
    if owner['paused'] or any(occupies(j) for j in saved['jobs'].values()):
        return None
    ordered = sorted(saved['jobs'].items(), key=lambda pair: (pair[1]['snapshot']['created_at'], pair[1]['snapshot']['number']))
    for identifier, previous in ordered:
        if previous['status'] != 'queued':
            continue
        denial = fresh(saved, github, previous)
        with store.edit() as state:
            owner = guard(state, token)
            if owner['paused'] or any(occupies(j) for j in state['jobs'].values()):
                return None
            config, job = state['config'], state['jobs'][identifier]
            if job['status'] != 'queued' or job['digest'] != previous['digest']:
                continue
            if any(state['jobs'].get(str(d), {}).get('status') != 'completed' for d in job['dependencies'] or []):
                continue
            if str(job['snapshot']['user']['id']) not in config['allowed']:
                denial = 'policy_hold', '작성자 allowlist 철회'
            if denial:
                job.update(status=denial[0], reason=denial[1], resume='현재 작성자/본문/권한을 확인하세요')
                continue
            if job['attempt'] >= config['max_attempts']:
                job.update(status='held', reason='재시도 한도', resume='사용자가 한도를 변경하거나 취소')
                continue
            job.update(status='claimed', epoch=owner['epoch'], started=time.time(), run=owner['run'],
                       coor_session=owner['session'], receipt=None,
                       attempt=job['attempt'] + 1, task_key=f"GH-{config['repository_id']}-{job['snapshot']['number']}-A{job['attempt'] + 1}")
            job['history'].append({'phase': 'claimed', 'at': iso(time.time()), 'task_key': job['task_key'],
                                   'attempt': job['attempt'], 'run': owner['run'], 'session': owner['session'], 'digest': job['digest']})
            record(state, 'delivered', issue_id=identifier, task_key=job['task_key'], epoch=owner['epoch'])
            return {'issue_id': identifier, 'task_key': job['task_key'], 'attempt': job['attempt'],
                    'branch': config['branch_prefix'] + f"{job['snapshot']['number']}-a{job['attempt']}",
                    'snapshot': job['snapshot'], 'digest': job['digest'], 'answers': job['answers'],
                    'scope': config['scope'], 'receipt_required': True,
                    'dependency_review_required': job['dependencies'] is None and any(j['status'] in HELD for j in state['jobs'].values())}


def checkpoint(store, github, token, identifier, phase, *, reason='', resume='', dependencies=None,
               tokens=0, receipt=None):
    saved = store.read()
    guard(saved, token)
    previous = saved['jobs'][str(identifier)]
    denial = fresh(saved, github, previous)
    with store.edit() as state:
        owner = guard(state, token)
        job = state['jobs'][str(identifier)]
        if job.get('epoch') != owner['epoch']:
            raise ValueError('이전 coor의 attempt입니다. 먼저 정본 receipt를 reconcile하세요')
        if job['task_key'] != previous['task_key'] or job['digest'] != previous['digest']:
            raise ValueError('작성자 검사 중 attempt/snapshot이 바뀌었습니다')
        if type(tokens) is not int or tokens < 0:
            raise ValueError('실제 확인한 모델 사용량만 양의 정수/0으로 기록하세요')
        job['tokens'] += tokens
        if str(job['snapshot']['user']['id']) not in state['config']['allowed']:
            denial = 'policy_hold', '작성자 allowlist 철회'
        if denial:
            job.update(status=denial[0], reason=denial[1], resume='사용자/작성자 재확인')
            return job['status']
        if time.time() - job['started'] > state['config']['max_seconds'] or job['tokens'] > state['config']['max_tokens']:
            job.update(status='held', reason='실행 시간/보고된 모델 사용량 한도', resume='사용자가 한도와 실제 사용량 확인')
            return 'held'
        if dependencies is not None:
            if (not isinstance(dependencies, list) or any(not isinstance(d, str) for d in dependencies) or
                    len(set(dependencies)) != len(dependencies) or str(identifier) in dependencies or any(d not in state['jobs'] for d in dependencies)):
                raise ValueError('확인 가능한 다른 issue ID만 dependencies에 넣으세요')
            job['dependencies'] = dependencies
        if phase in ('held', 'awaiting_author', 'changed', 'cancelled'):
            if not reason or not resume:
                raise ValueError('보류/취소의 사유와 재개 조건이 필요합니다')
        elif phase in ('running', 'reviewing'):
            if any(occupies(j) for key, j in state['jobs'].items() if key != str(identifier)):
                raise ValueError('다른 이슈의 task/worker가 아직 종료되지 않았습니다')
            if job['dependencies'] is None and any(j['status'] in HELD for j in state['jobs'].values()):
                raise ValueError('보류 이슈와의 의존 여부를 먼저 명시적으로 검토하세요')
            if not isinstance(receipt, dict) or not receipt:
                raise ValueError('실제 수신/task/worker 또는 리뷰 receipt가 필요합니다')
            if (job['status'] not in ('claimed', 'running', 'reviewing') or receipt.get('task_key') != job['task_key'] or
                    receipt.get('session') != owner['session'] or receipt.get('received') is not True):
                raise ValueError('실제 동일 coor가 수신한 현재 task key/session receipt가 필요합니다')
            if any(state['jobs'].get(str(d), {}).get('status') != 'completed' for d in job['dependencies'] or []):
                raise ValueError('아직 완료되지 않은 의존 이슈입니다')
            if phase == 'reviewing' and job['status'] != 'running':
                raise ValueError('실행 수신/시작을 기록한 뒤 리뷰하세요')
            if phase == 'reviewing' and job.get('dispatch_intents') and not job.get('settled'):
                raise ValueError('기존 worker의 확정 완료/종료 증거를 sync로 먼저 확인하세요')
        elif phase == 'queued':
            if not reason or job['status'] != 'held' or not job.get('settled'):
                raise ValueError('재시도는 보류 사유와 기존 task/worker의 확정 종료 증거가 필요합니다')
        else:
            raise ValueError('지원하지 않는 checkpoint phase')
        job['history'].append({'at': iso(time.time()), 'phase': phase, 'reason': reason, 'receipt': receipt})
        job.update(status=phase, reason=reason, resume=resume, receipt=receipt or job.get('receipt'))
        record(state, 'checkpoint', issue_id=str(identifier), phase=phase)
        return phase


def question(store, github, token, identifier, text):
    if not text.strip() or len(text) > 20000 or redact(text) != text:
        raise ValueError('질문은 비밀정보 없는 구체적인 정보 요청이어야 합니다')
    identifier = str(identifier)
    saved = store.read()
    guard(saved, token)
    author = github.issue(saved['config']['repository'], saved['jobs'][identifier]['snapshot']['number'])
    if fresh(saved, github, saved['jobs'][identifier], author):
        raise ValueError('현재 snapshot/작성자 정책을 재확인하세요')
    with store.edit() as state:
        guard(state, token)
        job = state['jobs'][identifier]
        question_id = digest([identifier, job['attempt'], text])[:24]
        recovery = state['outbox'].get(question_id)
        if (job['status'] not in ACTIVE | {'awaiting_author'} and not recovery) or job.get('epoch') != state['owner']['epoch']:
            raise ValueError('현재 claim한 이슈에서만 질문할 수 있습니다')
        if job['digest'] != saved['jobs'][identifier]['digest'] or str(job['snapshot']['user']['id']) not in state['config']['allowed']:
            raise ValueError('질문 준비 중 snapshot/작성자 정책이 바뀌었습니다')
        marker = '<!-- fullops-question:' + question_id + ' -->'
        existing = state['outbox'].get(question_id)
        if existing and existing.get('comment_id'):
            return existing
        if len(job['questions']) >= state['config']['max_attempts'] * 3:
            raise ValueError('질문/재확인 한도; 사용자에게 보류 상태를 알리세요')
        body = (f"@{author['user']['login']}\n\n질문 ID: {question_id}\n"
                f"Task: {job['task_key']} / attempt {job['attempt']}\n\n{text}\n\n"
                f"이 질문 ID를 적어 답변해 주세요. 답변의 충분성과 실행 범위를 확인한 뒤 같은 과제를 재개합니다.\n{marker}")
        state['outbox'].setdefault(question_id, {'issue_id': identifier, 'marker': marker, 'body': body,
                                      'status': 'prepared', 'question_id': question_id, 'created_at': iso(time.time()), 'attempts': 0})
        entry = state['outbox'][question_id]
        if entry['status'] not in ('sending', 'uncertain'):
            entry['body'] = body  # 미전송/확정 실패인 경우에만 최신 login으로 갱신한다.
        body = entry['body']
        record(state, 'question_prepared', issue_id=identifier, question_id=question_id)
    # ambiguous POST를 재시도하기 전에 기존 댓글의 발신 표식을 먼저 조회한다.
    saved = store.read()
    comments, _ = github.pages(f"/repos/{saved['config']['repository']}/issues/{job['snapshot']['number']}/comments?per_page=100", {})
    sender = github.get('/user')['id']
    matches = [c for c in comments if marker in (c.get('body') or '') and c.get('body') == body
               and c.get('user', {}).get('id') == sender]
    if len(matches) > 1:
        raise ValueError('중복 질문 전송이 발견됐습니다. 수동 확인 필요')
    current = store.read()
    guard(current, token)
    if fresh(current, github, current['jobs'][identifier]):
        raise ValueError('질문 전송 직전의 정책/본문이 변경됐습니다')
    with store.edit() as state:
        guard(state, token)
        entry = state['outbox'][question_id]
        if entry.get('comment_id'):
            return entry
        if not matches and entry['status'] in ('sending', 'uncertain'):
            raise ValueError('이전 질문 POST 결과가 미확인입니다. 조회에 없다는 이유로 중복 게시하지 않습니다')
        if not matches and (entry.get('attempts', 0) >= state['config']['max_attempts'] or entry.get('next_attempt', 0) > time.time()):
            raise ValueError('질문 전송 한도/backoff 중입니다. 사유·권한을 확인 후 재개하세요')
        entry['status'] = 'sending'
        if not matches:
            entry['attempts'] = entry.get('attempts', 0) + 1
    try:
        sent = matches[0] if matches else github.comment(saved['config']['repository'], job['snapshot']['number'], body)
    except (APIError, OSError) as error:
        with store.edit() as state:
            guard(state, token)
            if state['outbox'][question_id].get('comment_id'):
                return state['outbox'][question_id]
            definite = isinstance(error, APIError) and isinstance(error.status, int) and error.status in (401, 403, 404, 422, 429)
            state['outbox'][question_id].update(status='failed' if definite else 'uncertain',
                                              next_attempt=time.time() + (error.retry_after if isinstance(error, APIError) else 60))
            state['jobs'][identifier].update(status='held', reason=f'질문 게시 거부 HTTP {error.status}' if definite else '질문 전송 결과 미확인',
                                             resume='같은 질문의 outbox/권한/backoff를 확인하여 재조정')
        raise
    with store.edit() as state:
        guard(state, token)
        entry = state['outbox'][question_id]
        entry.update(status='sent', comment_id=sent['id'], url=sent['html_url'], created_at=sent['created_at'])
        job = state['jobs'][identifier]
        if question_id not in job['questions']:
            job['questions'].append(question_id)
        job.update(status='awaiting_author', reason='작성자 답변 대기', resume='질문에 충분한 작성자 답변')
        return entry


def poll_answers(store, github, token):
    saved = store.read()
    for identifier, job in saved['jobs'].items():
        if not job['questions'] or job['status'] in FINAL:
            continue
        path = f"/repos/{saved['config']['repository']}/issues/{job['snapshot']['number']}/comments?per_page=100"
        comments, cache = github.pages(path, safe_pages(saved['pages']))
        with store.edit() as state:
            guard(state, token)
            current = state['jobs'][identifier]
            own = {o.get('comment_id') for o in state['outbox'].values()}
            seen = set()
            for comment in comments:
                key = str(comment['id'])
                seen.add(key)
                previous = state['comments'].get(key)
                fingerprint = digest(comment.get('body') or '')
                if previous:
                    if previous.get('candidate') and previous['digest'] != fingerprint:
                        previous['changed'] = True
                        current.update(status='changed', reason='이미 관측한 댓글 수정', resume='작성자의 새 확인 댓글')
                    continue
                state['comments'][key] = {'issue_id': identifier, 'digest': fingerprint, 'processed': False,
                                          'candidate': False, 'snapshot': {**comment, 'body': redact(comment.get('body') or '')}}
                author = comment.get('user') or {}
                if (comment['id'] in own or '<!-- fullops-question:' in (comment.get('body') or '') or
                        author.get('id') != job['snapshot']['user']['id'] or str(author.get('id')) not in state['config']['allowed']):
                    state['comments'][key]['processed'] = True
                    continue
                # REST 댓글에는 편집자 provenance가 없다. 수정된 댓글은 새 지시로 자동 수용하지 않는다.
                if comment['updated_at'] != comment['created_at']:
                    state['comments'][key]['processed'] = True
                    current.update(status='changed', reason='댓글 편집자 provenance 미확인', resume='작성자의 새 확인 댓글')
                    continue
                if any(timestamp(comment['created_at']) >= timestamp(state['outbox'][q].get('created_at', '1970-01-01T00:00:00Z'))
                       for q in job['questions']):
                    state['comments'][key]['candidate'] = True
                    current['answers'].append({'comment_id': comment['id'], 'url': comment['html_url'],
                                               'body': redact(comment['body'] or ''), 'digest': fingerprint, 'received': False, 'decided': False})
            for key, comment in state['comments'].items():
                if comment['issue_id'] == identifier and key not in seen and comment.get('candidate'):
                    current.update(status='changed', reason='사용한 답변 댓글 삭제', resume='작성자의 새 확인 댓글')
            state['pages'] = safe_pages({**state['pages'], **cache})


def answer_delivery(store, token):
    with store.edit() as state:
        guard(state, token)
        if state['owner']['paused'] or any(j['status'] in ACTIVE for j in state['jobs'].values()):
            return None
        for identifier, job in state['jobs'].items():
            if str(job['snapshot']['user']['id']) not in state['config']['allowed']:
                continue
            answers = [a for a in job['answers'] if not a['received']]
            if job['status'] == 'awaiting_author' and answers:
                if any(occupies(j) for key, j in state['jobs'].items() if key != identifier):
                    continue
                for answer in answers:
                    answer['received'] = True
                job.update(status='claimed', epoch=state['owner']['epoch'])
                return {'issue_id': identifier, 'task_key': job['task_key'], 'attempt': job['attempt'],
                        'answer_candidates': answers, 'questions': job['questions'], 'receipt_required': True}
        return None


def resolve_answers(store, github, token, identifier, decision, reason):
    if decision not in ('sufficient', 'insufficient', 'conflicting') or not reason.strip():
        raise ValueError('답변의 충분성/충돌과 구체적 판단 근거가 필요합니다')
    with store.edit() as state:
        guard(state, token)
        job = state['jobs'][str(identifier)]
        if job['status'] != 'claimed' or job.get('epoch') != state['owner']['epoch'] or not job['answers']:
            raise ValueError('현재 coor가 수신한 답변만 처리할 수 있습니다')
        if fresh(state, github, job):
            raise ValueError('현재 작성자/본문을 확인하세요')
        guard(state, token)
        candidates = [a for a in job['answers'] if a['received'] and not a['decided']]
        if not candidates:
            raise ValueError('이미 판단한 답변입니다')
        comments, _ = github.pages(f"/repos/{state['config']['repository']}/issues/{job['snapshot']['number']}/comments?per_page=100", {})
        available = {c['id']: c for c in comments}
        for answer in candidates:
            comment = available.get(answer['comment_id'])
            if (not comment or digest(comment.get('body') or '') != answer['digest'] or
                    comment['updated_at'] != comment['created_at'] or
                    comment['user']['id'] != job['snapshot']['user']['id']):
                job.update(status='changed', reason='수신 답변의 수정/삭제/작성자 불일치', resume='작성자의 새 확인 댓글')
                return 'changed'
        for answer in candidates:
            answer['decided'] = True
            state['comments'][str(answer['comment_id'])]['processed'] = True
        job['history'].append({'phase': 'answer_decision', 'decision': decision, 'reason': reason,
                               'answers': [a['url'] for a in candidates]})
        job.update(status=('held' if job.get('dispatch_intents') and not job.get('settled') else 'queued')
                   if decision == 'sufficient' else 'awaiting_author', reason=reason,
                   resume='기존 worker 확정 종료를 sync로 확인한 뒤 queued checkpoint' if decision == 'sufficient' else '작성자의 충분한 새 답변')
        job['digest'] = digest([job['snapshot'], [a for a in job['answers'] if a['decided']]])
        # 다음 claim이 새 attempt를 발행한다. 기존 검색/지시/packet은 같은 시도로 재사용하지 않는다.


def reconcile(store, orca, token, identifier, reason, syncing=False):
    if not reason.strip():
        raise ValueError('기존 task/worker/receipt 확인 근거가 필요합니다')
    saved = store.read()
    guard(saved, token)
    job = saved['jobs'][str(identifier)]
    if job['status'] != 'reconciling' and not syncing:
        raise ValueError('인계 시 미확인 작업만 reconcile할 수 있습니다')
    run = job.get('run')
    if not run:
        raise ValueError('기존 Run identity가 없어 재배정하지 않습니다. 수동 확인 필요')
    tasks = orca.call('orchestration', 'task-list', '--run', run).get('tasks') or []
    workers = orca.call('orchestration', 'worker-list', '--run', run)
    if workers.get('page', {}).get('hasMore'):
        raise ValueError('전체 worker receipt를 확인하지 못했습니다. 다음 페이지 확인 필요')
    relevant = [t for t in tasks if integration.key_present(job['task_key'], str(t.get('spec') or ''))]
    if not relevant:
        raise ValueError('기존 task의 부재는 실행하지 않았다는 증거가 아닙니다; 수동 확인 필요')
    live = any(t.get('status') not in ('completed', 'failed', 'cancelled') for t in relevant)
    failed = any(t.get('status') in ('failed', 'cancelled') for t in relevant)
    entries = workers.get('workers') or []
    # 예전 런타임/미확인 fleet의 부재는 종료 증거가 아니다.
    task_ids = {t.get('id') for t in relevant} - {None}
    relevant_workers = [w for w in entries if w.get('taskId') in task_ids]
    exited = (task_ids and task_ids <= {w.get('taskId') for w in relevant_workers} and
              all(w.get('projection', {}).get('liveness', {}).get('verdict') == 'exited'
                  for w in relevant_workers))
    with store.edit() as state:
        owner = guard(state, token)
        job = state['jobs'][str(identifier)]
        job.update(status=('held' if failed else job['status']) if syncing else ('running' if live else 'held'), epoch=owner['epoch'],
                   settled=bool(not live and exited),
                   reason=('기존 task 실패/취소: ' if failed else '') + reason, resume='기존 worker 완료 후 검증; 같은 task를 재배정하지 않음')
        job['history'].append(json.loads(redact(json.dumps({'phase': 'reconciled', 'reason': reason, 'tasks': relevant, 'workers': workers}))))


def complete(store, github, token, identifier, worktree, review_key, base, head, pr_number):
    import review
    worktree = Path(worktree).resolve()
    if integration.directory(worktree).parent != integration.directory(store.repo).parent:
        raise ValueError('승인된 같은 Git 저장소 작업 공간만 완료할 수 있습니다')
    state = store.read()
    guard(state, token)
    job = state['jobs'][str(identifier)]
    if job['status'] != 'reviewing' or job.get('epoch') != state['owner']['epoch']:
        raise ValueError('현재 attempt의 리뷰 단계가 아닙니다')
    if job.get('dispatch_intents') and not job.get('settled'):
        raise ValueError('worker 확정 완료/종료를 먼저 확인하세요')
    if fresh(state, github, job):
        raise ValueError('완료 직전 snapshot/작성자/열림 상태를 재확인하세요')
    if integration.git(worktree, 'rev-parse', 'HEAD') != head:
        raise ValueError('완료 SHA가 현재 작업 공간과 다릅니다')
    review.check(worktree, review_key, base, head, task_key=job['task_key'])
    config = state['config']
    pr = github.get(f"/repos/{config['repository']}/pulls/{int(pr_number)}")
    head_branch = pr.get('head', {}).get('ref', '')
    expected_base = integration.config(worktree).get('git', {}).get('base', 'main')
    expected_branch = config['branch_prefix'] + f"{job['snapshot']['number']}-a{job['attempt']}"
    if (pr.get('draft') is not True or pr.get('state') != 'open' or pr.get('merged') or
            pr.get('head', {}).get('sha') != head or head_branch != expected_branch or
            pr.get('head', {}).get('repo', {}).get('id') != config['repository_id'] or
            pr.get('base', {}).get('repo', {}).get('id') != config['repository_id'] or
            pr.get('base', {}).get('ref') != expected_base):
        raise ValueError('같은 저장소의 현재 SHA·허용 작업 브랜치·draft PR·기본 base를 확인하지 못했습니다')
    with store.edit() as state:
        guard(state, token)
        current = state['jobs'][str(identifier)]
        if current['status'] != 'reviewing' or current.get('attempt') != job['attempt']:
            raise ValueError('리뷰/PR 확인 중 attempt가 변경됐습니다')
        if fresh(state, github, current):
            raise ValueError('완료 기록 직전의 정책/본문 변경')
        current.update(status='completed', head=head, base=base, review_key=review_key,
                       pr_url=pr['html_url'], reason='검증·리뷰·draft PR 완료; 병합은 사용자 판단')
        record(state, 'completed', issue_id=str(identifier), head=head, pr=pr['html_url'])


def worker_job(store, state, session, context):
    """host receipt와 Orca 정본 dispatch/task를 연결한다. 수동 세션은 연결하지 않는다."""
    for job in state['jobs'].values():
        binding = job.get('worker_sessions', {}).get(session)
        if binding:
            if context.get('dispatch') != binding['dispatch'] or context.get('task') != binding['task']:
                raise ValueError('자동 worker의 dispatch/task binding이 바뀌었습니다')
            return job, binding['epoch'] if binding['task_key'] == job.get('task_key') else None
    if not context.get('dispatch'):
        return None, None
    status = integration.orca('orchestration', 'worker-show', '--dispatch', context['dispatch'], cwd=store.repo)
    if status is None:
        raise ValueError('worker의 자동 이슈 범위를 Orca 정본에서 확인하지 못했습니다')
    projection = status.get('projection') or {}
    run = projection.get('runId')
    listing = integration.orca('orchestration', 'task-list', '--run', run, cwd=store.repo) if run else None
    if listing is None:
        raise ValueError('worker의 정본 task를 확인하지 못했습니다')
    task = next((t for t in listing.get('tasks', []) if t.get('id') == projection.get('taskId')), {})
    jobs = [j for j in state['jobs'].values() if j.get('run') == run and j.get('task_key') and
            integration.key_present(j['task_key'], str(task.get('spec') or ''))]
    if not jobs:
        return None, None
    pane = status.get('terminal') or {}
    receipt = hook_path(store.repo, session)
    native = json.loads(receipt.read_text()) if receipt.is_file() else {}
    if (len(jobs) != 1 or projection.get('dispatchId') != context['dispatch'] or
            projection.get('taskId') != context.get('task') or native.get('provider_session') != session or
            not native.get('orca_terminal') or pane.get('handle') != native['orca_terminal'] or
            not pane.get('worktreePath') or
            Path(pane.get('worktreePath') or '').resolve() != store.repo):
        raise ValueError('worker의 host session/terminal/task 작업 공간 binding이 다릅니다')
    job = jobs[0]
    with store.edit() as current:
        if current['epoch'] != state['epoch']:
            raise ValueError('worker 연결 중 coor 소유자가 바뀌었습니다')
        target = next(j for j in current['jobs'].values() if j.get('task_key') == job['task_key'])
        target.setdefault('worker_sessions', {})[session] = {
            'epoch': job['epoch'], 'dispatch': context['dispatch'], 'task': context['task'],
            'task_key': job['task_key']}
    return job, job['epoch']


def boundary(repo, session, command, files, commands, context=None):
    """기존 flow-gate의 해석 가능한 명령/파일에 자동 작업의 추가 범위 검사를 적용한다."""
    if not session:
        return None  # 동일 host session 증명이 없는 호출은 자동 모드에 연결되지 않는다.
    path = integration.directory(repo).parent / 'fullops-issues/state.sqlite'
    if not path.is_file():
        return None
    store = Store(repo)
    state = store.read()
    owner = state['owner']
    if not owner:
        return None
    coordinator = owner.get('provider_session', owner['session']) == session
    job = None
    if not coordinator:
        try:
            job, epoch = worker_job(store, state, session, context or {})
        except (ValueError, OSError) as error:
            return str(error)
        if job is None:
            return None
        from flow_gate import settlement_command
        if len(commands) == 1 and not files and settlement_command(command, context or {}):
            return None  # OFF/보류에서도 같은 worker의 완료·escalation 증거는 전달한다.
        if epoch != owner['epoch']:
            return '이전 coor의 worker입니다. 자동 실행 fencing token이 바뀌었습니다'
    jobs = [j for j in state['jobs'].values() if j['status'] not in FINAL and j.get('epoch') == owner['epoch']]
    if not jobs and job is None:
        return None
    try:
        guard(state, owner['token'])
    except ValueError as error:
        return str(error)
    job = job or next((j for j in jobs if j['status'] in ACTIVE), jobs[-1])
    control = any('issue_mode.py' in ' '.join(w) and any(c in w for c in
                  ('status', 'disable', 'pause', 'resume', 'wait', 'claim', 'checkpoint', 'question', 'answers', 'reconcile', 'sync', 'complete'))
                  for w in commands)
    if coordinator and control and len(commands) == 1 and not files:
        return None
    if control and not coordinator:
        return '자동 worker는 coor의 이슈 설정/상태를 변경할 수 없습니다'
    if owner['paused'] or job['status'] not in ACTIVE or job['status'] == 'reconciling':
        return '자동 작업이 보류/정책 변경/인계 확인 중입니다. 증거를 보존하고 checkpoint를 처리하세요'
    if str(job['snapshot']['user']['id']) not in state['config']['allowed']:
        return '자동 작업 작성자의 allowlist가 철회됐습니다'
    if time.time() - job.get('started', time.time()) > state['config']['max_seconds'] or job['tokens'] > state['config']['max_tokens']:
        return '자동 이슈 실행 시간/보고된 모델 사용량 한도를 초과했습니다'
    for words in commands:
        if not words:
            continue
        executable = Path(words[0]).name.lower().removesuffix('.exe')
        if any(re.search(r'(?:^|[/\\])(?:\.env[^/\\]*|auth\.json|credentials\.json|\.codex|\.claude)(?:$|[/\\])', w, re.I) for w in words):
            return '자동 이슈에서 비밀정보/host 권한 파일을 읽거나 변경할 수 없습니다'
        if 'issue_mode.py' in ' '.join(words) and 'configure' in words:
            return 'GitHub 이슈/댓글로 자동 작업 설정과 allowlist를 변경할 수 없습니다'
        if executable == 'git':
            if any(w in words for w in ('-C', '-c', '--git-dir', '--work-tree', '--force', '-f', '--force-with-lease')) or any(
                    w.startswith(('--config-env', '--git-dir=', '--work-tree=', '--exec-path', '-c', '-C')) for w in words[1:]):
                return '자동 작업의 Git 저장소/강제 변경 범위를 확인할 수 없습니다'
            if any(w in words for w in ('clean', 'reset')) or ('merge' in words and integration.git(repo, 'branch', '--show-current') == integration.config(repo)['git']['base']):
                return '자동 작업의 main 병합/파괴적 Git 명령은 사전 범위 밖입니다'
            if 'push' in words:
                expected = state['config']['branch_prefix'] + f"{job['snapshot']['number']}-a{job['attempt']}"
                branch = integration.git(repo, 'branch', '--show-current')
                if branch != expected or any(w in words for w in ('--all', '--mirror', '--tags', '--delete')):
                    return '자동 push는 허용 작업 브랜치만 가능합니다'
                arguments = words[words.index('push') + 1:]
                remote = integration.config(repo).get('git', {}).get('remote', 'origin')
                if arguments not in ([remote, f'refs/heads/{branch}:refs/heads/{branch}'],
                                     [remote, f'HEAD:refs/heads/{branch}']):
                    return '명시한 같은 저장소 remote와 작업 브랜치 외 push는 금지합니다'
                try:
                    remote_identity(repo, state['config']['repository'])
                except ValueError as error:
                    return str(error)
        if 'worker-start' in words:
            if (job['status'] != 'running' or not job.get('receipt') or '--run' not in words or
                    words[words.index('--run') + 1] != owner['run'] or
                    not integration.key_present(job['task_key'], ' '.join(words))):
                return '실제 동일 coor 수신 receipt와 현재 task key/Run을 기록한 뒤 기존 route/dispatch를 수행하세요'
        if executable == 'gh':
            if any(w in words for w in ('merge', 'close', '--ready', 'api', 'auth', 'repo', 'release', 'workflow', 'run', 'secret', 'variable', 'extension')):
                return '자동 모드의 병합/종료/배포/credential/임의 API 조작은 허용하지 않습니다'
            if '--repo' in words or '-R' in words or any(w.startswith(('--repo=', '-R=')) for w in words):
                return '자동 모드에서 GitHub 저장소를 임의 변경할 수 없습니다'
            if 'create' in words and ('pr' not in words or '--draft' not in words):
                return '자동 모드의 생성은 같은 저장소 draft PR만 허용합니다'
            if not any(w in words for w in ('view', 'list', 'status', 'diff', 'checks', 'create')):
                return 'GitHub 변경은 draft PR 생성과 durable outbox 질문만 허용합니다'
            if 'create' in words:
                expected = state['config']['branch_prefix'] + f"{job['snapshot']['number']}-a{job['attempt']}"
                if ('--head' not in words or '--base' not in words or
                        words[words.index('--head') + 1] != expected or
                        words[words.index('--base') + 1] != integration.config(repo)['git']['base']):
                    return 'draft PR의 허용 작업 head와 저장된 base를 명시하세요'
        if executable in ('curl', 'wget', 'ssh', 'scp', 'rsync', 'rm', 'rmdir', 'remove-item', 'del', 'kubectl', 'terraform', 'vercel', 'gcloud', 'aws', 'az'):
            return '임의 외부 전송/배포/삭제는 자동 이슈의 허용 범위 밖입니다'
    for name, _ in files:
        candidate = Path(name)
        if not candidate.is_absolute():
            candidate = Path(repo) / candidate
        try:
            candidate.resolve().relative_to(Path(repo).resolve())
        except ValueError:
            return '자동 작업 파일이 허용 작업 공간 밖입니다'
        if any(part.lower().startswith('.env') or part.lower() in ('.git', '.codex', '.claude') for part in candidate.parts):
            return '자동 이슈의 credential/실행 권한 변경은 허용 범위 밖입니다'
    return None


def reserve_dispatch(repo, session, commands):
    path = integration.directory(repo).parent / 'fullops-issues/state.sqlite'
    if not path.is_file() or not any('worker-start' in words for words in commands):
        return
    with Store(repo).edit() as state:
        owner = state['owner']
        if not owner or owner['provider_session'] != session:
            return
        guard(state, owner['token'])
        job = next(j for j in state['jobs'].values() if j['status'] == 'running' and j.get('epoch') == owner['epoch'])
        job.setdefault('dispatch_intents', []).append({'at': iso(time.time()), 'digest': digest(commands), 'run': owner['run']})
        job['settled'] = False
        record(state, 'dispatch_intent', task_key=job['task_key'], run=owner['run'])


def watch(store, github, token):
    """선택한 동일 세션의 lease 동안 busy 상태에도 수집한다. claim/dispatch/모델 호출은 하지 않는다."""
    failures, next_poll = 0, 0
    while True:
        state = store.read()
        try:
            owner = guard(state, token)
        except ValueError:
            return
        if not owner['paused'] and time.time() >= next_poll:
            try:
                poll(store, github, token)
                failures = 0
                next_poll = time.time() + state['config']['interval']
            except APIError as error:
                failures += 1
                with store.edit() as current:
                    guard(current, token)
                    record(current, 'api_backoff', status=error.status, attempt=failures)
                    if failures >= current['config']['max_attempts'] or error.status in (401, 404, 422):
                        current['owner'].update(paused=True, blocked='GitHub 인증/권한/일시 오류 한도; 사용자 확인 후 resume')
                next_poll = time.time() + max(error.retry_after, 60 * 2 ** (failures - 1))
        time.sleep(1)  # 모델과 연결되지 않은 로컬 코드 타이머


def start_watch(store, executable, token):
    command = [sys.executable, str(Path(__file__).resolve()), '--repo', str(store.repo),
               '--orca', executable, 'watch']
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, text=True, **options)
    child.stdin.write(json.dumps({'token': token}))
    child.stdin.close()
    with store.edit() as state:
        guard(state, token)
        state['owner']['poll_pid'] = child.pid
        record(state, 'poll_started', pid=child.pid)


def wait(store, github, orca, token):
    """별도 세션/PTY 입력 없이 현재 coor의 진행 중 tool call로 반환한다. 조용한 주기에는 출력 0회."""
    next_auth, ack = 0, None
    while True:
        state = store.read()
        owner = guard(state, token)
        now = time.time()
        if now >= next_auth:
            incarnation = owner_identity(store, orca, owner)
            if incarnation != owner['incarnation']:
                raise ValueError('coor terminal incarnation이 바뀌었습니다; 명시적으로 재활성화하세요')
            with store.edit() as state:
                guard(state, token)
                state['owner']['expires'] = time.time() + 90
            next_auth = now + 30
        if owner.get('blocked'):
            raise ValueError(owner['blocked'])
        # ACK할 조용한 delivery가 있으면 먼저 소진한다. 반환 시 ACK를 유실하지 않는다.
        if not ack:
            ready = answer_delivery(store, token) or claim(store, github, token)
            if ready:
                return {'status': 'issue_actionable', 'owner_session': owner['session'], 'work': ready}
        args = argparse.Namespace(orca=orca.executable, run=owner['run'], terminal=owner['terminal'], wait_ms=15000)
        messages = orca_wait.check(args, ack)
        ack = None
        batch = messages.get('messages') or []
        if batch and not all(m.get('type') in ('heartbeat', 'status') for m in batch):
            integration.record(store.repo, batch)
            return {'status': 'orchestration_actionable', 'deliveryId': messages.get('deliveryId'), 'messages': batch}
        if batch:
            ack = messages.get('deliveryId')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--orca', default=orca_wait.find_orca())
    sub = parser.add_subparsers(dest='command', required=True)
    config = sub.add_parser('configure')
    config.add_argument('--repository', required=True)
    config.add_argument('--allow-user', action='append', required=True)
    config.add_argument('--interval', type=int, default=300)
    config.add_argument('--backlog', action='store_true')
    config.add_argument('--approve-scope', action='store_true', required=True,
                        help='사용자가 선택한 고정 자동 범위: 구현/검증/리뷰/작업 브랜치 push/draft PR/동일 이슈 질문')
    for name, default in (('max-attempts', 3), ('max-seconds', 3600), ('max-tokens', 100000)):
        config.add_argument('--' + name, type=int, default=default)
    enable = sub.add_parser('enable')
    for field in ('session', 'provider-session', 'run', 'terminal'):
        enable.add_argument('--' + field, required=True)
    for name in ('pause', 'resume', 'disable'):
        sub.add_parser(name).add_argument('--session', required=True)
    for name in ('poll', 'wait', 'claim'):
        sub.add_parser(name).add_argument('--token', required=True)
    sub.add_parser('watch')  # lease capability는 argv/log 대신 stdin으로 전달한다.
    for name in ('checkpoint', 'question', 'answers', 'reconcile', 'sync', 'complete'):
        p = sub.add_parser(name)
        p.add_argument('--token', required=True)
        p.add_argument('--issue-id', required=True)
        if name == 'checkpoint':
            p.add_argument('--phase', required=True)
            p.add_argument('--reason', default='')
            p.add_argument('--resume', default='')
            p.add_argument('--dependencies', help='검토한 issue ID JSON 배열. 독립이면 []')
            p.add_argument('--receipt', help='실제 coor 수신/task/worker 증거 JSON 파일')
            p.add_argument('--tokens', type=int, default=0)
        elif name == 'question':
            p.add_argument('--body-file', required=True)
        elif name in ('answers', 'reconcile', 'sync'):
            p.add_argument('--reason', required=True)
            if name == 'answers':
                p.add_argument('--decision', choices=['sufficient', 'insufficient', 'conflicting'], required=True)
        else:
            for field in ('worktree', 'review-key', 'base', 'head'):
                p.add_argument('--' + field, required=True)
            p.add_argument('--pr-number', type=int, required=True)
    sub.add_parser('status')
    sub.add_parser('session-end')
    args = parser.parse_args()
    try:
        from done_gate import field
        event = json.load(sys.stdin) if args.command == 'session-end' else None
        repo = Path(integration.git((field(event, 'cwd') if event else None) or args.repo, 'rev-parse', '--show-toplevel')).resolve()
        if not integration.config(repo):
            raise ValueError('먼저 요청한 서비스 저장소에서 FullOps setup을 완료하세요')
        if args.command == 'session-end' and not (integration.directory(repo).parent / 'fullops-issues/state.sqlite').is_file():
            return 0
        store = Store(repo)
        if args.command == 'session-end':
            stop(store, field(event, 'session_id'))
            return 0
        if args.command == 'status':
            state = store.read()
            if state['owner']:
                state['owner'].pop('token', None)
            print(json.dumps({'config': state['config'], 'owner': state['owner'], 'cursor': state['cursor'],
                              'jobs': {k: {field: job.get(field) for field in ('status', 'task_key', 'attempt', 'reason', 'resume', 'pr_url')}
                                       for k, job in state['jobs'].items()}, 'events': state['events'][-20:]}, ensure_ascii=False, indent=2))
            return 0
        if args.command in ('pause', 'resume', 'disable'):
            if not stop(store, args.session, args.command):
                raise ValueError('그 session은 현재 자동 모드 소유자가 아닙니다')
            return 0
        github = GitHub()
        if hasattr(args, 'token'):
            owner = guard(store.read(), args.token)
            incarnation = owner_identity(store, Orca(args.orca), owner)
            if incarnation != owner['incarnation']:
                raise ValueError('coor terminal incarnation이 바뀌었습니다')
        if args.command == 'configure':
            configure(store, github, args.repository, args.allow_user, args.interval, args.backlog,
                      args.max_attempts, args.max_seconds, args.max_tokens, args.approve_scope)
            result = {'status': 'configured_OFF'}
        elif args.command == 'enable':
            result = activate(store, Orca(args.orca), args.session, args.run, args.terminal, args.provider_session)
            start_watch(store, args.orca, result['token'])
        elif args.command == 'watch':
            token = json.load(sys.stdin)['token']
            try:
                watch(store, github, token)
            except (ValueError, OSError, APIError, KeyError):
                with store.edit() as state:
                    if state['owner'] and state['owner']['token'] == token:
                        state['owner'].update(paused=True, blocked='poller 중단: 상태/lease/API를 확인하고 명시적으로 재활성화')
            return 0
        elif args.command == 'wait':
            result = wait(store, github, Orca(args.orca), args.token)
        elif args.command == 'claim':
            result = claim(store, github, args.token)
        elif args.command == 'checkpoint':
            result = checkpoint(store, github, args.token, args.issue_id, args.phase, reason=args.reason,
                                resume=args.resume, dependencies=json.loads(args.dependencies) if args.dependencies else None,
                                tokens=args.tokens, receipt=json.loads(local_file(store, args.receipt).read_text()) if args.receipt else None)
        elif args.command == 'question':
            result = question(store, github, args.token, args.issue_id, local_file(store, args.body_file).read_text(encoding='utf-8'))
        elif args.command == 'answers':
            result = resolve_answers(store, github, args.token, args.issue_id, args.decision, args.reason)
        elif args.command in ('reconcile', 'sync'):
            result = reconcile(store, Orca(args.orca), args.token, args.issue_id, args.reason, syncing=args.command == 'sync')
        elif args.command == 'complete':
            result = complete(store, github, args.token, args.issue_id, args.worktree, args.review_key, args.base, args.head, args.pr_number)
        else:
            poll(store, github, args.token)
            result = {'status': 'polled'}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, OSError, APIError, subprocess.SubprocessError, RuntimeError, sqlite3.Error) as error:
        if args.command == 'session-end':
            return 0  # 종료 hook은 제품 작업을 막지 않는다. lease도 별도로 만료된다.
        if 'store' in locals() and not isinstance(error, sqlite3.Error):
            with store.edit() as state:
                record(state, 'blocked', operation=args.command, error_type=type(error).__name__)
        print(json.dumps({'status': 'blocked', 'reason': str(error) if isinstance(error, (ValueError, APIError)) else type(error).__name__}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
