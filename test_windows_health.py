import json
import unittest
from beldin.windows_health import HealthCache, sanitize
from beldin.server import State

class WindowsHealthTests(unittest.TestCase):
    def test_no_query_on_request(self):
        cache=HealthCache(lambda: self.fail("request must not invoke provider"))
        self.assertIsNone(cache.read()["observed"])
    def test_provider_failure_redacted(self):
        def fail(): raise RuntimeError("secret path token")
        cache=HealthCache(fail); cache.refresh()
        self.assertNotIn("secret", json.dumps(cache.read()))
        self.assertFalse(cache.read()["observed"]["logs"]["System"]["available"])
    def test_raw_fields_removed(self):
        data=sanitize({"logs":{"System":{"available":True,"sampled_events":1,
            "groups":[{"source":"Service Control Manager","event_id":7023,"count":1,"message":"secret"}],
            "message":"secret"}}})
        self.assertNotIn("secret",json.dumps(data))
        self.assertEqual(data["logs"]["System"]["groups"][0]["count"],1)
    def test_bounds(self):
        data=sanitize({"logs":{"System":{"available":True,"sampled_events":99999,
            "groups":[{"source":"valid","event_id":1,"count":1}]*100}}})
        self.assertEqual(len(data["logs"]["System"]["groups"]),40)
        self.assertEqual(data["logs"]["System"]["sampled_events"],2000)
    def test_reject_bad_source(self):
        data=sanitize({"logs":{"System":{"available":True,
            "groups":[{"source":"C:\\private\\file","event_id":1,"count":1}]}}})
        self.assertEqual(data["logs"]["System"]["groups"],[])
    def test_capability(self):
        s=State(".")
        self.assertEqual(s.route("/v1/windows_health")[0],200)
        self.assertTrue(any(x["name"]=="windows_health" and x["permission"]=="OBSERVE"
                            for x in s.route("/v1/capabilities")[1]["observations"]))
    def test_refresh_timestamp(self):
        cache=HealthCache(lambda: {}); cache.refresh()
        self.assertIsNotNone(cache.read()["sampled_at_unix"])
        self.assertLess(cache.read()["age_seconds"],5)
