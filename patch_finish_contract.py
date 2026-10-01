from pathlib import Path

p = Path(r".\beldin\coding.py")
s = p.read_text(encoding="utf-8")

old = """                changed=bool(proposal['files'])
                validation=t['validation']
"""

new = """                changed=bool(proposal['files'])
            if not changed:
                blocker=args.get('blocker') if isinstance(args,dict) else None
                valid_blocker=(
                    isinstance(blocker,dict)
                    and isinstance(blocker.get('missing_capability'),str)
                    and bool(blocker['missing_capability'].strip())
                    and isinstance(blocker.get('reason'),str)
                    and bool(blocker['reason'].strip())
                    and isinstance(blocker.get('evidence_paths'),list)
                    and bool(blocker['evidence_paths'])
                    and all(isinstance(x,str) and x.strip() for x in blocker['evidence_paths'])
                )
                if not valid_blocker:
                    proposal['approval_eligible']=False
                    proposal['rejection_reason']='finish_requires_change_or_blocker'
                    t['status']='repair_required'; t['status_reason']='finish_requires_change_or_blocker'
                    self.event(t,'tool_error',tool='finish',error='finish_requires_change_or_blocker')
                    return {'error':'finish_requires_change_or_blocker','executed':False,
                            'message':'finish requires either changed files or blocker {missing_capability, reason, evidence_paths:[...]}. Continue investigating or act on the evidence.'}
                proposal['approval_eligible']=False
                proposal['blocker']=blocker
                t['blocker']=blocker
                t['status']='needs_human'; t['status_reason']='evidence_backed_blocker'
                self.event(t,'needs_human',reason='evidence_backed_blocker',blocker=blocker)
                return {'status':'blocked','executed':True,'blocker':blocker,'files':[]}
                validation=t['validation']
"""

if old not in s:
    raise SystemExit("PATCH_REFUSED: finish anchor not found")

s = s.replace(old, new, 1)

old_prompt = """finish: {evidence:{"R1":{"files":[...],"tests":[...]}}} - evidence is required when the task lists requirements; cited files must be in your change and cited tests must have passed."""

new_prompt = """finish: {evidence:{"R1":{"files":[...],"tests":[...]}}, blocker:{missing_capability:"...",reason:"...",evidence_paths:["..."]}}. A successful finish requires either changed files or, when no justified implementation is possible, a blocker with all three non-empty fields. evidence is required when the task lists requirements; cited files must be in your change and cited tests must have passed."""

if old_prompt not in s:
    raise SystemExit("PATCH_REFUSED: prompt anchor not found")

s = s.replace(old_prompt, new_prompt, 1)
p.write_text(s, encoding="utf-8", newline="")
print("FINISH_CONTRACT_PATCH_APPLIED")

