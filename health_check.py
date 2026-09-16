import json
from pathlib import Path
import sys
import urllib.request
from beldin.server import load_config
from beldin.metrics import ollama_get

host,port,token=load_config(Path(__file__).resolve().parent/'config.local.json')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
failures=[]
for path in ('health','telemetry','diagnostics','capabilities','events'):
    try:
        req=urllib.request.Request(f'http://{host}:{port}/v1/{path}',headers={'Authorization':'Bearer '+token})
        with opener.open(req,timeout=3) as r: data=json.load(r)
        assert data['api_version']=='1'
        if path=='telemetry': assert data['observed'] is not None and data['age_seconds']<10
        print(path+': OK')
    except Exception:
        failures.append(path); print(path+': FAILED')
try:
    opener.open(f'http://{host}:{port}/v1/health',timeout=3)
    failures.append('authentication')
except urllib.error.HTTPError as e:
    if e.code!=401: failures.append('authentication')
except Exception: failures.append('authentication')
ol=ollama_get('tags')
ok=ol['available'] and any(m['name']=='qwen3:8b' for m in ol['data']['models'])
print('qwen3:8b installed: '+str(ok))
if not ok: failures.append('qwen3')
sys.exit(bool(failures))
