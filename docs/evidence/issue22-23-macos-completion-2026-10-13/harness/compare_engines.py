from pathlib import Path
import sys,json,subprocess,os,time,hashlib
BASE=Path(__file__).parent;ROOT=Path('/Users/shin/MyDir/MyGit/Fullops-Squad-plugin');sys.path.insert(0,str(ROOT/'plugins/fullops-squad/scripts'))
import jev_test_web as web, web_contract as contract, jev_observe, web_analysis
from web_playwright import PlaywrightBrowser
ORIGIN=json.loads((BASE/'fixture-port.json').read_text())['origin']; OUT=BASE/'evidence/comparison';OUT.mkdir(exist_ok=True)
os.environ['PLAYWRIGHT_BROWSERS_PATH']='/private/tmp/fullops-macos-20261013-4vksnsnw/browsers';os.environ['FULLOPS_JEV_CACHE']=str(BASE/'jev-cache');os.environ['FULLOPS_JEV_CACHE_BYPASS']='1'
key=jev_observe.api_key(ROOT/'.env'); calls=[]; results=[]
# Fixed before measurement; all paths use the same goal and independent invariants.
budget={'max_steps':5,'max_seconds':90,'max_cost':.02,'max_input_chars':12000}
(OUT/'budget.json').write_text(json.dumps({'per_run':budget,'repetitions':3,'cases':['healthy','duplicate','no-check','no-theme'],'max_live_model_calls':60,'request_timeout_s':12,'model':jev_observe.MODEL,'effort':'not exposed by Jev API','cache':'bypassed; separate cold/warm probe later'},indent=2))
checks=[{'js':"document.documentElement.dataset.theme",'equals':'dark'},{'js':'window.submits','equals':1},{'js':"document.querySelectorAll('#list li').length",'equals':1},{'js':"document.querySelector('#list li')?.textContent.trim()",'equals':'milk'},{'js':"document.querySelector('#list input')?.checked",'equals':True}]
steps=[{'operation':'click','target':{'role':'button','name':'Dark theme'}},{'operation':'fill_submit','target':{'role':'textbox','name':'New todo'},'value':'milk'},{'operation':'check','target':{'role':'checkbox','name':'Toggle milk'}}]
def measured(payload):
 if len(calls)>=60:raise RuntimeError('fixed aggregate model call budget')
 start=time.monotonic();item={'request_bytes':len(json.dumps(payload).encode()),'request_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()}
 try:
  raw,elapsed=jev_observe.request(payload,key,timeout=12);item.update(response_bytes=len(json.dumps(raw).encode()),latency_s=elapsed,response=raw);return raw,elapsed
 except Exception as exc:item['error']=type(exc).__name__+': '+str(exc);raise
 finally:item['elapsed_s']=time.monotonic()-start;calls.append(item);(OUT/'live-calls.json').write_text(json.dumps(calls,indent=2)+'\n')
for engine in ('playwright','orca','orca-jev'):
 for repetition in range(1,4):
  for case in ('healthy','duplicate','no-check','no-theme'):
   scenario={'url':ORIGIN+'/'+case,'goal':'Select dark theme, add milk exactly once, then click its checkbox exactly once. Do not load, clear, retry, navigate or change anything else. Finish after those actions even if the fixture is defective.','covers':['DARK','ONE-SUBMIT','ONE-MILK','CHECKED'],'values':{'milk':'milk'},'safety':{'fixture':'human-labelled-isolated-todo','allowed_operations':['click','fill_submit','check']},'checks':checks,**budget}
   dest=OUT/engine/f'{repetition}-{case}';browser=None
   try:
    if engine=='playwright':browser=PlaywrightBrowser(ROOT,contract.policy(scenario),Path('/private/tmp/fullops-macos-20261013-4vksnsnw/tools/node_modules/@playwright/cli/package.json'))
    else:browser=web.Browser(web.find_orca(),'path:'+str(ROOT))
    summary=web.run(scenario,browser,measured if engine=='orca-jev' else None,dest,log=lambda *_:None,replay=None if engine=='orca-jev' else contract.replay_plan(scenario,steps))
    shadow=web_analysis.shadow(summary);(dest/'shadow-original.json').write_text(json.dumps(shadow,indent=2)+'\n')
    (dest/'shadow-labelled.json').write_text(json.dumps({'original':shadow,'human_label':'normal' if case=='healthy' else 'defect','label_source':'human-ground-truth.json','correction_reason':None if case=='healthy' else 'Confirmed seeded fixture mutation; independent observations identify violated invariant. Not evidence of a production defect.','gates_changed':False},indent=2)+'\n')
    results.append({'engine':engine,'repetition':repetition,'case':case,'passed':summary['passed'],'result':summary['result'],'checks':summary['checks'],'elapsed_s':summary['elapsed_s'],'jev_calls':summary['jev_calls'],'known_cost':summary['known_cost'],'executor':summary['executor']})
   except Exception as exc:results.append({'engine':engine,'repetition':repetition,'case':case,'error':type(exc).__name__+': '+str(exc)})
   finally:
    if engine!='playwright' and browser and browser.page:subprocess.run([web.find_orca(),'tab','close','--page',browser.page,'--worktree','path:'+str(ROOT),'--json'],capture_output=True,timeout=10)
   (OUT/'runs.json').write_text(json.dumps(results,indent=2)+'\n');print(engine,repetition,case,results[-1].get('passed'),results[-1].get('result',results[-1].get('error')),flush=True)
