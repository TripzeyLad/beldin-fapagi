# Beldin Interactive Desktop Agent

Status: bridge implemented and tested; interactive agent installed. Production backend reload requires the authorized Administrator context. Successful visible Notepad launch and safe modern-Notepad close are NOT verified.

## Architecture and authority

Authenticated clients use the unchanged /v1/chat interface. Server-side Notepad intent selection calls the existing safe-action proposal/confirmation system. Only a confirmed registered action reaches the loopback desktop bridge. /v2/route remains a planning endpoint; /v2/actions uses the same confirmation gate.

The Desktop Agent is a fixed execution component, not a model. It listens only on 127.0.0.1:8766. The backend remains on 127.0.0.1:8765. Surface/phone do not connect to the agent and require no Notepad-specific code when they already send chat history to /v1/chat.

The existing single bearer token defines the trusted client boundary. This is not a multi-user identity or per-user RBAC system.

## Transport and credentials

A separate randomly generated local secret is stored in config.desktop.json, readable only by the intended Windows account and SYSTEM. It is excluded by the existing config-file observation/backup deny policy and by .gitignore. It is never embedded in the mobile shell, passed on the command line, or transmitted as a bearer credential.

Requests and responses use HMAC-SHA256 over exact JSON bytes. Responses must match the request nonce. The backend uses fixed URLs, no proxies, no redirects, bounded reads and a three-second timeout. Requests use version 1, adapter notepad, an explicit registered operation, UUID invocation ID, a short timestamp window, agent startup epoch, and bounded args. Unknown/duplicate fields, arbitrary PID/HWND/path/command/selector and unknown adapter/operation are rejected.

The agent records up to 256 recently consumed invocation IDs for 60 seconds. It consumes before execution, never retries an uncertain action, and rejects requests issued for another agent startup epoch. Restart invalidates old requests. Audit on the backend retains the existing bounded 128-entry history; note contents are not recorded.

## Startup and lifecycle

INSTALL_BELDIN_DESKTOP_AGENT.ps1 accepts no arguments. It targets the fixed production root, bundled pythonw.exe and intended user SID. It creates a fixed per-user Startup shortcut named Beldin Desktop Agent.lnk, with arguments -B -m beldin.desktop_agent and the production working directory. No administrator task, general command runner, elevated principal or service change is created.

Reinstall preserves the secret. The installer explicitly sets only the credential file DACL. It does not require SeSecurityPrivilege. A fixed exclusive listening socket prevents a second agent from taking over the port. Windows login starts the shortcut. A real logoff ends the user process; console-session changes cause the agent to exit. Lock/noninteractive desktops reject execution. An unexpected crash requires rerunning the fixed installer or logging in again; there is no crash-restart supervisor in this version.

REMOVE_BELDIN_DESKTOP_AGENT.ps1 accepts no arguments, disables this agent in its own config, removes only its identity-checked shortcut, and lets the agent exit after its bounded request. It retains the secret and leaves Notepad windows untouched.

## Session evidence

Inspected on this pass: Explorer, the existing Beldin supervisor and backend are all in session 1. The supervisor uses the normal user interactive token with limited run level. Backend PID was 17600; supervisor PID 15184. The failure was not established as Session 0 isolation. The chat path previously lacked action dispatch.

The installed agent was verified online and interactive in session 1. Session ID and timestamp are returned only through authenticated health. The backend probes health on demand; there is no stale heartbeat cache pretending the agent remains online. The online state is separate from each operation's current availability.

## Notepad scope and ownership

The inspected installed package is Microsoft.WindowsNotepad 11.2607.14.0. The adapter pins its exact Microsoft WindowsApps executable path. An update changing that path makes the adapter unavailable pending a reviewed update.

OPEN_NOTEPAD:
- Only the fixed pinned executable, with no user arguments, can launch.
- Any existing Notepad process blocks launch before execution. This deliberately avoids assuming modern Notepad's process/tab reuse behavior.
- Only the Popen-owned process handle is considered; an exiting activation stub does not confer ownership of another process.
- Process image path, active session, and exactly one visible top-level window must match.
- Result is VERIFIED_SUCCESS only after those checks. A launch attempt alone yields no success claim.
- Session metadata includes invocation ID, retained process object, launch time, generated session ID and observed window handle.
- Concurrent external user activity remains a limitation; no operation may discard or overwrite user contents.

