import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright
async def main():
 root=Path(sys.argv[1]).resolve(); results=[];out=root/'qa-evidence';out.mkdir(exist_ok=True)
 async with async_playwright() as pw:
  browser=await pw.firefox.connect(Path('/private/tmp/fullops-completion-z_ii0xr2/firefox-endpoint.txt').read_text())
  try:
   for width in (320,390,1280):
    context=await browser.new_context(viewport={'width':width,'height':900},reduced_motion='reduce',service_workers='block');page=await context.new_page()
    await context.route('**/*',lambda route:route.abort())
    await page.set_content((root/'index.html').read_text());page.set_default_timeout(5000)
    checks=[]
    async def check(name,truth):checks.append({'name':name,'passed':bool(truth)})
    await check('empty',await page.locator('#status').inner_text()=='No todos yet')
    await check('no-overflow',await page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    await page.get_by_role('button',name='Dark theme').focus();await page.keyboard.press('Space');await check('keyboard-dark',await page.evaluate("document.documentElement.dataset.theme==='dark'"))
    await check('focus-visible',await page.locator('#theme').evaluate("e=>getComputedStyle(e).outlineStyle!=='none'"))
    await check('reduced-motion',await page.locator('body').evaluate("e=>getComputedStyle(e).transitionDuration==='0s'"))
    await page.keyboard.press('Alt+n');await check('shortcut-input-focus',await page.locator('#todo').evaluate('e=>e===document.activeElement'))
    await page.get_by_role('textbox',name='New todo').fill('milk');await page.get_by_role('button',name='Add',exact=True).click();await page.get_by_role('checkbox',name='Toggle milk').click()
    await check('one-add-and-check',await page.evaluate("window.submits===1&&document.querySelectorAll('#list li').length===1&&document.querySelector('#list input').checked"))
    await page.locator('#clear').click();await page.locator('#cancel').click();await check('cancel-preserves-focus',await page.evaluate("document.querySelectorAll('#list li').length===1&&document.activeElement.id==='clear'"))
    await page.locator('#clear').click();await page.keyboard.press('Escape');await page.wait_for_timeout(30);await check('escape-preserves-focus',await page.evaluate("!document.querySelector('#confirm').open&&document.activeElement.id==='clear'"))
    await page.locator('#clear').click();await page.locator('#confirmclear').click();await check('confirmed-clear',await page.locator('#list li').count()==0)
    await page.locator('#loadcase').select_option('error');await page.locator('#load').click();await check('loading',await page.locator('#status').inner_text()=='Loading');await page.wait_for_timeout(150);await check('error-no-auto-retry',await page.evaluate("window.loadRequests===1&&document.querySelector('#status').textContent==='Could not load todos'"))
    await page.locator('#retry').click();await page.wait_for_timeout(150);await check('manual-retry-once',await page.evaluate('window.loadRequests===2'))
    await page.locator('#loadcase').select_option('empty');await page.locator('#load').click();await page.wait_for_timeout(150);await check('load-empty',await page.locator('#status').inner_text()=='No todos yet')
    await page.locator('#loadcase').select_option('data');await page.locator('#load').click();await page.locator('#load').click(force=True,timeout=300);await page.wait_for_timeout(150);await check('repeat-disabled-load',await page.evaluate("window.loadRequests===4&&document.querySelectorAll('#list li').length===1"))
    await page.screenshot(path=str(out/f'{width}-dark.png'))
    await page.locator('#theme').click();await check('light-restored',await page.evaluate("document.documentElement.dataset.theme==='light'"))
    # set_content has opaque about:blank URL; local history navigation requires actual loopback fixture and is measured separately.
    results.append({'width':width,'checks':checks});await context.close()
  finally:await browser.close()
 record={'checks':results,'passed':all(c['passed'] for r in results for c in r['checks']),'model_calls':0,'network_requests_allowed':0,'browser':'Firefox155.0 broker, fresh context each width','unexamined':['loopback history back measured separately']};(out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record));return record['passed']
sys.exit(0 if asyncio.run(main()) else 1)
