"""Client-independent chat action selection and confirmation binding."""
import hashlib
import re
from datetime import datetime
from .routing import notepad_action, local_time_question
from .safe_actions import propose, confirm, cancel

def digest(text): return hashlib.sha256(text.encode("utf-8")).hexdigest()
def challenge(action_id):
    return "Open a Beldin-managed Notepad on Valkyrie? Reply yes or cancel within 60 seconds. [approval:"+action_id+"]"

def capability_summary(state):
    health=state.desktop.health()
    from .app_registry import validate
    allowed=getattr(state,'tools_enabled',True) is True and validate('windows_notepad','open_notepad',{})[0]
    base="I can provide authenticated observations, grounded Valkyrie status, and confirmation-gated registered safe actions. "
    if not health.get("online"):
        return base+"The Notepad adapter is installed, but the interactive desktop agent is unavailable, so I cannot currently open desktop applications."
    if allowed and health.get("operations",{}).get("open_notepad") is True:
        return base+"The desktop agent can attempt a managed Notepad launch when no existing Notepad is present. It verifies a visible owned window. Closing shared/user-edited tabs, text insertion and saving files are unavailable."
    return base+"The desktop agent is online, but Notepad launch is currently unavailable. Safe close, text insertion and saving files are unavailable."

def respond(messages,state):
    if not messages or messages[-1]["role"]!="user": return None
    text=messages[-1]["content"]
    normalized=" ".join(text.casefold().split()).strip(" .?!")
    if local_time_question(text):
        return "The local time on Valkyrie is "+datetime.now().astimezone().strftime("%I:%M %p %Z")+"."
    if normalized in ("what can you do","what can you do right now","what can you actually do","what capabilities do you currently have"):
        return capability_summary(state)
    if normalized in ("yes","yes please","confirm","cancel","no"):
        prior=messages[-2] if len(messages)>=2 else {}
        match=re.fullmatch(r"Open a Beldin-managed Notepad on Valkyrie\? Reply yes or cancel within 60 seconds\. \[approval:([A-Za-z0-9_-]{16})\]",prior.get("content",""))
        if prior.get("role")!="assistant" or not match:
            return "There is no matching desktop action to confirm in this conversation."
        key=match.group(1)
        with state.action_lock:
            item=state.pending_actions.get(key)
            bound=(item is not None and len(messages)>=3 and messages[-3]["role"]=="user"
                   and item.get("chat_digest")==digest(messages[-3]["content"])
                   and item["name"]=="open_notepad")
        if not bound: return "That desktop confirmation is unavailable or no longer valid."
        if normalized in ("cancel","no"):
            cancel(key,state)
            return "The pending desktop action was cancelled."
        code,result=confirm(key,state)
        if code!=200: return "That desktop confirmation has expired or was already used."
        status=result.get("result",{}).get("state")
        if status=="VERIFIED_SUCCESS":
            return "A Beldin-managed Notepad window is visible on Valkyrie. Safe automated close is not yet available."
        if status=="UNVERIFIABLE":
            return "I attempted the desktop action, but cannot verify its result. I will not retry automatically."
        return "The desktop action could not be completed. The agent or a required ownership check is unavailable."
    plan=notepad_action(text)
    if plan:
        if plan["action"]=="create_notepad_note":
            return "Verified text insertion into Notepad is unavailable. I have not opened or written a note."
        if plan["action"]=="close_beldin_notepad":
            return "I cannot safely close modern Notepad tabs yet because ownership and unsaved user changes cannot be verified."
        code,result=propose(plan["action"],plan["input"],state)
        if code!=200:
            return "Notepad launch is unavailable. The interactive desktop agent must be online and able to verify an isolated Notepad session."
        key=result["action_id"]
        with state.action_lock:
            state.pending_actions[key]["chat_digest"]=digest(text)
        return challenge(key)
    if re.match(r"save (?:it|this) to ",normalized):
        return "Saving arbitrary files through Notepad is not implemented or authorized."
    if re.fullmatch(r"close (?:my|the) other notepad[.!?]?",normalized):
        return "I cannot close a Notepad session that I do not own."
    return None
