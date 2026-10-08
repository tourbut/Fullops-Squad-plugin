"""인증된 GitHub 조회와 질문 전송. 모델 호출과 임의 URL/명령 실행은 하지 않는다."""
from datetime import datetime, timezone
import email.utils
import json
import math
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


class APIError(RuntimeError):
    def __init__(self, status, retry_after=60):
        super().__init__(f'GitHub API HTTP {status}; 인증/권한/요청을 확인하세요')
        self.status, self.retry_after = status, retry_after


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        target = urllib.parse.urlsplit(url)
        if (target.scheme != 'https' or target.netloc != 'api.github.com' or
                target.path != urllib.parse.urlsplit(request.full_url).path):
            raise APIError('foreign redirect')
        return super().redirect_request(request, fp, code, message, headers, url)


class GitHub:
    def __init__(self, token=None):
        self.token = token or os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        if not self.token:
            result = subprocess.run(['gh', 'auth', 'token', '--hostname', 'github.com'],
                                    capture_output=True, text=True, timeout=15)
            if result.returncode or not result.stdout.strip():
                raise APIError('authentication unavailable')
            self.token = result.stdout.strip()
        self.opener = urllib.request.build_opener(SafeRedirect())

    def request(self, path, method='GET', body=None, etag=None):
        url = 'https://api.github.com' + path if path.startswith('/') else path
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'api.github.com' or parsed.username:
            raise APIError('foreign URL')
        headers = {'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'FullOps-issue-mode'}
        if etag:
            headers['If-None-Match'] = etag
        raw = json.dumps(body).encode() if body is not None else None
        if raw:
            headers['Content-Type'] = 'application/json'
        try:
            with self.opener.open(urllib.request.Request(url, raw, headers, method=method), timeout=30) as response:
                return response.status, dict(response.headers.items()), json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 304:
                return 304, dict(error.headers.items()), None
            retry = error.headers.get('Retry-After', '60')
            try:
                delay = max(60, float(retry))
            except ValueError:
                try:
                    delay = max(60, email.utils.parsedate_to_datetime(retry).timestamp() - time.time())
                except (ValueError, TypeError, OverflowError):
                    delay = 60
            if error.headers.get('X-RateLimit-Remaining') == '0':
                try:
                    delay = max(delay, float(error.headers.get('X-RateLimit-Reset', '0')) - time.time())
                except ValueError:
                    pass
            if not math.isfinite(delay):
                delay = 60
            raise APIError(error.code, delay) from None
        except (OSError, ValueError):
            raise APIError('network/protocol unavailable') from None

    def get(self, path):
        return self.request(path)[2]

    def pages(self, path, cache):
        """완전한 페이지 순회만 호출자가 원자적으로 저장한다. 304에도 이전 Link를 유지한다."""
        rows, staged, seen = [], {}, set()
        scope = urllib.parse.urlsplit(path).path
        url = path
        while url:
            if urllib.parse.urlsplit(url).path != scope:
                raise APIError('pagination scope changed')
            if url in seen:
                raise APIError('pagination loop')
            seen.add(url)
            previous = cache.get(url, {})
            status, headers, data = self.request(url, etag=previous.get('etag'))
            headers = {k.lower(): v for k, v in headers.items()}
            if status == 304:
                if not previous:
                    raise APIError('304 without cached page')
                page = previous
            else:
                if not isinstance(data, list):
                    raise APIError('invalid page')
                match = re.search(r'<([^>]+)>;\s*rel="next"', headers.get('link', ''))
                page = {'etag': headers.get('etag'), 'rows': data, 'next': match[1] if match else None}
            staged[url] = page
            rows.extend(page['rows'])
            url = page['next']
        return rows, staged

    def issue(self, repository, number):
        """본문·작성자·최신 편집자를 한 GraphQL 응답에서 고정한다."""
        owner, name = repository.split('/')
        query = '''query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){
          databaseId issue(number:$number){databaseId number url title body createdAt updatedAt state lastEditedAt
          author{login ... on User{databaseId} ... on Bot{databaseId}}
          editor{login ... on User{databaseId} ... on Bot{databaseId}}}}}'''
        result = self.request('/graphql', 'POST', {'query': query, 'variables': {
            'owner': owner, 'name': name, 'number': number}})[2]
        if result.get('errors'):
            raise APIError('issue provenance unavailable')
        repo = result.get('data', {}).get('repository') or {}
        issue = repo.get('issue')
        if not issue or not (issue.get('author') or {}).get('databaseId'):
            raise APIError('issue identity unavailable')
        return {'id': issue['databaseId'], 'repository_id': repo['databaseId'], 'number': issue['number'],
                'html_url': issue['url'], 'title': issue['title'], 'body': issue['body'],
                'created_at': issue['createdAt'], 'updated_at': issue['updatedAt'], 'state': issue['state'].lower(),
                'user': {'id': issue['author']['databaseId'], 'login': issue['author']['login']},
                'edit_verified': not issue['lastEditedAt'] or
                    (issue.get('editor') or {}).get('databaseId') == issue['author']['databaseId']}

    def comment(self, repository, number, body):
        return self.request(f'/repos/{repository}/issues/{number}/comments', 'POST', {'body': body})[2]


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
