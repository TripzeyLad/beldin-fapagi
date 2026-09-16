# Valkyrie production audit — 2026-09-12

## Deployment state

Root: C:\Users\BELDIN_USER\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an\outputs\valkyrie-beldin

Source changes in this pass are saved and tested but NOT loaded in the running
process. Child PID 14580 remains on the previous version: Windows denied stop.
Expected scheduled task is Valkyrie Local Services, running supervise.py through
the bundled pythonw.exe. Current executable and loopback listener match; current
task/parent inspection via CIM is denied. The user-provided task identity was not
independently revalidated this pass. No duplicate child can be conclusively ruled
out without process inventory privileges.

Portproxy remains 192.0.2.10:8765 -> 127.0.0.1:8765 and
192.0.2.10:11434 -> 127.0.0.1:11434, PID 1860. Ollama PID 8692 is unchanged.

## PRESENT AND VERIFIED

Running production: public exact GET bootstrap paths /app, /app/, /app/app.js,
/app/manifest.json, /app/sw.js return 200 on loopback and same-host LAN address.
Anonymous /health, /v1/telemetry and /v2/capabilities return 401 on both.
Authenticated /v2/capabilities, /v2/node, /v2/action-history return 200 on both.
Installed Ollama tags include qwen3:8b.

Source inspection: authenticated v1 routes, v2 observe/actions/route/heartbeat,
bounded connection slots/timeouts, body/header/output bounds, mobile sessionStorage
token entry and Authorization headers, fixed local Ollama URL and model targeting.
Grounding bypasses Qwen for recognized state questions. Static serving uses an
exact dictionary, never a user-derived filesystem path.

Nine original observations: system_status, process_summary, service_status,
port_status, file_info, read_text, windows_health, ollama_status, project_status.
Availability in the registry does not establish provider success. Windows service
inventory is restricted to Ollama/Beldin names, which may not correspond to installed
Windows services; unavailable is expected. System metrics can be unavailable.

Five fixed confirmation-gated actions exist: create_note,
save_diagnostic_snapshot, run_beldin_tests, backup_beldin, ollama_model_warmup.
No live state-changing action was executed for this audit.
v1 registry represents OBSERVE, SAFE_ACTION, SYSTEM_CHANGE, BLOCKED; system changes
and shell are disabled. v2 exposes only specific observations and safe actions.

In-memory action audit is capped at 128 (64 returned); events at 64; latency at 128.
Confirmation removes the proposal before execution and expires after 60 seconds.
Public HTML/JS contains token-entry logic, not a canonical identity prompt.

## MISSING AND FIXED — saved source, pending reload

BELDIN_IDENTITY.md is now the single production identity source. No accessible
historical identity file was found in Documents/Codex; the Surface file was not
available. The user's personality specification is authoritative for this version.
identity.py loads it as the first system message for ordinary model calls.
Client system messages are demoted to user messages, preserving content.
Grounded current-state replies still precede model dispatch.

Added cancellation through /v2/actions op=cancel, and a 128 pending-proposal cap.
Added node_status and action_history observation aliases for existing endpoints.
These restore the intended historical observation areas without adding app control.

## PRESENT BUT UPDATED/REPAIRED — saved source, pending reload

Tool-call fields and raw JSON/XML call markers are suppressed before chat text is
returned. No model call is automatically executed; clients retain explicit
proposal/confirmation responsibility. This is defensive suppression, not a general
Qwen tool dispatcher.

Process summary now parses Windows CSV using csv.reader instead of json.loads.
Shared secret exclusions cover config.* and .env* variants plus common key files;
read/file-info tools and sanitized backup actions share that policy. Backup action
skips symlinks and resolved paths outside root. Config files and production tokens
were not edited.

Action validation now rejects malformed note titles, extra note fields, nonempty
snapshot arguments and invalid action names. Invalid confirmation IDs are rejected
without logging arbitrary client input.

92 production tests pass, including identity prompt injection for six identity
questions, ordinary chat, tool-text suppression, secret variants, cancellation,
pending bounds, process parsing, aliases, and prior grounding/bootstrap/auth/action
regressions. These are deterministic tests, not proof of every possible model reply.
Two real installed-model requests with the new context identified Beldin and
distinguished Qwen3 8B. They bypassed HTTP production to test the pending context;
authenticated production identity after reload is NOT yet verified.

## INTENTIONALLY DEFERRED / REMAINING AUDIT GAPS

- Production reload and post-reload loopback/LAN authenticated chat/identity/observe
  smoke tests require the privileged reload. Phone end-to-end remains user testing.
- Node endpoint stores the latest single heartbeat in state.node, overwriting its
  original Valkyrie metadata. It is not a multi-peer node inventory. Thirty-second
  freshness exists, but this design must be reconciled with the current Surface
  contract before changing response semantics.
- No durable audit/approval journal, principal-bound independent human approval
  credential, or crash-outcome reconciliation. Restart loses pending approvals
  (old IDs fail closed), history and cancellation records.
- Safe-action execution failures are not uniformly caught/audited. Timestamp-only
  note/snapshot names can collide. Backup/test subprocess bounds are partly
  post-hoc: backup size and captured test output are checked after collection.
- File tools constrain paths to the project root, not an explicit per-file allowlist.
  Secret-name exclusions cannot guarantee arbitrary renamed secrets are excluded.
- v2 JSON parsing still accepts duplicate keys/nonstandard JSON values unlike v1;
  schemas are generic. Routing uses broad substring rules outside the narrow state
  matcher; the grounding matcher is not exhaustive for arbitrary paraphrases.
- A duplicate unreachable v2/actions branch remains; no wholesale server rewrite.
- Historical surface_client.py is a handoff helper, not evidence of deployment on
  Surface; do not overwrite the current verified Surface implementation.
- Historical CAPABILITY_MANIFEST.json and SELF_KNOWLEDGE.md were not copied blindly:
  their claims exceed some runtime guarantees. /v2/capabilities is the production
  machine-readable inventory; this audit is the current human-readable status.
- No completed per-app registry/schema was found in the searched relevant outputs.
  No app adapters or new application-control authority were added.
- Legacy README/API statements remain historical; use this dated audit for current
  evidence. This pass does not establish exhaustive Windows health or startup recovery.

Historical references inspected: 2026-09-12/referenced-chatgpt-conversation-this-is-an-4/
outputs/valkyrie-beldin/{SELF_KNOWLEDGE.md,surface_client.py}; capability manifest
located there. Original mobile package and staged routing lineage were located in
prior passes; working production mobile assets were retained.

Changed production files: BELDIN_IDENTITY.md, PRODUCTION_AUDIT.md,
beldin/identity.py, beldin/mobile.py, beldin/secret_policy.py, beldin/tools.py,
beldin/safe_actions.py, beldin/server.py, test_identity.py, test_audit_repairs.py.

Backup: outputs/identity-audit-backup-20260912-180120 in the continuation task.
All 66 source files had matching SHA-256 copies before edits. Contains secrets:
keep local and private. Rollback material is available; privileged reload is needed.
