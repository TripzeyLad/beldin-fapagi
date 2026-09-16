"""Bounded, local-first observation tools for the v2 contract."""
import csv, json, os, platform, re, shutil, socket, subprocess, time
from pathlib import Path
from .secret_policy import denied

MAX_TEXT = 64 * 1024
PROJECT_ROOTS = ('beldin', 'outputs', 'work')
DENY_NAMES = {'config.local.json', '.env', 'secrets.json', 'token.txt'}
SERVICES = {'ollama': 'Ollama', 'beldin': 'Beldin'}

def _result(data=None, reason=None):
    r = {'available': reason is None, 'data': data if reason is None else None}
    if reason: r['reason'] = reason
    return r

def system_status(state):
    t = state.telemetry()['observed'] or {}
    return {'platform': platform.platform(), 'cpu': t.get('cpu'), 'ram': t.get('ram'), 'gpu': t.get('gpu'), 'disk': t.get('disk'), 'ollama': t.get('ollama'), 'service': {'status':'running','uptime_seconds':round(time.monotonic()-state.started,1)}}

def process_summary(name=None):
    try:
        rows=[]
        for line in subprocess.check_output(['tasklist','/FO','CSV','/NH'], text=True, timeout=2, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).splitlines()[:512]:
            parts=[]
            try: parts=next(csv.reader([line]))
            except Exception: continue
            if len(parts)>=5 and (not name or name.lower() in parts[0].lower()): rows.append({'name':parts[0][:128],'pid':int(parts[1]) if parts[1].isdigit() else None,'memory':parts[4][:32]})
        return _result(rows[:32])
    except Exception: return _result(reason='process_inventory_unavailable')

def service_status(name):
    key=str(name or '').lower()
    if key not in SERVICES: return _result(reason='service_not_allowlisted')
    try:
        out=subprocess.check_output(['sc.exe','query',SERVICES[key]], text=True, stderr=subprocess.DEVNULL, timeout=2, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        state=re.search(r'STATE\s+:\s+\d+\s+(\w+)',out)
        return _result({'name':SERVICES[key], 'state':state.group(1) if state else 'UNKNOWN'})
    except Exception: return _result(reason='service_query_unavailable')

def port_status(host='127.0.0.1', port=8765):
    allowed={'127.0.0.1','localhost','192.0.2.10'}
    if host not in allowed or type(port) is not int or port not in {8765,11434}: return _result(reason='endpoint_not_allowlisted')
    try:
        with socket.create_connection((host,port),timeout=.8): return _result({'host':host,'port':port,'reachable':True})
    except OSError: return _result({'host':host,'port':port,'reachable':False})

def file_info(root, relative):
    p=_safe_path(root,relative)
    if not p: return _result(reason='path_not_allowlisted')
    try:
        st=p.stat(); return _result({'path':str(p),'size':st.st_size,'modified_unix':st.st_mtime,'is_file':p.is_file(),'is_dir':p.is_dir()})
    except OSError: return _result(reason='file_unavailable')

def read_text(root, relative):
    p=_safe_path(root,relative)
    if not p or p.name.lower() in DENY_NAMES or not p.is_file(): return _result(reason='file_not_readable')
    try:
        if p.stat().st_size>MAX_TEXT: return _result(reason='file_too_large')
        return _result({'path':str(p),'text':p.read_text(encoding='utf-8')})
    except (OSError,UnicodeError): return _result(reason='text_unavailable')

def _safe_path(root, relative):
    base=Path(root).resolve(); rel=Path(str(relative))
    if rel.is_absolute() or '..' in rel.parts: return None
    p=(base/rel).resolve()
    try: p.relative_to(base)
    except ValueError: return None
    if denied(rel) or denied(p.relative_to(base)): return None
    return p

TOOLS = {
 'node_status': {'description':'latest recorded node metadata with freshness','permission':'OBSERVE','side_effect':'none','timeout_ms':500},
 'action_history': {'description':'bounded sanitized in-memory action history','permission':'OBSERVE','side_effect':'none','timeout_ms':500},
 'system_status': {'description':'bounded CPU, memory, GPU, disk, Ollama and service summary','permission':'OBSERVE','timeout_ms':2500,'side_effect':'none'},
 'process_summary': {'description':'bounded named process inventory','permission':'OBSERVE','timeout_ms':2500,'side_effect':'none'},
 'service_status': {'description':'allowlisted service state','permission':'OBSERVE','timeout_ms':2500,'side_effect':'none'},
 'port_status': {'description':'allowlisted local endpoint reachability','permission':'OBSERVE','timeout_ms':1000,'side_effect':'none'},
 'file_info': {'description':'allowlisted project file metadata','permission':'OBSERVE','timeout_ms':500,'side_effect':'none'},
 'read_text': {'description':'bounded allowlisted UTF-8 text read','permission':'OBSERVE','timeout_ms':500,'side_effect':'none'},
 'windows_health': {'description':'cached aggregate Windows critical/error summary','permission':'OBSERVE','timeout_ms':500,'side_effect':'none'},
 'ollama_status': {'description':'Ollama daemon and model availability','permission':'OBSERVE','timeout_ms':1000,'side_effect':'none'},
 'project_status': {'description':'Beldin project and test files summary','permission':'OBSERVE','timeout_ms':500,'side_effect':'none'},
}

def observe(name, args, state):
    if name not in TOOLS: return 404, {'error':'unknown_tool'}
    if name in ('node_status','action_history'):
        return state.route('/v2/node' if name=='node_status' else '/v2/action-history')
    args=args if isinstance(args,dict) else {}
    if name=='system_status': data=system_status(state)
    elif name=='process_summary': data=process_summary(args.get('name'))
    elif name=='service_status': data=service_status(args.get('name'))
    elif name=='port_status': data=port_status(args.get('host','127.0.0.1'),args.get('port',8765))
    elif name in ('file_info','read_text'): data=globals()[name](state.root,args.get('path',''))
    elif name=='windows_health': data=state.windows_health.read()
    elif name=='ollama_status': data=(state.telemetry()['observed'] or {}).get('ollama',_result(reason='not_sampled'))
    else:
        root=Path(state.root); data=_result({'root':str(root),'tests':len(list(root.glob('test_*.py'))),'config_present':(root/'config.local.json').exists()})
    return 200, {'tool':name,'result':data}
