"""Server-owned identity; never obtain the canonical prompt from clients."""
from pathlib import Path
import re
from .knowledge import category_context
from .conversation_memory import evidence

IDENTITY_PATH = Path(__file__).resolve().parents[1] / "BELDIN_IDENTITY.md"

def context(messages, state=None):
    identity = IDENTITY_PATH.read_text(encoding="utf-8")
    if not identity.strip() or len(identity) > 8192:
        raise ValueError("identity_unavailable")
    query=next((m.get('content','') for m in reversed(messages) if m.get('role')=='user'),'')
    extra=category_context(query,state)
    memory,diagnostics=evidence(messages,state)
    system=identity + ("\n\nDerived Beldin context:\n"+extra if extra else "") + memory
    result=[{"role":"system", "content":system}] + [
        {**m, "role":"user" if m["role"] == "system" else m["role"]}
        for m in messages]
    if state is not None:
        state.conversation_context={**diagnostics,'context_items':len(result),'roles':[m['role'] for m in result],
                                    'founding_or_capability_context':bool(extra),'history_source':'request','session_tracking':False}
    return result

def speech(content, tool_calls=None):
    if tool_calls or re.search(r'(?:<tool_call>|tool_calls|"(?:tool|action|function|arguments)"\s*:)', content, re.I):
        return "I could not complete that tool request. No action was executed through this chat."
    return content[:12000]
