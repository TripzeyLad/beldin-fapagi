# Startup and network inspection

Ollama 0.34.0 is running as the desktop application (ollama app plus ollama processes). A pre-existing Ollama.lnk is in `C:\Users\BELDIN_USER\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`. Its working directory resolves to `C:\Users\BELDIN_USER\AppData\Local\Programs\Ollama`; target resolution was unavailable in this session. Do not create a duplicate startup entry. Login/reboot startup remains unproven.

Local GET `/api/version` succeeds on both 127.0.0.1:11434 and 192.0.2.10:11434. WiFi is 192.0.2.10/24, gateway 192.0.2.1. This proves same-host LAN-address reachability only, not inbound Surface connectivity. Ethernet is disconnected.

CIM, Get-NetTCPConnection, Get-NetConnectionProfile and Get-NetFirewallRule returned access denied, including after requesting additional filesystem/network access. No firewall rules, registry settings, Ollama environment, models or startup entries changed. The exact bind address and inbound firewall exposure are not verified. netstat returned no usable evidence in this restricted session.

Stage 3 is deferred for the parts requiring inventory access. New Beldin service remains loopback-only. Do not enable LAN binding until the Surface address and Private network profile are verified and existing applicable allow rules are inspected. A narrower new rule alone cannot cancel a broader existing allow rule.

Next host-side inspection (PowerShell with appropriate Windows inventory rights):
```powershell
Get-NetConnectionProfile
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 11434,8765
Get-NetFirewallRule -Enabled True -Direction Inbound | Get-NetFirewallApplicationFilter
Get-NetFirewallRule -Enabled True -Direction Inbound | Get-NetFirewallPortFilter
Get-NetFirewallRule -DisplayName '*Ollama*' | Format-List *
```
Inspect matching rules' address, port, application and profile filters before specifying exact changes. Back up those rules and restore their exact prior values on rollback. No rollback of host configuration is currently needed.

References checked: https://docs.ollama.com/windows and https://docs.ollama.com/faq. The installed Windows application already provides background operation; a second `ollama serve` instance is unnecessary.

## Post-reboot checkpoint — September 11, 2026, 23:55 Phoenix

Resumed audit is saved at C:\Users\BELDIN_USER\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an-3\outputs\WINDOWS_HEALTH_REPORT.md. Windows Update/CBS reboot keys cleared, but Gaming Services PendingFileRenameOperations remains; stop boundary retained. Administrator access still unavailable. DPS again failed at startup. Ollama returned on localhost; Beldin did not, and was manually relaunched on localhost with unchanged authentication. 50/50 tests and five live authenticated endpoints pass. Public firewall retained; LAN/startup installation and GPU inference deferred. No Windows repairs applied. See the resumed report for exact evidence and remaining Surface test.
