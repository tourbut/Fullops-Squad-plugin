"""Independent reviewer-authored checks; never executes implementer qa.py."""
import asyncio
import hashlib
import json
from pathlib import Path

from playwright.async_api import async_playwright

SNAPSHOT = Path('/private/tmp/fullops-completion-z_ii0xr2/ui-codex-review-r02')
OUT = Path(__file__).resolve().parent
SHA = '3a361d576441b9bd7633b4641911c3388416e7b1'
URL = 'http://127.0.0.1:57186/ui-independent-codex-r02'
HTML = (SNAPSHOT / 'index.html').read_bytes()
EXPECTED_HASH = '6c219f8ce669bb3b337c58a79af77ac810728b1ccfa9d889b791759fdd9cf912'


async def main():
    if hashlib.sha256(HTML).hexdigest() != EXPECTED_HASH:
        raise RuntimeError('reviewed HTML hash changed')
    result = {'source_sha': SHA, 'index_sha256': EXPECTED_HASH,
              'reviewer': '/root/macos_standards_review', 'widths': [],
              'network_requests_allowed': 0, 'model_calls': 0,
              'implementer_qa_executed': False}
    async with async_playwright() as pw:
        browser = await pw.firefox.connect(Path('/private/tmp/fullops-completion-z_ii0xr2/firefox-endpoint.txt').read_text(), timeout=20000)
        try:
            result['browser'] = browser.version
            for width in (320, 390, 1280):
                checks, requests, errors, console_errors = [], [], [], []
                context = await browser.new_context(viewport={'width': width, 'height': 900},
                                                    reduced_motion='reduce', service_workers='block')

                async def guard(route):
                    request = route.request
                    if request.url == URL and request.method == 'GET' and request.resource_type == 'document':
                        requests.append({'url': request.url, 'method': request.method, 'action': 'fulfilled immutable reviewed bytes'})
                        await route.fulfill(status=200, content_type='text/html; charset=utf-8', body=HTML)
                    else:
                        requests.append({'url': request.url, 'method': request.method, 'action': 'blocked'})
                        await route.abort()

                await context.route('**/*', guard)
                page = await context.new_page()
                page.set_default_timeout(5000)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('console', lambda message: console_errors.append(message.text) if message.type == 'error' else None)

                async def record(name, expression):
                    observed = await page.evaluate(expression)
                    checks.append({'name': name, 'passed': observed is True, 'observed': observed})

                async def focus_theme():
                    await page.locator('#theme').focus()

                try:
                    await page.goto(URL, wait_until='networkidle')
                    await record('initial light and shortcut metadata', "document.documentElement.dataset.theme==='light' && document.querySelector('#todo').getAttribute('aria-keyshortcuts')==='Alt+n' && window.submits===0")
                    await record('initial mobile overflow', 'document.documentElement.scrollWidth<=innerWidth')
                    await focus_theme()
                    await page.keyboard.press('Space')
                    await record('keyboard theme and reduced motion', "document.documentElement.dataset.theme==='dark' && document.querySelector('#theme').getAttribute('aria-pressed')==='true' && getComputedStyle(document.body).transitionDuration==='0s'")
                    await record('keyboard focus visible', "getComputedStyle(document.activeElement).outlineStyle!=='none' && parseFloat(getComputedStyle(document.activeElement).outlineWidth)>=2")
                    await page.keyboard.press('Alt+n')
                    await record('shortcut focuses without submission', "document.activeElement.id==='todo' && window.submits===0 && document.querySelectorAll('#list li').length===0")
                    await page.locator('#todo').fill('draft remains')
                    await focus_theme()
                    await page.keyboard.press('Alt+n')
                    await record('shortcut preserves draft', "document.activeElement.id==='todo' && document.querySelector('#todo').value==='draft remains' && window.submits===0")
                    await focus_theme()
                    await page.keyboard.press('Control+Alt+n')
                    await record('control modifier excluded', "document.activeElement.id==='theme' && window.submits===0")
                    await focus_theme()
                    await page.keyboard.press('Meta+Alt+n')
                    await record('meta modifier excluded', "document.activeElement.id==='theme' && window.submits===0")
                    await page.locator('#todo').fill('milk')
                    await page.locator('#todo').press('Enter')
                    await page.get_by_role('checkbox', name='Toggle milk', exact=True).click()
                    await record('Enter submits once and checkbox completes', "window.submits===1 && document.querySelectorAll('#list li').length===1 && document.querySelector('#list li').textContent.trim()==='milk' && document.querySelector('#list input').checked")
                    await focus_theme()
                    await page.keyboard.press('Alt+n')
                    await record('shortcut after add does not resubmit', "document.activeElement.id==='todo' && window.submits===1 && document.querySelectorAll('#list li').length===1")
                    await record('dark state overflow', 'document.documentElement.scrollWidth<=innerWidth')
                    await page.screenshot(path=str(OUT / f'{width}-dark-independent.png'))
                    await page.locator('#clear').click()
                    await page.keyboard.press('Alt+n')
                    await record('modal shortcut keeps cancel focus', "document.querySelector('#confirm').open && document.activeElement.id==='cancel' && window.submits===1 && document.querySelectorAll('#list li').length===1")
                    await page.locator('#confirmclear').focus()
                    await page.keyboard.press('Alt+n')
                    await record('modal shortcut keeps confirm focus', "document.querySelector('#confirm').open && document.activeElement.id==='confirmclear' && window.submits===1")
                    await page.keyboard.press('Shift+Tab')
                    await record('modal backwards tab stays inside', "document.activeElement.id==='cancel'")
                    if width == 320:
                        await page.screenshot(path=str(OUT / '320-modal-independent.png'))
                    await page.keyboard.press('Escape')
                    await page.wait_for_function("!document.querySelector('#confirm').open && document.activeElement.id==='clear'")
                    await record('Escape returns focus and preserves row', "document.activeElement.id==='clear' && document.querySelectorAll('#list li').length===1")
                    await page.locator('#clear').click()
                    await page.locator('#cancel').click()
                    await record('cancel preserves row and focus', "document.activeElement.id==='clear' && document.querySelectorAll('#list li').length===1")
                    await page.locator('#details').click()
                    await record('details opens and focuses Back', "!document.querySelector('#detail').hidden && document.activeElement.id==='back' && location.hash==='#details'")
                    await page.locator('#back').click()
                    await page.wait_for_function("document.querySelector('#detail').hidden && location.hash==='' && document.activeElement.id==='details'")
                    await record('history Back restores details focus', "document.querySelector('#detail').hidden && location.hash==='' && document.activeElement.id==='details'")
                    await page.locator('#clear').click()
                    await page.locator('#confirmclear').click()
                    await record('confirmed clear preserved', "document.querySelectorAll('#list li').length===0 && document.activeElement.id==='clear' && !document.querySelector('#confirm').open")
                    await focus_theme()
                    await page.keyboard.press('Space')
                    await record('light restored and overflow', "document.documentElement.dataset.theme==='light' && document.querySelector('#theme').getAttribute('aria-pressed')==='false' && document.documentElement.scrollWidth<=innerWidth")
                    if width == 320:
                        await page.screenshot(path=str(OUT / '320-light-independent.png'))
                    (OUT / f'{width}-aria.txt').write_text(await page.locator('main').aria_snapshot())
                except Exception as error:
                    errors.append(type(error).__name__ + ': ' + str(error))
                    await page.screenshot(path=str(OUT / f'{width}-failure.png'))
                finally:
                    result['widths'].append({'width': width, 'height': 900, 'checks': checks,
                                             'requests': requests, 'page_errors': errors,
                                             'console_errors': console_errors})
                    await context.close()
        finally:
            await browser.close()
    result['passed'] = all(c['passed'] for w in result['widths'] for c in w['checks']) and all(
        len(w['checks']) == 20 and not w['page_errors'] and not w['console_errors'] and
        all(r['action'] != 'blocked' for r in w['requests']) for w in result['widths'])
    result['checks_total'] = sum(len(w['checks']) for w in result['widths'])
    result['checks_passed'] = sum(c['passed'] for w in result['widths'] for c in w['checks'])
    (OUT / 'qa.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'source_sha': SHA, 'passed': result['passed'],
                      'checks_total': result['checks_total'], 'checks_passed': result['checks_passed'],
                      'errors': [w['page_errors'] for w in result['widths']]}), flush=True)


asyncio.run(main())
