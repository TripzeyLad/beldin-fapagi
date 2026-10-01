# Disable only this agent and remove only its verified per-user shortcut.
$ErrorActionPreference = 'Stop'
if ($args.Count -ne 0) { throw 'This remover accepts no arguments.' }
if ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne 'REPLACE_WITH_LOCAL_ACCOUNT_SID') {
    throw 'Run as the intended Valkyrie user.'
}
$root = 'C:\Users\BELDIN_USER\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an\outputs\valkyrie-beldin'
$python = 'C:\Users\BELDIN_USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe'
$linkPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Beldin Desktop Agent.lnk'
if (Test-Path -LiteralPath $linkPath) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($linkPath)
    if ($link.TargetPath -ne $python -or $link.Arguments -ne '-B -m beldin.desktop_agent' -or $link.WorkingDirectory -ne $root) {
        throw 'Shortcut identity mismatch.'
    }
}
$configPath = Join-Path $root 'config.desktop.json'
if ((Get-Item -LiteralPath $configPath).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unexpected config link.' }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$config.enabled = $false
[IO.File]::WriteAllText($configPath,($config | ConvertTo-Json -Compress),[Text.UTF8Encoding]::new($false))
if (Test-Path -LiteralPath $linkPath) { Remove-Item -LiteralPath $linkPath }
'Desktop agent disabled; it will exit after its current bounded request. Notepad windows remain untouched. Secret retained for reinstall.'
