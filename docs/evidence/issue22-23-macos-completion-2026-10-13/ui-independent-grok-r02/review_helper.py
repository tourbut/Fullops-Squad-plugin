"""Independent fixed-SHA UI checks; does not import the implementer's QA."""
import asyncio
import hashlib
import json
from pathlib import Path

from playwright.async_api import async_playwright

SOURCE = Path('/private/tmp/fullops-completion-z_ii0xr2/ui-grok-review-r02')
OUT = Path(__file__).parent
ENDPOINT = Path('/private/tmp/fullops-completion-z_ii0xr2/firefox-endpoint.txt')
SHA = '7e7a4d2f5830233317abcca787ec180b3041625e'
URL = 'http://127.0.0.1:57186/independent-grok-r02'
HTML = (SOURCE / 'index.html').read_text()
checks, errors, requests, screenshots = [], [], [], []


def check(width, name, actual, expected):
    checks.append(dict(width=width, name=name, actual=actual, expected=expected, passed=actual == expected))


async def state(page):
    return await page.evaluate("""() => ({
        focus:document.activeElement.id, draft:document.querySelector('#todo').value,
        submits:window.submits, rows:document.querySelectorAll('#list li').length,
        theme:document.documentElement.dataset.theme,
        overflow:document.documentElement.scrollWidth>innerWidth,
        width:innerWidth, modal:document.querySelector('#confirm').open,
        focusInModal:document.querySelector('#confirm').contains(document.activeElement)
    })""")


async def shot(page, name):
    path = OUT / name
    await page.screenshot(path=str(path))
    screenshots.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))


