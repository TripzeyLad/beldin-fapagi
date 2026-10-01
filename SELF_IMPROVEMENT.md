# Beldin improving himself

## What you say
- "Beldin, fix yourself so that <what you want>" (or `/self <request>`) starts a task on the project marked `self` in `coding-projects.json`.
- "coding task status" or `/tasks` reports progress in one sentence per task.

## What he does
1. Copies himself into a disposable workspace (outside his own folder). The live system is never touched.
2. Works there with read/search/edit/test tools, validating in the no-network AppContainer sandbox.
3. If a validation or acceptance check fails he reads the failure and tries again, up to `max_attempts` (5 after `setup_local.py`) or `max_minutes` (60). Then he stops and says honestly that he could not do it. Nothing changed.
4. When a change passes, the task becomes `approval_needed` with the exact diff, files, checks and the requirement-to-evidence result.
5. Only you can approve: Control Center -> "Review and approve apply" asks for the separate approval token (memory only). Apply re-tests the exact approved bytes, writes, re-verifies and rolls back on any failure. A reload/restart to run the new code is still your verified reload step.

## What he can never change
The authority boundary is not editable by him: server/auth, safe actions, audit, the coding workflow and sandbox, the language registry, secret policy, approval gating, reload/install policy, setup, permissions and constitution docs, and their tests (`SELF_PROTECTED` in `beldin/coding.py`, plus per-project `protected` patterns). Attempts to edit them are refused; a protected change smuggled into the copy cannot be approved. Change those by hand.

## Languages
`beldin/languages.py` recognises 18 language families. Python validates from the bundled sandbox runtime. Every other language validates only when YOU provision its toolchain (no downloads happen):
`python setup_local.py --toolchain node=C:\tools\node\node.exe --toolchain go=C:\Go\bin\go.exe ...`
An unprovisioned language is reported as unverifiable, never as passed. How good the code is depends on the model in `models`; put a stronger coding model there once installed in Ollama.
Toolchain execution inside the AppContainer is written but UNTESTED on real Windows: run `BELDIN_SANDBOX_TEST=1` tests and one manual validation per toolchain before relying on it.

## Configuration lives on Valkyrie
`config.local.json` holds host, port, `token`, `approval_token` and a `surface` section (wake word, timeouts, memory, tools, speech speed). A Surface needs only three lines (`config.surface.env`, written by `setup_local.py`): `BELDIN_URL`, `BELDIN_TOKEN`, `BELDIN_APPROVAL_TOKEN`; `BELDIN_MIC_DEVICE` is optional and machine-specific. Values set locally still override.
