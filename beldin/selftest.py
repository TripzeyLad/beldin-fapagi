def run(state):
    observed=state.telemetry().get("observed") or {}
    return {"service":True,"auth":"request_authenticated","ollama":bool(observed.get("ollama")),"model":"qwen3:8b","v2":True,"safe_actions":True,"node_registry":hasattr(state,"node"),"memory_foundation":True,"reload_task":"external_task_status_required"}
