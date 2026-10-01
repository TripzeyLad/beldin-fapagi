import unittest
from unittest.mock import patch, MagicMock
import supervise

class EndIteration(Exception): pass

class SupervisorTests(unittest.TestCase):
    def test_existing_listeners_not_duplicated(self):
        with patch.object(supervise.Path,'is_file',return_value=True), patch.object(supervise,'listening',return_value=True), patch.object(supervise.subprocess,'Popen') as launch, patch.object(supervise.time,'sleep',side_effect=EndIteration):
            with self.assertRaises(EndIteration): supervise.main()
            launch.assert_not_called()
    def test_missing_services_fixed_commands_and_local_binding(self):
        with patch.object(supervise.Path,'is_file',return_value=True), patch.object(supervise,'listening',return_value=False), patch.object(supervise.subprocess,'Popen') as launch, patch.object(supervise.time,'sleep',side_effect=EndIteration), patch.dict(supervise.os.environ,{'BELDIN_TOKEN':'do-not-inherit'}):
            with self.assertRaises(EndIteration): supervise.main()
            self.assertEqual(launch.call_count,2)
            for call in launch.call_args_list:
                self.assertEqual(call.kwargs['env']['OLLAMA_HOST'],'127.0.0.1:11434')
                self.assertNotIn('BELDIN_TOKEN',call.kwargs['env'])
                self.assertNotIn('shell',call.kwargs)
    def test_live_children_not_relaunched(self):
        child=MagicMock(); child.poll.return_value=None
        with patch.object(supervise.Path,'is_file',return_value=True), patch.object(supervise,'listening',return_value=False), patch.object(supervise.subprocess,'Popen',return_value=child) as launch, patch.object(supervise.time,'sleep',side_effect=[None,EndIteration]):
            with self.assertRaises(EndIteration): supervise.main()
            self.assertEqual(launch.call_count,2)
