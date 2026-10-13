from pathlib import Path
import subprocess,os,json,shutil,time,hashlib
b=Path(__file__).parent;w=b/'cua-work';source=b/'evidence/cua-bounded-generated.py';ev=b/'evidence/cua-bounded-replay';ev.mkdir(exist_ok=True);records=[]
baseenv={'PATH':'/usr/bin:/bin','HOME':str(b/'browser-home'),'TMPDIR':str(b/'browser-tmp'),'PYTHONDONTWRITEBYTECODE':'1','PLAYWRIGHT_BROWSERS_PATH':str(b/'browsers')}
# No model/API call is available to this runner or the sandboxed generated process.
for n,(case,todo,default) in enumerate([('healthy','milk',True)],start=19):
 run=w/f'final_runs/run_{n}';run.mkdir();shutil.copy2(source,run/'final_script.py');endpoint=run/'endpoint.private.txt';proof=ev/f'run-{n}.json';start=time.monotonic()
 log=(run/'broker.log').open('w');broker=subprocess.Popen(['node',str(b/'firefox_broker.cjs'),str(endpoint)],stdout=log,stderr=subprocess.STDOUT)
 try:
  deadline=time.monotonic()+22
  while not endpoint.exists():
   if time.monotonic()>deadline or broker.poll() is not None:raise RuntimeError('fresh broker launch failed')
   time.sleep(.05)
  argv=['/usr/bin/sandbox-exec','-f',str(b/'cua-sandbox.sb'),str(b/'runtime/bin/python'),str(b/'execute_cua.py'),str(run/'final_script.py')]
  if not default:argv+=['--url','http://127.0.0.1:57186/'+case,'--todo',todo]
  p=subprocess.run(argv,env={**baseenv,'INDEPENDENT_PROOF':str(proof),'BROWSER_ENDPOINT_FILE':str(endpoint),'TODO_VALUE':todo},capture_output=True,text=True,timeout=60);(run/'execution.log').write_text(p.stdout+p.stderr);result=json.loads(proof.read_text());result.update(run=n,case=case,todo=todo,default_args=default,exit_code=p.returncode,total_elapsed_s=time.monotonic()-start,fresh_browser_process=True);proof.write_text(json.dumps(result,indent=2)+'\n');records.append(result);print(n,case,todo,result['pass'],flush=True)
 except Exception as exc:records.append({'run':n,'case':case,'error':type(exc).__name__+': '+str(exc)})
 finally:
  broker.terminate()
  try:broker.wait(timeout=8)
  except subprocess.TimeoutExpired:broker.kill();broker.wait()
  log.close();endpoint.unlink(missing_ok=True)
 (ev/'runs.json').write_text(json.dumps(records,indent=2)+'\n')
# Import/help smoke tests: a reusable generated path must not launch a browser at import.
code="import importlib.util; spec=importlib.util.spec_from_file_location('cua_task',"+repr(str(source))+"); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('IMPORT_SAFE',callable(m.complete_todo))"
p=subprocess.run([str(b/'runtime/bin/python'),'-B','-c',code],capture_output=True,text=True,timeout=10);(ev/'import-smoke.log').write_text(p.stdout+p.stderr)
p=subprocess.run([str(b/'runtime/bin/python'),'-B',str(source),'--help'],capture_output=True,text=True,timeout=10);(ev/'cli-help.log').write_text(p.stdout+p.stderr)
