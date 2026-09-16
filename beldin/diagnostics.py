"""Deterministic assessment; missing observations never imply good health."""
def assess(telemetry):
    obs=telemetry.get('observed') or {}
    issues=[]; unknown=[]
    def check(name,key,threshold):
        source=obs.get(name,{})
        value=(source.get('data') or {}).get(key) if source.get('available') else None
        if value is None: unknown.append(name)
        elif value>=threshold: issues.append({'metric':name+'.'+key,'value':value,'threshold':threshold})
    check('cpu','used_percent',90)
    check('ram','used_percent',90)
    check('disk','used_percent',90)
    gpu=obs.get('gpu',{})
    if not gpu.get('available'): unknown.append('gpu')
    else:
        for g in gpu.get('data') or []:
            used,total=g.get('used_mib'),g.get('total_mib')
            if used is None or not total: unknown.append('gpu_vram')
            elif used/total>=.9: issues.append({'metric':'gpu.vram_percent','value':round(100*used/total,2),'threshold':90})
            temp=g.get('temperature_c')
            if temp is None: unknown.append('gpu_temperature')
            elif temp>=85: issues.append({'metric':'gpu.temperature_c','value':temp,'threshold':85})
    version=obs.get('ollama',{}).get('version',{})
    if not version.get('available'): unknown.append('ollama')
    age=telemetry.get('age_seconds')
    stale=age is None or age>10
    return {'kind':'derived','status':'stale' if stale else 'pressure' if issues else 'unknown' if unknown else 'ok',
            'issues':issues,'unknown':sorted(set(unknown)), 'threshold_policy':'v1: cpu/ram/disk/vram >=90%; gpu >=85 C; stale >10s'}
