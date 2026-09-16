import unittest
from unittest.mock import patch
from beldin.server import State
from beldin.tools import observe, process_summary
from beldin.safe_actions import propose, cancel, confirm

class AuditRepairTests(unittest.TestCase):
    def test_cancel_and_replay(self):
        s=State('.')
        code,p=propose('create_note',{'text':'test'},s)
        self.assertEqual(code,200)
        self.assertEqual(cancel(p['action_id'],s)[0],200)
        self.assertEqual(confirm(p['action_id'],s)[0],409)
        self.assertEqual(cancel(p['action_id'],s)[0],409)

    def test_observation_aliases(self):
        for name in ('node_status','action_history'):
            self.assertEqual(observe(name,{},State('.'))[0],200)

    def test_process_csv(self):
        with patch('beldin.tools.subprocess.check_output',return_value='"python.exe","123","Console","1","12,345 K"'):
            self.assertEqual(process_summary()['data'][0]['pid'],123)

    def test_pending_bound(self):
        s=State('.')
        for _ in range(128): self.assertEqual(propose('create_note',{'text':'test'},s)[0],200)
        self.assertEqual(propose('create_note',{'text':'test'},s)[0],429)
        self.assertEqual(propose('create_note',{'text':'test','title':[]},s)[0],400)
