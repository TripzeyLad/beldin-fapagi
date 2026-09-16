import unittest
from beldin.routing import route_text, parse_qwen_tool_call, spoken_content

class RoutingTests(unittest.TestCase):
    def test_natural_observation_routes(self):
        self.assertEqual(route_text('How is Valkyrie doing?')['tool'], 'system_status')
        self.assertEqual(route_text('Is Ollama using the GPU?')['tool'], 'ollama_status')
    def test_actions_need_confirmation(self):
        p=route_text('Please back up Beldin')
        self.assertTrue(p['confirmation_required'])
    def test_only_allowlisted_bounded_json_is_call(self):
        c=parse_qwen_tool_call('```json\n{"tool":"system_status","input":{}}\n```', ['system_status'], [])
        self.assertEqual(c['name'],'system_status')
        self.assertIsNone(parse_qwen_tool_call('{"tool":"shell","input":{"cmd":"whoami"}}',['system_status'],[]))
    def test_tool_json_is_not_spoken(self):
        r=spoken_content('{"action":"backup_beldin","input":{}}', [], ['backup_beldin'])
        self.assertNotIn('backup_beldin', r['text'])

if __name__ == '__main__': unittest.main()
