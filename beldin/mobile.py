import hashlib
import json
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from .routing import live_state_question, grounded_status
from .identity import context, speech

ROOT = Path(__file__).parent / 'mobile'
ASSETS = {
    '/app': ('index.html', 'text/html; charset=utf-8'),
    '/app/': ('index.html', 'text/html; charset=utf-8'),
    '/app/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/app/manifest.json': ('manifest.json', 'application/manifest+json'),
    '/app/sw.js': ('sw.js', 'text/javascript; charset=utf-8'),
}

def asset(path):
    item = ASSETS.get(path)
    if not item: return None
    name, content_type = item
    return (ROOT / name).read_bytes(), content_type

# ---------------------------------------------------------------------------------------------
# Entry points into the real coding pipeline
#
# 1. Exact shortcuts (/self, /code, /tasks, "fix yourself ...") start or report immediately.
# 2. Anything else that *reads like* a coding task is turned into a PROPOSAL the human must
#    confirm ("yes" / "begin now"). Misrouting is therefore harmless: a wrong guess costs one
#    "cancel". Confirming only starts a sandboxed task; approve/apply stay on the separate
#    human approval channel (server.py), exactly as before.
# 3. Continuations ("begin now") are resolved against the stored proposal, never against chat
#    prose, so they can no longer be read as "keep narrating a fake run".
# ---------------------------------------------------------------------------------------------
SELF_REQUEST=re.compile(r"^(?:please\s+|beldin,?\s+)?(?:fix|change|update|improve|modify|upgrade|extend|refactor)\s+(?:yourself|your\s+(?:own\s+)?(?:code|source|system))\b[\s,:;-]*(.*)$",re.I)
TASK_STATUS=re.compile(r"\b(?:coding|self[- ]?change|self[- ]?improvement)\s+(?:task\s+)?status\b|how(?:'s| is) (?:the |that )?(?:self[- ]?change|coding task)",re.I)

CODE_VERB=re.compile(r"\b(?:fix|change|update|improve|modify|upgrade|extend|refactor|add|build|implement\w*|create|make|design\w*|develop\w*|write|teach|enable|allow|let|test\w*|investigat\w*)\b",re.I)
SELF_TARGET=re.compile(r"\b(?:yourself|your\s+(?:own\s+)?(?:code|source|system|tools?|abilit\w+|capabilit\w+|config\w*|voice|endpoints?))\b",re.I)
CODING_ENV=re.compile(r"\b(?:coding|self[- ]?improvement)(?:\s*/\s*(?:coding|self[- ]?improvement))?\s+(?:environment|sandbox|pipeline|system)\b",re.I)
CAPABILITY_QUESTION=re.compile(r"\b(?:toy\s*box|your\s+tools|what\s+tools\s+do\s+you\s+have|(?:what|which)\s+coding\s+(?:abilities|commands)|how\s+do\s+i\s+(?:give|ask)\s+you\s+(?:a\s+)?(?:coding\s+)?task)\b",re.I)
RAN_CHECK=re.compile(r"\b(?:did\s+you\s+(?:actually|really|even)\s+(?:run|simulate|test|execute|do)|(?:are|were)\s+you\s+(?:bullshitting|lying|faking|making\s+(?:it|that|this)\s+up)|(?:was|is)\s+that\s+(?:real|fake|made\s+up))\b",re.I)

YES_WORDS=('yes','yes please','y','yep','yeah','ok','okay','sure','confirm','confirmed','approved')
NO_WORDS=('no','cancel','nevermind','never mind','stop','abort')
TASK_MARK=re.compile(r"\[task:([A-Za-z0-9_-]{16})\]")
PENDING_TTL=600  # seconds a task proposal stays confirmable
_PENDING_LOCK=threading.Lock()

