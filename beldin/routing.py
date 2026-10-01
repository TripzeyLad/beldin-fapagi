"""Fail-closed natural-language routing and bounded Qwen call handling."""
import json, re

OBSERVE = {
    "system_status": ("valkyrie", ("valkyrie", "status", "doing", "health", "system")),
    "ollama_status": ("ollama", ("ollama", "gpu", "model")),
    "windows_health": ("windows_health", ("windows", "errors", "event", "crash")),
    "service_status": ("service_status", ("service", "services")),
}
ACTION_WORDS = {
    "run_beldin_tests": ("run", "test", "tests", "regression"),
    "backup_beldin": ("backup", "back up"),
    "ollama_model_warmup": ("warm", "warmup", "warm up"),
    "save_diagnostic_snapshot": ("snapshot", "diagnostic snapshot"),
}

def notepad_action(text):
    if not isinstance(text, str): return None
    s = re.sub(r"^(?:hey )?beldin[, ]+", "", text.strip().replace("’", "'"), flags=re.I)
    if re.fullmatch(r"(?:please )?(?:open|start|launch) (?:windows )?notepad[.!?]?", s, re.I):
        return {"kind":"action","action":"open_notepad","input":{},"confirmation_required":True}
    if re.fullmatch(r"(?:please )?close (?:the )?(?:beldin's notepad|notepad you opened|notepad)[.!?]?", s, re.I):
        return {"kind":"action","action":"close_beldin_notepad","input":{},"confirmation_required":True}
    m = re.fullmatch(r"(?:please )?(?:write|type|put) (.+) (?:in|into) (?:windows )?notepad[.!?]?", s, re.S|re.I)
    if not m:
        m = re.fullmatch(r"(?:please )?open (?:windows )?notepad and (?:write|type|put):? (.+)", s, re.S|re.I)
    if m and m.group(1).strip():
        return {"kind":"action","action":"create_notepad_note","input":{"text":m.group(1).strip()},"confirmation_required":True}
    return None

def local_time_question(text):
    s=' '.join(text.casefold().split()).strip(' .?!') if isinstance(text,str) else ''
    return bool(re.fullmatch(r'(?:beldin,? |qwen,? )?(?:what time is it|tell me what time it is)',s))

def live_state_question(text):
    """Bounded node-state intent; a node mention alone is not an observation."""
    if not isinstance(text, str) or len(text) > 4000:
        return False
    s = " ".join(text.casefold().replace("’", "'").split()).strip(" .?!")
    s = re.sub(r"^(?:please |hey beldin,? |beldin,? )", "", s)
    s = re.sub(r" (?:right now|currently|today|at the moment)$", "", s)
    node = r"(?:valkyrie|the valkyrie node)"
    patterns = (
        rf"how (?:is|is the status of) {node}(?: doing| functioning| running)?",
        rf"how's {node}(?: doing| functioning| running)?",
        rf"is {node} (?:okay|ok|online|offline|healthy|running|working|available|up|down)",
        rf"(?:what is|what's|show me|tell me|check) {node}'s (?:current |live )?(?:status|health|state)",
        rf"(?:what is|what's|show me|check) the (?:current |live )?(?:status|health|state) of {node}",
    )
    if any(re.fullmatch(p, s) for p in patterns):
        return True
    # Component observations, excluding historical, fictional and unrelated subjects.
    if re.search(r"\b(?:weather|story|mythology|yesterday|history|fiction|pretend)\b", s):
        return False
    return bool(re.search(r"\bvalkyrie\b", s)
                and re.search(r"\b(?:cpu|gpu|ram|memory|disk|temperature|uptime|ollama)\b", s)
                and re.search(r"\b(?:is|are|current|live|now|using|usage|available)\b", s))


def grounded_status(state):
    """Use fresh observations only. Never pass a failed observation to a model."""
    failure = "I cannot currently verify Valkyrie's live state."
    try:
        from .tools import observe
        sample = state.telemetry()
        age = sample.get("age_seconds")
        if type(age) not in (int, float) or not 0 <= age <= 10 or not sample.get("observed"):
            return failure
        code, result = observe("system_status", {}, state)
        data = result.get("result")
        if code != 200 or not isinstance(data, dict) or data.get("available") is False:
            return failure
        if data.get("service", {}).get("status") != "running":
            return failure
        return ("Valkyrie's Beldin service is responding. "
                "That does not establish overall machine or GPU health; "
                "I cannot currently verify those from this status check.")
    except Exception:
        return failure


def route_text(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return {"kind":"clarify", "reason":"empty_or_bounded_input"}
    s=text.casefold()
    if local_time_question(text): return {'kind':'time','source':'valkyrie_local_clock'}
    app = notepad_action(text)
    if app: return app
    if live_state_question(text):
        return {"kind":"observe", "tool":"system_status", "input":{}, "spoken_label":"valkyrie", "observation_required":True, "model_fallback_allowed":False}
    for action, words in ACTION_WORDS.items():
        if any(w in s for w in words):
            return {"kind":"action", "action":action, "input":{}, "confirmation_required":True}
    if re.search(r"\bvalkyrie\b", s):
        return {"kind":"chat", "reason":"no_live_state_intent"}
    for tool, (label, words) in OBSERVE.items():
        if any(w in s for w in words):
            return {"kind":"observe", "tool":tool, "input":{}, "spoken_label":label}
    return {"kind":"chat", "reason":"no_safe_route"}

def parse_qwen_tool_call(content, allowed_tools, allowed_actions):
    if not isinstance(content, str) or len(content) > 12000: return None
    candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.I|re.S)
    if not candidates and content.lstrip().startswith("{"): candidates=[content.strip()]
    if len(candidates) != 1: return None
    try: obj=json.loads(candidates[0])
    except (ValueError, RecursionError): return None
    if not isinstance(obj, dict) or set(obj) - {"tool","action","input"}: return None
    name=obj.get("tool") or obj.get("action")
    if not isinstance(name,str) or not isinstance(obj.get("input",{}),dict): return None
    if name not in set(allowed_tools) | set(allowed_actions): return None
    if len(json.dumps(obj, separators=(",",":"))) > 2048: return None
    return {"name":name,"input":obj.get("input",{}),"requires_confirmation":name in set(allowed_actions)}

def spoken_content(content, allowed_tools=(), allowed_actions=()):
    call=parse_qwen_tool_call(content, allowed_tools, allowed_actions)
    if call:
        return {"text":"I can do that." if call["requires_confirmation"] else "I’m checking that now.", "call":call}
    return {"text":content[:12000] if isinstance(content,str) else "I could not produce a response.", "call":None}
