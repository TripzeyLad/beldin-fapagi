import tempfile,unittest
from pathlib import Path
from beldin.app_registry import public_registry,validate
from beldin.install_policy import INSTALL_POLICY
from beldin.memory import remember,recall,forget
from beldin.server import State
from beldin.selftest import run
class BackendFoundationTests(unittest.TestCase):
 def test_app_registry_deny_default(self):
  self.assertEqual(public_registry()["default_policy"],"deny")
  self.assertTrue(validate("beldin_core","health_snapshot",{})[0])
  self.assertFalse(validate("unknown","shell",{})[0])
 def test_install_policy_is_metadata_only(self):
  self.assertEqual(INSTALL_POLICY["permission"],"SYSTEM_CHANGE")
  self.assertTrue(INSTALL_POLICY["confirmation_required"])
  self.assertFalse(INSTALL_POLICY["arbitrary_commands"])
  self.assertFalse(INSTALL_POLICY["allowlisted_packages"])
 def test_intentional_bounded_memory(self):
  with tempfile.TemporaryDirectory() as d:
   code,row=remember(d,"Surface is the voice terminal","architecture")
   self.assertEqual(code,200); self.assertEqual(recall(d,"voice")[1]["count"],1)
   self.assertEqual(forget(d,row["id"])[0],200); self.assertEqual(recall(d,"voice")[1]["count"],0)
 def test_selftest_truthful(self):
  s=State(".",lambda _:{"ollama":{"version":{"available":True}}});s.refresh()
  c=run(s);self.assertTrue(c["service"]);self.assertEqual(c["model"],"qwen3:8b");self.assertEqual(c["reload_task"],"external_task_status_required")
