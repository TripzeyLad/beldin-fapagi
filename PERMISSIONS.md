# Permission boundary

OBSERVE: `health_snapshot` returns a cached read-only snapshot. SAFE_ACTION: `reload_config` reserved but disabled. SYSTEM_CHANGE: reserved and disabled. BLOCKED: shell always denied. No client-supplied executable, script, path, URL or command is accepted. Dispatch accepts exactly `{action: string, input: object}`. All actions use bearer authentication.

No mutating action exists, so repeated observation requests are safe and no mutation replay cache is necessary yet. Do not enable mutation by toggling the metadata flag: a separately implemented handler and tests are mandatory.

Required future SYSTEM_CHANGE handshake design (not executable in v1): authenticated proposal contains exact allowlisted action, canonical validated arguments and a unique request ID. Server creates a cryptographically random challenge bound to that proposal, requesting principal, current configuration generation and a 60-second expiry. A separate local human approval step—not the same model credential—approves that digest. Dispatch atomically consumes approval and request ID before execution, with a durable bounded journal to reject duplicates across restart. Expired, changed, replayed or unapproved proposals fail closed. Crash recovery reports indeterminate completion and never blindly retries. BLOCKED is never overridable by a challenge. No approval endpoints are exposed now.
