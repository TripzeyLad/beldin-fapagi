import tempfile, unittest
from pathlib import Path
from beldin.server import State
from beldin.safe_actions import propose, confirm

class SafeActionTests(unittest.TestCase):
 def setUp(self): self.t=tempfile.TemporaryDirectory(); self.s=State(Path(self.t.name),provider=lambda _: {})
 def tearDown(self): self.t.cleanup()
 def test_confirmation_and_note(self):
  c,o=propose('create_note',{'text':'remember this','title':'test'},self.s); self.assertEqual(c,200); self.assertEqual(confirm(o['action_id'],self.s)[0],200); self.assertTrue(list((Path(self.t.name)/'notes'/'inbox').glob('*.md')))
 def test_expiry_and_replay(self):
  _,o=propose('save_diagnostic_snapshot',{},self.s); self.assertEqual(confirm(o['action_id'],self.s)[0],200); self.assertEqual(confirm(o['action_id'],self.s)[0],409)
 def test_invalid(self): self.assertEqual(propose('create_note',{'text':''},self.s)[0],400)
