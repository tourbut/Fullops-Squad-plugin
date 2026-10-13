from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import json
BASE=Path(__file__).parent
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  name=self.path.split('?')[0].strip('/') or 'healthy'
  if name=='api/private':self.send_response(401);self.end_headers();return
  content=(BASE/'fixture.html').read_text()
  if name=='duplicate':content=content.replace('window.submits++;','window.submits+=2;').replace('addTodo(input.value);', 'addTodo(input.value);addTodo(input.value);')
  if name=='no-check':content=content.replace("box.type='checkbox';", "box.type='checkbox';box.onclick=e=>{e.preventDefault();};")
  if name=='no-theme':content=content.replace("document.documentElement.dataset.theme=dark?'dark':'light';", "document.documentElement.dataset.theme='light';")
  data=content.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_POST(self):self.send_response(403);self.end_headers()
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
(BASE/'fixture-port.json').write_text(json.dumps({'port':server.server_port,'origin':f'http://127.0.0.1:{server.server_port}'}))
print('fixture',server.server_port,flush=True);server.serve_forever()
