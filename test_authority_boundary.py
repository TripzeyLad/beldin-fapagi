import json, tempfile, threading, unittest, http.client
from pathlib import Path
from unittest.mock import patch
from beldin import audit
from beldin.server import Server, State, load_approval_token
from beldin.safe_actions import propose, confirm


class AuthorityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.root = Path(self.t.name)
        self.state = State(self.root, provider=lambda _: {})
    def tearDown(self): self.t.cleanup()

    def http(self, approval_token, header):
        server = Server(('127.0.0.1', 0), 'c' * 40, self.state, approval_token)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        _, o = propose('create_note', {'text': 'hi'}, self.state)
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + 'c' * 40}
        if header: headers['X-Beldin-Approval'] = header
        conn.request('POST', '/v2/actions', json.dumps({'op': 'confirm', 'action_id': o['action_id']}), headers)
        r = conn.getresponse(); status = r.status; r.read(); conn.close()
        return status

    def test_client_token_alone_can_never_confirm(self):
        self.assertEqual(self.http('a' * 40, None), 403)
        self.assertEqual(self.http('a' * 40, 'c' * 40), 403)
        self.assertEqual(self.http(None, 'a' * 40), 403)   # not configured: fail closed
        self.assertFalse(list((self.root / 'notes').glob('**/*.md')) if (self.root / 'notes').exists() else [])

    def test_separate_credential_confirms(self):
        self.assertEqual(self.http('a' * 40, 'a' * 40), 200)

    def test_approval_token_must_differ_and_be_strong(self):
        cfg = self.root / 'c.json'; cfg.write_text(json.dumps({'approval_token': 'same' * 10}))
        with self.assertRaises(ValueError): load_approval_token(cfg, 'same' * 10)
        cfg.write_text(json.dumps({'approval_token': 'short'}))
        with self.assertRaises(ValueError): load_approval_token(cfg, 'x' * 40)
        cfg.write_text(json.dumps({}))
        self.assertIsNone(load_approval_token(cfg, 'x' * 40))

    def test_same_second_backups_and_notes_never_overwrite(self):
        with patch('time.strftime', return_value='20260920-000000'):
            paths = set()
            for _ in range(3):
                _, o = propose('backup_beldin', {}, self.state)
                _, r = confirm(o['action_id'], self.state); paths.add(r['result'].get('path'))
                _, o = propose('create_note', {'text': 'n'}, self.state)
                _, r = confirm(o['action_id'], self.state); paths.add(r.get('path'))
        self.assertEqual(len(paths), 6)

    def test_journal_is_durable_chained_and_fail_closed(self):
        _, o = propose('create_note', {'text': 'n'}, self.state); confirm(o['action_id'], self.state)
        self.assertEqual(audit.verify(self.root), (True, 'intact'))
        log = self.root / 'audit' / 'actions.jsonl'; log.write_text(log.read_text().replace('create_note', 'x'))
        self.assertFalse(audit.verify(self.root)[0])
        _, o = propose('create_note', {'text': 'n'}, self.state)
        with patch('beldin.safe_actions.audit.record', side_effect=audit.AuditError('x')):
            self.assertEqual(confirm(o['action_id'], self.state)[0], 500)


if __name__ == '__main__':
    unittest.main()
