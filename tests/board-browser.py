"""보드 문서 열람을 file://·HTTP에서 검증한다. Playwright와 브라우저가 필요하다 (--channel chrome 가능)."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fullops-squad/scripts'
sys.path.insert(0, str(SCRIPTS))
from board import write
from deliverables import render


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', help='설치된 브라우저 채널. 생략하면 Playwright Chromium')
    parser.add_argument('--out', type=Path, help='화면 캡처를 보존할 디렉터리')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='fullops-board-browser-') as tmp:
        repo = Path(tmp)
        subprocess.run(['git', 'init', '-q', '-b', 'main', tmp], check=True)
        subprocess.run([sys.executable, str(SCRIPTS / 'setup.py'), '--repo', tmp,
                        '--roles', 'dev', '--local-only'], check=True, capture_output=True)
        root = repo / '.fullops-squad'
        folder = root / 'docs/design-docs'
        folder.mkdir(parents=True, exist_ok=True)
        for doc_id, path, title, status, body in [
            ('D03', 'architecture.md', '전체 시스템 설계서', 'draft',
             '# 시스템 구조\n\n**핵심 구조**와 `API` 설명.\n\n| 구성 | 책임 |\n|---|---|\n| 엔진 | 처리 |\n\n'
             '```python\nprint("sample")\n```\n\n<img src=x onerror="window.boardInjected=1">\n[bad](javascript:alert(1))'),
            ('D03', '엔진 파이프라인.md', '엔진 파이프라인 설계서', 'draft', '# 엔진 파이프라인\n\n파일별 본문'),
            ('D05', 'interface-design.md', '인터페이스 설계서', 'draft', '# 인터페이스\n\n요청·응답 계약'),
            ('D07', 'data-model.md', '데이터베이스 설계서', 'approved', '# 데이터베이스\n\n저장 구조')]:
            (folder / path).write_text(render({'id': doc_id, 'title': title, 'status': status,
                'updated': '2026-10-05', 'owner': 'dev', 'summary': title}) + '\n' + body, encoding='utf-8')
        index = root / 'docs/deliverables/README.md'
        index.write_text(index.read_text(encoding='utf-8').replace('`docs/design-docs/tech-stack.md`',
                         '`docs/design-docs/엔진 파이프라인.md`, `docs/design-docs/tech-stack.md`'), encoding='utf-8')
        # Paths with spaces are literal file names, not section annotations.
        board = root / 'board/board.json'
        board.write_text(json.dumps({'title': '문서 열람 검증', 'phases': [
            {'name': '설계', 'status': 'active', 'deliverables': ['D03', 'D05', 'D07']}]}, ensure_ascii=False), encoding='utf-8')
        before = {p: p.read_bytes() for p in [index, board, *folder.glob('*.md')]}
        write(repo)
        page_file = root / 'board/index.html'
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(repo)))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, **({'channel': args.channel} if args.channel else {}))
                for mode, url in [('file', page_file.as_uri()),
                                  ('http', f'http://127.0.0.1:{server.server_port}/.fullops-squad/board/index.html')]:
                    page = browser.new_page(viewport={'width': 1280, 'height': 900})
                    errors, fetches = [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('request', lambda request: fetches.append(request.url) if request.resource_type in ('fetch', 'xhr') else None)
                    page.route('https://fonts.googleapis.com/**', lambda route: route.abort())
                    page.add_init_script('window.boardRefresh = []; window.setInterval = (callback, delay) => { window.boardRefresh.push({callback, delay}); return 1; };')
                    page.goto(url, wait_until='networkidle')
                    card = page.locator('.d[data-deliverable="D03"]')
                    card.focus()
                    page.keyboard.press('Enter')
                    assert page.evaluate('window.boardRefresh[0].delay') == 60000
                    page.evaluate('window.boardRefresh[0].callback()')  # Reading must not reload the page.
                    assert '시스템 구조' in page.locator('#detail .doc-body').inner_text()
                    assert page.locator('#detail .doc-body table').count() == 1
                    assert page.locator('#detail .doc-body pre').inner_text() == 'print("sample")'
                    assert page.locator('#detail .doc-body img, #detail .doc-body script').count() == 0
                    assert page.evaluate('window.boardInjected') is None
                    assert page.locator('#detail a[href^="javascript:"]').count() == 0
                    files = page.locator('#detail [data-document="D03"]')
                    assert files.count() == 3 and files.nth(2).is_disabled()
                    assert '파일 없음' in files.nth(2).inner_text()
                    files.nth(1).focus()
                    page.keyboard.press('Enter')
                    assert '파일별 본문' in page.locator('#detail .doc-body').inner_text()
                    if args.out:
                        args.out.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(args.out / f'{mode}-document.png'))
                    page.keyboard.press('Escape')
                    assert not page.locator('#detail').evaluate('(dialog) => dialog.open')
                    assert card.evaluate('(card) => card === document.activeElement')
                    page.locator('[data-phase="0"]').click()
                    page.locator('#detail [data-deliverable="D05"]').click()
                    assert '요청·응답 계약' in page.locator('#detail .doc-body').inner_text()
                    page.locator('[data-back-phase="0"]').click()
                    assert page.locator('#detail-title').inner_text() == '설계'
                    page.locator('#detail [data-deliverable="D07"]').click()
                    assert '저장 구조' in page.locator('#detail .doc-body').inner_text()
                    page.locator('#close').click()
                    page.locator('.d[data-deliverable="D01"]').click()
                    assert page.locator('#detail .doc-body').count() == 0
                    assert page.locator('#detail .doc-file').is_disabled()
                    page.keyboard.press('Escape')
                    page.set_viewport_size({'width': 360, 'height': 780})
                    card.click()
                    assert page.locator('#detail').evaluate('(d) => d.getBoundingClientRect().width') <= 328
                    assert not errors and not fetches, (errors, fetches)
                    page.close()
                missing = page_file.with_name('no-data.html')
                missing.write_text(page_file.read_text(encoding='utf-8').replace('<script src="board-data.js"></script>', ''), encoding='utf-8')
                page = browser.new_page()
                page.route('https://fonts.googleapis.com/**', lambda route: route.abort())
                page.add_init_script('window.boardRefresh = []; window.setInterval = (callback, delay) => { window.boardRefresh.push({callback, delay}); return 1; };')
                page.goto(missing.as_uri(), wait_until='networkidle')
                assert '데이터가 아직 없습니다' in page.locator('#app').inner_text()
                assert page.evaluate('window.boardRefresh.length === 1 && window.boardRefresh[0].delay === 60000')
                page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        assert all(p.read_bytes() == raw for p, raw in before.items())
    print('PASS: file/HTTP document reading, multiple/missing sources, Markdown, keyboard/back/focus, safe HTML, mobile, unchanged status')


if __name__ == '__main__':
    main()
