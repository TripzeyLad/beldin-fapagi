"""Private fixed Windows inspection for the Notepad agent; no input injection."""
import ctypes as c
from ctypes import wintypes as w
import os

class Native:
    def __init__(self):
        if os.name != "nt": raise OSError("windows_required")
        self.k = c.WinDLL("kernel32", use_last_error=True)
        self.u = c.WinDLL("user32", use_last_error=True)
        self.k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
        self.k.QueryFullProcessImageNameW.restype = w.BOOL
        self.k.ProcessIdToSessionId.argtypes = [w.DWORD, c.POINTER(w.DWORD)]
        self.k.WTSGetActiveConsoleSessionId.restype = w.DWORD
        self.u.OpenInputDesktop.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.u.OpenInputDesktop.restype = w.HANDLE
        self.u.CloseDesktop.argtypes = [w.HANDLE]
        self.u.GetUserObjectInformationW.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
        self.u.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
        self.u.IsWindowVisible.argtypes = [w.HWND]
        self.callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        self.u.EnumWindows.argtypes = [self.callback_type, w.LPARAM]

    def session_id(self):
        value = w.DWORD()
        if not self.k.ProcessIdToSessionId(os.getpid(), c.byref(value)): raise OSError("session_unavailable")
        return value.value

    def interactive(self):
        if self.session_id() == 0 or self.session_id() != self.k.WTSGetActiveConsoleSessionId(): return False
        desktop = self.u.OpenInputDesktop(0, False, 1)
        if not desktop: return False
        try:
            name = c.create_unicode_buffer(256)
            needed = w.DWORD()
            return bool(self.u.GetUserObjectInformationW(desktop, 2, name, c.sizeof(name), c.byref(needed))) and name.value == "Default"
        finally:
            self.u.CloseDesktop(desktop)

    def notepad_present(self):
        # Fixed Toolhelp snapshot. Failure is treated as ambiguous ownership.
        class Entry(c.Structure):
            _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD),
                        ("heap", c.c_size_t), ("module", w.DWORD), ("threads", w.DWORD),
                        ("parent", w.DWORD), ("priority", w.LONG), ("flags", w.DWORD),
                        ("exe", w.WCHAR * 260)]
        self.k.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
        self.k.CreateToolhelp32Snapshot.restype = w.HANDLE
        self.k.Process32FirstW.argtypes = [w.HANDLE, c.POINTER(Entry)]
        self.k.Process32NextW.argtypes = [w.HANDLE, c.POINTER(Entry)]
        self.k.CloseHandle.argtypes = [w.HANDLE]
        handle = self.k.CreateToolhelp32Snapshot(2, 0)
        if handle == c.c_void_p(-1).value: return True
        try:
            entry = Entry(); entry.size = c.sizeof(entry)
            if not self.k.Process32FirstW(handle, c.byref(entry)): return True
            while True:
                if entry.exe.casefold() == "notepad.exe": return True
                if not self.k.Process32NextW(handle, c.byref(entry)): break
            return False
        finally: self.k.CloseHandle(handle)

    def owned_windows(self, proc, expected):
        if proc.poll() is not None: return []
        name = c.create_unicode_buffer(32768); size = w.DWORD(len(name))
        if not self.k.QueryFullProcessImageNameW(int(proc._handle), 0, name, c.byref(size)): return []
        if name.value.casefold() != expected.casefold(): return []
        sid = w.DWORD()
        if not self.k.ProcessIdToSessionId(proc.pid, c.byref(sid)) or sid.value != self.session_id(): return []
        result = []
        @self.callback_type
        def visit(hwnd, unused):
            pid = w.DWORD(); self.u.GetWindowThreadProcessId(hwnd, c.byref(pid))
            if pid.value == proc.pid and self.u.IsWindowVisible(hwnd): result.append(int(hwnd))
            return True
        if not self.u.EnumWindows(visit, 0): return []
        return result if proc.poll() is None else []

