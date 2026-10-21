"""선택한 ego lite의 `ego-browser nodejs`로 웹 시나리오를 실행한다. 설치나 다른 실행기로의 전환은 하지 않는다.

ego-browser는 스크립트에 stdin을 넘기지 않아 호출마다 프로세스 하나다. 요청은 임시 JSON 파일, 응답은 표식 붙은 stdout 한 줄.
요청 차단이 없으므로 Orca와 같은 규칙(조작은 loopback fixture, 원격은 읽기·검사만)을 따른다.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from jev_observe import safe_text
from jev_test_web import Browser, SafetyStop

MARK = 'FULLOPS_EGO '


def find_ego(executable=None):
    if executable:
        return executable if Path(executable).is_file() else None
    found = shutil.which('ego-browser')
    if found:
        return found
    # ego lite 온보딩이 사용자 PATH에 이 폴더를 넣는다. 그 전에 연 터미널은 새 PATH를 모른다.
    folder = Path.home() / '.local/share/ego/active_version_dir'
    return next((str(folder / name) for name in ('ego-browser.exe', 'ego-browser') if (folder / name).is_file()), None)


def quoted(text):
    return "'" + text.replace('\\', '\\\\').replace("'", "\\'") + "'"


class EgoBrowser(Browser):
    request_filtering = False

    def __init__(self, safety, executable=None):
        self.safety, self.executable = safety, find_ego(executable)
        self.space = 'fullops-web-' + uuid.uuid4().hex[:12]
        self.folder, self.deadline, self.pending = None, None, None
        self.identity = {'name': 'ego', 'version': 'unverified', 'request_filtering': False, 'attached': False, 'popups_closed': 0}

    def rpc(self, action, **data):
        if self.folder is None:
            raise RuntimeError('ego_bridge_not_started')
        remaining = min(30, self.deadline - time.monotonic()) if self.deadline else 30
        if remaining <= 0:
            raise SafetyStop('time_budget')
        request = self.folder / 'request.json'
        request.write_text(json.dumps({'action': action, 'space': self.space, 'data': data,
                                       'timeout': max(1000, int(remaining * 1000) - 1500)}, ensure_ascii=False), encoding='utf-8')
        entry = (f'globalThis.__fullopsEgoRequest={quoted(request.as_posix())}; '
                 f'await import({quoted(Path(__file__).with_suffix(".mjs").as_uri())})')
        try:
            done = subprocess.run([self.executable, 'nodejs', '-e', entry], capture_output=True, text=True, encoding='utf-8', timeout=remaining)
        except subprocess.TimeoutExpired:
            raise SafetyStop('time_budget') from None
        # ego-browser는 스크립트의 console 출력을 stderr로 내보낸다.
        answers = [line[len(MARK):] for line in f'{done.stdout or ""}\n{done.stderr or ""}'.splitlines() if line.startswith(MARK)]
        try:
            response = json.loads(answers[-1])
        except (IndexError, ValueError):
            response = None
        if not isinstance(response, dict) or not response.get('ok'):
            raise RuntimeError('ego_bridge_failed: ' + (str(response.get('error')) if isinstance(response, dict) else 'no_answer'))
        return response.get('result')  # JavaScript undefined는 JSON에서 필드가 생략된다.

    def open(self, url):
        if not self.executable:
            raise RuntimeError('selected_ego_unavailable; install ego lite and finish its onboarding; no engine fallback')
        version = subprocess.run([self.executable, '--version'], capture_output=True, text=True, encoding='utf-8', timeout=10)
        if version.returncode == 0:
            self.identity['version'] = safe_text(' '.join((version.stdout or version.stderr or '').split()), 200) or 'unverified'
        self.folder = Path(tempfile.mkdtemp(prefix='fullops-ego-'))
        self.rpc('open', url=url, safety=self.safety)

    def evaluate(self, expression):
        return self.rpc('eval', expression=expression)

    def snapshot(self):
        return self.rpc('snapshot')

    def preflight(self, page, operation, ref, safety):
        seen = {k: page[k] for k in ('url', 'digest')}
        problem = self.rpc('preflight', page=seen, operation=operation, ref=ref, safety=safety)
        self.pending = None if problem else {'page': seen, 'ref': ref, 'safety': safety}
        return problem

    def act(self, operation, ref=None, value=None):
        saved, self.pending = self.pending, None
        if not saved or operation != 'scroll_down' and saved['ref'] != ref:
            return 'error: stale_state'
        answer = self.rpc('act', page=saved['page'], operation=operation, ref=ref, value=value, safety=saved['safety'])
        self.identity['popups_closed'] += answer.get('popups', 0)
        return answer['outcome']

    def close(self):
        if self.folder is None:
            return
        try:
            self.deadline = time.monotonic() + 10
            self.rpc('close')
        except (OSError, RuntimeError, SafetyStop):
            self.identity['cleanup'] = 'task_space_left_open'
        finally:
            shutil.rmtree(self.folder, ignore_errors=True)
            self.folder = None
