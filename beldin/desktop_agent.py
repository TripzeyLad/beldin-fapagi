"""Interactive-only local agent. No AI, LAN listener, shell, or generic adapter."""
import hmac
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from .desktop_protocol import PORT, LIMIT, encode, decode, mac, settings, validate, ID
from .desktop_native import Native
from .notepad import Adapter

ROOT=Path(__file__).resolve().parents[1]

class AgentServer(HTTPServer):
    allow_reuse_address=False

class Agent:
    def __init__(self, adapter, config):
        self.adapter=adapter
        self.config=config
        self.agent_id=uuid.uuid4().hex
        self.seen={}
    def handle(self,path,raw,signature):
        if not hmac.compare_digest(signature,mac(self.config["secret"],raw)):
            return 401,{"error":"unauthorized"}
        try: obj=decode(raw)
        except (ValueError,RecursionError): return 400,{"error":"invalid_request"}
        if not isinstance(obj,dict): return 400,{"error":"invalid_request"}
        if path=="/health":
            if (set(obj)!={"invocation_id","at"} or not isinstance(obj["invocation_id"],str)
                or not ID.fullmatch(obj["invocation_id"]) or type(obj["at"]) not in (int,float)
                or abs(time.time()-obj["at"])>10): return 400,{"error":"invalid_request"}
            return 200,{**self.adapter.health(),"version":1,"agent_id":self.agent_id,
                        "request_id":obj["invocation_id"],"at":time.time()}
        if path!="/dispatch" or not validate(obj): return 400,{"error":"invalid_request"}
        if obj["agent_id"]!=self.agent_id: return 409,{"error":"agent_epoch_changed"}
        now=time.monotonic()
        self.seen={k:v for k,v in self.seen.items() if now-v<60}
        key=obj["invocation_id"]
        if key in self.seen: return 409,{"error":"replayed_invocation"}
        if len(self.seen)>=256: return 429,{"error":"capacity"}
        self.seen[key]=now  # consume before execution, including failure
        try:
            if not self.config["enabled"]:
                result={"state":"UNAVAILABLE","error":"disabled"}
            else: result=self.adapter.execute(obj["operation"],obj["args"],key)
        except Exception: result={"state":"UNVERIFIABLE","error":"adapter_failure"}
        return 200,{**result,"request_id":key,"agent_id":self.agent_id,
                    "session_id":self.adapter.native.session_id()}

class Handler(BaseHTTPRequestHandler):
    server_version="BeldinDesktop"
    def setup(self):
        super().setup(); self.connection.settimeout(2)
    def log_message(self,*args): pass
    def send_error(self,code,message=None,explain=None):
        self.reply(code,{"error":"invalid_request"})
    def reply(self,code,value):
        raw=encode(value)
        if len(raw)>LIMIT: code,raw=503,b'{"error":"output_bound"}'
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("X-Beldin-MAC",mac(self.server.agent.config["secret"],raw))
        self.send_header("Cache-Control","no-store")
        self.send_header("Connection","close")
        self.end_headers(); self.wfile.write(raw); self.close_connection=True
    def do_POST(self):
        if (self.client_address[0]!="127.0.0.1" or self.headers.get("Transfer-Encoding")
            or len(self.headers.get_all("Content-Length",[]))!=1
            or len(self.headers.get_all("X-Beldin-MAC",[]))!=1
            or self.headers.get("Content-Type")!="application/json"
            or sum(len(k)+len(v) for k,v in self.headers.items())>4096):
            self.reply(400,{"error":"invalid_framing"}); return
        length=self.headers.get("Content-Length","")
        if not length.isascii() or not length.isdecimal() or int(length)>LIMIT:
            self.reply(413,{"error":"request_bound"}); return
        raw=self.rfile.read(int(length))
        code,result=self.server.agent.handle(self.path,raw,self.headers.get("X-Beldin-MAC",""))
        self.reply(code,result)

def main():
    import sys
    if len(sys.argv)!=1: raise SystemExit("Agent accepts no arguments.")
    config=settings(ROOT)
    native=Native()
    if not config["enabled"] or not native.interactive():
        raise SystemExit("Interactive desktop unavailable or agent disabled.")
    # Fixed port plus exclusive bind denies duplicate agents, including sessions.
    server=AgentServer(("127.0.0.1",PORT),Handler,bind_and_activate=False)
    import socket
    server.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    server.server_bind(); server.server_activate()
    server.agent=Agent(Adapter(native),config)
    server.timeout=1
    try:
        while native.session_id()==native.k.WTSGetActiveConsoleSessionId():
            if not settings(ROOT)['enabled']: break
            server.handle_request()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=="__main__": main()
