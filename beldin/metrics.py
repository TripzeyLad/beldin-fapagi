import ctypes
import csv
import io
import json
import os
import platform
import shutil
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def unavailable(reason='unavailable'):
    return {'available': False, 'data': None, 'reason': reason}


def observed(data):
    return {'available': True, 'data': data}


def ram():
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in ('total', 'free', 'page_total', 'page_free', 'virtual_total', 'virtual_free', 'extended')]
    try:
        m = Memory(); m.length = ctypes.sizeof(m)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return unavailable()
        return observed({'total_bytes': m.total, 'available_bytes': m.free, 'used_percent': m.load})
    except (AttributeError, OSError):
        return unavailable()


def cpu():
    def sample():
        values = [ctypes.c_ulonglong() for _ in range(3)]
        if not ctypes.windll.kernel32.GetSystemTimes(*(ctypes.byref(v) for v in values)):
            raise OSError()
        return [v.value for v in values]
    try:
        a = sample(); time.sleep(.1); b = sample()
        idle, kernel, user = [y-x for x,y in zip(a,b)]
        total = kernel + user
        return observed({'logical_processors': os.cpu_count(), 'used_percent': round(100*(total-idle)/total, 2) if total else None, 'sample_seconds': .1})
    except (AttributeError, OSError):
        return unavailable()


def disk(path):
    try:
        d = shutil.disk_usage(path)
        return observed({'total_bytes': d.total, 'free_bytes': d.free, 'used_percent': round(100*d.used/d.total, 2), 'health': None, 'health_reason': 'Physical drive health not queried'})
    except OSError:
        return unavailable('disk_access_failed')


def gpu():
    executable = shutil.which('nvidia-smi')
    if not executable:
        return unavailable('nvidia_smi_missing')
    try:
        p = subprocess.run([executable, '--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=1.5, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if p.returncode: return unavailable('nvidia_smi_failed')
        rows = []
        for row in list(csv.reader(io.StringIO(p.stdout)))[:8]:
            name, driver, total, used, util, temp = [s.strip() for s in row]
            def number(s):
                try: return float(s)
                except ValueError: return None
            rows.append(dict(name=name, driver_version=driver, total_mib=number(total), used_mib=number(used), utilization_percent=number(util), temperature_c=number(temp)))
        return observed(rows)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return unavailable('nvidia_smi_failed_or_timed_out')


def ollama_get(path):
    # Fixed upstream and fixed routes: no client-directed URL or proxy use.
    if path not in ('version', 'tags', 'ps'): return unavailable('invalid_route')
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:11434/api/' + path, timeout=.6) as r:
            data = r.read(262145)
            if len(data) > 262144: return unavailable('response_too_large')
            obj = json.loads(data)
            if not isinstance(obj, dict): return unavailable('invalid_response')
            if path == 'version': return observed({'version': obj.get('version')})
            models = obj.get('models')
            if not isinstance(models, list): return unavailable('invalid_response')
            return observed({'models': [{k:m.get(k) for k in ('name','model','size','size_vram','expires_at','context_length')} for m in models[:64] if isinstance(m, dict)]})
    except Exception:
        return unavailable('upstream_failed_or_timed_out')


def ollama():
    with ThreadPoolExecutor(max_workers=3) as pool:
        values = list(pool.map(ollama_get, ('version','tags','ps')))
    return dict(zip(('version','installed','running'), values))


def snapshot(path):
    with ThreadPoolExecutor(max_workers=5) as pool:
        jobs = {k: pool.submit(f) for k,f in {'cpu':cpu, 'ram':ram, 'disk':lambda:disk(path), 'gpu':gpu, 'ollama':ollama}.items()}
        result = {k:v.result() for k,v in jobs.items()}
    result['os'] = {'system': platform.system(), 'version': platform.version(), 'machine': platform.machine()}
    try:
        ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        result['system_uptime_seconds'] = ctypes.windll.kernel32.GetTickCount64()/1000
    except AttributeError: result['system_uptime_seconds'] = None
    return result
