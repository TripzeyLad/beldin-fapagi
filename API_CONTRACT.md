# Beldin API v1

Status: new server contract; the actual Surface client source and handoff attachment were not available. No claim of existing-client compatibility. Retrieve `beldin_tools.py` and its telemetry tests from Surface before writing an adapter.

Every endpoint requires `Authorization: Bearer <local token>`. Never put the token in a URL. No CORS headers. JSON responses have `api_version: "1"`. Additive keys may appear within v1; breaking changes require v2.

GET `/health` and `/v1/health`: service liveness, service version and service uptime. Liveness does not imply healthy hardware or reachable Ollama.

GET `/v1/telemetry`, `/v1/hardware`, `/v1/ollama`: same stable snapshot envelope, with `observed`, `sampled_at_unix`, `age_seconds`, and `service_uptime_seconds`. Observed keys: cpu, ram, disk, gpu, ollama, os, system_uptime_seconds. Each metric provider uses `{available: true, data: ...}` or `{available: false, data: null, reason: <stable code>}`. Individual unobservable fields are null. CPU is a 100 ms system-wide sample; memory and disk use bytes, GPU memory uses MiB, temperature Celsius, load percentages 0–100. Disk health is explicitly unobserved.

The collector refreshes every two seconds after collection completes. Clients must treat age >10 seconds as stale, and must not turn null into zero. Responses use cached observations and do not trigger hardware probes.

GET `/v1/diagnostics`: snapshot plus `assessment` (explicitly derived, fixed thresholds), bounded latency history, and scoped process status. GET `/capabilities` and `/v1/capabilities`: observation/action names, permission classes, input schema summaries and availability. GET `/v1/events`: up to 64 change events, monotonic IDs within one process lifetime, reset on restart. Poll and deduplicate locally; no long-lived stream or sensitive logs.

POST `/v1/actions`: Content-Type application/json, body at most 4096 bytes, exactly `{action: "health_snapshot", input: {}}`. Returns permission OBSERVE and cached result. All write actions disabled. Duplicate JSON keys and non-standard constants rejected. 403 means disabled/blocked, 413 oversized body, 415 wrong content type.

Limits: 8 simultaneous connections, socket timeout 2 seconds and total connection lifetime 3 seconds, path 256 characters, accepted headers 8 KiB (stdlib parser also enforces line/count limits), response 256 KiB, no GET bodies, no transfer encoding, no duplicate authorization or content-length. Exact routes only, no arbitrary paths or upstream URLs.

Errors are JSON with `api_version` and `error`. 400 malformed/framing, 401 missing/bad authorization, 404 unknown route, 405 unsupported method, 431 header/path limit, 503 response bound. Over-capacity connections are closed. Secrets, prompts and raw process arguments are never logged. HTTP is currently loopback-only; do not transmit bearer credentials across an untrusted network.
# Windows health extension (September 12)

Authenticated GET /v1/windows_health is an additive OBSERVE endpoint, advertised in /v1/capabilities. Existing endpoint schemas remain unchanged. No request parameters or shell commands are accepted.

The response has api_version "1", observed, sampled_at_unix, age_seconds, refresh_interval_seconds (60), and stale_after_seconds (120). Before the first collection observed and timestamps are null. Treat age over 120 seconds as stale. Each collection queries only System and Application critical/error events from the preceding 14 days, capped at 2,000 events per log and 40 provider/event-ID groups. Each subprocess has a 15-second timeout. Collection runs outside request handlers and outside the fast hardware collector.

observed contains schema_version 1, window_days 14, and logs.System / logs.Application. A successful log contains available true, sampled_events, truncated, and groups of source/event_id/count. An inaccessible log reports available false with a fixed reason. Raw messages, paths, usernames and extra provider fields are never returned. Missing access means unknown, never healthy or zero events. In the current sandbox-launched process both event queries are unavailable; collection under the intended normal user still needs validation.

Surface can consume this additive server contract when its actual client is available; client compatibility has not been demonstrated.
