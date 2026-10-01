"""Guards against beldin/mobile.py's raw-completion fallback fabricating tool execution.

Run this on Valkyrie (it needs the full beldin package, same as test_self_improvement.py):
    python -m pytest kit/valkyrie/payload/test_chat_no_fabrication.py -v
or:
    python -m unittest kit.valkyrie.payload.test_chat_no_fabrication -v
"""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from beldin import mobile
from beldin.server import State


class FakeHandler:
    """Same shape as the FakeHandler in test_self_improvement.py, but takes a full
    multi-turn message list so we can reproduce a real conversation history."""
    def __init__(self, state, messages, human=False):
        payload = json.dumps({'messages': messages}).encode()
        self.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(payload))}
        self.rfile = io.BytesIO(payload)
        self.server = type('S', (), {'state': state})()
        self.out = None
        self.human_approved = lambda: human
    def respond(self, code, obj):
        self.out = (code, obj)


class NoFabricationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = State(Path(self.tmp.name) / 'svc', provider=lambda _: {})
    def tearDown(self):
        self.tmp.cleanup()

    def test_explicit_simulate_request_is_refused_without_calling_ollama(self):
        messages = [{'role': 'user', 'content': 'Please simulate the handshake and verification process.'}]
        h = FakeHandler(self.state, messages)
        with patch('beldin.mobile.urlopen') as call:
            mobile.chat(h)
            call.assert_not_called()
        self.assertEqual(h.out[0], 200)
        self.assertIn('fake-execution', h.out[1]['message']['content'])
        self.assertIn('/self', h.out[1]['message']['content'])

    def test_bare_continuation_after_assistant_offered_to_simulate_is_refused(self):
        # This reproduces the exact failure: the assistant previously said it could
        # "simulate" something, then the human just said "Begin Now" with no /self
        # or "fix yourself" trigger anywhere in the message.
        messages = [
            {'role': 'user', 'content': 'Approved for simulation testing only. Proceed.'},
            {'role': 'assistant', 'content': 'I will now simulate the handshake and verification process.'},
            {'role': 'user', 'content': 'Begin Now'},
        ]
        h = FakeHandler(self.state, messages)
        with patch('beldin.mobile.urlopen') as call:
            mobile.chat(h)
            call.assert_not_called()
        self.assertEqual(h.out[0], 200)
        self.assertIn('fake-execution', h.out[1]['message']['content'])

    def test_ordinary_continuation_with_no_prior_simulation_talk_is_not_blocked(self):
        # "Begin now" / "go ahead" must not be blocked in general -- only when it
        # follows the assistant offering to simulate/roleplay something.
        messages = [
            {'role': 'assistant', 'content': "I can summarize the log file for you."},
            {'role': 'user', 'content': 'Go ahead'},
        ]
        h = FakeHandler(self.state, messages)
        reply = json.dumps({'message': {'content': 'Here is the summary...'}}).encode()
        with patch('beldin.mobile.urlopen', return_value=io.BytesIO(reply)) as call:
            mobile.chat(h)
            call.assert_called_once()
            # the anti-fabrication system message must still be injected as defense in depth
            sent_body = json.loads(call.call_args.args[0].data)
            self.assertEqual(sent_body['messages'][0]['role'], 'system')
            self.assertIn('cannot execute or simulate', sent_body['messages'][0]['content'])

    def test_real_self_improvement_trigger_still_works_and_is_never_treated_as_simulation(self):
        messages = [{'role': 'user', 'content': 'Beldin, fix yourself so the status command lists both models'}]
        h = FakeHandler(self.state, messages)
        with patch('beldin.mobile.urlopen') as call:
            mobile.chat(h)
            call.assert_not_called()  # handled entirely by the /self path, no completion needed
        self.assertEqual(h.out[0], 200)
        content = h.out[1]['message']['content']
        self.assertTrue(
            content.startswith('Self-improvement is not enabled') or 'started working on that' in content
        )


if __name__ == '__main__':
    unittest.main()
