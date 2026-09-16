# Beldin roadmap v1

Derived intent, not proof of current implementation.

| Area | State | Evidence |
|---|---|---|
| Core backend, auth, bounded tools and safe actions | IMPLEMENTED | Production registry and tests |
| Voice terminal and speech loop | PARTIAL | Surface owns microphone, STT and TTS |
| Shared memory and project graph | PARTIAL | Bounded memory foundation; no full graph |
| Research and evidence chains | PLANNED | No production research engine |
| Capability discovery and tool creation | PLANNED | Registry foundation only |
| Coding workflows | PARTIAL | Fixed Beldin regression action |
| Vision, CAD and simulation | ASPIRATIONAL | No verified adapters |
| Specialist agents and long-running tasks | ASPIRATIONAL | No production orchestration |
| Financial/external side effects | PLANNED | Permission taxonomy only |
| Physical and robotic interfaces | ASPIRATIONAL | Future hardware |

## Coordinated upgrade checkpoint (2026-09-13)

The staged `/app` shell is now a responsive Control Center for PC, phone, and
tablet. It reads the authenticated `/v2/control-center` aggregate, which exposes
fresh status, bounded event/action activity, running/queued/failed task views,
explicit log availability, and permission/availability metadata for quick
controls. Unsupported service restarts remain visibly unavailable until a
verified restart identity exists.

The additive model seam is `beldin/model_router.py` (default `qwen3:8b`; no
downloads). Structured long-term events append to `memory/events.jsonl` with
kind, provenance, confidence, timestamps, and optional correction links; raw
events are retained. Existing `memory/shared.jsonl` behavior remains compatible.

This checkpoint is staged code until the verified production Beldin process is
reloaded. The reload must preserve Ollama and existing portproxy rules.

Initialization instructed the founding engineer to inspect the workstation, inventory
capabilities, propose architecture and security, and build an incremental first slice.
It is not repeated at startup.
