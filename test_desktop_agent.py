import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from beldin.desktop_protocol import encode,decode,mac,validate,valid_args
from beldin.desktop_agent import Agent
from beldin.desktop_bridge import Bridge
from beldin.desktop_chat import respond, capability_summary
from beldin.notepad import Adapter, NOTEPAD
from beldin.server import State
from beldin.safe_actions import propose, confirm
from beldin.app_registry import APP_REGISTRY

class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.native=Mock()
        self.native.interactive.return_value=True
        self.native.session_id.return_value=1
        self.native.notepad_present.return_value=False
        self.adapter=Mock()
        self.adapter.native=self.native
        self.adapter.health.return_value={"interactive":True,"session_id":1,"operations":{"open_notepad":True}}
        self.adapter.execute.return_value={"state":"VERIFIED_SUCCESS"}
        self.config={"secret":"a"*64,"enabled":True,"version":1}
        self.agent=Agent(self.adapter,self.config)
        self.request={"version":1,"agent_id":self.agent.agent_id,"adapter":"notepad","operation":"open_notepad",
                      "invocation_id":uuid.uuid4().hex,"at":time.time(),"args":{}}
    def send(self,obj,signature=None):
        raw=encode(obj)
        return self.agent.handle("/dispatch",raw,signature or mac(self.config["secret"],raw))
    def test_authentication_required(self):
        self.assertEqual(self.send(self.request,"wrong")[0],401)
        self.adapter.execute.assert_not_called()
    def test_signed_operation_and_correlation(self):
        code,res=self.send(self.request)
        self.assertEqual(code,200)
        self.assertEqual(res["request_id"],self.request["invocation_id"])
        self.adapter.execute.assert_called_once_with("open_notepad",{},self.request["invocation_id"])
    def test_replay_consumed_before_execution(self):
        self.adapter.execute.side_effect=RuntimeError("secret internal error")
        self.assertEqual(self.send(self.request)[1]["state"],"UNVERIFIABLE")
        self.assertEqual(self.send(self.request)[0],409)
        self.assertEqual(self.adapter.execute.call_count,1)
    def test_epoch_replay_after_restart(self):
        self.request["agent_id"]=uuid.uuid4().hex
        self.assertEqual(self.send(self.request)[0],409)
        self.adapter.execute.assert_not_called()
    def test_old_future_requests_rejected(self):
        for shift in (-60,60):
            self.request["at"]=time.time()+shift
            self.assertEqual(self.send(self.request)[0],400)
    def test_extra_parameters_unknown_targets_rejected(self):
        for field in ("pid","hwnd","command","executable","path","shell","selector","task"):
            with self.subTest(field=field):
                obj={**self.request,field:"cmd.exe /c"}
                self.assertEqual(self.send(obj)[0],400)
                obj={**self.request,"args":{field:"powershell.exe"}}
                self.assertEqual(self.send(obj)[0],400)
        for field,value in (("adapter","shell"),("operation","save"),("version",True)):
            self.assertEqual(self.send({**self.request,field:value})[0],400)
        self.adapter.execute.assert_not_called()
    def test_malformed_duplicate_oversized(self):
        for raw in (b"{", b'{"x":1,"x":2}', b"x"*8193):
            with self.assertRaises((ValueError,RecursionError)):decode(raw)
    def test_inert_text_never_executed(self):
        adapter=Adapter(self.native)
        for text in ("powershell.exe","cmd.exe /c shutdown","Remove-Item C:\\*","<script> && |"):
            self.assertTrue(valid_args("create_notepad_note",{"text":text}))
            with patch("beldin.notepad.subprocess.Popen") as launch:
                self.assertEqual(adapter.execute("create_notepad_note",{"text":text},uuid.uuid4().hex)["state"],"UNAVAILABLE")
                launch.assert_not_called()
        self.assertFalse(valid_args("create_notepad_note",{"text":"x"*4097}))
    @patch("beldin.notepad.NOTEPAD")
    @patch("beldin.notepad.subprocess.Popen")
    def test_existing_notepad_never_touched(self,launch,path):
        path.is_file.return_value=True
        self.native.notepad_present.return_value=True
        self.assertEqual(Adapter(self.native).execute("open_notepad",{},uuid.uuid4().hex)["state"],"UNAVAILABLE")
        launch.assert_not_called()
    @patch("beldin.notepad.NOTEPAD")
    @patch("beldin.notepad.subprocess.Popen")
    def test_launch_requires_owned_visible_window(self,launch,path):
        path.is_file.return_value=True
        proc=Mock();proc.poll.return_value=None;launch.return_value=proc
        self.native.owned_windows.return_value=[321]
        adapter=Adapter(self.native)
        result=adapter.execute("open_notepad",{},uuid.uuid4().hex)
        self.assertEqual(result["state"],"VERIFIED_SUCCESS")
        launch.assert_called_once_with([str(path)],shell=False,close_fds=True)
        self.assertIs(adapter.owned["process"],proc)
    @patch("beldin.notepad.NOTEPAD")
    @patch("beldin.notepad.subprocess.Popen")
    def test_exited_launcher_not_adopted(self,launch,path):
        path.is_file.return_value=True;launch.return_value.poll.return_value=0
        self.assertEqual(Adapter(self.native).execute("open_notepad",{},uuid.uuid4().hex)["state"],"UNVERIFIABLE")
    @patch("beldin.notepad.NOTEPAD")
    @patch("beldin.notepad.subprocess.Popen")
    def test_ambiguous_windows_not_success(self,launch,path):
        path.is_file.return_value=True;launch.return_value.poll.return_value=None
        self.native.owned_windows.return_value=[1,2]
        self.assertEqual(Adapter(self.native).execute("open_notepad",{},uuid.uuid4().hex)["state"],"UNVERIFIABLE")
    def test_wrong_or_locked_session_no_launch(self):
        self.native.interactive.return_value=False
        with patch("beldin.notepad.subprocess.Popen") as launch:
            self.assertEqual(Adapter(self.native).execute("open_notepad",{},uuid.uuid4().hex)["state"],"UNAVAILABLE")
            launch.assert_not_called()
    def test_close_refuses_modern_unverified_contents(self):
        self.assertEqual(Adapter(self.native).execute("close_beldin_notepad",{},uuid.uuid4().hex)["state"],"UNAVAILABLE")
    def state(self):
        state=State(".")
        state.desktop=Mock()
        state.desktop.health.return_value={"online":True,"operations":{"open_notepad":True}}
        state.desktop.dispatch.return_value={"state":"VERIFIED_SUCCESS","verification":True}
        return state
    def test_confirmation_challenge_one_time(self):
        state=self.state(); messages=[{"role":"user","content":"Open Notepad."}]
        prompt=respond(messages,state)
        state.desktop.dispatch.assert_not_called()
        messages += [{"role":"assistant","content":prompt},{"role":"user","content":"yes"}]
        self.assertIn("visible",respond(messages,state))
        self.assertNotIn("visible",respond(messages,state))
        self.assertEqual(state.desktop.dispatch.call_count,1)
        invocation=state.desktop.dispatch.call_args.args[2]
        self.assertTrue(any(a.get("invocation_id")==invocation and a.get("confirmed") for a in state.action_audit))
    def test_confirmation_cannot_authorize_different_request(self):
        state=self.state()
        prompt=respond([{"role":"user","content":"Open Notepad."}],state)
        res=respond([{"role":"user","content":"Open something else"},{"role":"assistant","content":prompt},{"role":"user","content":"yes"}],state)
        self.assertIn("no longer valid",res);state.desktop.dispatch.assert_not_called()
    def test_cancel_expire(self):
        for answer,expired in (("cancel",False),("yes",True)):
            state=self.state(); messages=[{"role":"user","content":"Open Notepad."}]
            prompt=respond(messages,state)
            if expired:
                for item in state.pending_actions.values(): item["expires"]=0
            respond(messages+[{"role":"assistant","content":prompt},{"role":"user","content":answer}],state)
            state.desktop.dispatch.assert_not_called()
    def test_offline_reconnect_truth(self):
        state=self.state();state.desktop.health.return_value={"online":False}
        self.assertIn("unavailable",respond([{"role":"user","content":"Open Notepad."}],state))
        self.assertEqual(len(state.pending_actions),0)
        self.assertIn("unavailable",capability_summary(state))
        state.desktop.health.return_value={"online":True,"operations":{"open_notepad":True}}
        self.assertIn("approval:",respond([{"role":"user","content":"Open Notepad."}],state))
    def test_adapter_disabled_at_confirmation(self):
        state=self.state();code,p=propose("open_notepad",{},state);self.assertEqual(code,200)
        with patch.dict(APP_REGISTRY["windows_notepad"],{"enabled":False}):
            self.assertEqual(confirm(p["action_id"],state)[1]["result"]["state"],"UNAVAILABLE")
        state.desktop.dispatch.assert_not_called()
    def test_conversation_and_local_time(self):
        state=self.state()
        for text in ("Who are you?","Who made you?","What is Notepad?","Tell me about Notepad.","Why does Notepad have tabs?","I used Notepad yesterday.","What is Valkyrie's status?"):
            self.assertIsNone(respond([{"role":"user","content":text}],state))
        for text in ("What time is it?","Qwen, tell me what time it is."):
            self.assertIn("local time",respond([{"role":"user","content":text}],state))
        state.desktop.dispatch.assert_not_called()
    def test_config_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge=Bridge(directory)
            self.assertFalse(bridge.health()["online"])
            self.assertEqual(bridge.dispatch("open_notepad",{},uuid.uuid4().hex)["state"],"UNAVAILABLE")
    def test_health_stale_wrong_session(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,"config.desktop.json").write_text(json.dumps(self.config))
            bridge=Bridge(directory)
            good={"version":1,"agent_id":self.agent.agent_id,"interactive":True,"session_id":1,"at":time.time()}
            for delta in ({"at":0},{"interactive":False},{"session_id":0}):
                with patch.object(bridge,"_request",return_value={**good,**delta}):
                    self.assertFalse(bridge.health()["online"])
    def test_global_disable(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,"config.desktop.json").write_text(json.dumps({**self.config,"enabled":False}))
            bridge=Bridge(directory)
            with patch.object(bridge,"_request") as request:
                self.assertFalse(bridge.health()["online"]);request.assert_not_called()
    def test_reply_tampering_and_wrong_correlation(self):
        from contextlib import nullcontext
        for raw,signature in ((b'{"request_id":"wrong"}',None),(b'{}',"bad")):
            response=Mock();response.read.return_value=raw
            response.headers={"X-Beldin-MAC":signature or mac(self.config["secret"],raw)}
            opener=Mock();opener.open.return_value=nullcontext(response)
            with patch("beldin.desktop_bridge.build_opener",return_value=opener):
                with self.assertRaises(ValueError):
                    Bridge(".")._request("/health",{"invocation_id":"expected"},self.config)

