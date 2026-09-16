import tempfile, unittest
from pathlib import Path
from beldin.server import State
from beldin.tools import observe, file_info, read_text, port_status

class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); (self.root/'note.txt').write_text('hello',encoding='utf-8'); self.state=State(self.root, provider=lambda _: {'cpu':{},'ram':{},'gpu':{},'disk':{},'ollama':{}}); self.state.refresh()
    def tearDown(self): self.tmp.cleanup()
    def test_registry_and_system(self): self.assertEqual(observe('system_status',{},self.state)[0],200)
    def test_unknown_and_allowlist(self): self.assertEqual(observe('shell',{},self.state)[0],404); self.assertFalse(port_status('8.8.8.8',8765)['available'])
    def test_safe_file(self): self.assertTrue(file_info(self.root,'note.txt')['available']); self.assertEqual(read_text(self.root,'note.txt')['data']['text'],'hello')
    def test_traversal_and_secret(self): self.assertFalse(read_text(self.root,'../note.txt')['available']); (self.root/'config.local.json').write_text('token'); self.assertFalse(read_text(self.root,'config.local.json')['available'])
    def test_oversized(self): (self.root/'big.txt').write_text('x'*(64*1024+1)); self.assertFalse(read_text(self.root,'big.txt')['available'])

if __name__=='__main__': unittest.main()