async def run():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.firefox.connect(ENDPOINT.read_text().strip(), timeout=20000)
        for width in (320, 390, 1280):
            context = await browser.new_context(viewport={'width':width, 'height':900}, reduced_motion='reduce', service_workers='block')
            async def guard(route):
                request = route.request
                allowed = request.method == 'GET' and request.url == URL
                requests.append(dict(width=width, url=request.url, method=request.method, supplied=allowed))
                if allowed:
                    await route.fulfill(status=200, content_type='text/html', body=HTML)
                else:
                    await route.abort()
            await context.route('**/*', guard)
            page = await context.new_page()
            page.set_default_timeout(5000)
            page.on('pageerror', lambda error, w=width: errors.append(dict(width=w, pageerror=str(error))))
            try:
                await page.goto(URL, wait_until='networkidle')
                initial = await state(page)
                check(width, 'initial-light', initial['theme'], 'light')
                check(width, 'viewport-width', initial['width'], width)
                check(width, 'initial-no-overflow', initial['overflow'], False)
                check(width, 'declared-shortcut', await page.locator('#todo').get_attribute('aria-keyshortcuts'), 'Alt+n')
                check(width, 'restricted-disabled', await page.locator('#restricted').is_disabled(), True)
                await page.locator('#todo').fill('draft milk')
                await page.locator('#theme').focus()
                await page.keyboard.press('Alt+n')
                shortcut = await state(page)
                check(width, 'shortcut-focuses-todo', shortcut['focus'], 'todo')
                check(width, 'shortcut-preserves-draft', shortcut['draft'], 'draft milk')
                check(width, 'shortcut-does-not-submit', [shortcut['submits'], shortcut['rows']], [0, 0])
                check(width, 'shortcut-visible-focus', await page.locator('#todo').evaluate("e=>getComputedStyle(e).outlineStyle"), 'solid')
                await page.locator('#theme').focus()
                await page.keyboard.press('Control+Alt+n')
                check(width, 'ctrl-alt-does-not-trigger', (await state(page))['focus'], 'theme')
                await page.locator('#todo').fill('milk')
                await page.locator('#todo').press('Enter')
                added = await state(page)
                check(width, 'enter-single-submission', [added['submits'], added['rows']], [1, 1])
                check(width, 'milk-exact-text', (await page.locator('#list li').inner_text()).strip(), 'milk')
                await page.get_by_role('checkbox', name='Toggle milk', exact=True).click()
                check(width, 'checkbox-completes', await page.get_by_role('checkbox', name='Toggle milk', exact=True).is_checked(), True)
                await page.locator('#theme').click()
                check(width, 'dark-theme', (await state(page))['theme'], 'dark')
                check(width, 'dark-pressed', await page.locator('#theme').get_attribute('aria-pressed'), 'true')
                check(width, 'dark-token-background', await page.locator('body').evaluate("e=>getComputedStyle(e).backgroundColor"), 'rgb(22, 22, 22)')
                check(width, 'dark-no-overflow', (await state(page))['overflow'], False)
                check(width, 'reduced-motion', await page.locator('body').evaluate("e=>getComputedStyle(e).transitionDuration"), '0s')
                await shot(page, f'{width}-dark-independent.png')
                await page.locator('#todo').fill('kept during modal')
                await page.locator('#clear').click()
                modal = await state(page)
                check(width, 'modal-opens-cancel-focus', [modal['modal'], modal['focus']], [True, 'cancel'])
                await page.keyboard.press('Alt+n')
                modal_shortcut = await state(page)
                check(width, 'shortcut-keeps-modal-focus-boundary', modal_shortcut['focusInModal'], True)
                check(width, 'modal-shortcut-preserves-draft', modal_shortcut['draft'], 'kept during modal')
                check(width, 'modal-shortcut-no-submit', modal_shortcut['submits'], 1)
                await page.keyboard.press('Tab')
                check(width, 'modal-tab-focus-boundary', (await state(page))['focusInModal'], True)
                await page.keyboard.press('Shift+Tab')
                check(width, 'modal-shift-tab-focus-boundary', (await state(page))['focusInModal'], True)
                if width == 320:
                    await shot(page, '320-modal-independent.png')
                await page.keyboard.press('Escape')
                await page.wait_for_function("!document.querySelector('#confirm').open && document.activeElement.id==='clear'")
                check(width, 'escape-restores-clear-focus', [(await state(page))['modal'], (await state(page))['focus']], [False, 'clear'])
                check(width, 'cancel-preserves-milk', await page.locator('#list li').count(), 1)
                await page.locator('#clear').click()
                await page.locator('#confirmclear').click()
                cleared = await state(page)
                check(width, 'confirm-clear-clears-only-list', [cleared['rows'], cleared['submits'], cleared['focus']], [0, 1, 'clear'])
                await page.locator('#theme').click()
                check(width, 'theme-roundtrip-light', (await state(page))['theme'], 'light')
                check(width, 'light-token-background', await page.locator('body').evaluate("e=>getComputedStyle(e).backgroundColor"), 'rgb(255, 255, 255)')
                await page.locator('#loadcase').select_option('data')
                await page.locator('#load').click()
                await page.wait_for_function("!document.querySelector('#load').disabled")
                check(width, 'load-data-preserved', (await page.locator('#list li').inner_text()).strip(), 'loaded')
                await page.locator('#loadcase').select_option('empty')
                await page.locator('#load').click()
                await page.wait_for_function("!document.querySelector('#load').disabled")
                check(width, 'load-empty-preserved', await page.locator('#list li').count(), 0)
                await page.locator('#loadcase').select_option('error')
                await page.locator('#load').click()
                await page.wait_for_function("!document.querySelector('#retry').hidden")
                check(width, 'load-error-preserved', await page.locator('#status').inner_text(), 'Could not load todos')
                load_before = await page.evaluate('window.loadRequests')
                await page.locator('#retry').click()
                await page.wait_for_function("!document.querySelector('#load').disabled")
                check(width, 'retry-one-request', await page.evaluate('window.loadRequests'), load_before + 1)
                await page.locator('#details').click()
                check(width, 'details-opens-with-focus', [await page.locator('#detail').is_visible(), (await state(page))['focus']], [True, 'back'])
                check(width, 'details-real-history-entry', await page.evaluate('location.hash'), '#details')
                await page.locator('#back').click()
                await page.wait_for_function("location.hash==='' && document.querySelector('#detail').hidden")
                check(width, 'details-back-restores-focus', (await state(page))['focus'], 'details')
                await page.locator('#details').click()
                await page.go_back()
                await page.wait_for_function("document.querySelector('#detail').hidden")
                check(width, 'browser-back-preserved', [(await state(page))['focus'], await page.evaluate('location.hash')], ['details', ''])
                check(width, 'final-no-overflow', (await state(page))['overflow'], False)
            except Exception as exc:
                errors.append(dict(width=width, execution_error=type(exc).__name__ + ': ' + str(exc)))
                await shot(page, f'{width}-exception.png')
            finally:
                await context.close()
        await browser.close()
    record = dict(schema_version=1, reviewer='/root/macos_spec_review', source_sha=SHA,
                  source_files={name:hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in ('index.html','DESIGN.md','tokens.css','qa.py')},
                  independent_helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  browser='native Firefox broker with fresh context per viewport',
                  implementer_qa_imported_or_run=False, tests=checks, errors=errors, requests=requests,
                  screenshots=screenshots, pass_count=sum(c['passed'] for c in checks), fail_count=sum(not c['passed'] for c in checks))
    record['passed'] = record['fail_count'] == 0 and not errors and all(r['supplied'] for r in requests)
    (OUT/'qa-result.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({k:record[k] for k in ('source_sha','pass_count','fail_count','errors','passed')}, indent=2))


if __name__ == '__main__':
    asyncio.run(run())
