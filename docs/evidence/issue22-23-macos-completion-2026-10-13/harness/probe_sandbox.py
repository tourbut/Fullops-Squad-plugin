import json,socket
from pathlib import Path
result={}
for name,action in [('outside_write',lambda:Path('/private/tmp/fullops-cua-outside-probe').write_text('probe')),('protected_baseline_read',lambda:next(Path('/private/tmp/fullops-completion-z_ii0xr2/private-baseline').iterdir()).read_bytes()),('external_network',lambda:socket.create_connection(('1.1.1.1',443),timeout=2))]:
 try:action();result[name]='ALLOWED'
 except (OSError,StopIteration) as exc:result[name]={'blocked':True,'error':type(exc).__name__,'errno':getattr(exc,'errno',None)}
Path('/private/tmp/fullops-completion-z_ii0xr2/evidence/sandbox-probes.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
