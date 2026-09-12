<#
.SYNOPSIS
  Copy one configured TradeSync runtime secret to the Windows clipboard.

.DESCRIPTION
  Reads only the named variable from runtime.env and copies its value without
  printing it. Clear the clipboard after pasting into the provider form.
#>
param(
  [Parameter(Mandatory = $true)] [string] $Name,
  [string] $EnvFile = "E:\Projects\TradeSync\dashboard-runtime\runtime.env"
)

if ($Name -notmatch '^[A-Z][A-Z0-9_]*$') { throw "Name must look like an environment variable: $Name" }
if (-not (Test-Path $EnvFile)) { throw "runtime.env not found at $EnvFile" }

$pattern = "^\s*$([regex]::Escape($Name))\s*=(.*)$"
$line = Get-Content -Path $EnvFile -Encoding UTF8 |
  Where-Object { $_ -match $pattern } |
  Select-Object -Last 1

if (-not $line) { throw "$Name is not configured in runtime.env" }
$value = ([regex]::Match($line, $pattern)).Groups[1].Value.Trim()
if ([string]::IsNullOrWhiteSpace($value)) { throw "$Name is configured but empty" }

Set-Clipboard -Value $value
Write-Host "$Name copied to the clipboard ($($value.Length) characters); value not displayed."
