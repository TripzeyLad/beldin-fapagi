import hmac
import ipaddress
import json
import os
import socket
from pathlib import Path
import threading
import time
import subprocess
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from . import VERSION
from .metrics import snapshot
from .diagnostics import assess
from .actions import dispatch, REGISTRY
from .windows_health import HealthCache
from .tools import TOOLS, observe
from .safe_actions import ACTION_META, propose, confirm, cancel
from .routing import route_text
from .mobile import ASSETS, asset, chat
from .app_registry import public_registry
from .install_policy import INSTALL_POLICY
from .selftest import run as selftest


def load_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    token = os.environ.get('BELDIN_TOKEN') or config.get('token', '')
    if not isinstance(token, str) or len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError('A non-whitespace ASCII token of at least 32 characters is required')
    host = config.get('host', '127.0.0.1')
    # LAN deployment requires separately verified firewall and trusted peer configuration.
    if host != '127.0.0.1': raise ValueError('This installation is loopback-only until LAN configuration is verified')
    port = config.get('port', 8765)
    if type(port) is not int or not 1024 <= port <= 65535: raise ValueError('Invalid port')
    return host, port, token


class State:
    def __init__(self, root, provider=snapshot):
        self.root = root
        self.provider = provider
        self.started = time.monotonic()
        self.lock = threading.Lock()
        self.refresh_lock = threading.Lock()
        self.cache = None
        self.sampled = None
        self.latencies = deque(maxlen=128)
        self.events = deque(maxlen=64)
        self.event_sequence = 0
        self.previous_signature = None
        self.windows_health = HealthCache()
        self.pending_actions = {}
        self.action_lock = threading.Lock()
        self.action_audit = deque(maxlen=128)
        self.app_sessions = {}
        self.app_lock = threading.Lock()
        from .desktop_bridge import Bridge
        self.desktop = Bridge(root)
        self.node = {'node_id':'valkyrie','role':'brain','capabilities':['v1','v2','observe','safe_actions'],'software_version':VERSION,'last_seen_unix':time.time()}
        self.node_lock = threading.Lock()
        from .control_center import Controls
        self.controls = Controls(self)
        from .coding import CodingAgent
        self.coding = CodingAgent(root)

    def record_latency(self, seconds):
        with self.lock: self.latencies.append(round(seconds*1000,3))

    def refresh(self):
        if not self.refresh_lock.acquire(False): return False
        try:
            value = self.provider(self.root)
            with self.lock:
                self.cache = value
                self.sampled = time.time()
                health=assess({'observed':value,'age_seconds':0})['status']
                ol=value.get('ollama',{})
                running=ol.get('running',{})
                names=tuple(sorted(str(m.get('name',''))[:128] for m in (running.get('data') or {}).get('models',[])[:64]))
                signature=(health,bool(ol.get('version',{}).get('available')),names)
                if signature!=self.previous_signature:
                    self.event_sequence+=1
                    self.events.append({'id':self.event_sequence,'at_unix':self.sampled,'type':'status_changed','assessment':health,'ollama_reachable':signature[1],'running_models':list(names)})
                    self.previous_signature=signature
            return True
        finally: self.refresh_lock.release()

    def telemetry(self):
        with self.lock:
            return {'observed': self.cache, 'sampled_at_unix': self.sampled,
                    'age_seconds': max(0,time.time()-self.sampled) if self.sampled else None,
                    'service_uptime_seconds': time.monotonic()-self.started}

    def control_metadata(self):
        return self.controls.metadata()

    def route(self, path):
        if path == '/v2/coding': return 200, self.coding.description()
        if path == '/v2/coding/tasks': return 200, {'tasks':self.coding.all_tasks()}
        if path == '/v2/control-center/logs': return 200, self.controls.logs()
        if path == '/v2/control-center/activity': return 200, self.controls.activity()
        if path == '/v2/control-center/reload':
            from .control_center import read_record
            return 200, {'api_version':'2','instance_id':self.controls.instance_id,'operation':read_record(self.root)}
        if path in ('/v2/capabilities','/v2/tools'):
            return 200, {'api_version':'2','service_version':VERSION,'tools':[{**{'id':n,'input_schema':{'type':'object'},'result_schema':{'type':'object'},'errors':['tool_error']},**m} for n,m in TOOLS.items()], 'actions':[{**{'id':n,'input_schema':{'type':'object'},'result_schema':{'type':'object'},'errors':['action_error']},**m} for n,m in ACTION_META.items()]}
        if path == '/v1/windows_health':
            return 200, self.windows_health.read()
        if path=='/v1/events':
            with self.lock: events=list(self.events)
            return 200,{'events':events,'retention_limit':64,'latest_id':events[-1]['id'] if events else None,'reset_on_restart':True}
        if path == '/v2/node':
            with self.node_lock: node=dict(self.node)
            age=round(max(0,time.time()-node['last_seen_unix']),1)
            node.update({'health_freshness_seconds':age,'online':age<=30})
            return 200, {'api_version':'2','node':node,'freshness_policy_seconds':30}
        if path == '/v2/action-history':
            with self.action_lock: entries=list(self.action_audit)
            return 200, {'api_version':'2','entries':entries[-64:],'retention_limit':128,'secrets_redacted':True}
        if path == '/v2/control-center':
            # Read-only aggregate for the responsive Control Center.  Keep
            # unavailable providers explicit; never invent logs or task state.
            sample = self.telemetry()
            with self.lock:
                events = list(self.events)[-32:]
            with self.action_lock:
                audit = list(self.action_audit)[-64:]
                pending = len(self.pending_actions)
            return 200, {
                'api_version':'2',
                'status': {'service':'running','instance_id':self.controls.instance_id,'pid':os.getpid(),'sampled_at_unix':sample.get('sampled_at_unix'),
                           'age_seconds':sample.get('age_seconds'),'observed':sample.get('observed')},
                'activity': {'events':events,'actions':audit,'pending_actions':pending, **self.controls.activity()},
                'tasks': {'running':[], 'queued':[],
                          'failed':[x for x in audit if x.get('status') in ('failed','timeout')][-16:]},
                'logs': {'available':True,'kind':'event_metadata','reason':'Event metadata available; raw process logs and chat content are not retained'},
                'controls': self.control_metadata()
                ,'coding': {'enabled':bool(self.coding.projects),'tasks':self.coding.all_tasks()}
            }
        if path == '/v2/model-router':
            from .model_router import describe
            return 200, {'api_version':'2', **describe()}
        if path == '/v2/memory/status':
            from .memory_store import status
            return 200, {'api_version':'2', **status(self.root)}
        if path == '/v2/app-capabilities':
            desktop=self.desktop.health()
            return 200, {'api_version':'2', **public_registry(desktop), 'desktop':desktop}
        if path == '/v2/desktop-health':
            return 200, {'api_version':'2', 'desktop':self.desktop.health()}
        if path == '/v2/install-policy':
            return 200, {'api_version':'2', **INSTALL_POLICY}
        if path == '/v2/self-test':
            return 200, {'api_version':'2','checks':selftest(self)}
        if path in ('/capabilities','/v1/capabilities'):
            return 200, {'service_version':VERSION,'observations':[
                {'name':name,'endpoint':'/v1/'+name,'permission':'OBSERVE','available':True,'input_schema':{'type':'object','additionalProperties':False}}
                for name in ('health','telemetry','hardware','ollama','diagnostics','events','windows_health')],
                'actions':[{'name':name,**meta} for name,meta in REGISTRY.items()],
                'availability_note':'Endpoint availability is not metric availability; inspect each observed provider.'}
        if path == '/v1/diagnostics':
            data=self.telemetry()
            with self.lock: history=list(self.latencies)
            return 200, {**data,'assessment':assess(data),'request_latency_ms':history,
                         'processes':{'beldin':{'pid':os.getpid(),'status':'running'},'ollama':{'available':False,'data':None,'reason':'process_inventory_not_enabled; see observed.ollama for API state'}}}
        if path in ('/health','/v1/health'):
            return 200, {'status':'running', 'service_version': VERSION, 'service_uptime_seconds': time.monotonic()-self.started}
        if path in ('/v1/telemetry', '/v1/hardware', '/v1/ollama'):
            return 200, self.telemetry()
        return 404, {'error':'not_found'}


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    request_queue_size = 8
    def __init__(self, address, token, state):
        self.token, self.state = token, state
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(False):
            self.shutdown_request(request); return
        try: super().process_request(request, address)
        except Exception:
            self.slots.release(); raise

    def process_request_thread(self, request, address):
        try: super().process_request_thread(request, address)
        finally: self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Never log request contents or exceptions containing credentials.