# Fabrication guard. The model has no tools in this path, so it must not narrate a run.
# Only a request to simulate/pretend *execution* is refused; ordinary roleplay is fine.
SIM_WORDS=re.compile(r"\b(?:simulat\w*|pretend|act\s+as\s+if|walk\s+me\s+through\s+what\s+happens\s+when\s+you)\b",re.I)
EXEC_WORDS=re.compile(r"\b(?:hand-?shake|endpoint|connect\w*|command|execut\w*|run(?:ning)?|deploy\w*|protocol|verif\w*|logs?|test\w*|tool|remote|install\w*|apply)\b",re.I)
CONTINUATION_CUE=re.compile(r"^(?:begin(?:\s+now)?|start(?:\s+now)?|go\s*ahead|proceed(?:\s+with\s+(?:the|this)\s+\w+)?|do\s+it|continue|yes,?\s*(?:begin|proceed|go\s*ahead)?)[.!\s]*$",re.I)
# Output-side check: an execution-report-shaped reply with no real run behind it is discarded.
FAKE_REPORT=re.compile(r"(?:^|\n)\s*(?:\*\*)?(?:result|timestamp|log summary|commands tested|simulated response)\b[^\n]{0,12}:|(?:simulated|executed|tested)\s+successfully|all\s+(?:commands|tests)\s+(?:were\s+)?(?:executed|passed)|\bGET\s+/\w+`?\s*(?:\u2192|->)",re.I)

NO_FABRICATION_SYSTEM_MSG=(
    "In this chat you are a plain text model and you cannot execute or simulate anything: you "
    "cannot run code, call tools, reach the network or run tests, and nothing you write is the "
    "result of running anything. Beldin does have a real sandboxed coding and self-improvement "
    "pipeline, but dedicated code starts it, not you. The user can describe a change to Beldin "
    "or to an approved project in plain words (or use /self <change>, /code PROJECT <request>, "
    "/tasks); the system then asks them to confirm before a sandboxed task starts, and nothing "
    "is applied until the human approves the exact diff. If a request needs that pipeline, say "
    "so and suggest they describe the change. Never present your own text as command output, "
    "logs, timestamps, handshake results or test results, and never narrate a 'simulated' run."
)
NO_SIMULATION_REPLY=(
    "I won't write a fake-execution trace: nothing would actually have run, so every result "
    "would be invented. To do real work, describe the change in plain words (for example "
    "\"add a /health endpoint to yourself\") and I'll propose a sandboxed task for you to "
    "confirm, or use /self <change>, /code PROJECT <request>, /tasks for real task status."
)
FABRICATED_REPLY=(
    "I started to write something that read like an execution report, but nothing ran, so I "
    "discarded it. If you want real work, describe the change (or use /self <change>, "
    "/code PROJECT <request>) and I'll propose a sandboxed task for you to confirm."
)


