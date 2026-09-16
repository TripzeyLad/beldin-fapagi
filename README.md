# Valkyrie Beldin handoff

## September 12 continuation update

The live service now includes authenticated /v1/windows_health, advertised as OBSERVE. It exposes a separately cached, bounded aggregate of Windows events, without raw messages or an arbitrary-command interface. All 57 tests pass. Live missing/wrong-token rejection and the authenticated cache response pass. Both log providers currently report unavailable under the sandbox account; do not interpret this as a healthy Windows result. Existing five authenticated endpoints continue to pass.

Windows RestoreHealth completed successfully; SFC found no integrity violations; no servicing reboot required. DPS still fails with error 5 and requires an actual denied-operation trace. The GPU benchmark achieved 46.57–56.09 generation tok/s on the prior short prompt. Current Beldin process is 6304 at this checkpoint, loopback-only; startup/LAN deployment remains pending. Always verify process identity before stopping it.

## Result

Beldin 1.0.0 is running locally at `http://127.0.0.1:8765`, authenticated, with 50 passing tests and successful live health/telemetry/diagnostics/capabilities/events checks. This is a working local foundation, **not yet a proven Surface-ready LAN deployment**. No third-party dependencies were added. No existing Ollama, Qwen, Surface, JARVIS, firewall or startup files were modified.

Project directory:
`C:\Users\BELDIN_USER\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an\outputs\valkyrie-beldin`

Python verified: 3.12.14, using the existing bundled runtime shown in commands below. This runtime is managed by Codex and its path may change after updates; a durable standalone Python installation should be chosen before automatic startup is installed.

## Architecture and security

Windows metrics → bounded background collector → cached v1 JSON API → future Surface adapter. CPU/RAM/uptime use Windows APIs through Python ctypes; disk uses stdlib disk usage; NVIDIA uses fixed nvidia-smi arguments with a 1.5-second timeout; Ollama uses fixed localhost API routes, no proxies and 0.6-second socket timeouts. Provider failures are unavailable/null. Sampling happens every two seconds after the preceding sample completes. Clients must inspect sample age; >10 seconds is stale.

Requests have a three-second connection lifetime, two-second socket timeout, eight concurrent connections, bounded bodies and responses, authentication on every endpoint, no CORS, no request-content logging, no arbitrary shell/URL/path dispatch. Config requires a long bearer token. It was generated locally and never displayed. `config.local.json` is ignored by git; do not share or include it in an archive. Local config uses the directory's existing Windows permissions. There is no multi-user authorization system or TLS. Do not use on an untrusted network.

The only enabled action is a cached read-only health snapshot. All write classes are disabled. See `PERMISSIONS.md` for the required future human approval and replay-protection design. `/v1/events` retains 64 status changes in memory, resets on restart, and contains no prompts or raw process arguments. Diagnostics retain 128 successful GET route latencies (not end-to-end network timing or every rejected request). Beldin reports its own PID; Ollama process details remain explicitly unavailable, with API runtime status reported separately.

## Stage checkpoints

| Stage | Validation and outcome |
|---|---|
| 0 baseline | CPU/RAM/GPU/disk/uptime/Ollama snapshot saved; 1 MiB temporary-file round trip verified; physical disk health, board model and exact Windows edition unavailable. Inference moved to stage 7 after observing GPU contention. |
| 1 foundation | 18 automated tests passed. |
| 2 contract | 22 cumulative tests passed. Versioned server contract documented; actual Surface schema/source absent, adapter deferred. |
| 3 startup/network | 22 cumulative tests passed; Ollama answers localhost and same-host LAN IP. Windows network/firewall inventory denied; startup persistence and firewall hardening deferred. No configuration change made. |
| 4 diagnostics | 29 cumulative tests passed; deterministic thresholds, unknown/stale handling, latency retention. |
| 5 permissions | 37 cumulative tests passed; all writes disabled, future confirmation design documented. |
| 6 capabilities | 41 cumulative tests passed; discoverable endpoint/action schemas and permission classes. |
| 7 model | Two successful bounded Qwen CPU inferences; 41 cumulative tests passed; no tuning adopted. |
| 8 events | 44 cumulative tests passed; bounded polling endpoint and change detection. |
| 9 final | 50 cumulative tests passed after HTTP action/security coverage and absolute connection deadline. Static compilation passed. Live authenticated endpoints and unauthenticated rejection passed. |

