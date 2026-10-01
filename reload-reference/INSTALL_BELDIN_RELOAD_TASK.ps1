$ErrorActionPreference='Stop'
$root='C:\Users\BELDIN_USER\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an\outputs\valkyrie-beldin'
$helper='C:\Users\BELDIN_USER\Documents\Codex\2026-09-12\continue-the-beldin-project-from-the\outputs\BELDIN_VERIFIED_RELOAD.ps1'
$taskName='Beldin Verified Reload'
if(-not (Test-Path -LiteralPath $helper)){throw 'Fixed helper missing.'}
$action=New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$helper+'"') -WorkingDirectory $root
$principal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null
Write-Output "Installed fixed task '$taskName'. It accepts no arguments and targets only the verified Beldin child."
