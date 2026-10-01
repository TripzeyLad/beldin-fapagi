"""Authenticated, bounded local desktop protocol. Secret never crosses transport."""
import hashlib
import hmac
import json
import re
import time
from pathlib import Path

PORT = 8766
LIMIT = 8192
ACTIONS = ("open_notepad", "close_beldin_notepad", "create_notepad_note")
ID = re.compile(r"[a-f0-9]{32}")
def encode(obj):
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode()
def mac(secret, data):
    return hmac.new(secret.encode("ascii"), data, hashlib.sha256).hexdigest()
def decode(data):
    if len(data) > LIMIT: raise ValueError("bounded_request")
    def pairs(items):
        d = {}
        for k,v in items:
            if k in d: raise ValueError("duplicate_field")
            d[k]=v
        return d
    return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
def settings(root):
    value = json.loads((Path(root)/"config.desktop.json").read_text(encoding="utf-8"))
    if set(value) != {"version","secret","enabled"} or value["version"] != 1 or type(value["enabled"]) is not bool:
        raise ValueError("agent_config")
    if not isinstance(value["secret"],str) or not re.fullmatch("[a-f0-9]{64}",value["secret"]):
        raise ValueError("agent_secret")
    return value
def valid_args(operation, args):
    if not isinstance(args,dict) or operation not in ACTIONS: return False
    if operation != "create_notepad_note": return args == {}
    text=args.get("text")
    return set(args)=={"text"} and isinstance(text,str) and 0<len(text)<=4096 and bool(text.strip()) and len(encode(args))<=6000
def validate(obj):
    if not isinstance(obj,dict) or set(obj)!={"version","agent_id","adapter","operation","invocation_id","at","args"}:
        return False
    return (type(obj["version"]) is int and obj["version"]==1 and obj["adapter"]=="notepad"
            and isinstance(obj["agent_id"],str) and ID.fullmatch(obj["agent_id"]) is not None
            and isinstance(obj["invocation_id"],str) and ID.fullmatch(obj["invocation_id"]) is not None
            and type(obj["at"]) in (int,float) and abs(time.time()-obj["at"])<=10
            and valid_args(obj["operation"],obj["args"]))
