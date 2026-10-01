import tempfile
import unittest
from pathlib import Path
from beldin.coding import CodingAgent, CodingError

UNITTEST_OUT = 'test_answer (test_calc.CalcTests.test_answer) ... ok\n\nRan 1 test in 0.001s\n\nOK\n'
OK = dict(status='completed', exit_code=0, stdout='', stderr=UNITTEST_OUT, command=['python', '-m', 'unittest'])


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.project = root / 'project'; self.project.mkdir()
        (self.project / 'calc.py').write_text('answer = 1\n')
        self.agent = CodingAgent(root / 'svc', projects={'demo': {'path': str(self.project)}},
                                 runner=lambda *a, **k: dict(OK))

    def tearDown(self): self.tmp.cleanup()

    def task(self, **kw):
        t = self.agent.create('demo', **kw)
        self.agent.tool(t, 'patch', {'path': 'calc.py', 'old': '1', 'new': '2'})
        self.agent.tool(t, 'test', {})
        return t

    def test_green_tests_alone_do_not_satisfy_declared_requirements(self):
        t = self.task(requirements=['answer must be 2'])
        r = self.agent.tool(t, 'finish', {})
        self.assertEqual(r['error'], 'acceptance_incomplete')
        self.assertFalse(t['proposal']['approval_eligible'])
        with self.assertRaisesRegex(CodingError, 'acceptance_incomplete'):
            self.agent.approve(t, t['proposal']['digest'])

    def test_fabricated_evidence_is_rejected(self):
        t = self.task(requirements=['answer must be 2'])
        for ev in ({'R1': {'files': ['other.py'], 'tests': ['test_answer']}},
                   {'R1': {'files': ['calc.py'], 'tests': ['test_invented']}},
                   {'R1': {'files': ['calc.py'], 'tests': []}}):
            self.assertEqual(self.agent.tool(t, 'finish', {'evidence': ev})['error'], 'acceptance_incomplete')

    def test_verified_evidence_reaches_approval(self):
        t = self.task(requirements=['answer must be 2'])
        self.agent.tool(t, 'finish', {'evidence': {'R1': {'files': ['calc.py'], 'tests': ['test_answer']}}})
        self.assertEqual(t['status'], 'approval_needed')
        self.assertEqual(t['acceptance']['status'], 'complete')
        self.assertEqual(self.agent.approve(t, t['proposal']['digest'])['status'], 'approved')

    def test_edit_after_finish_invalidates_acceptance(self):
        t = self.task(requirements=['answer must be 2'])
        self.agent.tool(t, 'finish', {'evidence': {'R1': {'files': ['calc.py'], 'tests': ['test_answer']}}})
        self.agent.tool(t, 'edit', {'path': 'calc.py', 'content': 'answer = 3\n'})
        self.assertEqual(t['acceptance']['status'], 'not_evaluated')

    def test_constraints_enforced(self):
        t = self.task(constraints={'forbidden_paths': ['calc.py']})
        self.assertIn('forbidden_path:calc.py', self.agent.tool(t, 'finish', {})['problems'])
        t = self.task(constraints={'required_tests': ['test_missing']})
        self.assertIn('required_test:test_missing', self.agent.tool(t, 'finish', {})['problems'])
        t = self.task(constraints={'max_files': 1, 'required_tests': ['test_answer']})
        self.agent.tool(t, 'finish', {})
        self.assertEqual(t['status'], 'approval_needed')

    def test_unmapped_task_is_labelled_not_silently_verified(self):
        t = self.task()
        self.agent.tool(t, 'finish', {})
        self.assertEqual(t['proposal']['acceptance']['status'], 'unmapped')

    def test_invalid_declarations_rejected(self):
        for kw in ({'requirements': 'x'}, {'requirements': [1]}, {'constraints': {'shell': 1}},
                   {'constraints': {'required_tests': ['a b']}}):
            with self.assertRaises(CodingError): self.agent.create('demo', **kw)


if __name__ == '__main__':
    unittest.main()
