import asyncio,json,time,hashlib
from pathlib import Path
from playwright.async_api import async_playwright
b=Path(__file__).parent;out=b/'evidence/e2e';out.mkdir(exist_ok=True)
async def main():
 results=[]
 async with async_playwright() as pw:
  for rep in range(1,4):
   for case in ('healthy','duplicate','no-check','no-theme'):
    start=time.monotonic();browser=await pw.firefox.launch(headless=True);context=await browser.new_context(viewport={'width':1280,'height':1800},service_workers='block');page=await context.new_page();url='http://127.0.0.1:57186/'+case;blocked=[]
    async def guard(route):
     if route.request.method=='GET' and route.request.url==url:await route.continue_()
     else:blocked.append(route.request.url);await route.abort()
    await context.route('**/*',guard);await context.route_web_socket('**/*',lambda ws:ws.close());page.set_default_timeout(20000)
    try:
     await page.goto(url);await page.get_by_role('button',name='Dark theme').click();await page.get_by_role('textbox',name='New todo').fill('milk');await page.get_by_role('button',name='Add',exact=True).click();await page.get_by_role('checkbox',name='Toggle milk').first.click()
     actual=await page.evaluate("({theme:document.documentElement.dataset.theme,submissions:window.submits,rows:document.querySelectorAll('#list li').length,text:document.querySelector('#list li')?.textContent.trim(),checked:document.querySelector('#list input')?.checked})");expected={'theme':'dark','submissions':1,'rows':1,'text':'milk','checked':True};result={'repetition':rep,'case':case,'passed':actual==expected and not blocked,'actual':actual,'expected':expected,'blocked':blocked,'model_calls':0,'cost':0,'browser':browser.version,'viewport':page.viewport_size,'elapsed_s':time.monotonic()-start};await page.screenshot(path=str(out/f'{rep}-{case}.png'));results.append(result)
    finally:await browser.close()
    (out/'runs.json').write_text(json.dumps(results,indent=2)+'\n');print(rep,case,results[-1]['passed'],flush=True)
asyncio.run(main())
