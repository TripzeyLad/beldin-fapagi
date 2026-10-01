# Beldin reload control

Work/Codex runs as FRONTROOM\\CodexSandboxOffline at medium integrity with
only SeChangeNotifyPrivilege. It cannot terminate the verified Python Beldin
child PID 8088; this reproduces Access is denied. Task and CIM details are
denied to this caller. This establishes that the caller lacks PROCESS_TERMINATE;
an elevated inspection is required to distinguish task principal, token and DACL.

The selected mechanism is a fixed scheduled task installed once by an
administrator. BELDIN_VERIFIED_RELOAD.ps1 accepts no parameters. It checks the
single loopback 8765 listener, refuses PID 1860, verifies the exact bundled
pythonw executable, -B -m beldin.server, production supervisor parent and
production root, rechecks the listener, stops only that child, and verifies a
different matching respawn. It cannot select a PID, command, executable, task,
service, portproxy or Ollama target.

One-time elevated setup command:

    & 'C:\Users\BELDIN_USER\Documents\Codex\2026-09-12\continue-the-beldin-project-from-the\outputs\INSTALL_BELDIN_RELOAD_TASK.ps1'

Future Work/Codex action:

    schtasks.exe /run /tn "Beldin Verified Reload"

The previous failure was caused by interactive Stop-Process confirmation under
PowerShell -NonInteractive, not insufficient SYSTEM privilege. The authoritative
helper uses Stop-Process -Id $old -Force -Confirm:$false after all identity gates.
The temporary diagnostic trap and Windows Temp log were removed. Verify a run with
Get-ScheduledTaskInfo -TaskName "Beldin Verified Reload" and require
LastTaskResult = 0. Then verify 127.0.0.1:8765 belongs to the replacement Beldin
child while 192.0.2.10:8765 remains the existing system portproxy PID 1860.
The installation command must run from Administrator PowerShell. Normal future
reload is: schtasks.exe /run /tn "Beldin Verified Reload".
