# Beldin Notepad pilot

The `windows_notepad` application is deny-by-default and exposes only three
registered operations: `open_notepad`, `create_notepad_note`, and
`close_beldin_notepad`. All are `SAFE_ACTION` operations and use the existing
confirmation and audit pipeline.

The backend dispatches through the authenticated interactive Desktop Agent.
See BELDIN_DESKTOP_AGENT_CONTROL.md for its authoritative architecture and setup.
The adapter pins the inspected Microsoft WindowsNotepad 11.2607.14.0 executable.
It accepts no executable, command line, PID, filesystem path, or UI selector.
Launch is blocked by any existing Notepad. Success requires a visible window
matching the retained launched-process handle, executable and active session.
Safe close is UNAVAILABLE: modern shared/restored/user-edited tabs cannot yet
be verified. The earlier force-termination implementation has been removed.
Successful live interactive launch is still pending user acceptance.

Text is data, not an instruction, and is bounded to 4,096 characters. Saving,
Save As, opening existing files, and arbitrary filesystem paths are not
implemented. The current service context does not have a verified bounded
Notepad text-control interface, so `create_notepad_note` returns
`UNAVAILABLE` rather than claiming that text was written. It must not be
enabled until insertion and postcondition inspection can be verified against
the actual Windows Notepad architecture.

Future adapters must reuse the registry, independent permission class,
confirmation, ownership, bounded arguments/output, postcondition verification,
and sanitized audit pattern. No generic application launcher or shell
fallback is permitted.
