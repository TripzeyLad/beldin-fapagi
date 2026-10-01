"""Minimal intentional shared-memory foundation; no automatic chat capture."""
import json,re,time
from pathlib import Path
MAX_ENTRY=4096; MAX_RESULTS=20
def _path(root): return Path(root)/"memory"/"shared.jsonl"
def remember(root,text,topic="general",source="explicit_user"):
    if (not isinstance(text,str) or not text.strip() or len(text)>MAX_ENTRY or
        not isinstance(topic,str) or len(topic)>128 or topic.casefold() in
        {"constitution","founding","origin","system"} or
        not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}",source)): return 400,{"error":"invalid_memory"}
    p=_path(root); p.parent.mkdir(exist_ok=True)
    row={"id":str(time.time_ns()),"created_at_unix":time.time(),"topic":topic[:128],"source":source,"text":text}
    if p.exists() and p.stat().st_size>1024*1024:return 413,{"error":"memory_capacity"}
    with p.open("a",encoding="utf-8",newline="\n") as f:f.write(json.dumps(row,ensure_ascii=True)+"\n")
    return 200,{"status":"remembered","id":row["id"]}
def recall(root,query,topic=None):
    if not isinstance(query,str) or len(query)>256:return 400,{"error":"invalid_memory"}
    rows=[];p=_path(root)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines()[-2000:]:
            try:r=json.loads(line)
            except ValueError:continue
            if query.casefold() in r.get("text","").casefold() and (topic is None or r.get("topic")==topic):rows.append(r)
    return 200,{"entries":rows[-MAX_RESULTS:],"count":len(rows[-MAX_RESULTS:])}
def forget(root,entry_id):
    if not isinstance(entry_id,str) or not re.fullmatch(r"[0-9]{10,32}",entry_id):return 400,{"error":"invalid_memory_id"}
    p=_path(root)
    if not p.exists():return 404,{"error":"memory_not_found"}
    rows=[json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()];kept=[r for r in rows if r.get("id")!=entry_id]
    if len(kept)==len(rows):return 404,{"error":"memory_not_found"}
    p.write_text("".join(json.dumps(r,ensure_ascii=True)+"\n" for r in kept),encoding="utf-8")
    return 200,{"status":"forgotten","id":entry_id}