## Baseline and performance

Observed CPU: AMD Ryzen 5 5600X, 12 logical processors. Usable memory 31.9 GiB; 13.8 GiB available at baseline. CPU utilization 52% over a short 100 ms sample: the PC was already busy, not idle. OS kernel build 10.0.26200, AMD64; exact edition unverified. RTX 3060, 12288 MiB VRAM, driver 616.56. Baseline GPU: 10697 MiB used, 45% utilization, 59°C. Exact board/vendor SKU was not verified.

Working C: volume: 249,362,067,456 bytes total, 46,317,576,192 bytes free. Temporary 1 MiB write+flush took 11.9 ms; cached read 0.37 ms. This is a basic file-I/O check, not physical SSD performance or health. Other drive-letter observations: G about 909 GB free, M about 1.90 TB, S about 923 GB; B about 2.8 MB and D zero as reported by PowerShell. Their types/physical mappings are unverified, so no writes or health claims were made for them. WD Black identity and motherboard remain unverified because CIM access was denied.

Ollama 0.34.0; only `qwen3:8b` installed, 5,225,388,164 bytes, Q4_K_M from installed model metadata. No model initially running. API version latency 14–16 ms. With GPU headroom only around 1.7 GB, GPU loading experiments were deferred. Two inference smoke trials used CPU only, two threads, context 2048, thinking off, temperature 0, seed 42, maximum 16 output tokens and keep_alive 0. These were request-local settings; no defaults changed.

| Trial | Wall time | Load time | Generated tokens | Generation rate |
|---|---:|---:|---:|---:|
| Tiny prompt | 21.06 s | 18.15 s | 6 | 4.87 tokens/s |
| 102-token diagnostic input | 15.93 s | 5.49 s | 16 (capped) | 4.30 tokens/s |

The second response was deliberately truncated at the cap; neither trial is a voice-quality evaluation. GPU memory remained occupied by other work, and no model remained running after the trials. No performance tuning was adopted or shown to improve GPU latency. More context, concurrency, keep-alive and alternate-model comparisons are deferred until a representative GPU baseline is possible. Nothing was downloaded or upgraded.

Raw evidence: `VALKYRIE_BASELINE.json` and `MODEL_BENCHMARK.json`. Future baseline runs overwrite the baseline JSON; copy it first if retaining historical comparisons.

## Exact commands

PowerShell:
```powershell
Set-Location 'C:\Users\BELDIN_USER\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an\outputs\valkyrie-beldin'
$beldinPython = 'C:\Users\BELDIN_USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'

# Live health check (does not print the token)
& $beldinPython .\health_check.py

# Full test suite and static compilation
& $beldinPython -m unittest discover -v
& $beldinPython -m compileall -q beldin

# Launch only if no instance is already running
& $beldinPython -m beldin.server

# Repeat bounded CPU-only model smoke test when no other model session is active
& $beldinPython .\benchmark.py
```

The live service was launched as a hidden background Python process (PID 25404 at this handoff). It is not installed as a Windows service or login task. Reboot/login persistence is not claimed. Its output contains only the listening address/version. Existing Ollama application startup was preserved. See `STARTUP_NETWORK.md` for host inspection and exact unresolved checks.

## Surface integration smoke test

From Surface, first verify the existing model path without changing it:
```powershell
Invoke-RestMethod 'http://192.0.2.10:11434/api/version' -TimeoutSec 3
Invoke-RestMethod 'http://192.0.2.10:11434/api/tags' -TimeoutSec 3
```
Then run the existing Surface voice assistant and ask it to check Valkyrie's status. The new telemetry API is intentionally not reachable from Surface yet. To complete that step: obtain Surface's `beldin_tools.py`/telemetry tests, verify its endpoint/header/schema, inspect the actual Windows Private profile and applicable firewall rules, implement/test the matching adapter and narrowly scoped LAN binding, then perform one authenticated telemetry call and one live spoken status request. Never put the token in a URL or chat. Do not infer compatibility from the shared permission names.

