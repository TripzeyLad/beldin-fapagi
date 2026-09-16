"""Opt-in real production-model semantic checks; no canned response mocks."""
import json
import os
from pathlib import Path
import unittest
import urllib.request

CASES = {
    "general": ["Who are you?", "What are you?", "What's your name?",
                "Tell me about yourself.", "Introduce yourself."],
    "creator": ["Who made you?", "Who built you?", "Who built Beldin?", "Who created you?"],
    "model": ["What model are you using?", "What LLM do you use?", "What's under the hood?"],
    "distinction": ["Are you Qwen?"],
    "provenance": ["Who developed Qwen?", "Who made the model you're using?"],
    "ordinary": ["Give me one practical tip for organizing my day."]
}

class IdentityPolicyTests(unittest.TestCase):
    def test_canonical_hierarchy(self):
        text=(Path(__file__).parent/'BELDIN_IDENTITY.md').read_text(encoding='utf-8')
        self.assertIn('Public creator alias:', text)
        self.assertIn('Changing that component does not change', text)
        self.assertIn('Technical self-knowledge', text)

    def test_admin_alias_is_private(self):
        root=Path(__file__).parent
        meta=json.loads((root/'config.creator.json').read_text())
        from beldin.identity import context
        from beldin.secret_policy import denied
        self.assertNotIn(meta['developer_admin_alias'],context([])[0]['content'])
        self.assertTrue(denied('config.creator.json'))

    @unittest.skipUnless(os.environ.get('BELDIN_LIVE_IDENTITY_TEST')=='1', 'opt-in live inference')
    def test_live_semantics(self):
        root=Path(__file__).parent
        identity=(root/'BELDIN_IDENTITY.md').read_text(encoding='utf-8')
        public_alias=next(line.split(':',1)[1].strip() for line in identity.splitlines() if line.startswith('Public creator alias:'))
        admin_alias=json.loads((root/'config.creator.json').read_text())['developer_admin_alias']
        token=json.loads((root/'config.local.json').read_text())['token']
        base=os.environ.get('BELDIN_TEST_BASE','http://127.0.0.1:8765')
        for kind, questions in CASES.items():
            for question in questions:
                with self.subTest(kind=kind, question=question):
                    body=json.dumps({'messages':[{'role':'user','content':question}]}).encode()
                    req=urllib.request.Request(base+'/v1/chat',data=body,
                        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
                    with urllib.request.urlopen(req,timeout=55) as response:
                        answer=json.load(response)['message']['content']
                    text=answer.casefold()
                    if kind in ('general','creator','ordinary'):
                        for word in ('qwen','alibaba','ollama','foundation model','base model','inference engine','backend provider'):
                            self.assertNotIn(word,text)
                    if kind=='general': self.assertIn('beldin',text)
                    if kind=='creator': self.assertIn(public_alias.casefold(),text)
                    self.assertNotIn(admin_alias.casefold(),text)
                    if kind in ('model','distinction'):
                        self.assertIn('qwen',text)
                        self.assertIn('model',text)
                    if kind=='distinction': self.assertIn('beldin',text)
                    if kind=='provenance': self.assertIn('alibaba',text)
                    print(json.dumps({'question':question,'semantic_checks':'passed'}))
