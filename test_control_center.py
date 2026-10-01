import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, Mock
from beldin.server import State, Server
from beldin.control_center import read_record, write_record, run_reload, verified_reload

class ControlCenterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.state=State(Path(self.tmp.name),provider=lambda _: {'ollama':{}})
        self.c=self.state.controls
        self.verify=patch('beldin.control_center.verified_reload',return_value=True)
        self.verify.start()
    def tearDown(self):
        self.verify.stop()
        self.tmp.cleanup()
    def execute(self,**body): return self.c.execute(body)
    def propose(self): return self.execute(action='reload_beldin',op='propose')[1]['confirmation_id']
    def confirm(self,key): return self.execute(action='reload_beldin',op='confirm',confirmation_id=key)
    def test_metadata_all_controls_and_tiers(self):
        m={x['id']:x for x in self.c.metadata()}
        self.assertEqual(len(m),10)
        for name in ('refresh_status','rescan_models','view_logs','view_activity'):
            self.assertTrue(m[name]['available']); self.assertEqual(m[name]['permission'],'OBSERVE')
        for name in ('restart_ollama','restart_gateway','retry_task','cancel_task','view_script'):
            self.assertFalse(m[name]['available']);self.assertTrue(m[name]['reason'])
        self.assertEqual(m['reload_beldin']['permission'],'SERVICE_CHANGE')
        self.assertTrue(m['reload_beldin']['confirmation_required'])
    def test_refresh_success_failure_and_busy(self):
        self.assertEqual(self.execute(action='refresh_status')[0],200)
        self.assertIsNotNone(self.state.sampled)
        with patch.object(self.state,'refresh',return_value=False):
            self.assertEqual(self.execute(action='refresh_status')[0],409)
        with patch.object(self.state,'refresh',side_effect=RuntimeError('secret')):
            code,result=self.execute(action='refresh_status')
            self.assertEqual(code,503);self.assertNotIn('secret',str(result))
    def test_rescan_calls_tags_and_reports_failure(self):
        for available,expected in ((True,200),(False,503)):
            result={'available':available,'data':{'models':[{'name':'test'}]} if available else None}
            with patch('beldin.control_center.ollama_get',return_value=result) as scan:
                code,body=self.execute(action='rescan_models')
                self.assertEqual(code,expected);self.assertEqual(body['models'],result)
                scan.assert_called_once_with('tags')
    def test_disabled_controls_reject_even_confirmed(self):
        for meta in self.c.metadata():
            if not meta['available']:
                self.assertEqual(self.execute(action=meta['id'],op='confirm',confirmation_id='x')[0],403)
        self.assertEqual(self.execute(action='shell')[0],404)
    def test_views_have_real_data_and_explicit_limits(self):
        self.c.audit('rescan_models','completed')
        logs=self.state.route('/v2/control-center/logs')[1]
        self.assertEqual(logs['actions'][-1]['action'],'rescan_models')
        self.assertFalse(logs['raw_logs_available'])
        self.c.active_chats=1
        activity=self.state.route('/v2/control-center/activity')[1]
        self.assertEqual(activity['active_chat_requests'],1)
        self.assertFalse(activity['script_tracking_available'])
        for name in ('view_logs','view_activity'):
            self.assertEqual(self.execute(action=name)[0],405)
    def test_confirmation_boolean_cannot_bypass(self):
        with patch('beldin.control_center.subprocess.Popen') as launch:
            self.assertEqual(self.execute(action='reload_beldin',confirmed=True)[0],400)
            self.assertEqual(self.execute(action='reload_beldin')[0],409)
            self.assertEqual(self.confirm('forged')[0],409)
            launch.assert_not_called()
    def test_confirmation_cancel_expire_replay(self):
        key=self.propose()
        self.assertEqual(self.execute(action='reload_beldin',op='cancel',confirmation_id=key)[0],200)
        self.assertEqual(self.confirm(key)[0],409)
        key=self.propose();self.c.challenges[key]=time.time()-1
        self.assertEqual(self.confirm(key)[0],409)
    def test_launch_is_detached_fixed_and_one_use(self):
        key=self.propose()
        with patch('beldin.control_center.subprocess.Popen') as launch,patch.dict(os.environ,{'BELDIN_TOKEN':'secret'}):
            code,body=self.confirm(key)
            self.assertEqual(code,202)
            args=launch.call_args.args[0]
            self.assertEqual(args[1:4],['-B','-m','beldin.reload_worker'])
            self.assertNotIn('BELDIN_TOKEN',launch.call_args.kwargs['env'])
            self.assertEqual(read_record(self.state.root)['status'],'accepted')
            self.assertEqual(self.confirm(key)[0],409)
            self.assertEqual(launch.call_count,1)
    def test_launch_failure_is_failure_and_consumes_challenge(self):
        key=self.propose()
        with patch('beldin.control_center.subprocess.Popen',side_effect=OSError('secret')):
            self.assertEqual(self.confirm(key)[0],503)
        self.assertEqual(read_record(self.state.root)['status'],'failed')
        self.assertEqual(self.confirm(key)[0],409)
    def test_unavailable_at_confirm_is_rejected(self):
        key=self.propose()
        with patch('beldin.control_center.verified_reload',return_value=False):
            self.assertEqual(self.confirm(key)[0],403)
    def test_active_chat_blocks_reload(self):
        key=self.propose();self.c.active_chats=1
        with patch('beldin.control_center.subprocess.Popen') as launch:
            self.assertEqual(self.confirm(key)[0],409);launch.assert_not_called()
    def test_worker_success_failure_timeout_and_operation_mismatch(self):
        for result,status in ((Mock(returncode=0,stdout='Verified Beldin reload: 100 -> 200'),'completed'),
                              (Mock(returncode=1,stdout='secret'),'failed'),
                              (Mock(returncode=0,stdout='Verified Beldin reload: 999 -> 200'),'failed')):
            record=dict(id='a'*32,status='accepted',started_at_unix=time.time(),old_pid=100)
            write_record(self.state.root,record)
            with patch('beldin.control_center.time.sleep'),patch('beldin.control_center.subprocess.run',return_value=result):
                run_reload(self.state.root,'a'*32)
            got=read_record(self.state.root)
            self.assertEqual(got['status'],status);self.assertNotIn('secret',str(got))
        write_record(self.state.root,dict(id='a'*32,status='accepted',started_at_unix=time.time()-100))
        self.assertEqual(read_record(self.state.root)['status'],'failed')
        with patch('beldin.control_center.subprocess.run') as run:
            run_reload(self.state.root,'different');run.assert_not_called()
    def test_worker_survives_new_state(self):
        write_record(self.state.root,dict(id='a'*32,status='completed',started_at_unix=time.time(),old_pid=1,new_pid=2))
        new=State(self.state.root)
        self.assertEqual(new.route('/v2/control-center/reload')[1]['operation']['new_pid'],2)
        self.assertNotEqual(new.controls.instance_id,self.c.instance_id)
    def test_http_auth_validation_all_controls_and_chat(self):
        server=Server(('127.0.0.1',0),'test-only-'+'x'*40,self.state)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,method='GET',body=None,auth=True,content_type='application/json'):
            conn=http.client.HTTPConnection(*server.server_address,timeout=5)
            headers={'Content-Type':content_type}
            if auth:headers['Authorization']='Bearer '+server.token
            conn.request(method,path,body,headers)
            res=conn.getresponse();data=json.loads(res.read());conn.close();return res.status,data
        endpoint='/v2/control-center/action'
        try:
            for path in ('/v2/control-center','/v2/control-center/logs','/v2/control-center/activity','/v2/control-center/reload'):
                self.assertEqual(request(path,auth=False)[0],401)
                self.assertEqual(request(path)[0],200)
            for meta in self.c.metadata():
                body=json.dumps({'action':meta['id']})
                self.assertEqual(request(endpoint,'POST',body,False)[0],401)
            for body in ('[]','{','{"action":"rescan_models","action":"reload_beldin"}','{"action":"reload_beldin","confirmed":true}','{"action":NaN}'):
                self.assertEqual(request(endpoint,'POST',body)[0],400)
            self.assertEqual(request(endpoint,'POST','x'*2049)[0],400)
            self.assertEqual(request(endpoint,'POST','{}',content_type='text/plain')[0],415)
            self.assertEqual(request(endpoint,'POST','{"action":"refresh_status"}')[0],200)
            with patch('beldin.mobile.urlopen') as upstream:
                upstream.return_value.__enter__.return_value.read.return_value=b'{"message":{"content":"READY"}}'
                code,reply=request('/v1/chat','POST','{"messages":[{"role":"user","content":"Say READY"}]}')
                self.assertEqual(code,200);self.assertEqual(reply['message']['content'],'READY')
                self.assertEqual(self.c.active_chats,0)
            write_record(self.state.root,dict(id='a'*32,status='accepted',started_at_unix=time.time()))
            self.assertEqual(request('/v1/chat','POST','{"messages":[{"role":"user","content":"hello"}]}')[0],503)
        finally:
            server.shutdown();server.server_close();thread.join()
