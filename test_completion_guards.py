import unittest
import test_coding_acceptance as fixtures
from beldin.coding import CodingError, collect_validation


class CompletionGuards(unittest.TestCase):
    setUp=fixtures.AcceptanceTests.setUp
    tearDown=fixtures.AcceptanceTests.tearDown
    task=fixtures.AcceptanceTests.task

    def test_requested_tests_cannot_be_omitted_after_green_repository_suite(self):
        t=self.task(prompt='Fix shipping and add boundary and bad-input tests.')
        r=self.agent.tool(t,'finish',{})
        self.assertIn('requested_test_changes_missing',r['problems'])
        with self.assertRaises(CodingError): self.agent.approve(t,t['proposal']['digest'])

    def test_declared_changed_paths_are_enforced(self):
        t=self.task(constraints={'required_changed_paths':['test_calc.py']})
        self.assertIn('required_changed_path:test_calc.py',self.agent.tool(t,'finish',{})['problems'])
        self.agent.tool(t,'edit',{'path':'test_calc.py','content':'import unittest\n'})
        self.agent.tool(t,'test',{})
        self.assertTrue(self.agent.tool(t,'finish',{})['approval_eligible'])

    def test_bad_constraint_types_rejected(self):
        for c in ({'require_test_changes':1},{'required_changed_paths':['../escape.py']}):
            with self.assertRaises(CodingError): self.agent.create('demo',constraints=c)

    def test_model_receives_declared_acceptance_contract(self):
        seen=[]
        def model(messages,model):
            seen.extend(messages)
            return {'tool':'finish','args':{}}
        self.agent.model_call=model
        t=self.agent.create('demo',prompt='Inspect',requirements=['reject bool'],constraints={'required_tests':['test_bool']})
        self.agent.agent_loop(t)
        text='\n'.join(m['content'] for m in seen)
        self.assertIn('reject bool',text)
        self.assertIn('test_bool',text)
        self.assertEqual(t['status'],'repair_required')

    def test_empty_tested_diff_cannot_be_approved_directly(self):
        t=self.agent.create('demo');self.agent.test(t);p=self.agent.diff(t)
        with self.assertRaisesRegex(CodingError,'empty_proposal'): self.agent.approve(t,p['digest'])

    def test_validation_excludes_live_secrets_but_keeps_boundary_source(self):
        for name in ('config.desktop.json','config.creator.json','config.surface.env','private.key'):
            (self.project/name).write_text('private fixture value')
        (self.project/'secret_policy.py').write_text('VALUE = 1\n')
        files=collect_validation(self.project)
        self.assertIn('secret_policy.py',files)
        self.assertFalse(any(n.startswith('config.') or n.endswith('.key') for n in files))

if __name__=='__main__': unittest.main()
