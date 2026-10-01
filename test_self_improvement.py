import http.client, io, json, tempfile, threading, time, unittest
from pathlib import Path
from beldin.coding import CodingAgent, CodingError
from beldin import languages, mobile
from beldin.server import Server, State, surface_settings

PASS = dict(status='completed', exit_code=0, stdout='', stderr='test_ok (test_calc.T.test_ok) ... ok\n\nRan 1 test in 0.001s\n\nOK\n')
FAIL = dict(status='completed', exit_code=1, stdout='', stderr='FAIL: test_ok\nAssertionError: 1 != 2\n')


def scripted(*turns):
    seq = list(turns); seen = []
    def call(messages, model):
        seen.append(messages)
        return seq.pop(0)
    call.seen = seen
    return call


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.project = root / 'proj'; (self.project / 'beldin').mkdir(parents=True)
        (self.project / 'calc.py').write_text('answer = 1\n')
        (self.project / 'test_calc.py').write_text('import unittest\n')
        (self.project / 'beldin' / 'coding.py').write_text('# authority\n')
        (self.project / 'beldin' / 'feature.py').write_text('x = 1\n')
        self.root = root
    def tearDown(self): self.tmp.cleanup()

    def agent(self, model, runner=None, **cfg):
        a = CodingAgent(self.root / 'svc', projects={'me': {'path': str(self.project), 'production': True, 'self': True}},
                        runner=runner or (lambda *a, **k: dict(PASS)), model_call=model)
        a.max_attempts = cfg.get('max_attempts', 3)
        return a


class SelfBoundaryTests(Base):
    def test_authority_files_are_never_editable_by_beldin(self):
        a = self.agent(scripted()); t = a.create('me')
        for path in ('beldin/coding.py', 'coding-projects.json', 'PERMISSIONS.md', 'test_coding_extra.py', 'setup_local.py'):
            r = a.tool(t, 'edit', {'path': path, 'content': 'x'}) if path != 'coding-projects.json' else None
            if r is not None: self.assertEqual(r['error'], 'authority_boundary_protected', path)
        self.assertEqual(a.tool(t, 'edit', {'path': 'beldin/feature.py', 'content': 'x = 2\n'})['status'], 'edited')

    def test_protected_change_smuggled_into_copy_cannot_be_approved(self):
        a = self.agent(scripted()); t = a.create('me')
        (t['_home'] / 'dev' / 'beldin' / 'coding.py').write_text('# weakened\n')   # bypassing the tool
        a.test(t); r = a.tool(t, 'finish', {})
        self.assertEqual(r['error'], 'authority_boundary_protected')
        with self.assertRaises(CodingError): a.approve(t, t['proposal']['digest'])


class PursueTests(Base):
    EDIT = {'tool': 'edit', 'args': {'path': 'calc.py', 'content': 'answer = 2\n'}}
    def test_keeps_trying_until_validated_then_stops_for_approval(self):
        model = scripted(
            self.EDIT, {'tool': 'finish', 'args': {}},                       # attempt 1: finishes without validating
            {'tool': 'test', 'args': {'command': 'validate'}}, {'tool': 'finish', 'args': {}})   # attempt 2
        a = self.agent(model); t = a.create('me', 'make answer 2')
        a.pursue(t)
        self.assertEqual(t['status'], 'approval_needed')
        self.assertEqual([x['outcome'] for x in t['attempts']], ['failed', 'proposal_ready'])
        self.assertIn('previous attempt', model.seen[-1][1]['content'])
        self.assertIn('Nothing has been applied', t['report']['summary'])
        self.assertEqual((self.project / 'calc.py').read_text(), 'answer = 1\n')   # live project untouched

    def test_gives_up_honestly_and_changes_nothing(self):
        turns = []
        for _ in range(3): turns += [self.EDIT, {'tool': 'test', 'args': {'command': 'validate'}}, {'tool': 'finish', 'args': {}}]
        a = self.agent(scripted(*turns), runner=lambda *x, **k: dict(FAIL)); t = a.create('me', 'make answer 2')
        a.pursue(t)
        self.assertEqual(t['status'], 'needs_human'); self.assertEqual(len(t['attempts']), 3)
        self.assertIn('Nothing was changed', t['report']['summary'])
        with self.assertRaises(CodingError): a.approve(t, 'x')
        self.assertEqual((self.project / 'calc.py').read_text(), 'answer = 1\n')

    def test_an_empty_proposal_is_not_success(self):
        a = self.agent(scripted({'tool': 'finish', 'args': {}}, {'tool': 'finish', 'args': {}}), max_attempts=2)
        t = a.create('me', 'do something'); a.pursue(t)
        self.assertEqual(t['status'], 'needs_human')

    def test_single_attempt_keeps_legacy_behaviour(self):
        a = self.agent(scripted(self.EDIT, {'tool': 'test', 'args': {}}, {'tool': 'finish', 'args': {}}), max_attempts=1)
        t = a.create('me', 'x'); a.pursue(t); self.assertEqual(t['status'], 'approval_needed'); self.assertNotIn('attempts', t)


