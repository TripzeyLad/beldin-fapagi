"""Closed registry. No callable write actions and no shell execution."""
REGISTRY = {
    'health_snapshot': {'permission':'OBSERVE','available':True,'input_schema':{'type':'object','properties':{},'additionalProperties':False}},
    'reload_config': {'permission':'SAFE_ACTION','available':False,'input_schema':{'type':'object','additionalProperties':False}},
    'system_change': {'permission':'SYSTEM_CHANGE','available':False,'input_schema':{'type':'object','additionalProperties':False}},
    'shell': {'permission':'BLOCKED','available':False,'input_schema':{'type':'object','additionalProperties':False}},
}

def dispatch(body, state):
    if not isinstance(body,dict) or set(body)!={'action','input'} or not isinstance(body.get('action'),str) or not isinstance(body.get('input'),dict):
        return 400,{'error':'invalid_action_request'}
    action=REGISTRY.get(body['action'])
    if not action: return 404,{'error':'unknown_action'}
    if not action['available']: return 403,{'error':'action_disabled','permission':action['permission']}
    if body['input']: return 400,{'error':'invalid_action_input'}
    if body['action']=='health_snapshot': return 200,{'permission':'OBSERVE','result':state.telemetry()}
    return 403,{'error':'action_disabled'}
