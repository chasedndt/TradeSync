<#
.SYNOPSIS
  Reuse the existing ChaseOS // Hermes bot token for the TradeSync discord-reader,
  copying it file-to-file so the value is never displayed or pasted anywhere.

.DESCRIPTION
  Reads DISCORD_BOT_TOKEN from the Hermes runtime's .env (WSL share) and writes it
  as DISCORD_BOT_TOKEN into TradeSync's runtime.env, replacing any existing line.
  Prints only the variable name and the character count. The reader uses the
  token read-only (channel messages); it never posts.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\copy-hermes-discord-token.ps1
#>
param(
  [string] $HermesEnv = "\\wsl.localhost\Ubuntu\home\chaseos\runtimes\hermes-home\.env",
  [string] $EnvFile = "E:\Projects\TradeSync\dashboard-runtime\runtime.env",
  [string] $SourceName = "DISCORD_BOT_TOKEN",
  [string] $TargetName = "DISCORD_BOT_TOKEN"
)

if (-not (Test-Path $HermesEnv)) { throw "Hermes .env not reachable at $HermesEnv" }
if (-not (Test-Path $EnvFile)) { throw "runtime.env not found at $EnvFile" }

$line = Get-Content -Path $HermesEnv -Encoding UTF8 | Where-Object { $_ -match "^\s*$([regex]::Escape($SourceName))\s*=" } | Select-Object -First 1
if (-not $line) { throw "$SourceName not present in the Hermes .env" }
$value = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
if ([string]::IsNullOrWhiteSpace($value)) { throw "$SourceName is empty in the Hermes .env" }

$lines = Get-Content -Path $EnvFile -Encoding UTF8
$pattern = "^\s*$([regex]::Escape($TargetName))\s*="
$kept = @($lines | Where-Object { $_ -notmatch $pattern })
$kept += "$TargetName=$value"
Set-Content -Path $EnvFile -Value $kept -Encoding UTF8
Write-Host "$TargetName copied into runtime.env ($($value.Length) characters). Value not displayed."
