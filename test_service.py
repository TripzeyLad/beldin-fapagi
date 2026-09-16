import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from beldin.server import Server, State, load_config
from beldin.metrics import unavailable, ollama_get, gpu

TOKEN='test-only-'+'x'*40

class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state=State('.',lambda _: {'cpu':unavailable(), 'ram':unavailable(), 'gpu':unavailable(), 'disk':unavailable(), 'ollama':{}})
        cls.state.refresh()
        cls.server=Server(('127.0.0.1',0),TOKEN,cls.state)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def request(self,path='/v1/health',method='GET',token=TOKEN,body=None,headers=None):
        c=http.client.HTTPConnection(*self.server.server_address,timeout=3)
        h={'Authorization':'Bearer '+token} if token else {}
        h.update(headers or {})
        c.request(method,path,body=body,headers=h)
        r=c.getresponse(); result=(r.status,json.loads(r.read())); c.close(); return result
    def test_health(self): self.assertEqual(self.request()[0],200)
    def test_auth_missing(self): self.assertEqual(self.request(token='')[0],401)
    def test_auth_wrong(self): self.assertEqual(self.request(token='no')[0],401)
    def test_auth_before_route(self): self.assertEqual(self.request('/no',token='')[0],401)
    def test_unknown(self): self.assertEqual(self.request('/no')[0],404)
    def test_traversal(self): self.assertEqual(self.request('/../config.local.json')[0],404)
    def test_query_secret_not_echoed(self): self.assertNotIn(TOKEN,json.dumps(self.request('/?token='+TOKEN)))
    def test_unavailable(self): self.assertIsNone(self.request('/v1/telemetry')[1]['observed']['cpu']['data'])
    def test_version(self): self.assertEqual(self.request()[1]['api_version'],'1')
    def test_get_body(self): self.assertEqual(self.request(body='x')[0],400)
    def test_post_denied(self): self.assertEqual(self.request(method='POST')[0],405)
    def test_action_http(self): self.assertEqual(self.request('/v1/actions','POST',body='{"action":"health_snapshot","input":{}}',headers={'Content-Type':'application/json'})[0],200)
    def test_action_auth(self): self.assertEqual(self.request('/v1/actions','POST',token='',body='{}')[0],401)
    def test_action_duplicate_json(self): self.assertEqual(self.request('/v1/actions','POST',body='{"action":"shell","action":"health_snapshot","input":{}}',headers={'Content-Type':'application/json'})[0],400)
    def test_action_malformed(self): self.assertEqual(self.request('/v1/actions','POST',body='{',headers={'Content-Type':'application/json'})[0],400)
    def test_action_oversized(self): self.assertEqual(self.request('/v1/actions','POST',body='x'*4097,headers={'Content-Type':'application/json'})[0],413)
    def test_action_content_type(self): self.assertEqual(self.request('/v1/actions','POST',body='{}')[0],415)
    def test_transfer_encoding(self): self.assertEqual(self.request(headers={'Transfer-Encoding':'chunked'})[0],400)
    def test_path_bounded(self): self.assertEqual(self.request('/'+'x'*300)[0],431)
    def test_upstream_failure(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=TimeoutError): self.assertFalse(ollama_get('ps')['available'])
    def test_upstream_allowlist(self): self.assertFalse(ollama_get('../config')['available'])
    def test_gpu_missing(self):
        with patch('shutil.which',return_value=None): self.assertFalse(gpu()['available'])
    def test_config_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'; p.write_text('{"token":"short"}')
            with patch.dict('os.environ',{},clear=True),self.assertRaises(ValueError): load_config(p)
    def test_public_bind_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'; p.write_text(json.dumps({'token':TOKEN,'host':'0.0.0.0'}))
            with self.assertRaises(ValueError): load_config(p)

if __name__=='__main__': unittest.main()
