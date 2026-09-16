import unittest
from types import SimpleNamespace
from unittest.mock import patch

from beldin.app_registry import public_registry, validate
from beldin.notepad import create_note
from beldin.routing import route_text


class NotepadPilotTests(unittest.TestCase):
    def test_registry_is_explicit_and_deny_by_default(self):
        reg = public_registry()
        ops = reg['apps']['windows_notepad']['operations']
        self.assertEqual(reg['default_policy'], 'deny')
        self.assertEqual(set(ops), {'open_notepad', 'create_notepad_note', 'close_beldin_notepad'})
        self.assertEqual(validate('windows_notepad', 'open_notepad', ({}) )[0], True)
        self.assertEqual(validate('windows_notepad', 'run_shell', {})[0], False)

    def test_action_routing_requires_imperative_intent(self):
        self.assertEqual(route_text('Open Notepad.')['action'], 'open_notepad')
        self.assertEqual(route_text('Start Notepad.')['action'], 'open_notepad')
        self.assertEqual(route_text('Launch Notepad.')['action'], 'open_notepad')
        self.assertEqual(route_text('Write hello world in Notepad.')['action'], 'create_notepad_note')
        self.assertEqual(route_text('Close the Notepad you opened.')['action'], 'close_beldin_notepad')
        for text in ('What is Notepad?', 'Tell me about Notepad.', 'I opened Notepad yesterday.',
                     'Is Notepad good for programming?', 'Why does Notepad have tabs?'):
            self.assertEqual(route_text(text)['kind'], 'chat')

    def test_note_text_is_data_and_bounded(self):
        state = SimpleNamespace()
        result = create_note(state, 'powershell.exe Remove-Item C:\\* && cmd.exe /c shutdown')
        self.assertEqual(result['state'], 'UNAVAILABLE')
        self.assertNotIn('executed', result)
        self.assertEqual(create_note(state, 'x' * 4097)['error'], 'text_too_long_or_empty')

    @patch('beldin.notepad.subprocess.Popen')
    def test_backend_cannot_launch_directly(self, popen):
        from beldin.notepad import open_notepad
        self.assertEqual(open_notepad(SimpleNamespace())['state'], 'UNAVAILABLE')
        popen.assert_not_called()

    def test_close_requires_owned_session_id(self):
        from beldin.notepad import close_notepad
        state = SimpleNamespace(app_lock=__import__('threading').Lock(), app_sessions={})
        self.assertEqual(close_notepad(state, 'unowned')['state'], 'UNVERIFIABLE')


if __name__ == '__main__':
    unittest.main()
