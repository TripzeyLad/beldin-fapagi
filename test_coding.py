import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from beldin.coding import CodingAgent,CodingError,safe_path,collect
from beldin.server import State,Server

OK=dict(status='completed',exit_code=0,stdout='ok',stderr='',command=['python','-m','unittest'])
FAIL={**OK,'exit_code':1,'stderr':'test failed'}

class CodingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.project=self.root/'project'; self.project.mkdir(); (self.project/'calc.py').write_text('answer = 1\n')
        self.agent=CodingAgent(self.root/'service',projects={'demo':{'path':str(self.project),'production':True}},runner=lambda *a,**k:dict(OK))
        self.t=self.agent.create('demo')
    def tearDown(self): self.tmp.cleanup()
    def edit(self): return self.agent.tool(self.t,'patch',{'path':'calc.py','old':'1','new':'2'})
    def review(self):
        self.edit(); self.agent.test(self.t); p=self.agent.diff(self.t); self.agent.approve(self.t,p['digest']); return p
    def test_root_selection(self):
        for p in ('other','../project',str(self.project)):
            with self.assertRaises(CodingError): self.agent.create(p)
    def test_path_escape_and_windows_aliases(self):
        for name in ('../calc.py','/calc.py','C:/calc.py','a\\b','a:b','a/../b','NUL','a.','x/CON.txt','.git/a','config.local.json','coding-projects.json','token.txt','runtime/a'):
            with self.subTest(name=name),self.assertRaises(CodingError): safe_path(self.project,name)
    def test_validation_has_required_protected_files_without_exposing_them_to_model(self):
        (self.project/'secret_policy.py').write_text('VALUE = 7\n')
        (self.project/'config.creator.json').write_text('{"enabled": true}\n')
        origin=self.project/'origin'; origin.mkdir()
        (origin/'MANIFEST.json').write_text('{"version": 1}\n')

        self.t=self.agent.create('demo')

        visible=self.agent.tool(self.t,'list',{})['files']
        self.assertEqual(visible,['calc.py'])

        seen={}
        def runner(runtime,workspace,argv,**kwargs):
            workspace=Path(workspace)
            seen['secret']=(workspace/'secret_policy.py').read_text()
            seen['config']=(workspace/'config.creator.json').read_text()
            seen['origin']=(workspace/'origin'/'MANIFEST.json').read_text()
            return dict(OK)

        self.agent.runner=runner
        self.edit()
        proposed=self.agent.diff(self.t)
        self.agent.test(self.t)

        self.assertIn('VALUE = 7',seen['secret'])
        self.assertIn('"enabled": true',seen['config'])
        self.assertIn('"version": 1',seen['origin'])
        self.assertTrue(self.t['validation']['passed'])
        self.assertEqual(self.t['validation']['digest'],proposed['digest'])

    def test_hardlinks_rejected(self):
        os.link(self.project/'calc.py',self.project/'linked.py')
        with self.assertRaises(CodingError): collect(self.project)
    def test_inspect_search_edit_diff_leave_production_untouched(self):
        self.assertEqual(self.agent.tool(self.t,'list',{})['files'],['calc.py'])
        self.assertIn('answer',self.agent.tool(self.t,'read',{'path':'calc.py'})['content'])
        self.assertEqual(self.agent.tool(self.t,'search',{'query':'answer'})['matches'][0]['line'],1)
        self.edit(); p=self.agent.diff(self.t)
        self.assertIn('+answer = 2',p['patch']); self.assertEqual((self.project/'calc.py').read_text(),'answer = 1\n')

    def test_search_result_audit_is_bounded_metadata(self):
        actions=iter([{'tool':'search','args':{'query':'answer'}},{'tool':'finish','args':{}}])
        self.agent.model_call=lambda *a: next(actions)
        self.agent.agent_loop(self.t)
        audit=[e for e in self.t['events'] if e['action']=='search_result'][-1]
        self.assertEqual(audit['step'],1)
        self.assertEqual(audit['match_count'],1)
        self.assertEqual(audit['matched_paths'],['calc.py'])
        self.assertFalse(audit['truncated'])
        self.assertNotIn('text',audit)

    def test_nonliteral_search_rejected_before_workspace_scan(self):
        for query in ('import.*without.*from','import.*without.*as',
                      'import.*without.*parentheses','.*','*.py.*'):
            with self.subTest(query=query),patch('beldin.coding.collect') as scan:
                result=self.agent.tool(self.t,'search',{'query':query})
                scan.assert_not_called()
                self.assertEqual(result['error'],'search_query_not_literal')
                self.assertFalse(result['executed'])
                self.assertNotIn('matches',result)
                self.assertIn('literal plain-text substring matching',result['message'])
                self.assertEqual(result['example']['args']['query'],'import ')
                self.assertLess(len(json.dumps(result)),500)

    def test_literal_source_punctuation_is_preserved(self):
        source='obj.attr\nitems[0]\nf(x)\na * b\nx + y\na | b\n^value$\nimport os\n'
        self.agent.tool(self.t,'edit',{'path':'calc.py','content':source})
        for query in source.splitlines():
            with self.subTest(query=query):
                result=self.agent.tool(self.t,'search',{'query':query})
                self.assertEqual([m['text'] for m in result['matches']],[query])

    def test_rejected_searches_share_no_progress_budget_with_misses(self):
        queries=iter(['a.*b','missing-a','c.*d','missing-b','e.*f'])
        seen=[]
        def model(messages,model):
            seen.extend(m['content'] for m in messages)
            return {'tool':'search','args':{'query':next(queries)}}
        self.agent.model_call=model
        original=collect
        with patch('beldin.coding.collect',wraps=original) as scan:
            with self.assertRaisesRegex(CodingError,'^model_stuck_no_progress$'):
                self.agent.agent_loop(self.t)
            self.assertEqual(scan.call_count,2)
        errors=[e for e in self.t['events'] if e.get('error')=='search_query_not_literal']
        self.assertEqual([e['step'] for e in errors],[1,3,5])
        interventions=[e for e in self.t['events'] if e['action']=='no_progress_intervention']
        self.assertEqual([e['step'] for e in interventions],[3])
        self.assertIn('no regex, no wildcards, do not use .*',seen[0])
        self.assertTrue(any('Tool result (data):' in m and 'search_query_not_literal' in m for m in seen))

    def test_rejected_search_streak_can_recover_and_reset(self):
        actions=iter([
            {'tool':'search','args':{'query':'a.*b'}},
            {'tool':'search','args':{'query':'c.*d'}},
            {'tool':'list','args':{}},
            {'tool':'read','args':{'path':'calc.py'}},
            {'tool':'search','args':{'query':'e.*f'}},
            {'tool':'search','args':{'query':'answer'}},
            {'tool':'search','args':{'query':'g.*h'}},
            {'tool':'search','args':{'query':'i.*j'}},
            {'tool':'patch','args':{'path':'calc.py','old':'1','new':'2'}},
            {'tool':'test','args':{}},
            {'tool':'diff','args':{}},
            {'tool':'finish','args':{}},
        ])
        self.agent.model_call=lambda *a:next(actions)
        self.agent.agent_loop(self.t)
        self.assertEqual(self.t['status'],'approval_needed')
        self.assertFalse(any(e['action']=='no_progress_intervention' for e in self.t['events']))
        self.assertEqual((self.project/'calc.py').read_text(),'answer = 1\n')

    def test_repeated_malformed_search_preserves_exact_repeat_guard(self):
        self.agent.model_call=lambda *a:{'tool':'search','args':{'query':'a.*b'}}
        with patch('beldin.coding.collect') as scan:
            with self.assertRaisesRegex(CodingError,'^model_stuck_repeated_action$'):
                self.agent.agent_loop(self.t)
            scan.assert_not_called()

    def test_distinct_malformed_searches_terminate_at_five(self):
        queries=iter(['a.*b','c.*d','e.*f','g.*h','i.*j'])
        self.agent.model_call=lambda *a:{'tool':'search','args':{'query':next(queries)}}
        with patch('beldin.coding.collect') as scan:
            with self.assertRaisesRegex(CodingError,'^model_stuck_no_progress$'):
                self.agent.agent_loop(self.t)
            scan.assert_not_called()
        self.assertEqual(self.t['events'][-1]['step'],5)
        self.assertFalse(any(e['action']=='search_result' for e in self.t['events']))

    def test_no_match_guidance_and_stuck_detector(self):
        seen=[]
        actions=iter([{'tool':'search','args':{'query':'missing'}}]*5)
        def model(messages, model):
            seen.append(messages[0]['content'])
            return next(actions)
        self.agent.model_call=model
        with self.assertRaises(CodingError) as ctx: self.agent.agent_loop(self.t)
        self.assertEqual(str(ctx.exception),'model_stuck_repeated_action')
        self.assertIn('create the smallest reasonable new source and test files',seen[0])
        self.assertIn('must never be retried',seen[0])
        self.assertIn('literal plain-text substring matching, not regular expressions',seen[0])
        self.assertTrue(any(e.get('error')=='model_stuck_repeated_action' for e in self.t['events']))
        audit=[e for e in self.t['events'] if e['action']=='search_result']
        self.assertEqual(audit[0]['match_count'],0)
        self.assertEqual(audit[0]['matched_paths'],[])
        self.assertNotIn('text',audit[0])

    def test_zero_search_streak_intervenes_then_terminates(self):
        queries=iter(['missing-a','missing-b','missing-c','missing-d','missing-e'])
        seen=[]
        def model(messages, model):
            seen.append([m['content'] for m in messages if m['role']=='user'])
            return {'tool':'search','args':{'query':next(queries)}}
        self.agent.model_call=model
        with self.assertRaises(CodingError) as ctx: self.agent.agent_loop(self.t)
        self.assertEqual(str(ctx.exception),'model_stuck_no_progress')
        self.assertTrue(any(e['action']=='no_progress_intervention' for e in self.t['events']))
        self.assertTrue(any(e.get('error')=='model_stuck_no_progress' for e in self.t['events']))
        self.assertTrue(any('Hard progress instruction' in content for turn in seen for content in turn))

    def test_zero_search_streak_resets_on_productive_and_nonzero_progress(self):
        actions=iter([
            {'tool':'search','args':{'query':'missing-a'}},
            {'tool':'search','args':{'query':'missing-b'}},
            {'tool':'read','args':{'path':'calc.py'}},
            {'tool':'search','args':{'query':'answer'}},
            {'tool':'search','args':{'query':'missing-c'}},
            {'tool':'search','args':{'query':'missing-d'}},
            {'tool':'finish','args':{}},
        ])
        self.agent.model_call=lambda *a:next(actions)
        self.agent.agent_loop(self.t)
        self.assertEqual(self.t['status'],'approval_needed')
        self.assertFalse(any(e['action']=='no_progress_intervention' for e in self.t['events']))
    def test_patch_requires_unique_match(self):
        with self.assertRaises(CodingError): self.agent.tool(self.t,'patch',{'path':'calc.py','old':'none','new':'x'})

    def churn_searches(self):
        return [{'tool':'search','args':{'query':q}} for q in ('answer','ans',' = ','1')]

    def run_churn_actions(self,actions):
        pending=iter(actions); self.churn_messages=[]
        def model(messages,model):
            self.churn_messages.append([dict(m) for m in messages])
            return next(pending)
        self.agent.model_call=model
        self.agent.agent_loop(self.t)

    def test_successful_search_churn_intervenes_with_bounded_paths(self):
        for i in range(25):
            self.agent.tool(self.t,'edit',{'path':f'candidate{i}.py','content':'answer = 1\n'})
        self.run_churn_actions(self.churn_searches()+[{'tool':'finish','args':{}}])
        events=[e for e in self.t['events'] if e['action']=='search_churn_intervention']
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['step'],4)
        self.assertEqual(len(events[0]['matched_paths']),5)
        self.assertNotIn('content',events[0])
        instruction=[m['content'] for m in self.churn_messages[-1] if 'Hard progress instruction: enough' in m['content']][0]
        self.assertIn('read it before',instruction)
        self.assertLess(len(instruction),1800)

    def test_search_requires_read_blocks_execution(self):
        actions=self.churn_searches()+[{'tool':'search','args':{'query':'never execute'}},{'tool':'finish','args':{}}]
        with patch.object(self.agent,'tool',wraps=self.agent.tool) as tool:
            self.run_churn_actions(actions)
        self.assertEqual([c.args[1] for c in tool.call_args_list],['search']*4+['finish'])
        results=[json.loads(m['content'].removeprefix('Tool result (data): ')) for m in self.churn_messages[-1] if m['content'].startswith('Tool result (data): ')]
        self.assertEqual(results[-1]['error'],'search_requires_read')
        self.assertFalse(results[-1]['executed'])
        self.assertEqual(results[-1]['matched_paths'],['calc.py'])

    def test_search_churn_recovers_on_read_and_resets_refusals(self):
        actions=self.churn_searches()+[
            {'tool':'search','args':{'query':'blocked'}},
            {'tool':'read','args':{'path':'calc.py'}},
        ]+self.churn_searches()[:1]+[
            {'tool':'patch','args':{'path':'calc.py','old':'1','new':'2'}},
            {'tool':'test','args':{}},{'tool':'diff','args':{}},{'tool':'finish','args':{}}]
        self.run_churn_actions(actions)
        self.assertEqual(self.t['status'],'approval_needed')
        self.assertIn('+answer = 2',self.t['proposal']['patch'])
        self.assertEqual((self.project/'calc.py').read_text(),'answer = 1\n')
        self.assertEqual(len([e for e in self.t['events'] if e.get('error')=='search_requires_read']),1)
        self.assertEqual(self.t['research']['searches'],6)

    def test_search_churn_refusal_fails_early(self):
        with patch.object(self.agent,'tool',wraps=self.agent.tool) as tool:
            with self.assertRaisesRegex(CodingError,'^model_stuck_search_churn$'):
                self.run_churn_actions(self.churn_searches()+[
                    {'tool':'search','args':{'query':'different'}},
                    {'tool':'search','args':{'query':'another'}}])
        self.assertEqual(tool.call_count,4)
        self.assertEqual(self.t['events'][-1]['step'],6)

    def test_short_search_sequences_work(self):
        self.run_churn_actions(self.churn_searches()[:3]+[
            {'tool':'read','args':{'path':'calc.py'}},
        ]+self.churn_searches()[:3]+[{'tool':'finish','args':{}}])
        self.assertEqual(self.t['status'],'approval_needed')
        self.assertFalse(any(e['action']=='search_churn_intervention' for e in self.t['events']))

    def test_list_and_failed_read_do_not_clear_active_churn(self):
        with self.assertRaisesRegex(CodingError,'^model_stuck_search_churn$'):
            self.run_churn_actions(self.churn_searches()+[
                {'tool':'search','args':{'query':'blocked'}},
                {'tool':'list','args':{}},
                {'tool':'read','args':{'path':'missing.py'}},
                {'tool':'search','args':{'query':'still blocked'}}])
        self.assertEqual(self.t['events'][-1]['step'],8)

    def test_non_search_progress_still_has_sixteen_step_cap(self):
        actions=[{'tool':op,'args':{}} for op in ('test','diff')]*8
        with self.assertRaisesRegex(CodingError,'^model_step_limit$'):
            self.run_churn_actions(actions)
        self.assertEqual(len(self.churn_messages),16)

    def test_global_search_budget_survives_read(self):
        actions=self.churn_searches()[:3]+[{'tool':'read','args':{'path':'calc.py'}}]+self.churn_searches()[:3]
        with patch.object(self.agent,'tool',wraps=self.agent.tool) as tool:
            self.run_churn_actions(actions+[
                {'tool':'search','args':{'query':'budget blocked'}},{'tool':'finish','args':{}}])
        self.assertEqual(sum(c.args[1]=='search' for c in tool.call_args_list),6)
        self.assertEqual(self.t['research']['searches'],7)
        self.assertTrue(any(e.get('error')=='research_requires_action' for e in self.t['events']))

    def test_search_read_cycle_fails_early_without_executing_research(self):
        actions=[{'tool':'search','args':{'query':'answer'}},{'tool':'read','args':{'path':'calc.py'}},
                 {'tool':'search','args':{'query':'1'}},{'tool':'read','args':{'path':'calc.py'}},
                 {'tool':'search','args':{'query':'ans'}},{'tool':'list','args':{}}]
        with patch.object(self.agent,'tool',wraps=self.agent.tool) as tool:
            with self.assertRaisesRegex(CodingError,'^model_stuck_research_loop$'):
                self.run_churn_actions(actions)
        self.assertEqual(tool.call_count,4)
        self.assertEqual(self.t['events'][-1]['step'],6)

    def test_productive_edit_test_advances_phase_without_refilling_searches(self):
        phases=[]
        actions=iter([{'tool':'search','args':{'query':'answer'}},
                      {'tool':'read','args':{'path':'calc.py'}},
                      {'tool':'read','args':{'path':'calc.py'}},
                      {'tool':'patch','args':{'path':'calc.py','old':'1','new':'2'}},
                      {'tool':'test','args':{}},{'tool':'finish','args':{}}])
        def model(*args):
            phases.append(self.t.get('research',{}).get('phase','DISCOVER'))
            return next(actions)
        self.agent.model_call=model
        self.agent.agent_loop(self.t)
        self.assertEqual(phases,['DISCOVER','DISCOVER','INSPECT','ACT','VALIDATE','PROPOSE'])
        self.assertEqual(self.t['research']['searches'],1)
        self.assertNotIn('_approved',self.t)

    def test_failed_test_allows_only_one_bounded_diagnostic_window(self):
        self.agent.runner=lambda *a,**k:dict(FAIL)
        self.run_churn_actions([
            {'tool':'read','args':{'path':'calc.py'}},{'tool':'read','args':{'path':'calc.py'}},
            {'tool':'test','args':{}},
            {'tool':'search','args':{'query':'answer'}},{'tool':'read','args':{'path':'calc.py'}},
            {'tool':'search','args':{'query':'1'}},
            {'tool':'test','args':{}},
            {'tool':'search','args':{'query':'blocked'}},{'tool':'finish','args':{}}])
        self.assertEqual(len([e for e in self.t['events'] if e['action']=='diagnostic_research_allowed']),1)
        self.assertEqual(len([e for e in self.t['events'] if e['action']=='search_result']),2)
        self.assertTrue(any(e.get('error')=='research_requires_action' for e in self.t['events']))

    def test_noop_edit_and_failed_read_cannot_clear_action_requirement(self):
        with self.assertRaisesRegex(CodingError,'^model_stuck_research_loop$'):
            self.run_churn_actions([
                {'tool':'read','args':{'path':'calc.py'}},{'tool':'read','args':{'path':'calc.py'}},
                {'tool':'search','args':{'query':'blocked'}},
                {'tool':'edit','args':{'path':'calc.py','content':(self.t['_home']/'dev'/'calc.py').read_bytes().decode()}},
                {'tool':'read','args':{'path':'missing.py'}}])

    def test_patch_failure_allows_bounded_diagnostics(self):
        self.run_churn_actions([
            {'tool':'read','args':{'path':'calc.py'}},{'tool':'read','args':{'path':'calc.py'}},
            {'tool':'patch','args':{'path':'calc.py','old':'missing','new':'2'}},
            {'tool':'search','args':{'query':'answer'}},{'tool':'read','args':{'path':'calc.py'}},
            {'tool':'finish','args':{}}])
        self.assertEqual(self.t['research']['diagnostic_left'],1)
    def test_approval_requires_review_and_green_tests(self):
        with self.assertRaises(CodingError): self.agent.approve(self.t,'fake')
        self.edit(); p=self.agent.diff(self.t)
        with self.assertRaises(CodingError): self.agent.approve(self.t,p['digest'])
        with self.assertRaises(CodingError): self.agent.apply(self.t)
    def test_stale_approval_and_expiry(self):
        self.review(); self.agent.tool(self.t,'edit',{'path':'calc.py','content':'answer=3'})
        with self.assertRaises(CodingError): self.agent.apply(self.t)
        self.agent.test(self.t); p=self.agent.diff(self.t); self.agent.approve(self.t,p['digest'])
        self.t['_approved']=(p['digest'],0)
        with self.assertRaises(CodingError): self.agent.apply(self.t)
    def test_apply_snapshot_and_single_use(self):
        self.review(); r=self.agent.apply(self.t)
        self.assertEqual(r['status'],'applied'); self.assertEqual((self.project/'calc.py').read_text(),'answer = 2\n')
        self.assertEqual((Path(r['rollback_location'])/'calc.py').read_text(),'answer = 1\n')
        with self.assertRaises(CodingError): self.agent.apply(self.t)
    def test_concurrent_target_change_rejected(self):
        self.review(); (self.project/'calc.py').write_text('external change')
        with self.assertRaises(CodingError): self.agent.apply(self.t)
        self.assertEqual((self.project/'calc.py').read_text(),'external change')
    def test_failed_postdeployment_tests_roll_back_and_remove_only_new_files(self):
        self.edit(); self.agent.tool(self.t,'edit',{'path':'new.py','content':'x=1'})
        self.agent.test(self.t); p=self.agent.diff(self.t); self.agent.approve(self.t,p['digest'])
        results=iter([OK,FAIL]); self.agent.runner=lambda *a,**k:dict(next(results))
        with self.assertRaises(CodingError): self.agent.apply(self.t)
        self.assertEqual(self.t['status'],'rolled_back');self.assertFalse((self.project/'new.py').exists())
        self.assertEqual((self.project/'calc.py').read_text(),'answer = 1\n')
    def test_predeployment_failure_never_writes(self):
        self.review(); self.agent.runner=lambda *a,**k:dict(FAIL)
        with self.assertRaises(CodingError): self.agent.apply(self.t)
        self.assertEqual((self.project/'calc.py').read_text(),'answer = 1\n')
    def test_model_has_no_approval_or_dangerous_tools(self):
        for op in ('approve','apply','delete','shell','install','restart','network','admin'):
            with self.assertRaises(CodingError): self.agent.tool(self.t,op,{})
        with self.assertRaises(CodingError): self.agent.test(self.t,'powershell')
    def test_test_result_and_sandbox_failure(self):
        result=self.agent.test(self.t); self.assertEqual(result['stdout'],'ok');self.assertEqual(result['exit_code'],0)
        def broken(*a,**k): raise OSError('sandbox unavailable')
        self.agent.runner=broken
        with self.assertRaises(OSError): self.agent.test(self.t)

    def test_failed_and_zero_test_validation_blocks_finish(self):
        self.agent.tool(self.t,'patch',{'path':'calc.py','old':'1','new':'2'})
        self.agent.runner=lambda *a,**k:dict({**OK,'exit_code':5,'stdout':'Ran 0 tests','stderr':''})
        self.agent.test(self.t)
        result=self.agent.tool(self.t,'finish',{})
        self.assertEqual(result['error'],'validation_required')
        self.assertEqual(self.t['status'],'repair_required')
        self.assertEqual(self.t['status_reason'],'validation_required')
        self.assertTrue(self.t['validation']['needs_revalidation'])
        self.assertFalse(self.t['proposal']['approval_eligible'])
        with self.assertRaisesRegex(CodingError,'^approval_not_available$'):
            self.agent.approve(self.t,self.t['proposal']['digest'])

    def test_passing_validation_is_invalidated_by_later_edit(self):
        self.edit(); self.agent.test(self.t)
        self.assertTrue(self.t['validation']['passed'])
        self.agent.tool(self.t,'edit',{'path':'calc.py','content':'answer = 3\n'})
        result=self.agent.tool(self.t,'finish',{})
        self.assertEqual(result['error'],'validation_required')

    def test_successful_retest_clears_repair_state(self):
        self.edit(); self.agent.runner=lambda *a,**k:dict(FAIL); self.agent.test(self.t)
        self.assertEqual(self.t['validation']['last_exit_code'],1)
        self.assertTrue(self.t['validation']['needs_revalidation'])
        self.agent.runner=lambda *a,**k:dict({**OK,'stdout':'Ran 1 test'})
        self.agent.test(self.t)
        self.assertTrue(self.t['validation']['passed'])
        self.assertFalse(self.t['validation']['needs_revalidation'])
        self.assertEqual(self.agent.tool(self.t,'finish',{})['files'],['calc.py'])
        self.assertEqual(self.t['status'],'approval_needed')

    def test_small_low_risk_oversized_change_is_blocked(self):
        t=self.agent.create('demo',prompt='Find one small, low-risk code-quality issue')
        self.agent.tool(t,'edit',{'path':'calc.py','content':'\n'.join(f'answer = {i}' for i in range(50))+'\n'})
        self.agent.test(t)
        result=self.agent.tool(t,'finish',{})
        self.assertEqual(result['error'],'change_exceeds_requested_scope')
        self.assertEqual(t['status'],'repair_required')
        self.assertEqual(t['status_reason'],'change_exceeds_requested_scope')
        self.assertFalse(t['proposal']['approval_eligible'])
        with self.assertRaisesRegex(CodingError,'^approval_not_available$'):
            self.agent.approve(t,t['proposal']['digest'])

    def test_small_low_risk_sensitive_broad_change_is_blocked(self):
        t=self.agent.create('demo',prompt='Find one small, low-risk code-quality issue')
        self.agent.tool(t,'edit',{'path':'coding_sandbox.py','content':'\n'.join('x = 1' for _ in range(10))+'\n'})
        self.agent.test(t)
        result=self.agent.tool(t,'finish',{})
        self.assertEqual(result['error'],'change_exceeds_requested_scope')
        self.assertEqual(t['status'],'repair_required')

    def test_genuinely_small_validated_change_reaches_approval(self):
        t=self.agent.create('demo',prompt='Find one small, low-risk code-quality issue')
        self.agent.tool(t,'patch',{'path':'calc.py','old':'1','new':'2'})
        self.agent.test(t)
        self.agent.tool(t,'finish',{})
        self.assertEqual(t['status'],'approval_needed')
        self.assertTrue(t['proposal']['approval_eligible'])

    def test_research_read_accounting_survives_diagnostic_reset(self):
        self.agent.runner=lambda *a,**k:dict(FAIL)
        actions=iter([{'tool':'read','args':{'path':'calc.py'}},{'tool':'read','args':{'path':'calc.py'}},
                      {'tool':'test','args':{}},{'tool':'search','args':{'query':'answer'}},
                      {'tool':'read','args':{'path':'calc.py'}},{'tool':'finish','args':{}}])
        self.agent.model_call=lambda *a:next(actions)
        self.agent.agent_loop(self.t)
        self.assertEqual(self.t['research']['reads'],3)
    def test_model_loop(self):
        actions=iter([{'tool':'read','args':{'path':'calc.py'}},{'tool':'patch','args':{'path':'calc.py','old':'1','new':'2'}},{'tool':'test','args':{}},{'tool':'finish','args':{}}])
        self.agent.model_call=lambda *a:next(actions)
        self.agent.agent_loop(self.t)
        self.assertEqual(self.t['status'],'approval_needed');self.assertNotIn('_approved',self.t)

    def test_repeated_identical_action_is_blocked_and_model_recovers(self):
        actions=iter([
            {'tool':'read','args':{'path':'calc.py'}},
            {'tool':'read','args':{'path':'calc.py'}},
            {'tool':'read','args':{'path':'calc.py'}},
            {'tool':'list','args':{}},
            {'tool':'finish','args':{}},
        ])
        calls=[]
        original=self.agent.tool
        def recording_tool(task,op,args):
            calls.append((op,args))
            return original(task,op,args)
        self.agent.tool=recording_tool
        self.agent.model_call=lambda *a:next(actions)
        self.agent.agent_loop(self.t)
        self.assertEqual([op for op,_ in calls],['read','read','finish'])
        blocked=[e for e in self.t['events'] if e['action']=='tool_error' and e.get('error')=='repeated_action_blocked']
        self.assertEqual(len(blocked),1)
        self.assertEqual(self.t['status'],'approval_needed')
    def test_cancel(self):
        self.agent.request({'op':'cancel','id':self.t['id']})
        with self.assertRaises(CodingError): self.agent.tool(self.t,'read',{'path':'calc.py'})
    def test_authenticated_endpoints(self):
        state=State(self.root,provider=lambda _:{});state.coding=self.agent
        server=Server(('127.0.0.1',0),'x'*32,state)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            for method,path,body in [('GET','/v2/coding',None),('GET','/v2/coding/tasks',None),('POST','/v2/coding',json.dumps({'op':'create','project':'demo'}))]:
                for authorized,status in ((False,401),(True,200)):
                    c=http.client.HTTPConnection(*server.server_address,timeout=5)
                    headers={'Content-Type':'application/json'}
                    if authorized: headers['Authorization']='Bearer '+'x'*32
                    c.request(method,path,body,headers);r=c.getresponse();self.assertEqual(r.status,status);r.read();c.close()
        finally: server.shutdown();server.server_close();worker.join()

