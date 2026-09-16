"""Bounded Qwen validation under GPU contention; no persistent tuning."""
import json
from pathlib import Path
import time
import urllib.request
from beldin.metrics import gpu, ollama_get

root=Path(__file__).resolve().parent
result={'gpu_before':gpu(),'running_before':ollama_get('ps'),'trials':[], 'adopted_changes':[]}
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for _ in range(3):
    start=time.perf_counter(); value=ollama_get('version')
    result.setdefault('version_latency_seconds',[]).append({'seconds':time.perf_counter()-start,'available':value['available']})
running=result['running_before']
if not running['available'] or running['data']['models']:
    result['deferred']='Existing model session or unknown running state; do not change its runtime.'
else:
    # GPU memory is already occupied by other work. Use two CPU threads to
    # confirm inference without competing for scarce GPU memory.
    prompts=['Reply with exactly: Beldin ready.',
             'You are Beldin. Use only these observations. CPU utilization 52 percent. RAM available 14 GB. GPU VRAM used 10.7 of 12 GB. Ollama API reachable. No running model. Disk free 43 GB. Explain the most likely constraint for loading an 8-billion parameter assistant model in one short sentence. Do not invent metrics or recommend changing system settings.']
    for prompt in prompts:
        payload={'model':'qwen3:8b','prompt':prompt,'stream':False,'think':False,'keep_alive':0,
                 'options':{'temperature':0,'seed':42,'num_predict':16,'num_ctx':2048,'num_thread':2,'num_gpu':0}}
        start=time.perf_counter()
        try:
            request=urllib.request.Request('http://127.0.0.1:11434/api/generate',json.dumps(payload).encode(),{'Content-Type':'application/json'})
            with opener.open(request,timeout=35) as r:
                raw=r.read(65537)
                if len(raw)>65536: raise ValueError('oversized_response')
                d=json.loads(raw)
            trial={k:d.get(k) for k in ('done','done_reason','total_duration','load_duration','prompt_eval_count','prompt_eval_duration','eval_count','eval_duration')}
            trial['wall_seconds']=time.perf_counter()-start
            trial['tokens_per_second']=d.get('eval_count',0)*1e9/d['eval_duration'] if d.get('eval_duration') else None
            trial['response_nonempty']=bool(d.get('response'))
            trial['mode']='CPU only, 2 threads, 16-token cap, context 2048, thinking off, unload after request'
            result['trials'].append(trial)
        except Exception as e:
            result['trials'].append({'error':type(e).__name__,'wall_seconds':time.perf_counter()-start})
            break
result['gpu_after']=gpu(); result['running_after']=ollama_get('ps')
result['interpretation']='CPU fallback smoke timings under existing GPU contention, not representative GPU voice latency. GPU comparison and persistent tuning deferred until VRAM is available. No other installed model was available.'
(root/'MODEL_BENCHMARK.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
