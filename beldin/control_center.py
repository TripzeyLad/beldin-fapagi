"""Bounded authenticated control operations; fixed, verified reload executor."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from .metrics import ollama_get

PRODUCTION_ROOT = Path(r'C:\Users\BELDIN_USER\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an\outputs\valkyrie-beldin')
RELOAD_SCRIPT = Path(r'C:\Users\BELDIN_USER\Documents\Codex\2026-09-12\continue-the-beldin-project-from-the\outputs\BELDIN_VERIFIED_RELOAD.ps1')
RELOAD_SHA256 = 'fee8fab1c997c40afd64b7d7f63fce97949605e0715fbc1b15ed7418f26c8e4e'
POWERSHELL = Path(r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')
ACTION_ENDPOINT = '/v2/control-center/action'

def verified_reload(root):
    try:
        return (os.name == 'nt' and Path(root).resolve() == PRODUCTION_ROOT.resolve()
                and POWERSHELL.is_file()
                and hashlib.sha256(RELOAD_SCRIPT.read_bytes()).hexdigest() == RELOAD_SHA256)
    except OSError:
        return False

def record_path(root):
    return Path(root) / 'runtime' / 'control-reload.json'

def write_record(root, record):
    path = record_path(root)
    path.parent.mkdir(exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(record), encoding='utf-8')
    temp.replace(path)

def read_record(root):
    try:
        raw = record_path(root).read_bytes()
        if len(raw) > 4096: return None
        record = json.loads(raw)
        if not isinstance(record, dict): return None
        safe = {k: record[k] for k in ('id','status','started_at_unix','finished_at_unix','old_pid','new_pid','error') if k in record}
        if safe.get('status') in ('accepted','running') and time.time() - safe.get('started_at_unix', 0) > 90:
            safe.update(status='failed', error='reload_result_timeout')
        return safe
    except (OSError, ValueError, TypeError):
        return None

class Controls:
    def __init__(self, state):
        self.state = state
        self.lock = threading.RLock()
        self.challenges = {}
        self.active_chats = 0
        self.instance_id = secrets.token_hex(16)

    def metadata(self):
        enabled = verified_reload(self.state.root)
        def item(id, label, available=True, reason='', permission='OBSERVE', endpoint=ACTION_ENDPOINT):
            return dict(id=id, label=label, available=available, reason=reason,
                        permission=permission, confirmation_required=permission=='SERVICE_CHANGE', endpoint=endpoint)
        return [
            item('refresh_status','Refresh status'),
            item('reload_beldin','Reload Beldin',enabled,'Verified reload script unavailable or changed' if not enabled else '', 'SERVICE_CHANGE'),
            item('restart_gateway','Restart gateway',False,'Use Reload Beldin: Beldin is the gateway', 'SERVICE_CHANGE'),
            item('restart_ollama','Restart Ollama',False,'Unavailable: no verified Ollama restart executor', 'SERVICE_CHANGE'),
            item('rescan_models','Rescan models'),
            item('retry_task','Retry task',False,'Staged: no executable task queue','SAFE_ACTION'),
            item('cancel_task','Cancel task',False,'Staged: no executable task queue','SAFE_ACTION'),
            item('view_logs','View event log',endpoint='/v2/control-center/logs'),
            item('view_activity','View activity details',endpoint='/v2/control-center/activity'),
            item('view_script','View current script',False,'Staged: no script execution tracker'),
        ]

    def audit(self, action, status):
        with self.state.action_lock:
            self.state.action_audit.append(dict(at_unix=time.time(), event='control_result', action=action, status=status))

    def logs(self):
        with self.state.lock: events = list(self.state.events)[-32:]
        with self.state.action_lock: actions = list(self.state.action_audit)[-64:]
        return dict(api_version='2', available=True, kind='bounded_event_and_action_metadata',
                    events=events, actions=actions, reload=read_record(self.state.root),
                    raw_logs_available=False, reset_on_restart=True,
                    reason='Event/action metadata only. Chat contents and raw process output are not retained.')

    def activity(self):
        with self.lock: chats = self.active_chats
        return dict(api_version='2', active_chat_requests=chats,
                    current=[dict(action='chat', count=chats, endpoint='/v1/chat')] if chats else [],
                    reload=read_record(self.state.root),
                    script_tracking_available=False, command_tracking_available=False,
                    reason='No script or command execution tracker is installed.')

    def busy_reload(self):
        record = read_record(self.state.root)
        return record and record.get('status') in ('accepted','running')

    def execute(self, body):
        if (not isinstance(body, dict) or set(body)-{'action','op','confirmation_id'}
                or not isinstance(body.get('action'), str)):
            return 400, {'error':'invalid_control_request'}
        action = body['action']
        meta = next((x for x in self.metadata() if x['id']==action), None)
        if not meta: return 404, {'error':'unknown_control'}
        if not meta['available']: return 403, {'error':'control_unavailable','reason':meta['reason']}
        if action != 'reload_beldin':
            if set(body) != {'action'}: return 400, {'error':'invalid_control_request'}
            if action == 'refresh_status':
                try:
                    if not self.state.refresh(): return 409, {'error':'refresh_in_progress'}
                except Exception:
                    self.audit(action, 'failed')
                    return 503, {'error':'status_refresh_failed'}
                self.audit(action,'completed')
                return 200, dict(status='completed', sampled_at_unix=self.state.sampled)
            if action == 'rescan_models':
                models = ollama_get('tags')
                self.audit(action,'completed' if models['available'] else 'failed')
                return (200 if models['available'] else 503), dict(status='completed' if models['available'] else 'failed', models=models)
            return 405, {'error':'use_read_endpoint'}
        with self.lock:
            if any(t.get('_busy') for t in getattr(self.state,'coding',None).tasks.values()) if getattr(self.state,'coding',None) else False:
                return 409, {'error':'coding_task_in_progress'}
            if self.active_chats: return 409, {'error':'chat_in_progress'}
            if self.busy_reload(): return 409, {'error':'reload_in_progress'}
            now = time.time()
            self.challenges = {k:v for k,v in self.challenges.items() if v > now}
            if body.get('op') == 'propose' and set(body)=={'action','op'}:
                if len(self.challenges) >= 16: return 429, {'error':'too_many_confirmations'}
                challenge = secrets.token_hex(16)
                self.challenges[challenge] = now + 60
                return 200, dict(status='confirmation_required', permission='SERVICE_CHANGE', confirmation_id=challenge,
                                 expires_in_seconds=60, summary='Reload only Beldin through its verified external supervisor script. The page reconnects automatically.')
            if body.get('op') == 'cancel' and set(body)=={'action','op','confirmation_id'}:
                key = body.get('confirmation_id')
                if not isinstance(key,str): return 400, {'error':'invalid_confirmation'}
                if self.challenges.pop(key,None) is None: return 409, {'error':'confirmation_expired'}
                return 200, {'status':'cancelled'}
            if body.get('op') != 'confirm' or set(body)!={'action','op','confirmation_id'}:
                return 409, {'error':'confirmation_required'}
            key = body.get('confirmation_id')
            if not isinstance(key,str) or self.challenges.pop(key,None) is None:
                return 409, {'error':'confirmation_expired'}
            # One-use confirmation consumed before launching anything.
            record = dict(id=secrets.token_hex(16), status='accepted', started_at_unix=now, old_pid=os.getpid())
            try:
                write_record(self.state.root, record)
                env = os.environ.copy()
                env.pop('BELDIN_TOKEN', None)
                subprocess.Popen([sys.executable,'-B','-m','beldin.reload_worker',record['id']],
                                 cwd=self.state.root, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                                 creationflags=getattr(subprocess,'DETACHED_PROCESS',0)|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
            except OSError:
                record.update(status='failed', error='reload_helper_launch_failed')
                try: write_record(self.state.root, record)
                except OSError: pass
                return 503, {'error':'reload_helper_launch_failed'}
            self.audit(action, 'accepted')
            return 202, dict(status='accepted', operation_id=record['id'], instance_id=self.instance_id)

def run_reload(root, operation_id):
    """Runs outside the HTTP service. Never accepts a path or command from a request."""
    record = read_record(root)
    if not record or record.get('id') != operation_id or record.get('status')!='accepted': return
    time.sleep(2)  # Let the HTTP acceptance response leave before stopping Beldin.
    try:
        if not verified_reload(root): raise ValueError('unverified')
        record['status'] = 'running'
        write_record(root, record)
        proc = subprocess.run([str(POWERSHELL),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(RELOAD_SCRIPT)],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=55,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        match = re.search(r'Verified Beldin reload: (\d+) -> (\d+)', proc.stdout or '')
        if proc.returncode != 0 or not match or int(match[1]) != record['old_pid'] or match[1] == match[2]:
            raise ValueError('not_verified')
        record.update(status='completed', new_pid=int(match[2]))
    except Exception:
        record.update(status='failed', error='verified_reload_failed')
    record['finished_at_unix'] = time.time()
    write_record(root, record)