class Handler(BaseHTTPRequestHandler):
    server_version = 'Beldin'
    sys_version = ''
    def setup(self):
        super().setup(); self.connection.settimeout(2)

    def handle(self):
        def expire():
            try: self.connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        # Chat is the only bounded upstream call; keep the existing three-second
        # deadline for every diagnostic route while allowing one local model reply.
        try: first_line = self.rfile.peek(4096).split(b'\r\n', 1)[0]
        except (AttributeError, OSError): first_line = b''
        deadline = 50 if b'POST /v1/chat ' in first_line else (10 if b'POST /v2/actions ' in first_line else 3)
        timer=threading.Timer(deadline,expire); timer.daemon=True; timer.start()
        try: super().handle()
        finally: timer.cancel()

    def log_message(self, *args): pass

    def send_error(self, code, message=None, explain=None):
        self.respond(code, {'error':'invalid_request'})

    def respond(self, code, obj):
        payload = json.dumps({'api_version':'1', **obj}, allow_nan=False).encode()
        if len(payload)>262144:
            code=503; payload=b'{"api_version":"1","error":"response_too_large"}'
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Connection','close')
        self.end_headers(); self.wfile.write(payload)
        self.close_connection=True

    def authorized(self):
        if len(self.path)>256 or sum(len(k)+len(v) for k,v in self.headers.items())>8192:
            self.respond(431,{'error':'request_too_large'}); return False
        auth = self.headers.get_all('Authorization', [])
        valid = len(auth)==1 and hmac.compare_digest(auth[0].encode(), ('Bearer '+self.server.token).encode())
        # Only exact bootstrap GET paths are public; APIs and other methods
        # retain the existing authentication and framing checks.
        public_static = self.command == 'GET' and self.path in ASSETS
        if not valid and not public_static:
            self.respond(401,{'error':'unauthorized'}); return False
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))>1:
            self.respond(400,{'error':'invalid_framing'}); return False
        return True

    def do_GET(self):
        started=time.monotonic()
        if not self.authorized(): return
        if self.headers.get('Content-Length','0') != '0':
            self.respond(400,{'error':'unexpected_body'}); return
        static = asset(self.path)
        if static:
            payload, content_type = static
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Connection', 'close')
            self.end_headers(); self.wfile.write(payload); self.close_connection=True
            self.server.state.record_latency(time.monotonic()-started)
            return
        code,obj = self.server.state.route(self.path)
        self.respond(code,obj)
        self.server.state.record_latency(time.monotonic()-started)

    def do_POST(self):
        if not self.authorized(): return
        if self.path == '/v2/coding':
            if self.headers.get('Content-Type')!='application/json': self.respond(415,{'error':'json_required'}); return
            length=self.headers.get('Content-Length','')
            if not length.isdecimal() or int(length)>100000: self.respond(413,{'error':'body_too_large'}); return
            try:
                def unique(items):
                    obj={}
                    for key,value in items:
                        if key in obj: raise ValueError('duplicate')
                        obj[key]=value
                    return obj
                body=json.loads(self.rfile.read(int(length)),object_pairs_hook=unique)
            except (ValueError,RecursionError): self.respond(400,{'error':'invalid_json'}); return
            code,result=self.server.state.coding.request(body)
            self.respond(code,{'api_version':'2',**result}); return
        if self.path == '/v2/route':
            if self.headers.get('Content-Type')!='application/json': self.respond(415,{'error':'json_required'}); return
            length=self.headers.get('Content-Length','')
            if not length.isdecimal() or int(length)>4096: self.respond(413,{'error':'body_too_large'}); return
            try: body=json.loads(self.rfile.read(int(length)))
            except (ValueError,RecursionError): self.respond(400,{'error':'invalid_json'}); return
            if not isinstance(body,dict) or not isinstance(body.get('text'),str): self.respond(400,{'error':'invalid_route_request'}); return
            self.respond(200,{'api_version':'2','plan':route_text(body['text'])}); return
        if self.path == '/v2/control-center/action':
            if self.headers.get('Content-Type')!='application/json': self.respond(415,{'error':'json_required'}); return
            length=self.headers.get('Content-Length','')
            if not length.isdecimal() or int(length)>2048: self.respond(400,{'error':'invalid_body'}); return
            def unique_pairs(items):
                obj = {}
                for key,value in items:
                    if key in obj: raise ValueError('duplicate')
                    obj[key] = value
                return obj
            try: body=json.loads(self.rfile.read(int(length)), object_pairs_hook=unique_pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError,RecursionError): self.respond(400,{'error':'invalid_json'}); return
            code,obj=self.server.state.controls.execute(body)
            self.respond(code,{'api_version':'2',**obj}); return
        if self.path == '/v2/actions':
            if self.headers.get('Content-Type')!='application/json': self.respond(415,{'error':'json_required'}); return
            length=self.headers.get('Content-Length','')
            if not length.isdecimal() or int(length)>4096: self.respond(413,{'error':'body_too_large'}); return
            try: body=json.loads(self.rfile.read(int(length)))
            except (ValueError,RecursionError): self.respond(400,{'error':'invalid_json'}); return
            if not isinstance(body,dict): self.respond(400,{'error':'invalid_action_request'}); return
            if body.get('op')=='cancel': code,obj=cancel(body.get('action_id'),self.server.state)
            elif body.get('op')=='propose': code,obj=propose(body.get('action'),body.get('input',{}),self.server.state)
            elif body.get('op')=='confirm': code,obj=confirm(body.get('action_id'),self.server.state)
            else: code,obj=400,{'error':'invalid_action_operation'}
            self.respond(code,obj); return
        if self.path == '/v1/chat':
            controls = self.server.state.controls
            with controls.lock:
                if controls.busy_reload():
                    self.respond(503,{'error':'beldin_reloading'}); return
                controls.active_chats += 1
            try: chat(self)
            finally:
                with controls.lock: controls.active_chats -= 1
            return
        if self.path == '/v2/heartbeat':
            if self.headers.get('Content-Type')!='application/json': self.respond(415,{'error':'json_required'}); return
            length=self.headers.get('Content-Length','')
            if not length.isdecimal() or int(length)>2048: self.respond(400,{'error':'invalid_body'}); return
            try: body=json.loads(self.rfile.read(int(length)))
            except (ValueError,RecursionError): self.respond(400,{'error':'invalid_json'}); return
            if not isinstance(body,dict) or not isinstance(body.get('node_id'),str) or not isinstance(body.get('role'),str): self.respond(400,{'error':'invalid_heartbeat'}); return
            caps=body.get('capabilities',[])
            if not isinstance(caps,list) or len(caps)>32 or not all(isinstance(x,str) for x in caps): self.respond(400,{'error':'invalid_heartbeat'}); return
            with self.server.state.node_lock:
                self.server.state.node={'node_id':body['node_id'][:64],'role':body['role'][:32],'capabilities':[x[:64] for x in caps],'software_version':str(body.get('software_version','unknown'))[:64],'last_seen_unix':time.time()}
            self.respond(200,{'api_version':'2','status':'recorded','node':dict(self.server.state.node)}); return
        if self.path == '/v2/observe':
            if self.headers.get('Content-Type')!='application/json': self.respond(415,{'error':'json_required'}); return
            length=self.headers.get('Content-Length','')
            if not length.isascii() or not length.isdecimal() or int(length)>4096: self.respond(400,{'error':'invalid_body'}); return
            try: body=json.loads(self.rfile.read(int(length)))
            except (ValueError,RecursionError): self.respond(400,{'error':'invalid_json'}); return
            if not isinstance(body,dict) or not isinstance(body.get('tool'),str) or not isinstance(body.get('input',{}),dict): self.respond(400,{'error':'invalid_observe_request'}); return
            code,obj=observe(body['tool'],body.get('input',{}),self.server.state); self.respond(code,obj); return
        if self.path == '/v2/actions':
            if self.headers.get('Content-Type')!='application/json': self.respond(415,{'error':'json_required'}); return
            length=self.headers.get('Content-Length','')
            if not length.isdecimal() or int(length)>4096: self.respond(400,{'error':'invalid_body'}); return
            try: body=json.loads(self.rfile.read(int(length)))
            except (ValueError,RecursionError): self.respond(400,{'error':'invalid_json'}); return
            if not isinstance(body,dict): self.respond(400,{'error':'invalid_action_request'}); return
            if body.get('op')=='propose': code,obj=propose(body.get('action'),body.get('input',{}),self.server.state)
            elif body.get('op')=='confirm': code,obj=confirm(body.get('action_id'),self.server.state)
            else: code,obj=400,{'error':'invalid_action_operation'}
            self.respond(code,obj); return
        if self.path!='/v1/actions': self.respond(405,{'error':'method_not_allowed'}); return
        if self.headers.get('Content-Type')!='application/json':
            self.respond(415,{'error':'json_required'}); return
        length=self.headers.get('Content-Length','')
        if not length.isascii() or not length.isdecimal():
            self.respond(400,{'error':'invalid_length'}); return
        size=int(length)
        if size>4096: self.respond(413,{'error':'body_too_large'}); return
        def pairs(items):
            result={}
            for k,v in items:
                if k in result: raise ValueError('duplicate')
                result[k]=v
            return result
        try:
            body=json.loads(self.rfile.read(size), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, RecursionError, TimeoutError):
            self.respond(400,{'error':'invalid_json'}); return
        code,obj=dispatch(body,self.server.state)
        self.respond(code,obj)


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--config', default=str(Path(__file__).resolve().parents[1]/'config.local.json'))
    args=parser.parse_args()
    host,port,token=load_config(args.config)
    state=State(Path(args.config).resolve().parent)
    state.refresh()
    stop=threading.Event()
    def sample():
        while not stop.wait(2):
            try: state.refresh()
            except Exception: pass
    threading.Thread(target=sample,daemon=True).start()
    def sample_windows():
        while not stop.is_set():
            state.windows_health.refresh()
            if stop.wait(60): break
    threading.Thread(target=sample_windows,daemon=True).start()
    server=Server((host,port),token,state)
    print(f'Beldin {VERSION} listening on {host}:{port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: stop.set(); server.server_close()

if __name__=='__main__': main()
