"""Notepad desktop operations. No backend process control or caller paths."""
import subprocess
import time
import uuid
from pathlib import Path

# Version pinned to the installed Microsoft package inspected on Valkyrie.
NOTEPAD = Path(r"C:\Program Files\WindowsApps\Microsoft.WindowsNotepad_11.2607.14.0_x64__8wekyb3d8bbwe\Notepad\Notepad.exe")
MAX_TEXT_CHARS = 4096

class Adapter:
    def __init__(self, native):
        self.native = native
        self.owned = None

    def health(self):
        interactive = self.native.interactive()
        installed = NOTEPAD.is_file()
        isolated = interactive and installed and not self.native.notepad_present()
        return {"interactive": interactive, "session_id": self.native.session_id(),
                "operations": {"open_notepad": isolated,
                               "close_beldin_notepad": False, "create_notepad_note": False},
                "limitation": "Existing Notepad blocks launch; safe per-tab close and text insertion unavailable."}

    def execute(self, operation, args, invocation_id):
        if not self.native.interactive():
            return {"state": "UNAVAILABLE", "error": "interactive_session_unavailable"}
        if operation == "create_notepad_note":
            return create_note(None, args.get("text"))
        if operation == "close_beldin_notepad":
            # Modern Notepad can contain restored/user-edited/shared tabs. A
            # process handle alone never authorizes discarding their contents.
            return {"state": "UNAVAILABLE", "error": "safe_notepad_close_unavailable"}
        if operation != "open_notepad" or args:
            return {"state": "FAILED", "error": "invalid_operation"}
        if not NOTEPAD.is_file():
            return {"state": "UNAVAILABLE", "error": "notepad_version_unavailable"}
        if self.native.notepad_present():
            return {"state": "UNAVAILABLE", "error": "existing_notepad_requires_isolation"}
        if self.owned is not None and self.owned["process"].poll() is None:
            return {"state": "UNAVAILABLE", "error": "managed_session_already_active"}
        try:
            proc = subprocess.Popen([str(NOTEPAD)], shell=False, close_fds=True)
            end = time.monotonic() + 2
            while time.monotonic() < end:
                if proc.poll() is not None:
                    break  # Never adopt a process activated by a launcher.
                windows = self.native.owned_windows(proc, str(NOTEPAD))
                if len(windows) == 1 and self.native.interactive():
                    session = "np-" + uuid.uuid4().hex
                    self.owned = {"session_id": session, "process": proc, "window": windows[0],
                                  "invocation_id": invocation_id, "created": time.time()}
                    return {"state": "VERIFIED_SUCCESS", "session_id": session,
                            "verification": "owned_process_visible_window"}
                if len(windows) > 1:
                    break
                time.sleep(0.05)
        except (OSError, ValueError):
            return {"state": "FAILED", "error": "notepad_launch_failed"}
        return {"state": "UNVERIFIABLE", "error": "notepad_window_ownership_unverified"}


def create_note(state, text):
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
        return {"state": "FAILED", "error": "text_too_long_or_empty", "max_text_chars": MAX_TEXT_CHARS}
    return {"state": "UNAVAILABLE", "error": "verified_notepad_text_interface_unavailable"}


def open_notepad(state):
    return {"state": "UNAVAILABLE", "error": "desktop_dispatch_required"}


def close_notepad(state, session_id):
    return {"state": "UNVERIFIABLE", "error": "safe_notepad_close_unavailable"}
