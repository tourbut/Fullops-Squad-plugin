"""격리된 같은 앱/fixture를 Orca·Playwright에서 모델 없이 검증한다. 기본 npm test에는 브라우저가 필요 없다."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/fullops-squad/scripts'))
import jev_test_web as web
import web_contract as contract
from web_playwright import PlaywrightBrowser

HTML = '''<!doctype html><meta charset="utf-8"><title>Isolated engine fixture</title>
<style>body{font:16px sans-serif}input{width:240px;height:32px}li{padding:12px}</style>
<main><h1>Todo fixture</h1><form><label>New todo <input id="todo" autocomplete="off"></label><button>Add</button></form>
<ul id="list"></ul><button disabled>Restricted</button><a href="https://blocked.invalid/">Outside</a>
<button id="network">Unapproved request</button>
<form action="https://blocked.invalid/"><button>Foreign form submit</button></form>
<form><button formaction="https://blocked.invalid/override">Foreign submit override</button></form></main><script>
window.submits=0;const form=document.querySelector('form'),input=document.querySelector('input');
form.onsubmit=event=>{event.preventDefault();window.submits++;const li=document.createElement('li');
const label=document.createElement('label');const box=document.createElement('input');box.type='checkbox';box.setAttribute('aria-label','Toggle milk');
label.append(box,document.createTextNode(input.value));li.append(label);document.querySelector('ul').append(li);};
input.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();form.requestSubmit();}};
document.querySelector('#network').onclick=()=>fetch('/forbidden',{method:'POST'}).catch(()=>{});
</script>'''


class Handler(BaseHTTPRequestHandler):
    writes = 0
    def do_GET(self):
        data = (HTML.replace('window.submits++;', 'window.submits+=2;') if self.path == '/broken' else HTML).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_POST(self):
        type(self).writes += 1
        self.send_response(204)
        self.end_headers()
    def log_message(self, *args):
        pass


def exercise(factory, url, out):
    scenario = {'url': url, 'goal': 'Add milk once, then mark it complete. Never use Outside or Unapproved request.',
                'covers': ['ONE-SUBMIT', 'CHECKBOX'], 'values': {'milk': 'milk'}, 'max_steps': 4, 'max_seconds': 90,
                'safety': {'fixture': 'isolated-todo', 'allowed_operations': ['fill_submit', 'check', 'click']},
                'checks': [{'js': 'window.submits', 'equals': 1},
                           {'js': "document.querySelector('#list input')?.checked", 'equals': True}]}
    plan = contract.replay_plan(scenario, [
        {'operation': 'fill_submit', 'target': {'role': 'textbox', 'name': 'New todo'}, 'value': 'milk'},
        {'operation': 'check', 'target': {'role': 'checkbox', 'name': 'Toggle milk'}}])
    browser = factory(contract.policy(scenario))
    result = web.run(scenario, browser, None, out / 'healthy', replay=plan)
    assert result['passed'] and result['jev_calls'] == 0, result
    assert 'cleanup' not in result['executor'], result['executor']
    broken_scenario = {**scenario, 'url': url.replace('/todo', '/broken')}
    broken_plan = contract.replay_plan(broken_scenario, plan['steps'])
    broken = web.run(broken_scenario, factory(contract.policy(broken_scenario)), None, out / 'inserted-bug', replay=broken_plan)
    assert not broken['passed'] and not broken['assertions_passed'] and broken['checks'][0]['value'] == 2, broken
    probes = {}
    browser = factory(contract.policy(scenario))
    try:
        browser.open(url)
        raw = browser.snapshot()
        page = contract.observation(raw, scenario)
        textbox = next(e for e in page['elements'] if e['role'] == 'textbox')
        browser.evaluate("document.querySelector('input').replaceWith(document.querySelector('input').cloneNode(true))")
        assert browser.preflight(page, 'fill_submit', textbox['ref'], contract.policy(scenario)) == 'stale_state'
        probes['identical_dom_replacement'] = 'stale_state'
        browser.evaluate("const cover=document.createElement('div');cover.id='cover';cover.style='position:fixed;inset:0;background:gray;z-index:9999';document.body.append(cover)")
        page = contract.observation(browser.snapshot(), scenario)
        textbox = next(e for e in page['elements'] if e['role'] == 'textbox')
        assert browser.preflight(page, 'fill_submit', textbox['ref'], contract.policy(scenario)) == 'not_actionable'
        probes['occlusion'] = 'not_actionable'
        browser.evaluate("document.querySelector('#cover').remove()")
        page = contract.observation(browser.snapshot(), scenario)
        outside = next(e for e in page['elements'] if e['role'] == 'link' and e['name'] == 'Outside')
        assert browser.preflight(page, 'click', outside['ref'], contract.policy(scenario)) == 'origin_not_allowed'
        probes['external_origin'] = 'origin_not_allowed'
        for name in ('Foreign form submit', 'Foreign submit override'):
            page = contract.observation(browser.snapshot(), scenario)
            target = next(e for e in page['elements'] if e['role'] == 'button' and e['name'] == name)
            assert browser.preflight(page, 'click', target['ref'], contract.policy(scenario)) == 'origin_not_allowed'
        probes['foreign_form_submit_and_override'] = 'origin_not_allowed'
    finally:
        browser.close()
    if browser.request_filtering:
        dangerous = {**scenario, 'checks': [{'js': 'window.submits', 'equals': 0}]}
        block_plan = contract.replay_plan(dangerous, [{'operation': 'click', 'target': {'role': 'button', 'name': 'Unapproved request'}}])
        blocked = web.run(dangerous, factory(contract.policy(dangerous)), None, out / 'network', replay=block_plan)
        assert not blocked['passed'] and blocked['result'] == 'blocked_policy', blocked
        assert Handler.writes == 0, 'request guard allowed a write'
        probes['unapproved_same_origin_post'] = 'blocked'
    return {'healthy': result, 'inserted_bug': broken, 'probes': probes,
            'fixture_sha256': hashlib.sha256(HTML.encode()).hexdigest(),
            'metrics': {'sample': 'one healthy fixture and one known counter bug; deterministic replay only',
                        'healthy_passes': 1, 'inserted_bugs_detected': 1, 'false_passes': 0, 'false_failures': 0,
                        'measured_jev_calls': 0, 'measured_api_cost': 0,
                        'unmeasured': ['model exploration quality', 'general bug recall', 'CUAWright', 'visual quality'],
                        'timing_claim': 'per-run elapsed_s only; this small sequential sample does not establish performance gains'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('orca', 'playwright', 'both'), default='playwright')
    parser.add_argument('--playwright-package', type=Path)
    parser.add_argument('--browser-executable')
    parser.add_argument('--worktree', default='path:' + ROOT.as_posix())
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/todo'
    orca_tabs = []
    try:
        with tempfile.TemporaryDirectory(prefix='fullops-web-browser-') as temp:
            out = args.out or Path(temp)
            result = {}
            if args.engine in ('playwright', 'both'):
                result['playwright'] = exercise(lambda safety: PlaywrightBrowser(ROOT, safety, args.playwright_package, args.browser_executable), url, out / 'playwright')
            if args.engine in ('orca', 'both'):
                version = subprocess.run([web.find_orca(), '--version'], capture_output=True, text=True, timeout=10)
                def factory(safety):
                    browser = web.Browser(web.find_orca(), args.worktree)
                    if version.returncode == 0:
                        browser.identity['version'] = version.stdout.strip()
                    original = browser.open
                    def open_and_track(url):
                        original(url)
                        orca_tabs.append(browser.page)
                    browser.open = open_and_track
                    return browser
                result['orca'] = exercise(factory, url, out / 'orca')
            if len(result) == 2:
                a, b = (v['healthy'] for v in result.values())
                assert a['scenario_sha256'] == b['scenario_sha256']
                assert a['checks'] == b['checks']
                assert result['orca']['inserted_bug']['scenario_sha256'] == result['playwright']['inserted_bug']['scenario_sha256']
                assert result['orca']['inserted_bug']['checks'] == result['playwright']['inserted_bug']['checks']
            if args.out:
                args.out.mkdir(parents=True, exist_ok=True)
                (args.out / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print('PASS: real browser single-submit, independent assertions, stale DOM, occlusion, origin and optional network guard; no model calls')
    finally:
        for page in orca_tabs:
            subprocess.run([web.find_orca(), 'tab', 'close', '--page', page, '--worktree', args.worktree, '--json'], capture_output=True, timeout=15)
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
