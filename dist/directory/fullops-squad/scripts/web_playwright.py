"""선택한 로컬 Playwright CLI의 기존 런타임을 stdio로 연결한다. 설치나 브라우저 다운로드는 하지 않는다."""
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import threading
import time

from jev_test_web import Browser, SafetyStop


def stop_process(process):
    """깨진 bridge만 정리한다. macOS는 프로세스 그룹, Windows는 해당 PID의 자식 트리를 종료한다."""
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=10)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            os.killpg(process.pid, getattr(signal, 'SIGKILL', 9))
        process.wait(timeout=5)


class PlaywrightBrowser(Browser):
    request_filtering = True

    def __init__(self, repo, safety, package_file=None, executable=None, headed=False):
        self.package_file = package_file or repo / '.fullops-squad/tools/frontend/playwright/node_modules/@playwright/cli/package.json'
        self.options = {'package_file': str(Path(self.package_file).resolve()), 'safety': safety,
                        'executable': executable, 'headed': headed}
        self.process, self.deadline, self.serial = None, None, 0
        self.responses = queue.Queue()
        self.identity = {'name': 'playwright', 'version': 'unverified', 'request_filtering': True, 'attached': False}

    def rpc(self, action, **data):
        if self.process is None:
            raise RuntimeError('playwright_bridge_not_started')
        remaining = min(30, self.deadline - time.monotonic()) if self.deadline else 30
        if remaining <= 0:
            raise SafetyStop('time_budget')
        self.serial += 1
        self.process.stdin.write(json.dumps({'id': self.serial, 'action': action, 'data': data, 'timeout': max(1, int(remaining * 1000))}, ensure_ascii=False) + '\n')
        self.process.stdin.flush()
        try:
            response = self.responses.get(timeout=remaining)
        except queue.Empty:
            raise SafetyStop('time_budget') from None
        if not isinstance(response, dict) or response.get('id') != self.serial or not response.get('ok'):
            raise RuntimeError('playwright_bridge_failed: ' + (response.get('error', 'closed') if isinstance(response, dict) else 'closed'))
        return response.get('result')  # JavaScript undefined는 JSON에서 필드가 생략된다.

    def open(self, url):
        if not Path(self.package_file).is_file() or not shutil.which('node'):
            raise RuntimeError('selected_playwright_unavailable; install selected local tool explicitly; no engine fallback')
        options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
        self.process = subprocess.Popen([shutil.which('node'), str(Path(__file__).with_suffix('.cjs'))],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        encoding='utf-8', bufsize=1, **options)
        def read():
            try:
                for line in self.process.stdout:
                    try:
                        self.responses.put(json.loads(line))
                    except ValueError:
                        self.responses.put(None)
            finally:
                self.responses.put(None)
        threading.Thread(target=read, daemon=True).start()
        self.identity = self.rpc('start', **self.options)
        self.rpc('open', url=url)

    def evaluate(self, expression):
        return self.rpc('eval', expression=expression)

    def snapshot(self):
        return self.rpc('snapshot')

    def preflight(self, page, operation, ref, safety):
        return self.rpc('preflight', page={k: page[k] for k in ('url', 'digest')}, operation=operation, ref=ref)

    def act(self, operation, ref=None, value=None):
        return self.rpc('act', operation=operation, ref=ref, value=value)

    def close(self):
        if self.process is None:
            return
        try:
            self.deadline = time.monotonic() + 5
            self.identity.update(self.rpc('close'))
            self.process.wait(timeout=5)
        except (OSError, RuntimeError, SafetyStop, subprocess.TimeoutExpired):
            self.identity['cleanup'] = 'forced_after_bridge_failure'
            stop_process(self.process)
        finally:
            for stream in (self.process.stdin, self.process.stdout):
                stream.close()