class LanguageTests(Base):
    def test_registry_detects_many_languages_and_is_honest_about_toolchains(self):
        self.assertEqual(languages.detect(['a.py', 'b.go', 'c.rs', 'd.java', 'e.ts', 'f.rb']),
                         ['python', 'typescript', 'go', 'rust', 'java', 'ruby'])
        avail, missing = languages.commands({}, ['go'])
        self.assertEqual(avail, {}); self.assertTrue(all(m['reason'] == 'toolchain_not_provisioned' for m in missing))
        self.assertGreaterEqual(len(languages.LANGUAGES), 15)

    def test_validate_runs_provisioned_toolchain_in_sandbox_and_counts_as_evidence(self):
        (self.project / 'main.go').write_text('package main\n')
        calls = []
        def runner(runtime, ws, argv, **kw):
            calls.append((argv, kw.get('tool'))); return dict(PASS) if kw.get('tool') is None else dict(status='completed', exit_code=0, stdout='ok', stderr='')
        a = self.agent(scripted(), runner=runner)
        go = str(self.root / 'tools' / 'go.exe')  # native absolute path; runner is mocked
        a.toolchains = {'go': go}
        t = a.create('me', requirements=['main compiles'])
        a.tool(t, 'edit', {'path': 'main.go', 'content': 'package main\nfunc main(){}\n'})
        a.tool(t, 'test', {'command': 'validate'})
        self.assertIn((['vet', './...'], go), calls)
        self.assertIn((['test', './...'], go), calls)
        self.assertNotIn(None, [c[1] for c in calls if c[0][0] == 'vet'])
        r = a.tool(t, 'finish', {'evidence': {'R1': {'files': ['main.go'], 'tests': ['go_vet']}}})
        self.assertEqual(t['status'], 'approval_needed', r)

    def test_unprovisioned_language_cannot_be_claimed_verified(self):
        a = self.agent(scripted()); t = a.create('me')
        with self.assertRaises(CodingError): a.test(t, 'go_vet')

    def test_language_summary_is_exposed(self):
        d = self.agent(scripted()).description()
        self.assertIn('rust', d['languages']); self.assertIn('proficiency', d)


class HumanGateAndSettingsTests(Base):
    def http(self, state, method, path, body=None, approval=None):
        server = Server(('127.0.0.1', 0), 'c' * 40, state, 'a' * 40)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        h = {'Authorization': 'Bearer ' + 'c' * 40, 'Content-Type': 'application/json'}
        if approval: h['X-Beldin-Approval'] = approval
        conn.request(method, path, json.dumps(body) if body is not None else None, h)
        r = conn.getresponse(); data = json.loads(r.read() or b'{}'); conn.close(); return r.status, data

    def test_only_the_human_credential_can_approve_or_apply_a_change(self):
        a = self.agent(scripted()); state = State(self.root / 'svc2', provider=lambda _: {}); state.coding = a
        t = a.create('me')
        for op in ('approve', 'apply'):
            self.assertEqual(self.http(state, 'POST', '/v2/coding', {'op': op, 'id': t['id'], 'digest': 'x'})[0], 403)
            self.assertEqual(self.http(state, 'POST', '/v2/coding', {'op': op, 'id': t['id'], 'digest': 'x'}, 'c' * 40)[0], 403)
        self.assertEqual(self.http(state, 'POST', '/v2/coding', {'op': 'approve', 'id': t['id'], 'digest': 'x'}, 'a' * 40)[0], 409)  # reaches logic

    def test_surface_settings_come_from_valkyrie_and_are_validated(self):
        s = surface_settings({'wake_word': 'Beldin', 'active_timeout': 9999, 'memory_turns': 8, 'barge_in': 'yes', 'evil': 1})
        self.assertEqual(s['memory_turns'], 8); self.assertEqual(s['active_timeout'], 30); self.assertIs(s['barge_in'], False)
        self.assertNotIn('evil', s)
        state = State(self.root / 'svc3', provider=lambda _: {}); state.surface_overrides = {'memory_turns': 9}
        code, body = self.http(state, 'GET', '/v2/surface-config')
        self.assertEqual((code, body['settings']['memory_turns']), (200, 9))


class FakeHandler:
    def __init__(self, state, text, human=False):
        payload = json.dumps({'messages': [{'role': 'user', 'content': text}]}).encode()
        self.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(payload))}
        self.rfile = io.BytesIO(payload); self.server = type('S', (), {'state': state})(); self.out = None
        self.human_approved = lambda: human
    def respond(self, code, obj): self.out = (code, obj)


