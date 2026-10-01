from pathlib import Path

p = Path(r".\beldin\coding.py")
s = p.read_text(encoding="utf-8-sig")

# 1. Empty finish must contain a verified blocker.
anchor = """                changed=bool(proposal['files'])
                validation=t['validation']
"""
replacement = """                changed=bool(proposal['files'])
                if not changed:
                    blocker=args.get('blocker') if isinstance(args,dict) else None
                    read_paths=(t.get('_research') or {}).get('read_paths',[])
                    valid_blocker=(
                        isinstance(blocker,dict)
                        and isinstance(blocker.get('missing_capability'),str)
                        and bool(blocker['missing_capability'].strip())
                        and isinstance(blocker.get('reason'),str)
                        and bool(blocker['reason'].strip())
                        and isinstance(blocker.get('evidence_paths'),list)
                        and bool(blocker['evidence_paths'])
                        and all(isinstance(x,str) and x.strip() for x in blocker['evidence_paths'])
                        and all(x in read_paths for x in blocker['evidence_paths'])
                    )
                    if not valid_blocker:
                        proposal['approval_eligible']=False
                        proposal['rejection_reason']='finish_requires_change_or_blocker'
                        t['status']='repair_required'
                        t['status_reason']='finish_requires_change_or_blocker'
                        self.event(t,'tool_error',tool='finish',error='finish_requires_change_or_blocker')
                        return {'error':'finish_requires_change_or_blocker','executed':False,
                                'message':'finish requires changed files or an evidence-backed blocker.'}
                    proposal['approval_eligible']=False
                    proposal['blocker']=blocker
                    t['blocker']=blocker
                    t['status']='needs_human'
                    t['status_reason']='evidence_backed_blocker'
                    self.event(t,'needs_human',reason='evidence_backed_blocker',blocker=blocker)
                    return {'status':'blocked','executed':True,'blocker':blocker,'files':[]}
                validation=t['validation']
"""
if s.count(anchor) != 1:
    raise SystemExit("PATCH_REFUSED: finish anchor")
s = s.replace(anchor,replacement,1)

# 2. pursue() recognizes blocker as a terminal, honest outcome.
anchor = """            ok=(t['status']=='approval_needed' and bool(proposal.get('files')) and bool(proposal.get('approval_eligible')))
            attempts.append(dict(n=n,outcome='proposal_ready' if ok else 'failed',error=error,reason=t.get('status_reason'),
                                 files=len(proposal.get('files',[])),validation_passed=bool(t['validation'].get('passed'))))
            self.event(t,'attempt',n=n,ok=ok)
            if ok: break
"""
replacement = """            ok=(t['status']=='approval_needed' and bool(proposal.get('files')) and bool(proposal.get('approval_eligible')))
            blocked=(t['status']=='needs_human' and bool(t.get('blocker')))
            attempts.append(dict(n=n,outcome='proposal_ready' if ok else ('blocked' if blocked else 'failed'),error=error,reason=t.get('status_reason'),
                                 files=len(proposal.get('files',[])),validation_passed=bool(t['validation'].get('passed'))))
            self.event(t,'attempt',n=n,ok=ok,blocked=blocked)
            if ok or blocked: break
"""
if s.count(anchor) != 1:
    raise SystemExit("PATCH_REFUSED: pursue anchor")
s = s.replace(anchor,replacement,1)

# 3. Report the blocker structurally.
anchor = """        elif outcome=='cancelled': summary='Cancelled. Nothing was changed.'
        else:
"""
replacement = """        elif outcome=='cancelled': summary='Cancelled. Nothing was changed.'
        elif outcome=='blocked':
            blocker=t.get('blocker') or {}
            summary=(f"Investigation reached a verified boundary: {blocker.get('missing_capability','unknown capability')}. "
                     f"{blocker.get('reason','Human input or authority is required.')} Nothing was changed on the live system.")
        else:
"""
if s.count(anchor) != 1:
    raise SystemExit("PATCH_REFUSED: report anchor")
s = s.replace(anchor,replacement,1)

anchor = """                    validation_passed=bool(t['validation'].get('passed')),production=t.get('production'))
"""
replacement = """                    validation_passed=bool(t['validation'].get('passed')),production=t.get('production'),
                    blocker=t.get('blocker'))
"""
if s.count(anchor) != 1:
    raise SystemExit("PATCH_REFUSED: report return anchor")
s = s.replace(anchor,replacement,1)

# 4. Final pursue outcome.
anchor = """        if ok: t['report']=self.report(t,'proposal_ready')
        else:
"""
replacement = """        if ok: t['report']=self.report(t,'proposal_ready')
        elif t.get('blocker'): t['report']=self.report(t,'blocked')
        else:
"""
if s.count(anchor) != 1:
    raise SystemExit("PATCH_REFUSED: final outcome anchor")
s = s.replace(anchor,replacement,1)

# 5. Tell the model the actual finish contract.
anchor = """diff: {}; finish: {evidence:{"R1":{"files":[...],"tests":[...]}}} - evidence is required when the task lists requirements; cited files must be in your change and cited tests must have passed.
"""
replacement = """diff: {}; finish: {evidence:{"R1":{"files":[...],"tests":[...]}}} for a changed proposal, or finish: {blocker:{missing_capability:"...",reason:"...",evidence_paths:["path"]}} when investigation proves no justified code change can proceed. Blocker evidence_paths must name files you actually read. Bare empty finish is invalid. Requirement evidence is required when the task lists requirements; cited files must be in your change and cited tests must have passed.
"""
if s.count(anchor) != 1:
    raise SystemExit("PATCH_REFUSED: prompt anchor")
s = s.replace(anchor,replacement,1)

p.write_text(s,encoding="utf-8")
print("PATCH_CREATED_OK")
