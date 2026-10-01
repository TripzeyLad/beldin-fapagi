"""Bounded derived constitution/origin context and current capability summary."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONSTITUTION=(ROOT/"BELDIN_CONSTITUTION.md").read_text(encoding="utf-8")
ROADMAP=(ROOT/"BELDIN_ROADMAP.md").read_text(encoding="utf-8")
ORIGIN=(ROOT/"origin"/"MANIFEST.json").read_text(encoding="utf-8")
def category_context(text,state=None):
    s=(text or "").casefold()
    if any(x in s for x in ("what can you do","capabilit","right now","actually do")):
        if state is None:return "Current capability state is unavailable."
        from .desktop_chat import capability_summary
        return capability_summary(state)+" Founding aspirations are not current capabilities."
    if any(x in s for x in ("eventually","supposed to become","long-term","planned","original purpose","prime directive")):return ROADMAP[:5000]+"\n\n"+CONSTITUTION[:5000]
    if any(x in s for x in ("original instruction","first task","initialization","how did you start","founding")):return "The preserved founding artifacts are historical. Initialization instructed the founding engineer to inspect the workstation, inventory capabilities, propose architecture and security, and build an incremental first slice. It is not a recurring startup command.\nOrigin manifest: "+ORIGIN[:1200]
    if any(x in s for x in ("prime directive","authority","truth","figure it out","build it")):return CONSTITUTION[:5000]
    return ""