class ChatTests(Base):
    def test_fix_yourself_starts_a_self_task_and_status_reports_it(self):
        a = self.agent(scripted({'tool': 'finish', 'args': {}}), max_attempts=1)
        state = State(self.root / 'svc4', provider=lambda _: {}); state.coding = a
        h = FakeHandler(state, 'Beldin, fix yourself so the status command lists both models'); mobile.chat(h)
        self.assertIn('Nothing changes until you approve', h.out[1]['message']['content'])
        for _ in range(50):
            if not any(t['_busy'] for t in a.tasks.values()): break
            time.sleep(0.05)
        h2 = FakeHandler(state, '/tasks'); mobile.chat(h2); self.assertIn('Task ', h2.out[1]['message']['content'])

    def test_vague_or_unconfigured_self_request(self):
        a = self.agent(scripted()); state = State(self.root / 'svc5', provider=lambda _: {}); state.coding = a
        h = FakeHandler(state, 'fix yourself'); mobile.chat(h); self.assertIn('Tell me what to change', h.out[1]['message']['content'])
        a.projects['me'].pop('self')
        h = FakeHandler(state, 'fix yourself so that it works well'); mobile.chat(h); self.assertIn('not enabled', h.out[1]['message']['content'])



class ValidationHonestyTests(Base):
    def go_task(self, provisioned=False):
        (self.project / 'main.go').write_text('package main\n')
        a = self.agent(scripted())
        if provisioned: a.toolchains = {'go': str(self.root / 'go.exe')}
        t = a.create('me')
        a.tool(t, 'edit', {'path': 'main.go', 'content': 'package main\nfunc main() {}\n'})
        return a, t

    def test_mixed_unprovisioned_language_is_unverifiable_and_cannot_approve(self):
        a,t = self.go_task()
        r = a.test(t, 'validate')
        self.assertEqual(r['status'], 'UNVERIFIABLE')
        self.assertFalse(t['validation']['passed'])
        self.assertEqual(t['validation']['status'], 'UNVERIFIABLE')
        self.assertEqual(a.tool(t, 'finish', {})['error'], 'validation_required')
        with self.assertRaises(CodingError): a.approve(t, t['proposal']['digest'])

    def test_python_only_run_cannot_validate_changed_go(self):
        for provisioned in (False, True):
            with self.subTest(provisioned=provisioned):
                a,t = self.go_task(provisioned)
                self.assertEqual(a.test(t, 'unittest')['status'], 'UNVERIFIABLE')
                self.assertNotIn('_tested', t)

    def test_go_failure_does_not_leave_approval_evidence(self):
        a,t = self.go_task(True)
        a.test(t, 'validate')
        self.assertTrue(t['validation']['passed'])
        a.runner = lambda *args, **kw: dict(FAIL) if kw.get('tool') else dict(PASS)
        a.test(t, 'validate')
        self.assertFalse(t['validation']['passed'])
        self.assertNotIn('_commands_ok', t)
        self.assertNotIn('_tested', t)

    def test_runner_exception_clears_previous_pass(self):
        a,t = self.go_task(True)
        a.test(t, 'validate')
        def broken(*args, **kw): raise RuntimeError('missing tool')
        a.runner = broken
        with self.assertRaises(RuntimeError): a.test(t, 'validate')
        self.assertFalse(t['validation']['passed'])
        self.assertNotIn('_tested', t)

    def test_go_only_without_toolchain_is_unverifiable(self):
        a,t = self.go_task()
        for p in (t['_home'] / 'dev').rglob('*.py'): p.unlink()
        for p in self.project.rglob('*.py'): p.unlink()
        self.assertEqual(a.test(t, 'validate')['status'], 'UNVERIFIABLE')

    def test_relative_path_is_not_provisioned_or_advertised(self):
        available, missing = languages.commands({'go':'tools/go'}, ['go'])
        self.assertFalse(available)
        self.assertEqual(len(missing), 2)
        self.assertEqual(languages.summary({'go':'tools/go'})['go']['validation'], [])

    def test_validatorless_language_cannot_pass_using_python(self):
        a = self.agent(scripted()); t = a.create('me')
        a.tool(t, 'edit', {'path':'query.sql','content':'select 1;'})
        self.assertEqual(a.test(t, 'validate')['status'], 'UNVERIFIABLE')

    def test_powershell_check_parses_file_instead_of_unconditional_success(self):
        specs,_ = languages.commands({'pwsh':str(self.root / 'pwsh.exe')}, ['powershell'])
        argv, applies = languages.expand(specs['pwsh_check'], ['hello.ps1'])
        self.assertTrue(applies)
        import base64
        script=base64.b64decode(argv[0][2]).decode('utf-16le')
        self.assertIn("ParseFile('hello.ps1'", script)
        self.assertIn('if($errors.Count){exit 1}', script)

if __name__ == '__main__':
    unittest.main()