class DesktopHTTPTests(unittest.TestCase):
    def test_authenticated_clients_share_server_action_flow(self):
        import http.client
        from beldin.server import Server
        state=State(".")
        state.desktop=Mock()
        state.desktop.health.return_value={"online":True,"operations":{"open_notepad":True}}
        state.desktop.dispatch.return_value={"state":"VERIFIED_SUCCESS","verification":True}
        token="test-only-token-"+"x"*32
        server=Server(("127.0.0.1",0),token,state)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def chat(messages,auth=True):
            conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=3)
            headers={"Content-Type":"application/json"}
            if auth: headers["Authorization"]="Bearer "+token
            conn.request("POST","/v1/chat",json.dumps({"messages":messages}),headers)
            response=conn.getresponse();data=json.loads(response.read());status=response.status;conn.close()
            return status,data
        try:
            for client in ("Surface","phone"):
                messages=[{"role":"user","content":"Beldin, open Notepad."}]
                with patch("beldin.mobile.urlopen") as model:
                    code,result=chat(messages);self.assertEqual(code,200)
                    prompt=result["message"]["content"];self.assertIn("approval:",prompt)
                    messages += [{"role":"assistant","content":prompt},{"role":"user","content":"yes"}]
                    code,result=chat(messages);self.assertIn("visible",result["message"]["content"])
                    model.assert_not_called()
            self.assertEqual(state.desktop.dispatch.call_count,2)
            self.assertEqual(chat([{"role":"user","content":"Open Notepad."}],False)[0],401)
            state.desktop.health.return_value={"online":False}
            with patch("beldin.mobile.urlopen") as model:
                self.assertIn("unavailable",chat([{"role":"user","content":"Open Notepad."}])[1]["message"]["content"])
                model.assert_not_called()
        finally: server.shutdown();server.server_close();worker.join()
    def test_agent_http_auth_framing_response_and_duplicate_bind(self):
        import http.client
        import socket
        from beldin.desktop_agent import Handler, AgentServer
        from http.server import HTTPServer
        native=Mock();native.session_id.return_value=1
        adapter=Mock();adapter.native=native
        adapter.health.return_value={"interactive":True,"session_id":1,"operations":{"open_notepad":True}}
        config={"secret":"b"*64,"enabled":True,"version":1}
        server=AgentServer(("127.0.0.1",0),Handler,bind_and_activate=False)
        if hasattr(socket,"SO_EXCLUSIVEADDRUSE"):
            server.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        server.server_bind();server.server_activate()
        server.agent=Agent(adapter,config)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            with self.assertRaises(OSError):
                duplicate=HTTPServer(server.server_address,Handler)
            nonce=uuid.uuid4().hex
            raw=encode({"invocation_id":nonce,"at":time.time()})
            for signature,status in (("bad",401),(mac(config["secret"],raw),200)):
                conn=http.client.HTTPConnection(*server.server_address,timeout=3)
                conn.request("POST","/health",raw,{"Content-Type":"application/json","X-Beldin-MAC":signature})
                response=conn.getresponse();data=response.read()
                self.assertEqual(response.status,status)
                self.assertEqual(response.getheader("X-Beldin-MAC"),mac(config["secret"],data));conn.close()
                if status==200:self.assertEqual(decode(data)["request_id"],nonce)
        finally:server.shutdown();server.server_close();worker.join()
    def test_secret_excluded_from_read_and_backup_policy(self):
        from beldin.secret_policy import denied
        self.assertTrue(denied("config.desktop.json"))
    def test_installer_scope_and_no_kill_adapter(self):
        root=Path(__file__).parent
        install=(root/"INSTALL_BELDIN_DESKTOP_AGENT.ps1").read_text()
        self.assertIn("$args.Count -ne 0",install)
        self.assertIn("Beldin Desktop Agent.lnk",install)
        self.assertIn("SetAccessRuleProtection",install)
        for name in ("notepad.py","desktop_native.py","desktop_agent.py","desktop_bridge.py"):
            src=(root/"beldin"/name).read_text()
            self.assertNotIn("TerminateProcess",src)
            self.assertNotIn("os.kill(",src)
            self.assertNotIn("shell=True",src)
