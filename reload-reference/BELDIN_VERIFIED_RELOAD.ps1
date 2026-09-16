$ErrorActionPreference='Stop'
$root='C:\Users\BELDIN_USER\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an\outputs\valkyrie-beldin'
$python='C:\Users\BELDIN_USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe'
$supervise=Join-Path $root 'supervise.py'
$lines=@(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8765 -State Listen)
if($lines.Count -ne 1){throw 'Beldin listener is missing or ambiguous.'}
$old=[int]$lines[0].OwningProcess
if($old -eq 1860){throw 'Refusing portproxy/system PID.'}
$p=Get-CimInstance Win32_Process -Filter "ProcessId=$old"
if($p.ExecutablePath -ne $python -or $p.CommandLine -notmatch '(?i)-B\s+-m\s+beldin\.server\s*$'){throw 'Beldin child identity mismatch.'}
$parent=Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ParentProcessId)"
if($parent.ExecutablePath -ne $python -or $parent.CommandLine -notmatch [regex]::Escape($supervise)){throw 'Supervisor identity mismatch.'}
$again=@(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8765 -State Listen)
if($again.Count -ne 1 -or $again[0].OwningProcess -ne $old){throw 'Listener changed during checks.'}
Stop-Process -Id $old -Force -Confirm:$false
$new=$null
for($i=0;$i -lt 40;$i++){Start-Sleep -Seconds 1;$x=@(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue);if($x.Count -eq 1 -and $x[0].OwningProcess -ne $old){$new=[int]$x[0].OwningProcess;break}}
if($null -eq $new){throw 'Supervisor did not respawn Beldin within 40 seconds.'}
$np=Get-CimInstance Win32_Process -Filter "ProcessId=$new"
if($np.ExecutablePath -ne $python -or $np.CommandLine -notmatch '(?i)-B\s+-m\s+beldin\.server\s*$'){throw 'Replacement identity mismatch.'}
Write-Output "Verified Beldin reload: $old -> $new"


