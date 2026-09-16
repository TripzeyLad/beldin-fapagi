import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from beldin.routing import route_text, live_state_question, grounded_status
from beldin.mobile import chat

POSITIVE = ["How is Valkyrie?", "How's Valkyrie?", "How is Valkyrie doing?",
            "Is Valkyrie okay?", "Is Valkyrie online?", "What's Valkyrie's status?",
            "How’s Valkyrie doing right now?", "What is Valkyrie's status?",
            "Please check Valkyrie's current health", "Is the Valkyrie node up?",
            "What is Valkyrie's GPU usage now?"]
NEGATIVE = ["What's the weather like on Valkyrie?", "Tell me a story about Valkyrie",
            "Explain Valkyrie mythology", "What was Valkyrie's status yesterday?",
            "Why did you name the machine Valkyrie?", "Write a poem about Valkyrie"]

class GroundingTests(unittest.TestCase):
    def test_status_variants(self):
        for text in POSITIVE:
            with self.subTest(text=text):
                p = route_text(text)
                self.assertEqual(p["tool"], "system_status")
                self.assertFalse(p["model_fallback_allowed"])

    def test_unrelated_mentions(self):
        for text in NEGATIVE:
            with self.subTest(text=text):
                self.assertFalse(live_state_question(text))
                self.assertEqual(route_text(text)["kind"], "chat")

    def state(self, age=0):
        return SimpleNamespace(telemetry=lambda: {"age_seconds": age, "observed": {"cpu": {}}})

    def handler(self, text, state):
        payload=json.dumps({"messages":[
            {"role":"assistant", "content":"RTX 3060 is functioning as expected"},
            {"role":"user", "content":text}]}).encode()
        return SimpleNamespace(headers={"Content-Type":"application/json", "Content-Length":str(len(payload))},
                               rfile=io.BytesIO(payload), server=SimpleNamespace(state=state), respond=Mock())

    def test_model_never_called_for_status_even_with_fabricated_history(self):
        with patch("beldin.mobile.urlopen") as model, patch("beldin.tools.observe", return_value=(200, {"result":{"service":{"status":"running"}}})):
            for text in POSITIVE:
                h=self.handler(text,self.state())
                chat(h)
                speech=h.respond.call_args.args[1]["message"]["content"]
                self.assertIn("service is responding",speech)
                self.assertNotIn("RTX 3060",speech)
                self.assertNotIn("status is normal",speech)
            model.assert_not_called()

    def test_failures_never_fall_back_to_model(self):
        for result in [(503, {}), (200, {"result":{"available":False}}), (200, {"result":None})]:
            with patch("beldin.mobile.urlopen") as model, patch("beldin.tools.observe",return_value=result):
                h=self.handler("How is Valkyrie?",self.state()); chat(h)
                self.assertIn("cannot currently verify",h.respond.call_args.args[1]["message"]["content"])
                model.assert_not_called()
        with patch("beldin.tools.observe",side_effect=TimeoutError):
            self.assertIn("cannot currently verify",grounded_status(self.state()))

    def test_stale_and_missing_observations(self):
        for age in [None, 11, -1, float("nan")]:
            with patch("beldin.tools.observe") as observe:
                self.assertIn("cannot currently verify",grounded_status(self.state(age)))
                observe.assert_not_called()

    def test_weather_keeps_model_path(self):
        with patch("beldin.mobile.urlopen") as model:
            model.return_value.__enter__.return_value.read.return_value=b'{"message":{"content":"Weather response"}}'
            h=self.handler(NEGATIVE[0],self.state()); chat(h)
            model.assert_called_once()
            self.assertEqual(h.respond.call_args.args[1]["message"]["content"],"Weather response")
