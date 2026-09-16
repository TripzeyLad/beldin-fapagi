import hashlib,json,unittest
from pathlib import Path
from beldin.knowledge import category_context
from beldin.memory import remember
from beldin.server import State
ROOT=Path(__file__).parent
class FoundingTests(unittest.TestCase):
 def test_origin_hashes_and_separation(self):
  m=json.loads((ROOT/"origin"/"MANIFEST.json").read_text())
  for d in m["documents"]:
   p=ROOT/"origin"/d["source_filename"]
   self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest().upper(),d["sha256"])
   self.assertTrue(d["historical"]);self.assertTrue(d["immutable"])
  self.assertTrue((ROOT/"BELDIN_CONSTITUTION.md").exists())
  self.assertTrue((ROOT/"BELDIN_ROADMAP.md").exists())
 def test_founding_context_is_bounded_and_not_memory(self):
  self.assertIn("historical",category_context("What was my first task?").casefold())
  self.assertIn("aspirations",category_context("What can you do right now?",State(".")))
  self.assertEqual(remember(ROOT,"constitution","system")[0],400)
