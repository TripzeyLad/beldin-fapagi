"""Small confirmation-gated actions with fixed destinations."""
import hashlib, json, re, secrets, time, subprocess, sys, shutil, zipfile, urllib.request
import copy, uuid
from .desktop_protocol import ACTIONS as DESKTOP_ACTIONS, valid_args
from pathlib import Path
from .secret_policy import denied

ACTION_META = {
 'create_note': {'description':'create a new note in the dedicated notes directory','permission':'SAFE_ACTION','confirmation_required':True},
 'save_diagnostic_snapshot': {'description':'save a bounded current health snapshot','permission':'SAFE_ACTION','confirmation_required':True},
 'run_beldin_tests': {'description':'run the fixed Beldin regression suite with a bounded timeout','permission':'SAFE_ACTION','confirmation_required':True},
 'backup_beldin': {'description':'create a verified timestamped Beldin project backup excluding secrets and caches','permission':'SAFE_ACTION','confirmation_required':True},
 'ollama_model_warmup': {'description':'warm the allowlisted qwen3:8b model without downloading anything','permission':'SAFE_ACTION','confirmation_required':True},
 'open_notepad': {'description':'launch one Beldin-managed Windows Notepad session','permission':'SAFE_ACTION','confirmation_required':True},
 'create_notepad_note': {'description':'place bounded literal text in a Beldin-managed unsaved Notepad note when verified UI support is available','permission':'SAFE_ACTION','confirmation_required':True},
 'close_beldin_notepad': {'description':'close only a verified Beldin-managed Notepad session','permission':'SAFE_ACTION','confirmation_required':True},
}

def _execute_fixed(name, args, state):
    root=Path(state.root)
    if name in DESKTOP_ACTIONS:
        return {'state':'UNAVAILABLE','error':'confirmed_desktop_dispatch_required'}
    if name=='run_beldin_tests':
        try:
            p=subprocess.run([sys.executable,'-m','unittest','discover','-v'],cwd=root,text=True,capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            out=(p.stdout+'\n'+p.stderr).strip()
            return {'status':'passed' if p.returncode==0 else 'failed','returncode':p.returncode,'output':out[-12000:]}
        except subprocess.TimeoutExpired as e: return {'status':'timeout','returncode':None,'output':((e.stdout or '')[-4000:] if isinstance(e.stdout,str) else '')}
    if name=='backup_beldin':
        d=root/'backups'; d.mkdir(exist_ok=True); target=d/('beldin-'+time.strftime('%Y%m%d-%H%M%S')+'.zip')
        excluded={'config.local.json','.env','secrets.json','token.txt'}
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
            for p in root.rglob('*'):
                if not p.is_file() or denied(p.relative_to(root)) or p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) or p.suffix.lower() in {'.log','.pyc','.zip'}: continue
                if p==target: continue
                z.write(p,p.relative_to(root))
        if not target.is_file() or target.stat().st_size>64*1024*1024: return {'status':'failed','error':'backup_verification_failed'}
        with zipfile.ZipFile(target) as z:
            bad=[n for n in z.namelist() if Path(n).name.lower() in excluded]
            if bad: return {'status':'failed','error':'backup_contains_denied_file'}
        return {'status':'verified','path':str(target),'size_bytes':target.stat().st_size}
    if name=='ollama_model_warmup':
        body=json.dumps({'model':'qwen3:8b','prompt':'ping','stream':False,'options':{'num_predict':1},'keep_alive':0}).encode()
        try:
            req=urllib.request.Request('http://127.0.0.1:11434/api/generate',data=body,headers={'Content-Type':'application/json'},method='POST')
            with urllib.request.urlopen(req,timeout=20) as r: data=json.loads(r.read(65536))
            return {'status':'warmed','model':'qwen3:8b','done':bool(data.get('done'))}
        except Exception: return {'status':'failed','error':'ollama_warmup_unavailable'}
    return None