## Backup and rollback

All deliverables were created in a new dedicated directory; no pre-existing Beldin files were found within the inspected workspace or modified. A foundation snapshot was saved before diagnostics/action additions:
`C:\Users\BELDIN_USER\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an\work\backups\foundation-before-diagnostics.zip`

SHA-256: `9FCE544F58FA7EC50745F2B9E9103430E6F49E418052B5638FE8546786465331` (rechecked). This predates credential generation and contains no local token. It is a project checkpoint, not a backup of the existing Ollama installation.

Rollback: stop only the verified Beldin process, then archive this new project directory if desired. For the current PID, inspect identity before stopping to avoid PID reuse:
```powershell
Get-CimInstance Win32_Process -Filter 'ProcessId = 25404' | Select-Object ExecutablePath,CommandLine
# Only if the result is this project's Python -m beldin.server:
Stop-Process -Id 25404
```
If process inspection is denied, use Task Manager to verify that exact Beldin instance before ending it. Do not stop other Python or Ollama processes. No firewall/startup/model rollback is needed because none were changed.

## Next development stage

Complete the real Surface contract and Windows firewall/startup inventory, then install the narrowly scoped LAN service with a durable Python path. After one end-to-end voice/telemetry smoke test, benchmark Qwen with free GPU memory and representative full voice prompts. Keep writes disabled until a specific useful action and independent human approval flow are implemented and tested.

## Capability sprint update (September 12, 2026)

The v1 contract and authenticated endpoints are unchanged. A v2 contract is implemented behind `/v2/capabilities`, `/v2/observe`, and `/v2/actions`; it is intentionally additive so existing Surface clients remain compatible. Observe tools are bounded and server-selected: `system_status`, `process_summary`, `service_status`, `port_status`, `ollama_status`, `windows_health`, `project_status`, `file_info`, and `read_text`. File tools reject traversal, reparse escapes, denylisted secret names, and text over 64 KiB.

Two useful writes are confirmation-gated: `create_note` writes a new Markdown file only under `notes/inbox`, and `save_diagnostic_snapshot` writes a timestamped JSON snapshot only under `diagnostics`. A proposal returns a short-lived action ID; confirmation consumes it once, so stale or replayed confirmations fail closed. Arbitrary shell, process kill, service control, model download, registry/firewall edits, and reboot remain blocked.

The sprint checkpoint archive is `outputs/beldin-capability-checkpoint-20260912.zip` (SHA-256 `2A4FEDCDBF94620B72368943AD66F61901337E7D3E01C160E99D29658F705967`). The current service was live and healthy during this pass, but the sandbox denied process identity inspection; therefore the running instance was not restarted and live v2 smoke calls are pending an administrator-authorized controlled reload.

## Live v2 verification (September 12, 2026)

The existing loopback listener on port 8765 was identified as the bundled Python executable, but it served the older v1 image (`/v2/capabilities` returned 404). It was left running. The checkpointed code was started separately on `127.0.0.1:8875` and exercised with the existing bearer token; no external binding was used.

Live checks passed for authenticated `/v2/capabilities`, `system_status`, `ollama_status`, `windows_health`, `project_status`, and an allowlisted `README.md` read. `create_note` and `save_diagnostic_snapshot` each returned a confirmation challenge, executed once into `notes/inbox` and `diagnostics`, and rejected replay with 409. Missing and incorrect authorization returned 401; unknown tools, traversal, malformed action IDs, oversized payloads, and v1 health compatibility were checked. The in-memory audit recorded proposal, execution, replay/expiry events; audit state resets on process restart.

The next fixed-function SAFE_ACTION set is available behind the same confirmation gate: `run_beldin_tests` (30-second bounded fixed unittest command), `backup_beldin` (verified timestamped zip excluding local config, secrets, caches, logs and nested archives), and `ollama_model_warmup` (allowlisted `qwen3:8b`, localhost API, no download). Live execution of all three passed. `beldin_service_restart` and `ollama_service_restart` remain deferred until supported service identity and restart mechanism are independently verified; arbitrary commands, process control, model downloads, registry/firewall changes and reboot remain blocked.
