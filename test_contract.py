import unittest
from unittest.mock import patch
from beldin.server import State
from beldin.metrics import ollama_get

class ContractTests(unittest.TestCase):
    def test_empty_sample_is_explicit(self):
        d=State('.').telemetry(); self.assertIsNone(d['observed']); self.assertIsNone(d['sampled_at_unix'])
    def test_aliases_stable(self):
        s=State('.',lambda _: {'cpu':{'available':False,'data':None,'reason':'test'}}); s.refresh()
        for path in ('/v1/telemetry','/v1/hardware','/v1/ollama'):
            code,d=s.route(path); self.assertEqual(code,200)
            self.assertEqual(set(d),{'observed','sampled_at_unix','age_seconds','service_uptime_seconds'})
            self.assertFalse(d['observed']['cpu']['available'])
    def test_invalid_upstream_json(self):
        with patch('urllib.request.OpenerDirector.open') as p:
            p.return_value.__enter__.return_value.read.return_value=b'no json'
            self.assertFalse(ollama_get('ps')['available'])
    def test_oversized_upstream(self):
        with patch('urllib.request.OpenerDirector.open') as p:
            p.return_value.__enter__.return_value.read.return_value=b'x'*262145
            self.assertEqual(ollama_get('ps')['reason'],'response_too_large')
