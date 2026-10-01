import hashlib
import pathlib
import unittest

class ReloadControlTests(unittest.TestCase):
    def setUp(self):
        out=pathlib.Path(__file__).parent/'reload-reference'
        self.text=(out/'BELDIN_VERIFIED_RELOAD.ps1').read_text(encoding='utf-8')
        self.installer=(out/'INSTALL_BELDIN_RELOAD_TASK.ps1').read_text(encoding='utf-8')
        self.docs=(out/'BELDIN_RELOAD_CONTROL.md').read_text(encoding='utf-8')
    def test_reload_fixture_matches_pinned_identity(self):
        digest=hashlib.sha256((pathlib.Path(__file__).parent/'reload-reference'/'BELDIN_VERIFIED_RELOAD.ps1').read_bytes()).hexdigest()
        self.assertEqual(digest,'fee8fab1c997c40afd64b7d7f63fce97949605e0715fbc1b15ed7418f26c8e4e')

    def test_fixed_identity_and_no_inputs(self):
        self.assertIn('LocalPort 8765',self.text)
        self.assertIn("if($old -eq 1860)",self.text)
        self.assertIn('beldin\\.server',self.text)
        self.assertIn('supervise.py',self.text)
        self.assertIn('Stop-Process -Id $old -Force -Confirm:$false',self.text)
        self.assertNotIn("Set-Content 'C:\\Windows\\Temp",self.text)
        self.assertNotIn('$args',self.text)
        self.assertNotIn('Stop-Process -Id $old\n',self.text)
    def test_forbidden_targets_absent(self):
        self.assertNotIn('11434',self.text)
        self.assertIn('1860',self.text)
        self.assertNotIn('Stop-Process -Id $args',self.text)

    def test_installer_and_docs_are_fixed(self):
        self.assertIn("$taskName='Beldin Verified Reload'",self.installer)
        self.assertIn("-UserId 'SYSTEM'",self.installer)
        self.assertIn('-RunLevel Highest',self.installer)
        self.assertIn('BELDIN_VERIFIED_RELOAD.ps1',self.installer)
        self.assertNotIn('$args',self.installer)
        self.assertIn('NonInteractive',self.docs)
        self.assertIn('Force -Confirm:$false',self.docs)
        self.assertIn('LastTaskResult',self.docs)
