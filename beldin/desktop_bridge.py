"""Brain-side client: fixed localhost peer; authenticated replies; no retry."""
import hmac
import time
import uuid
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from .desktop_protocol import PORT, LIMIT, encode, decode, mac, settings, validate

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class Bridge:
    def __init__(self, root):
        self.root=root
    def _request(self, path, obj, config):
        payload=encode(obj)
        if len(payload)>LIMIT: raise ValueError("request_too_large")
        request=Request("http://127.0.0.1:"+str(PORT)+path, data=payload, method="POST",
                        headers={"Content-Type":"application/json","X-Beldin-MAC":mac(config["secret"],payload)})
        with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=3) as response:
            raw=response.read(LIMIT+1)
            signature=response.headers.get("X-Beldin-MAC","")
        if len(raw)>LIMIT or not hmac.compare_digest(signature,mac(config["secret"],raw)):
            raise ValueError("invalid_agent_response")
        value=decode(raw)
        if not isinstance(value,dict) or value.get("request_id")!=obj["invocation_id"]:
            raise ValueError("response_correlation")
        return value
    def health(self):
        try:
            config=settings(self.root)
            if not config["enabled"]: raise ValueError("disabled")
            nonce=uuid.uuid4().hex
            result=self._request("/health",{"invocation_id":nonce,"at":time.time()},config)
            if (result.get("version")!=1 or not isinstance(result.get("agent_id"),str)
                or result.get("interactive") is not True or type(result.get("session_id")) is not int
                or result["session_id"]<=0 or type(result.get("at")) not in (int,float)
                or abs(time.time()-result["at"])>5): raise ValueError("stale_session")
            return {**result,"online":True}
        except Exception:
            return {"online":False,"operations":{},"error":"desktop_agent_unavailable"}
    def dispatch(self, operation, args, invocation_id):
        health=self.health()
        if not health["online"] or health.get("operations",{}).get(operation) is not True:
            return {"state":"UNAVAILABLE","error":"desktop_operation_unavailable","invocation_id":invocation_id}
        try:
            config=settings(self.root)
            if not config["enabled"]: raise ValueError("disabled")
            obj={"version":1,"agent_id":health["agent_id"],"adapter":"notepad","operation":operation,
                 "invocation_id":invocation_id,"at":time.time(),"args":args}
            if not validate(obj): raise ValueError("invalid_dispatch")
            result=self._request("/dispatch",obj,config)
            if result.get("agent_id")!=health["agent_id"] or result.get("session_id")!=health["session_id"]:
                raise ValueError("changed_session")
            if result.get("state") not in ("VERIFIED_SUCCESS","FAILED","UNAVAILABLE","UNVERIFIABLE","PARTIAL"):
                raise ValueError("invalid_result")
            # Output is a fixed projection, never arbitrary agent strings.
            return {"state":result["state"],"invocation_id":invocation_id,
                    "verification":result.get("verification")=="owned_process_visible_window",
                    "error": "desktop_action_not_verified" if result["state"]!="VERIFIED_SUCCESS" else None}
        except Exception:
            # A lost response may mean execution occurred. Never retry it.
            return {"state":"UNVERIFIABLE","error":"desktop_result_unverified","invocation_id":invocation_id}
