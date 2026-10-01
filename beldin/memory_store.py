"""Append-only long-term memory plumbing with provenance and confidence."""
import json, time, uuid
from pathlib import Path

KINDS = {'episodic','semantic','procedural','project'}
def _events(root): return Path(root)/'memory'/'events.jsonl'
def append(root, text, kind='episodic', source='observed', confidence=0.5, correction_of=None):
    if not isinstance(text,str) or not text.strip() or len(text)>8192 or kind not in KINDS or not isinstance(source,str) or len(source)>256 or type(confidence) not in (int,float) or not 0<=confidence<=1:
        return 400, {'error':'invalid_memory_event'}
    row={'id':uuid.uuid4().hex,'created_at_unix':time.time(),'kind':kind,'text':text,'source':source[:256],'confidence':float(confidence)}
    if correction_of is not None: row['correction_of']=str(correction_of)[:64]
    p=_events(root);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists() and p.stat().st_size>16*1024*1024:return 413,{'error':'memory_capacity'}
    with p.open('a',encoding='utf-8',newline='\n') as f:f.write(json.dumps(row,ensure_ascii=True)+'\n')
    return 200, {'status':'recorded','id':row['id']}
def search(root, query, kind=None, limit=20):
    if not isinstance(query,str) or len(query)>256 or kind is not None and kind not in KINDS:return 400,{'error':'invalid_memory_query'}
    p=_events(root); rows=[]
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines()[-5000:]:
            try:r=json.loads(line)
            except ValueError:continue
            if query.casefold() in r.get('text','').casefold() and (kind is None or r.get('kind')==kind):rows.append(r)
    return 200, {'entries':rows[-max(1,min(limit,50)):], 'count':len(rows[-max(1,min(limit,50)):]), 'originals_retained':True}
def status(root):
    p=_events(root); return {'available':True,'path':'memory/events.jsonl','records':sum(1 for _ in p.open(encoding='utf-8')) if p.exists() else 0,'originals_retained':True,'storage_tier':'configurable_local'}
