<#
.SYNOPSIS
  Put one secret into runtime.env through a desktop prompt, so the value never
  passes through a chat, a shell history, or an agent.

.DESCRIPTION
  Opens a Windows input box for the named variable, then writes NAME=value into
  E:\Projects\TradeSync\dashboard-runtime\runtime.env, replacing any existing
  line for that name. The value is not echoed anywhere. Nothing else in the
  file is touched.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\set-runtime-secret.ps1 -Name DISCORD_BOT_TOKEN
#>
param(
  [Parameter(Mandatory = $true)] [string] $Name,
  [string] $EnvFile = "E:\Projects\TradeSync\dashboard-runtime\runtime.env",
  [string] $Prompt = ""
)

if ($Name -notmatch '^[A-Z][A-Z0-9_]*$') { throw "Name must look like an environment variable: $Name" }
if (-not (Test-Path $EnvFile)) { throw "runtime.env not found at $EnvFile" }

Add-Type -AssemblyName Microsoft.VisualBasic
if (-not $Prompt) { $Prompt = "Paste the value for $Name. It is written straight to runtime.env and shown nowhere." }
$value = [Microsoft.VisualBasic.Interaction]::InputBox($Prompt, "TradeSync: $Name", "")
if ([string]::IsNullOrWhiteSpace($value)) { Write-Host "Cancelled; $Name unchanged."; exit 1 }
$value = $value.Trim()

$lines = Get-Content -Path $EnvFile -Encoding UTF8
$pattern = "^\s*$([regex]::Escape($Name))\s*="
$kept = @($lines | Where-Object { $_ -notmatch $pattern })
$kept += "$Name=$value"
Set-Content -Path $EnvFile -Value $kept -Encoding UTF8
Write-Host "$Name written to runtime.env ($($value.Length) characters). Value not displayed."
