import json
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
    latest_user = next((m['content'] for m in reversed(safe) if m['role'] == 'user'), '')
    if latest_user.startswith('/code '):
        parts=latest_user.split(' ',2)
        if len(parts)!=3:
            reply='Use /code PROJECT your coding request. Approved projects: '+', '.join(handler.server.state.coding.projects)
        else:
            code,result=handler.server.state.coding.request({'op':'create','project':parts[1],'prompt':parts[2],'model':model})
            reply=('Coding task '+result['id']+' started locally. Follow its tests and diff in Control Center. Deployment requires your approval.'
                   if code==202 else 'Coding task could not start: '+result.get('error','unavailable'))
        handler.respond(200,{'model':model,'message':{'role':'assistant','content':reply}}); return
    from .desktop_chat import respond as desktop_chat
    desktop_reply = desktop_chat(safe, handler.server.state)
    if desktop_reply is not None:
        handler.respond(200, {'model':model, 'message':{'role':'assistant','content':desktop_reply}})
        return
    if live_state_question(latest_user):
        handler.respond(200, {'model': model, 'message': {'role': 'assistant', 'content': grounded_status(handler.server.state)}})
        return
    try:
        payload = json.dumps({'model': model, 'messages': context(safe, handler.server.state), 'stream': False, 'think': False, 'options': {'temperature': 0.2, 'num_predict':512}}).encode()
        req = Request('http://127.0.0.1:11434/api/chat', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(req, timeout=45) as response: result = json.loads(response.read(65536))
        msg = result.get('message') if isinstance(result, dict) else None
        if not isinstance(msg, dict) or not isinstance(msg.get('content'), str): raise ValueError
        handler.respond(200, {'model': model, 'message': {'role': 'assistant', 'content': speech(msg['content'], msg.get('tool_calls'))}})
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        handler.respond(502, {'error': 'ollama_unavailable'})
