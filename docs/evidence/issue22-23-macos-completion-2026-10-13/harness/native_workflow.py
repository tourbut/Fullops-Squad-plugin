from pathlib import Path
import os,subprocess,shutil,json,time,hashlib
BASE=Path(__file__).parent;EV=BASE/'evidence/native-workflow';EV.mkdir(exist_ok=True)
design='Preserve the accessible neutral todo fixture, all current labels/IDs/behavior and light/dark tokens. Implement Alt+n keyboard shortcut that focuses New todo without submitting, and expose aria-keyshortcuts on the input. No dependencies, network, storage, or other features. Read DESIGN.md and tokens.css, write plan.md, implement index.html, write critique.md, then RUN the supplied exact browser QA command and inspect qa-evidence/result.json. Keep canonical DESIGN.md, tokens.css and qa.py byte-identical. Do not spawn agents.'
clean={k:v for k,v in os.environ.items() if not k.startswith('ORCA_')};records=[]
for host in ('codex','grok'):
 work=BASE/('ui-'+host+'-r01');work.mkdir(exist_ok=True);(work/'DESIGN.md').write_text(design+'\n');(work/'index.html').write_text((BASE/'fixture.html').read_text());(work/'tokens.css').write_text(':root{--bg:#fff;--fg:#202020;--border:#707070}html[data-theme=dark]{--bg:#161616;--fg:#eee;--border:#999}\n');shutil.copy2(BASE/'native_qa.py',work/'qa.py')
 subprocess.run(['git','init','-q',str(work)],check=True);subprocess.run(['git','-C',str(work),'add','.'],check=True);subprocess.run(['git','-C',str(work),'commit','-qm','Freeze canonical native UI task'],check=True)
 protected={p:hashlib.sha256((work/p).read_bytes()).hexdigest() for p in ('DESIGN.md','tokens.css','qa.py')}
 qa=f'{BASE}/runtime/bin/python {work}/qa.py {work}'
 prompt=design+'\nUse actual file-edit tools. Run this exact QA command: '+qa+'. If any check fails, fix only index.html and rerun. Return concise final report with actual command exit and critique. Do not change test code to make it pass. Work only in '+str(work)
 (EV/(host+'-prompt.txt')).write_text(prompt);config=BASE/(host+'-ui-home');config.mkdir(exist_ok=True)
 auth=config/'auth.json';shutil.copy2(Path.home()/('.'+host+'/auth.json'),auth);auth.chmod(0o600)
 if host=='codex':
  argv=['codex','--no-daemon','exec','--ignore-user-config','--ephemeral','--sandbox','workspace-write','--model','gpt-6.1-sol','-c','model_reasoning_effort="medium"','-c','sandbox_workspace_write.network_access=true','--json','-'];env={**clean,'CODEX_HOME':str(config)};input_=prompt
 else:
  (config/'config.toml').write_text('[models]\ndefault="grok-4.6"\nmax_completion_tokens=4096\nmax_retries=0\n')
  argv=['grok','--cwd',str(work),'--sandbox','workspace','--tools','read_file,write_file,search_replace,run_terminal_cmd','--no-subagents','--max-turns','10','--disable-web-search','--permission-mode','dontAsk','--allow','Edit('+str(work)+'/**)','--allow','Write('+str(work)+'/**)','--allow','Bash('+qa+'*)','--output-format','json','--model','grok-4.6','--effort','medium','--prompt-file',str(EV/(host+'-prompt.txt'))];env={**clean,'GROK_HOME':str(config)};input_=None
 start=time.monotonic()
 try:
  done=subprocess.run(argv,input=input_,cwd=work,env=env,capture_output=True,text=True,timeout=240);(EV/(host+'.log')).write_text(done.stdout);(EV/(host+'.stderr.log')).write_text(done.stderr);record={'host':host,'argv':argv,'exit_code':done.returncode,'elapsed_s':time.monotonic()-start,'protected_before':protected,'protected_after':{p:hashlib.sha256((work/p).read_bytes()).hexdigest() for p in protected},'qa_exists':(work/'qa-evidence/result.json').exists()}
  if record['qa_exists']:record['qa']=json.loads((work/'qa-evidence/result.json').read_text())
  records.append(record);print(host,done.returncode,record['qa_exists'],flush=True)
 except subprocess.TimeoutExpired as exc:
  (EV/(host+'.timeout.log')).write_text((exc.stdout or b'').decode() if isinstance(exc.stdout,bytes) else exc.stdout or '');records.append({'host':host,'elapsed_s':time.monotonic()-start,'error':'240s timeout'})
 finally:auth.unlink(missing_ok=True);(EV/'runs.json').write_text(json.dumps(records,indent=2)+'\n')