@unittest.skipUnless(os.environ.get('BELDIN_SANDBOX_TEST')=='1','Windows account integration test; opt in explicitly')
class SandboxIntegration(unittest.TestCase):
    def test_real_isolation_and_captured_output(self):
        from beldin.coding_sandbox import run
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            root=Path(temp); outside=root/'outside.txt';outside.write_text('preserve')
            dev=root/'dev';dev.mkdir()
            code='''import unittest, pathlib, socket, os
class Isolation(unittest.TestCase):
 def test_host_read_denied(self):
  with self.assertRaises(PermissionError): pathlib.Path(OUTSIDE).read_text()
 def test_host_write_denied(self):
  with self.assertRaises(PermissionError): pathlib.Path(OUTSIDE).write_text('changed')
 def test_network_denied(self):
  with self.assertRaises(OSError): socket.create_connection(('127.0.0.1',11434),timeout=2)
 def test_no_token(self): self.assertNotIn('BELDIN_TOKEN',os.environ)
 def test_stderr_stdout(self): print('captured')
'''.replace('OUTSIDE',repr(str(outside)))
            (dev/'test_isolation.py').write_text(code)
            result=run(Path(__file__).parent/'sandbox-python',dev,['unittest','discover','-v'])
            self.assertEqual(result['exit_code'],0,result);self.assertIn('captured',result['stdout'])
            self.assertIn('Ran 5 tests',result['stderr']);self.assertEqual(outside.read_text(),'preserve')
    def test_timeout_and_cancel(self):
        from beldin.coding_sandbox import run
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            dev=Path(temp); (dev/'test_wait.py').write_text('import time\ntime.sleep(30)')
            result=run(Path(__file__).parent/'sandbox-python',dev,['unittest','discover'],timeout=1)
            self.assertEqual(result['status'],'timeout')
            cancel=threading.Event();cancel.set()
            result=run(Path(__file__).parent/'sandbox-python',dev,['unittest','discover'],cancel=cancel)
            self.assertEqual(result['status'],'cancelled')

if __name__=='__main__': unittest.main()