def _norm(text): return ' '.join(text.casefold().split()).strip(' .!?')
def _digest(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()

def _self_project(coding):
    return next((k for k,v in coding.projects.items() if v.get('self')),None) if coding else None

def task_target(text, coding):
    """(project, is_self) if the message reads like a request for a coding task, else None.
    is_self with project None means self-improvement is not enabled."""
    if not coding or CONTINUATION_CUE.match(text.strip()): return None
    if CODING_ENV.search(text) or (SELF_TARGET.search(text) and CODE_VERB.search(text)):
        return _self_project(coding), True
    if CODE_VERB.search(text):
        low=text.lower()
        for name,cfg in coding.projects.items():
            if not cfg.get('self') and re.search(r'(?<!\w)'+re.escape(name.lower())+r'(?!\w)',low):
                return name, False
    return None

def propose_task(state, project, prompt, is_self, user_text):
    key=secrets.token_urlsafe(12)  # 16 url-safe chars
    now=time.time()
    with _PENDING_LOCK:
        pending=getattr(state,'pending_tasks',None)
        if pending is None: pending=state.pending_tasks={}
        for k in [k for k,v in pending.items() if v['expires']<now]: pending.pop(k,None)
        pending[key]=dict(project=project,prompt=prompt,digest=_digest(user_text),expires=now+PENDING_TTL)
    shown=prompt if len(prompt)<=600 else prompt[:600]+'...'
    kind='self-improvement' if is_self else 'coding'
    return (f"That sounds like a sandboxed {kind} task on {project}:\n\"{shown}\"\n"
            "I would work in a separate copy, and nothing changes until you approve the exact diff. "
            f"Reply yes (or begin now) to start it, or cancel. [task:{key}]")

def confirm_task(safe, state, coding, model):
    """Reply string if the latest message answers a task proposal; None if it doesn't."""
    if not coding or len(safe)<2 or safe[-2]['role']!='assistant': return None
    m=TASK_MARK.search(safe[-2]['content'])
    if not m: return None
    text=safe[-1]['content']; norm=_norm(text)
    yes=bool(CONTINUATION_CUE.match(text.strip())) or norm in YES_WORDS
    if not (yes or norm in NO_WORDS): return None
    with _PENDING_LOCK:
        pending=getattr(state,'pending_tasks',None) or {}
        item=pending.pop(m.group(1),None)  # single use, whether yes or no
    if norm in NO_WORDS: return 'Cancelled. Nothing was started.'
    bound=(item is not None and item['expires']>=time.time() and len(safe)>=3 and safe[-3]['role']=='user'
           and item['digest']==_digest(safe[-3]['content']))
    if not bound: return 'That task confirmation is unavailable or has expired. Send the request again and I will re-propose it.'
    code,result=coding.request({'op':'create','project':item['project'],'prompt':item['prompt'],'model':model})
    if code==202:
        return ('I started working on that in a separate copy. I will keep trying until I have a tested change, then ask you to approve it. '
                'Nothing changes until you approve. Task '+result['id']+'.')
    return 'I could not start that: '+result.get('error','unavailable')

def coding_capabilities(coding):
    if not coding: return 'The coding pipeline is not enabled on this Valkyrie install, so I have no task tools available.'
    selfp=_self_project(coding)
    projects=', '.join(coding.projects) or 'none'
    return ("In this chat I'm a text model, so I can't run anything myself, but Valkyrie has a real sandboxed coding pipeline. "
            f"Approved projects: {projects}. Self-improvement is {'enabled' if selfp else 'not enabled'}. "
            "Describe a change to me or to one of those projects in plain words and I'll propose a task for you to confirm. "
            "Shortcuts: /self <change>, /code PROJECT <request>, /tasks. Every task works in a separate copy "
            "and only you can approve applying the diff.")

def ran_check_reply(coding):
    tasks=coding.all_tasks()[-3:] if coding else []
    if not tasks:
        return 'No. There are no coding tasks in the log, so nothing I described was actually run. Anything that looked like results was generated text.'
    listed=' '.join(f"Task {t['id']}: {(t.get('report') or {}).get('summary') or t['status'].replace('_',' ')}" for t in tasks)
    return ('Only what is in the task log actually ran: '+listed+' Anything else that looked like results in this chat was generated text, not output from a run.')[:1500]

def wants_fake_run(text): return bool(SIM_WORDS.search(text) and EXEC_WORDS.search(text))


def chat(handler):
    if handler.headers.get('Content-Type') != 'application/json':
        handler.respond(415, {'error': 'json_required'}); return
    length = handler.headers.get('Content-Length', '')
    if not length.isdecimal() or int(length) > 16384:
        handler.respond(413, {'error': 'body_too_large'}); return
    try:
        body = json.loads(handler.rfile.read(int(length)))
        messages = body.get('messages') if isinstance(body, dict) else None
        if not isinstance(messages, list) or not messages or len(messages) > 24: raise ValueError
        safe, total = [], 0
        for msg in messages:
            if not isinstance(msg, dict) or msg.get('role') not in ('system', 'user', 'assistant') or not isinstance(msg.get('content'), str): raise ValueError
            content = msg['content'][:4000]; total += len(content)
            if total > 12000: raise ValueError
            safe.append({'role': msg['role'], 'content': content})
        from .model_router import choose
        model = choose(body.get('model'))
        if body.get('model') is not None and body.get('model') != model: raise ValueError
    except (ValueError, TypeError, json.JSONDecodeError):
        handler.respond(400, {'error': 'invalid_chat_request'}); return
    def say(text): handler.respond(200, {'model': model, 'message': {'role': 'assistant', 'content': text}})
    state = handler.server.state
    latest_user = next((m['content'] for m in reversed(safe) if m['role'] == 'user'), '')
    coding=getattr(state,'coding',None)
    self_project=_self_project(coding)
    m=SELF_REQUEST.match(latest_user.strip())
    if coding and (latest_user.startswith('/self') or m):
        request=(latest_user[5:].strip() if latest_user.startswith('/self') else m.group(1).strip())
        if not self_project: reply='Self-improvement is not enabled: no project is marked self in coding-projects.json.'
        elif len(request)<8: reply='Tell me what to change about myself, for example: fix yourself so that the status command lists both models.'
        else:
            code,result=coding.request({'op':'create','project':self_project,'prompt':request,'model':model})
            reply=('I started working on that in a separate copy. I will keep trying until I have a tested change, then ask you to approve it. Nothing changes until you approve. Task '+result['id']+'.'
                   if code==202 else 'I could not start that: '+result.get('error','unavailable'))
        say(reply); return
    if coding and (latest_user.startswith('/tasks') or TASK_STATUS.search(latest_user)):
        tasks=coding.all_tasks()[-5:]
        reply='No coding tasks yet.' if not tasks else ' '.join(
            f"Task {t['id']}: {(t.get('report') or {}).get('summary') or t['status'].replace('_',' ')}" for t in tasks)
        say(reply[:1500]); return
    if coding and latest_user.startswith('/code '):
        parts=latest_user.split(' ',2)
        if len(parts)!=3:
            reply='Use /code PROJECT your coding request. Approved projects: '+', '.join(coding.projects)
        else:
            code,result=coding.request({'op':'create','project':parts[1],'prompt':parts[2],'model':model})
            reply=('Coding task '+result['id']+' started locally. Follow its tests and diff in Control Center. Deployment requires your approval.'
                   if code==202 else 'Coding task could not start: '+result.get('error','unavailable'))
        say(reply); return
    # A yes / begin now / cancel that answers one of *our* task proposals. Must run before
    # desktop_chat, which otherwise claims every bare "yes".
    confirmed=confirm_task(safe, state, coding, model)
    if confirmed is not None:
        say(confirmed); return
    from .desktop_chat import respond as desktop_chat
    desktop_reply = desktop_chat(safe, state, human_approved=getattr(handler, 'human_approved', lambda: False)())
    if desktop_reply is not None:
        say(desktop_reply); return
    if live_state_question(latest_user):
        say(grounded_status(state)); return
    if RAN_CHECK.search(latest_user):
        say(ran_check_reply(coding)); return  # answered from the task log, not the model's self-report
    target=task_target(latest_user, coding)
    if target is not None:
        project,is_self=target
        if not project: say('Self-improvement is not enabled: no project is marked self in coding-projects.json.'); return
        say(propose_task(state, project, latest_user.strip()[:4000], is_self, latest_user)); return
    if CAPABILITY_QUESTION.search(latest_user):
        say(coding_capabilities(coding)); return
    recent_assistant = ' '.join(m['content'] for m in safe[-6:] if m['role'] == 'assistant')
    if wants_fake_run(latest_user) or (CONTINUATION_CUE.match(latest_user.strip()) and wants_fake_run(recent_assistant)):
        say(NO_SIMULATION_REPLY); return
    try:
        grounded_messages = context(safe, state)
        grounded_messages[0]['content'] += '\n\n' + NO_FABRICATION_SYSTEM_MSG
        payload = json.dumps({'model': model, 'messages': grounded_messages, 'stream': False, 'think': False, 'options': {'temperature': 0.2, 'num_predict':512}}).encode()
        req = Request('http://127.0.0.1:11434/api/chat', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(req, timeout=45) as response: result = json.loads(response.read(65536))
        msg = result.get('message') if isinstance(result, dict) else None
        if not isinstance(msg, dict) or not isinstance(msg.get('content'), str): raise ValueError
        out = speech(msg['content'], msg.get('tool_calls'))
        if len(FAKE_REPORT.findall(out)) >= 2: out = FABRICATED_REPLY
        handler.respond(200, {'model': model, 'message': {'role': 'assistant', 'content': out}})
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        handler.respond(502, {'error': 'ollama_unavailable'})