def propose(name, args, state):
    if not isinstance(name,str): return 400, {'error':'invalid_action'}
    if name not in ACTION_META: return 404, {'error':'unknown_action'}
    if not isinstance(args,dict): return 400, {'error':'invalid_input'}
    if name in DESKTOP_ACTIONS:
        from .app_registry import validate
        if getattr(state,'tools_enabled',True) is not True: return 403, {'error':'tools_disabled'}
        if not valid_args(name,args) or not validate('windows_notepad',name,args)[0]:
            return 400, {'error':'invalid_input'}
        health=state.desktop.health()
        if not health.get('online') or health.get('operations',{}).get(name) is not True:
            return 503, {'error':'desktop_operation_unavailable'}
    if name=='create_note' and (set(args)-{'text','title'} or not isinstance(args.get('title','note'),str) or len(args.get('title','note'))>128): return 400, {'error':'invalid_input'}
    if name=='save_diagnostic_snapshot' and args: return 400, {'error':'invalid_input'}
    if name=='create_note' and (not isinstance(args.get('text'),str) or not args['text'].strip() or len(args['text'])>8192): return 400, {'error':'invalid_note'}
    if name in ('run_beldin_tests','backup_beldin','ollama_model_warmup') and args not in ({}, {'model':'qwen3:8b'}): return 400, {'error':'invalid_input'}
    if name=='open_notepad' and args: return 400, {'error':'invalid_input'}
    if name=='create_notepad_note' and (set(args)-{'text'} or not isinstance(args.get('text'),str) or not args['text'].strip() or len(args['text'])>4096): return 400, {'error':'invalid_note'}
    if name=='close_beldin_notepad' and args: return 400, {'error':'invalid_input'}
    action_id=secrets.token_urlsafe(12)
    with state.action_lock:
        for key in list(state.pending_actions):
            if state.pending_actions[key]['expires'] < time.time(): del state.pending_actions[key]
        if len(state.pending_actions)>=128: return 429, {'error':'too_many_pending_actions'}
        invocation_id=uuid.uuid4().hex
        state.pending_actions[action_id]={'name':name,'args':copy.deepcopy(args),'expires':time.time()+60,'invocation_id':invocation_id}; state.action_audit.append({'at_unix':time.time(),'event':'proposed','action_id':action_id,'action':name,'invocation_id':invocation_id})
    sentence={'create_note':'create a new note in the Beldin notes inbox','save_diagnostic_snapshot':'save a timestamped diagnostic snapshot','run_beldin_tests':"run Beldin's fixed regression suite",'backup_beldin':'create a verified Beldin project backup','ollama_model_warmup':'warm the qwen3:8b model without downloading it','open_notepad':'open a Beldin-managed Notepad session','create_notepad_note':'create a bounded unsaved Notepad note','close_beldin_notepad':'close a verified Beldin-managed Notepad session'}[name]
    return 200, {'action_id':action_id,'status':'confirmation_required','expires_in_seconds':60,'summary':sentence}

def cancel(action_id, state):
    if not isinstance(action_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16}',action_id): return 400, {'error':'invalid_action_id'}
    with state.action_lock:
        item=state.pending_actions.pop(action_id,None)
        if not item: return 409, {'error':'confirmation_expired'}
        state.action_audit.append({'at_unix':time.time(),'event':'cancelled','action_id':action_id})
    return 200, {'status':'cancelled'}

def confirm(action_id, state):
    if not isinstance(action_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16}',action_id): return 409, {'error':'confirmation_expired'}
    with state.action_lock:
        item=state.pending_actions.pop(str(action_id),None)
        if not item or item['expires']<time.time():
            state.action_audit.append({'at_unix':time.time(),'event':'expired','action_id':str(action_id)})
            return 409, {'error':'confirmation_expired'}
    root=Path(state.root); root.mkdir(exist_ok=True)
    if item['name'] in DESKTOP_ACTIONS:
        from .app_registry import validate
        started=time.monotonic()
        invocation_id=item['invocation_id']
        if getattr(state,'tools_enabled',True) is not True or not valid_args(item['name'],item['args']) or not validate('windows_notepad',item['name'],item['args'])[0]:
            result={'state':'UNAVAILABLE','error':'desktop_action_disabled'}
        else:
            result=state.desktop.dispatch(item['name'],item['args'],invocation_id)
        with state.action_lock:
            state.action_audit.append({'at_unix':time.time(),'event':'desktop_result','action_id':action_id,
                'invocation_id':invocation_id,'action':item['name'],'adapter':'notepad','permission':'SAFE_ACTION',
                'confirmed':True,'state':result['state'],'verification':result.get('verification',False),
                'duration_ms':round((time.monotonic()-started)*1000)})
        return 200, {'status':result['state'].lower(),'action_id':action_id,'invocation_id':invocation_id,'result':result}
    if item['name']=='create_note':
        d=root/'notes'/'inbox'; d.mkdir(parents=True,exist_ok=True)
        slug=re.sub(r'[^A-Za-z0-9_-]+','-',item['args'].get('title','note')).strip('-')[:48] or 'note'
        path=d/(time.strftime('%Y%m%d-%H%M%S')+'-'+slug+'.md')
        path.write_text(item['args']['text'],encoding='utf-8',newline='\n')
    elif item['name']=='save_diagnostic_snapshot':
        d=root/'diagnostics'; d.mkdir(exist_ok=True); path=d/(time.strftime('%Y%m%d-%H%M%S')+'.json')
        payload={'created_at_unix':time.time(),'telemetry':state.telemetry(),'windows_health':state.windows_health.read()}
        path.write_text(json.dumps(payload,ensure_ascii=True,allow_nan=False,indent=2),encoding='utf-8')
    else:
        result=_execute_fixed(item['name'],item['args'],state)
        if result is None: return 400, {'error':'unsupported_action'}
        with state.action_lock: state.action_audit.append({'at_unix':time.time(),'event':'result','action_id':action_id,'action':item['name'],'status':result.get('status')})
        return 200, {'status':'executed','action_id':action_id,'result':result}
    with state.action_lock: state.action_audit.append({'at_unix':time.time(),'event':'executed','action_id':action_id,'action':item['name']})
    return 200, {'status':'executed','action_id':action_id,'path':str(path)}
