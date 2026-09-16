import http.client
import json
import threading
import unittest
from unittest.mock import patch
from beldin.server import Server, State
from beldin.mobile import ASSETS

class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=Server(('127.0.0.1',0),'test-only-'+'z'*40,State('.'))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def request(self,path,method='GET',body=None,auth=False,headers=None):
        c=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        h=dict(headers or {})
        if auth: h['Authorization']='Bearer '+self.server.token
        c.request(method,path,body,h)
        r=c.getresponse(); result=(r.status,r.read(),r.getheader('Content-Type')); c.close()
        return result

    def test_public_bootstrap(self):
        for path in ASSETS:
            with self.subTest(path=path):
                status,data,mime=self.request(path)
                self.assertEqual(status,200)
                self.assertTrue(data)
                self.assertNotIn(self.server.token.encode(),data)
                self.assertEqual(mime,ASSETS[path][1])
        self.assertIn(b'id="token"',self.request('/app')[1])

    def test_api_auth_required(self):
        for path in ['/health','/v1/telemetry','/v1/events','/v1/capabilities','/v2/capabilities','/v2/node']:
            self.assertEqual(self.request(path)[0],401)
        for path in ['/v1/chat','/v2/observe','/v2/actions','/v2/route','/app']:
            self.assertEqual(self.request(path,'POST',b'{}')[0],401)

    def test_unknown_and_traversal(self):
        for path in ['/app/../config.local.json','/app/%2e%2e/config.local.json','/app/unknown','/app?x=1','/app//app.js']:
            self.assertEqual(self.request(path)[0],401)
            self.assertEqual(self.request(path,auth=True)[0],404)

    def test_bounds_and_framing(self):
        self.assertEqual(self.request('/app',body=b'x')[0],400)
        self.assertEqual(self.request('/app',headers={'Transfer-Encoding':'chunked'})[0],400)
        self.assertEqual(self.request('/app',headers={'X-Large':'x'*8200})[0],431)
        self.assertEqual(self.request('/app/'+'x'*260)[0],431)
        c=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        c.putrequest('GET','/app')
        c.putheader('Content-Length','0'); c.putheader('Content-Length','0'); c.endheaders()
        r=c.getresponse(); self.assertEqual(r.status,400); r.read(); c.close()

    def test_authenticated_chat(self):
        with patch('beldin.mobile.urlopen') as upstream:
            upstream.return_value.__enter__.return_value.read.return_value=b'{"message":{"content":"Ready"}}'
            status,data,_=self.request('/v1/chat','POST',json.dumps({'messages':[{'role':'user','content':'Say ready'}]}),True,{'Content-Type':'application/json'})
            self.assertEqual(status,200)
            self.assertEqual(json.loads(data)['message']['content'],'Ready')

    def test_authenticated_observation(self):
        status,data,_=self.request('/v2/observe','POST','{"tool":"system_status","input":{}}',True,{'Content-Type':'application/json'})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(data)['tool'],'system_status')