CLOSE_BELDIN_NOTEPAD is unavailable. The previous force-termination implementation was removed. Modern Notepad may contain restored or user-edited tabs; current code cannot verify safe per-tab close.

CREATE_NOTEPAD_NOTE is unavailable. Text is validated as literal data, limited to 4096 characters and transport bounds. No insertion, saving, existing-file opening or generic input automation occurs.

Thus the requested smoke with an existing user Notepad is currently a truthful refusal test, not proof of isolated second-window control. Broad application control remains unimplemented.

## Confirmation and responses

All desktop actions remain SAFE_ACTION with explicit confirmation. Parameters are copied into pending state, expire after 60 seconds and are consumed once. Chat confirmations use a request-specific approval marker and preceding user-message digest; a bare yes does not approve another conversation's pending action. Clients must preserve returned assistant messages, as the mobile client already does. Cancellation, expiry and replay remain enforced.

The backend checks app registry and global desktop enabled state again at dispatch. Lost responses produce UNVERIFIABLE with no automatic retry. Ordinary Notepad questions remain normal conversation. Canonical identity and live machine status continue through their existing paths.

## Current capability truth and API

/v2/desktop-health is authenticated.
/v2/app-capabilities aggregates authenticated agent health with the registry.
/v1/chat current-capability answers consult fresh agent availability.
Registered code does not imply an operation is currently available.

Agent unavailable: state unavailable and no model claim of execution.
Existing Notepad: agent online, open unavailable.
No existing Notepad + accessible pinned executable + interactive desktop: launch may be attempted after confirmation; runtime verification still determines success.

## Deployment and manual verification

The agent startup is already installed. The backend reload request returned Windows Access Denied. Run this exact existing mechanism in the previously authorized Administrator PowerShell context:

    schtasks.exe /run /tn "Beldin Verified Reload"

Wait for completion, then check:

    Get-ScheduledTaskInfo -TaskName "Beldin Verified Reload"

LastTaskResult must be 0. 267009 / 0x41301 means still running. Verify the backend PID changes and the existing LAN portproxy remains PID 1860. Do not manually terminate the backend.

Run outputs/VERIFY_DESKTOP_BRIDGE.py using the bundled Python in the authorized user context. /v2/desktop-health must change from the current live 404 to 200.

Manual application check:
1. Keep an existing user Notepad open. Ask Open Notepad. Expect unavailable; existing contents must remain untouched.
2. Save/close that user Notepad yourself only if you wish to test launch.
3. Ask Open Notepad from a client using /v1/chat, then yes. Check for a visible new window and truthful verified result.
4. Ask Close the Notepad you opened. Expect unavailable. Close the test window manually.
5. Ask What is Notepad. Expect conversation, no launch.
6. Ask What can you do right now. Availability should reflect the current agent/session.
7. Use the fixed remover, check offline refusal, then installer and check reconnect.

Live creation and modern per-tab close remain acceptance blockers. Surface transport itself has not been inspected here: a client calling Ollama directly will not gain backend dispatch. No Surface/phone code was changed.

## Future adapter checklist

NO FUTURE DESKTOP ADAPTER MAY BYPASS THE DESKTOP AGENT + PERMISSION + OWNERSHIP + VERIFICATION PIPELINE.

- Register one explicit adapter and operation schema; reject extra fields.
- Fix executable/interface selection in reviewed code, never model input.
- Classify permissions independently; preserve explicit confirmation for state changes.
- Bound arguments, runtime, response and audit retention.
- Keep data inert, and do not log note contents or credentials.
- Retain ownership handles/creation identity and verify session/window relationships.
- Prove separation from existing user instances before enabling close or edits.
- Verify postconditions and return UNVERIFIABLE for ambiguous or lost outcomes.
- Test replay, stale health, disabled registry, global disable, restart and response tampering.
- Conduct live interactive acceptance before advertising AVAILABLE.
- Do not add generic shell, arbitrary PID/process control, unrestricted GUI selectors or arbitrary filesystem access.
