# Fixed per-user installer. Run in Valkyrie's logged-in user session.
$ErrorActionPreference = 'Stop'
if ($args.Count -ne 0) { throw 'This installer accepts no arguments.' }
$root = 'C:\Users\BELDIN_USER\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an\outputs\valkyrie-beldin'
$python = 'C:\Users\BELDIN_USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe'
$expectedSid = 'REPLACE_WITH_LOCAL_ACCOUNT_SID'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($identity.User.Value -ne $expectedSid -or (Get-Process -Id $PID).SessionId -eq 0) {
    throw 'Run as the intended logged-in Valkyrie user.'
}
foreach ($path in @($root,$python,(Join-Path $root 'beldin\desktop_agent.py'))) {
    $item = Get-Item -LiteralPath $path
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unexpected reparse point.' }
}
$configPath = Join-Path $root 'config.desktop.json'
$existingConfig = Test-Path -LiteralPath $configPath
if ($existingConfig) {
    if ((Get-Item -LiteralPath $configPath).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unexpected config link.' }
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if ($config.version -ne 1 -or $config.secret -notmatch '^[a-f0-9]{64}$') { throw 'Invalid existing agent config.' }
} else {
    # Apply ACL to an empty file before writing the separately generated secret.
    New-Item -ItemType File -Path $configPath | Out-Null
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $config = [pscustomobject]@{version=1;secret=([BitConverter]::ToString($bytes).Replace('-','').ToLowerInvariant());enabled=$true}
}
$acl = New-Object Security.AccessControl.FileSecurity
$acl.SetAccessRuleProtection($true,$false)
foreach ($sid in @($expectedSid,'S-1-5-18')) {
    $rule = New-Object Security.AccessControl.FileSystemAccessRule(
        (New-Object Security.Principal.SecurityIdentifier($sid)),
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow)
    $acl.AddAccessRule($rule)
}
$fileInfo = [IO.FileInfo]::new($configPath)
if ($PSVersionTable.PSEdition -eq 'Core') {
    [IO.FileSystemAclExtensions]::SetAccessControl($fileInfo,$acl)
} else {
    $fileInfo.SetAccessControl($acl)
}
if (-not $existingConfig -or $config.enabled -ne $true) {
    $config.enabled = $true
    [IO.File]::WriteAllText($configPath,($config | ConvertTo-Json -Compress),[Text.UTF8Encoding]::new($false))
}
$startup = [Environment]::GetFolderPath('Startup')
if (-not $startup.StartsWith('C:\Users\BELDIN_USER\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected startup directory.' }
$linkPath = Join-Path $startup 'Beldin Desktop Agent.lnk'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($linkPath)
if ((Test-Path -LiteralPath $linkPath) -and
    ($link.TargetPath -ne $python -or $link.Arguments -ne '-B -m beldin.desktop_agent' -or $link.WorkingDirectory -ne $root)) {
    throw 'Existing shortcut has unexpected identity.'
}
$link.TargetPath = $python
$link.Arguments = '-B -m beldin.desktop_agent'
$link.WorkingDirectory = $root
$link.WindowStyle = 7
$link.Description = 'Authenticated Beldin interactive desktop agent'
$link.Save()
$verify = $shell.CreateShortcut($linkPath)
if ($verify.TargetPath -ne $python -or $verify.Arguments -ne '-B -m beldin.desktop_agent' -or $verify.WorkingDirectory -ne $root) {
    throw 'Shortcut verification failed.'
}
# The fixed listener rejects a duplicate agent. No unrelated process is stopped.
Start-Process -FilePath $python -ArgumentList '-B -m beldin.desktop_agent' -WorkingDirectory $root -WindowStyle Hidden
'Installed fixed per-user startup shortcut; agent launch requested. Verify authenticated health.'
