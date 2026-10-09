param(
    [ValidateRange(1, 65535)]
    [int]$UdpPort = 41641
)

$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as administrator, then run this script again."
}

$rules = @(
    @{
        Name = "Connect Tailscale direct UDP inbound"
        Direction = "Inbound"
    },
    @{
        Name = "Connect Tailscale direct UDP outbound"
        Direction = "Outbound"
    }
)

foreach ($rule in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Set-NetFirewallRule -InputObject $existing -Enabled True -Profile Any -Action Allow
        Get-NetFirewallPortFilter -AssociatedNetFirewallRule $existing |
            Set-NetFirewallPortFilter -Protocol UDP -LocalPort $UdpPort
    } else {
        New-NetFirewallRule `
            -DisplayName $rule.Name `
            -Direction $rule.Direction `
            -Action Allow `
            -Protocol UDP `
            -LocalPort $UdpPort `
            -Profile Any | Out-Null
    }
}

Write-Host "Windows Firewall allows inbound and outbound Tailscale UDP/$UdpPort."

$tailscalePath = (Get-Command tailscale.exe -ErrorAction SilentlyContinue).Source
if (-not $tailscalePath) {
    $tailscalePath = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
}

if (Test-Path $tailscalePath) {
    Write-Host "`nTailscale diagnostics (tailscale netcheck):"
    & $tailscalePath netcheck
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "tailscale netcheck failed."
    }
} else {
    Write-Warning "tailscale.exe was not found; firewall rules were configured."
}

Write-Host "`nIf the route still uses DERP, check UDP/$UdpPort port forwarding on the router."
Write-Host "Forward this port to this computer's LAN IP on both peers' networks."
Write-Host "This script does not change router settings or bypass CGNAT or UDP blocking."
