import unittest
from beldin.diagnostics import assess
from beldin.server import State

class DiagnosticTests(unittest.TestCase):
    def data(self):
        return {'age_seconds':0,'observed':{**{k:{'available':True,'data':{'used_percent':10}} for k in ('cpu','ram','disk')},'gpu':{'available':True,'data':[{'used_mib':1,'total_mib':10,'temperature_c':50}]},'ollama':{'version':{'available':True}}}}
    def test_healthy(self): self.assertEqual(assess(self.data())['status'],'ok')
    def test_unknown_not_zero(self): self.assertEqual(assess({'age_seconds':0})['status'],'unknown')
    def test_stale(self):
        d=self.data(); d['age_seconds']=11; self.assertEqual(assess(d)['status'],'stale')
    def test_cpu_threshold(self):
        d=self.data(); d['observed']['cpu']['data']['used_percent']=90; self.assertEqual(assess(d)['status'],'pressure')
    def test_gpu_temperature(self):
        d=self.data(); d['observed']['gpu']['data'][0]['temperature_c']=85; self.assertEqual(assess(d)['status'],'pressure')
    def test_retention(self):
        s=State('.')
        for i in range(200): s.record_latency(.01)
        self.assertEqual(len(s.latencies),128)
    def test_no_process_arguments(self): self.assertNotIn('command_line',str(State('.').route('/v1/diagnostics')))
