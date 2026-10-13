from pathlib import Path
import os,sys,json,time,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
b=Path(__file__).parent;root=Path('/Users/shin/MyDir/MyGit/Fullops-Squad-plugin');sys.path.insert(0,str(root/'plugins/fullops-squad/scripts'));import jev_observe as jev
out=b/'evidence/cache-api';out.mkdir(exist_ok=True);key=jev.api_key(root/'.env');records=[]
payload={'model':jev.MODEL,'state':{'goal':'dark theme, add milk once, check it','actual':{'theme':'dark','submissions':1,'rows':1,'text':'milk','checked':True}},'questions':{'outcome':{'type':'choice','instructions':'Does actual satisfy every part of goal?','criteria':{'normal':'All task invariants hold','defect':'One or more task invariants fail'}}}}
(out/'budget.json').write_text(json.dumps({'live_requests_max':3,'live_timeout_s':12,'local_failure_repeats':3,'no_automatic_retry':True,'cold_warm':'application response cache only; OS/provider/browser caches uncontrolled','token_limit':'bounded fixed request; Jev API exposes no generation max_tokens setting; actual token usage recorded'},indent=2)+'\n')
for n in range(3):
 os.environ['FULLOPS_JEV_CACHE']=str(b/f'cache-cycle-{n}');os.environ.pop('FULLOPS_JEV_CACHE_BYPASS',None)
 for mode in ('cold','warm'):
  start=time.monotonic()
  try:
   raw,elapsed=jev.request(payload,key,timeout=12);record={'cycle':n,'mode':mode,'elapsed_s':time.monotonic()-start,'reported_latency_s':elapsed,'cached':raw.get('cached',False),'provider_calls':0 if raw.get('cached') else 1,'request_bytes':len(json.dumps(payload).encode()),'response_bytes':len(json.dumps(raw).encode()),'response':raw}
  except Exception as exc:record={'cycle':n,'mode':mode,'error':type(exc).__name__+': '+str(exc),'provider_cost':'unknown'}
  records.append(record);(out/'cache-runs.json').write_text(json.dumps(records,indent=2)+'\n');print(n,mode,record.get('cached'),flush=True)
counts={}
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  case=self.path.strip('/');counts[case]=counts.get(case,0)+1
  if case=='timeout':time.sleep(.6)
  code=int(case) if case.isdigit() else 200
  self.send_response(code);self.end_headers()
  try:self.wfile.write(b'not-json' if case=='malformed' else b'{}')
  except (BrokenPipeError,ConnectionResetError):pass
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();errors=[];os.environ['FULLOPS_JEV_CACHE_BYPASS']='1'
for case in ('401','429','503','malformed','timeout'):
 for n in range(3):
  jev.URL=f'http://127.0.0.1:{server.server_port}/{case}';start=time.monotonic();before=counts.get(case,0)
  try:jev.request(payload,'fixture_invalid_key',timeout=.2 if case=='timeout' else 2);result='UNEXPECTED_SUCCESS'
  except Exception as exc:result=type(exc).__name__+': '+str(exc)
  errors.append({'case':case,'repetition':n,'elapsed_s':time.monotonic()-start,'error':result,'server_attempts':counts.get(case,0)-before,'provider_calls':0,'cost':0,'source':'controlled local HTTP failure, not observed external provider outage'})
server.shutdown();(out/'failure-runs.json').write_text(json.dumps(errors,indent=2)+'\n');print('failures',len(errors),flush=True)
