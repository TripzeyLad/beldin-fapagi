"""Deny-by-default application capability registry schema."""
APP_REGISTRY = {
    "beldin_core": {"adapter": "internal", "operations": {
        "health_snapshot": {"permission": "OBSERVE", "confirmation_required": False,
                             "max_input_bytes": 1024, "max_output_bytes": 16384},
    }},
    "windows_notepad": {"adapter": "notepad", "enabled": True, "transport":"local_desktop_agent", "operations": {
        "open_notepad": {"permission": "SAFE_ACTION", "confirmation_required": True,
                          "max_input_bytes": 256, "max_output_bytes": 4096},
        "create_notepad_note": {"permission": "SAFE_ACTION", "confirmation_required": True,
                                 "max_input_bytes": 8192, "max_output_bytes": 4096,
                                 "max_text_chars": 4096, "state": "registered_but_unavailable_until_verified_ui"},
        "close_beldin_notepad": {"permission": "SAFE_ACTION", "confirmation_required": True,
                                  "max_input_bytes": 256, "max_output_bytes": 4096},
    }},
}
def public_registry(desktop=None):
    import copy
    apps=copy.deepcopy(APP_REGISTRY)
    health=desktop or {}
    for name,op in apps['windows_notepad']['operations'].items():
        op['state']='AVAILABLE' if health.get('online') and health.get('operations',{}).get(name) is True and validate('windows_notepad',name,{})[0] else 'UNAVAILABLE'
        op['source']='authenticated_desktop_probe'
    return {"version":1,"default_policy":"deny","apps":apps}
def validate(app_id, operation, args):
    op=APP_REGISTRY.get(app_id,{}).get("operations",{}).get(operation)
    if not op or not isinstance(args,dict) or APP_REGISTRY.get(app_id,{}).get('enabled',True) is not True: return False,"capability_not_allowlisted"
    if app_id == 'windows_notepad':
        from .desktop_protocol import valid_args
        if op.get('permission')!='SAFE_ACTION' or op.get('confirmation_required') is not True: return False,'permission_denied'
        if not valid_args(operation,args): return False,"invalid_input"
    if len(str(args).encode())>op["max_input_bytes"]: return False,"input_too_large"
    return True,op
