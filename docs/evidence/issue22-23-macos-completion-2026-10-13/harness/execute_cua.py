"""Trusted runner: generated file cannot supply its own acceptance verdict."""
import asyncio, hashlib, json, os, runpy, sys, time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.async_api import Browser, BrowserContext, BrowserType
SCRIPT=Path(sys.argv[1]).resolve(); OUT=Path(os.environ['INDEPENDENT_PROOF']); ORIGIN='http://127.0.0.1:57186'
original_context=Browser.new_context; original_close=Browser.close
observations=[]; blocked=[]
async def restricted_context(self,*args,**kwargs):
    kwargs.update(viewport={'width':1280,'height':1800},service_workers='block')
    context=await original_context(self,*args,**kwargs)
    async def guard(route):
        request=route.request
        if request.method=='GET' and request.url.split('?')[0] in [ORIGIN+'/'+x for x in ('healthy','duplicate','no-check','no-theme')]:
            await route.continue_()
        else:
            blocked.append({'method':request.method,'url':request.url}); await route.abort()
    await context.route('**/*',guard)
    await context.route_web_socket('**/*',lambda ws:ws.close())
    return context
async def restricted_page(self,**kwargs):
    context=await restricted_context(self,**kwargs)
    return await context.new_page()
async def audited_close(self,*args,**kwargs):
    for context in self.contexts:
        for page in context.pages:
            try:
                data=await page.evaluate("({theme:document.documentElement.dataset.theme,submissions:window.submits,rows:document.querySelectorAll('#list li').length,text:document.querySelector('#list li')?.textContent.trim(),checked:document.querySelector('#list input')?.checked??false})")
                data.update(url=page.url,viewport=page.viewport_size)
                observations.append(data)
            except Exception as exc:observations.append({'capture_error':str(exc)})
    return await original_close(self,*args,**kwargs)
async def broker_launch(self,**kwargs):
    if self.name!='firefox':raise RuntimeError('unapproved engine')
    return await self.connect(Path(os.environ.get('BROWSER_ENDPOINT_FILE','/private/tmp/fullops-completion-z_ii0xr2/firefox-endpoint.txt')).read_text(),timeout=20000)
BrowserType.launch=broker_launch
Browser.new_context=restricted_context; Browser.new_page=restricted_page; Browser.close=audited_close
start=time.monotonic(); error=None
sys.argv=[str(SCRIPT),*sys.argv[2:]]
try:runpy.run_path(str(SCRIPT),run_name='__main__')
except BaseException as exc:error=type(exc).__name__+': '+str(exc)
finally:
    expected={'theme':'dark','submissions':1,'rows':1,'text':os.environ.get('TODO_VALUE','milk'),'checked':True}
    passed=not error and len(observations)==1 and all(observations[0].get(k)==v for k,v in expected.items()) and not blocked
    record={'script_sha256':hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),'elapsed_s':time.monotonic()-start,'observations':observations,'expected':expected,'pass':passed,'error':error,'blocked_requests':blocked,'model_calls':0,'authority':'trusted external DOM oracle before browser.close; not generated FINAL_RESPONSE'}
    OUT.write_text(json.dumps(record,indent=2)+'\n'); print(json.dumps(record),flush=True)
if error:sys.exit(2)
