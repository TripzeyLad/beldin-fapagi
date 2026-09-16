import unittest
from beldin.server import State

class EventTests(unittest.TestCase):
    def test_only_changes(self):
        s=State('.',lambda _: {})
        s.refresh(); s.refresh(); self.assertEqual(len(s.events),1)
    def test_bounded(self):
        s=State('.')
        for i in range(100):
            s.provider=lambda _,i=i: {'ollama':{'version':{'available':bool(i%2)}}}
            s.refresh()
        self.assertEqual(len(s.events),64); self.assertEqual(s.event_sequence,100)
    def test_poll_shape(self):
        d=State('.').route('/v1/events')[1]
        self.assertEqual(d['events'],[]); self.assertTrue(d['reset_on_restart'])
