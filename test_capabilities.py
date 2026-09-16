import unittest
from beldin.server import State

class CapabilityTests(unittest.TestCase):
    def test_alias(self):
        s=State('.'); self.assertEqual(s.route('/capabilities'),s.route('/v1/capabilities'))
    def test_metadata(self):
        c=State('.').route('/capabilities')[1]
        for x in c['observations']+c['actions']:
            self.assertIn(x['permission'],('OBSERVE','SAFE_ACTION','SYSTEM_CHANGE','BLOCKED'))
            self.assertIn('input_schema',x); self.assertIsInstance(x['available'],bool)
    def test_no_enabled_writes(self):
        for a in State('.').route('/capabilities')[1]['actions']:
            if a['permission']!='OBSERVE': self.assertFalse(a['available'])
    def test_no_secrets(self): self.assertNotIn('token',str(State('.').route('/capabilities')))
