"""Fixed, read-only Windows event summary; stdlib only; no raw event messages.

Run using an explicit trusted Python path. No arguments, endpoints or repairs.
Each fixed log query has a 15 second timeout and 2,001-record fetch cap.
For future Beldin integration, invoke outside the request handler and cache it.
"""
import json
import os
from pathlib import Path
import subprocess
import threading
import time


def sanitize(value):
    """Allow only aggregate counts; discard arbitrary messages/paths/extra keys."""
    result = {"schema_version": 1, "window_days": 14, "logs": {}}
    for name in ("System", "Application"):
        item = value.get("logs", {}).get(name, {}) if isinstance(value, dict) else {}
        if not isinstance(item, dict) or item.get("available") is not True:
            result["logs"][name] = {"available": False, "reason": "query_unavailable"}
            continue
        groups = []
        for row in item.get("groups", [])[:40]:
            if not isinstance(row, dict): continue
            source, event_id, count = row.get("source"), row.get("event_id"), row.get("count")
            if (isinstance(source, str) and 0 < len(source) <= 128
                and all(c.isascii() and (c.isalnum() or c in " ._-") for c in source)
                and type(event_id) is int and 0 <= event_id <= 65535
                and type(count) is int and 0 <= count <= 2000):
                groups.append({"source": source, "event_id": event_id, "count": count})
        sampled = item.get("sampled_events")
        result["logs"][name] = {"available": True,
            "sampled_events": min(2000, max(0, sampled)) if type(sampled) is int else None,
            "truncated": item.get("truncated") is True, "groups": groups}
    return result


class HealthCache:
    def __init__(self, provider=None):
        self.provider = provider or summarize
        self.lock = threading.Lock()
        self.value = None
        self.sampled = None

    def refresh(self):
        try: value = sanitize(self.provider())
        except Exception: value = sanitize({})
        with self.lock:
            self.value, self.sampled = value, time.time()

    def read(self):
        with self.lock:
            return {"observed": self.value, "sampled_at_unix": self.sampled,
                    "age_seconds": max(0, time.time()-self.sampled) if self.sampled else None,
                    "refresh_interval_seconds": 60, "stale_after_seconds": 120}


def summarize():
    if os.name != "nt":
        return {"available": False, "reason": "windows_required"}
    shell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    # Do not inherit PowerShell 7's module search path into Windows PowerShell 5.1.
    query_env = os.environ.copy()
    query_env["PSModulePath"] = str(shell.parent / "Modules")
    result = {"schema_version": 1, "window_days": 14, "logs": {}}
    for log in ("System", "Application"):
        script = r"""
$ErrorActionPreference='Stop'
try {
  $rows=@(Get-WinEvent -FilterHashtable @{LogName='LOG_NAME';Level=1,2;StartTime=(Get-Date).AddDays(-14)} -MaxEvents 2001)
  $capped=$rows.Count -gt 2000
  $rows=@($rows | Select-Object -First 2000)
  $groups=@($rows | Group-Object ProviderName,Id | Sort-Object Count -Descending | Select-Object -First 40 | ForEach-Object {
    [pscustomobject]@{source=$_.Group[0].ProviderName;event_id=$_.Group[0].Id;count=$_.Count}
  })
  @{available=$true;sampled_events=$rows.Count;truncated=$capped;groups=$groups} | ConvertTo-Json -Depth 5 -Compress
} catch {
  if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') {
    @{available=$true;sampled_events=0;truncated=$false;groups=@()} | ConvertTo-Json -Compress
  } else {
    @{available=$false;reason='query_failed_or_access_denied'} | ConvertTo-Json -Compress
  }
}
""".replace("LOG_NAME", log)
        try:
            completed = subprocess.run(
                [str(shell), "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
                env=query_env,
            )
            if completed.returncode or len(completed.stdout) > 65536:
                raise ValueError("invalid_result")
            result["logs"][log] = json.loads(completed.stdout.decode("utf-8-sig"))
        except subprocess.TimeoutExpired:
            result["logs"][log] = {"available": False, "reason": "timeout"}
        except (OSError, ValueError, UnicodeError):
            result["logs"][log] = {"available": False, "reason": "query_unavailable"}
    return result


if __name__ == "__main__":
    print(json.dumps(summarize(), indent=2))
