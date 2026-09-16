import unittest
from beldin.actions import dispatch
from beldin.server import State

class ActionTests(unittest.TestCase):
    def test_observe(self): self.assertEqual(dispatch({'action':'health_snapshot','input':{}},State('.'))[0],200)
    def test_shell_blocked(self): self.assertEqual(dispatch({'action':'shell','input':{}},None)[0],403)
    def test_system_disabled(self): self.assertEqual(dispatch({'action':'system_change','input':{}},None)[0],403)
    def test_safe_disabled(self): self.assertEqual(dispatch({'action':'reload_config','input':{}},None)[0],403)
    def test_unknown(self): self.assertEqual(dispatch({'action':'powershell','input':{}},None)[0],404)
    def test_extra_fields(self): self.assertEqual(dispatch({'action':'health_snapshot','input':{},'confirmation':'invented'},None)[0],400)
    def test_input_rejected(self): self.assertEqual(dispatch({'action':'health_snapshot','input':{'cmd':'whoami'}},None)[0],400)
    def test_non_object(self): self.assertEqual(dispatch([],None)[0],400)
