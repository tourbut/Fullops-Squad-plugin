from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
import sys,json,subprocess,time,hashlib
base=Path(__file__).resolve().parents[2]
source=base/'final-source';artifacts=base/'native-ui-r01-review';out=base/'evidence/native-ui/orca-qa';out.mkdir(exist_ok=True)
sys.path.insert(0,str(source/'plugins/fullops-squad/scripts'))
import jev_test_web as web,web_contract as contract
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  host=self.path[1:]
  if host not in ('codex','grok'):self.send_error(404);return
  data=(artifacts/(host+'.html')).read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_POST(self):self.send_error(403)
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);Thread(target=server.serve_forever,daemon=True).start()
results={}
try:
 for host,name in [('codex','Dark theme'),('grok','Theme: light')]:
  url=f'http://127.0.0.1:{server.server_port}/{host}'
  scenario={'url':url,'goal':'Switch to dark theme, add milk exactly once, then complete it. Never use foreign links/forms or Unapproved request.','covers':['THEME','ONE-SUBMIT','CHECKBOX'],'values':{'milk':'milk'},'max_steps':5,'max_seconds':120,'safety':{'fixture':'native-ui-macos','allowed_operations':['click','fill_submit','check']},'checks':[{'js':'document.documentElement.dataset.theme','equals':'dark'},{'js':'window.submits','equals':1},{'js':"document.querySelector('#list input')?.checked",'equals':True}]}
  plan=contract.replay_plan(scenario,[{'operation':'click','target':{'role':'button','name':name}},{'operation':'fill_submit','target':{'role':'textbox','name':'New todo'},'value':'milk'},{'operation':'check','target':{'role':'checkbox','name':'Toggle milk'}}])
  browser=web.Browser('orca','path:/Users/shin/MyDir/MyGit/Fullops-Squad-plugin');browser.identity['version']='1.4.224'
  try:
   result=web.run(scenario,browser,None,out/host,replay=plan)
   results[host]={'result':result,'artifact_sha256':hashlib.sha256((artifacts/(host+'.html')).read_bytes()).hexdigest()}
   print(host,result['passed'],result['jev_calls'],flush=True)
  finally:
   if browser.page:
    p=subprocess.run(['orca','tab','close','--page',browser.page,'--worktree','path:/Users/shin/MyDir/MyGit/Fullops-Squad-plugin','--json'],capture_output=True,text=True,timeout=15)
    (out/(host+'-tab-close.json')).write_text(p.stdout)
finally:
 server.shutdown();server.server_close()
 (out/'result.json').write_text(json.dumps(results,indent=2)+'\n')
assert len(results)==2 and all(x['result']['passed'] for x in results.values()),results
