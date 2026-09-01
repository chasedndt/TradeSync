[CmdletBinding()]
param(
    [string]$OutputRoot = "E:\ChaseOSBuilds\market-command-phase0-resource-audit\evidence",
    [string]$ExpectedDriveLetter = "E",
    [string]$ExpectedDriveLabel = "ChaseOS_Runtime",
    [double]$MinimumFreeGiB = 10.0,
    [double]$MinimumFreePercent = 5.0,
    [double]$MaximumMemoryPercent = 65.0,
    [double]$MaximumCpuPercent = 30.0,
    [int]$CpuSampleIntervalSeconds = 1,
    [int]$CpuSampleCount = 3,
    [switch]$NoEvidenceWrite,
    [switch]$Json,
    [switch]$EnforceCoreStartGate
)

$ErrorActionPreference = "Stop"

function Test-LocalHttpJson {
    param([string]$Uri)
    try {
        $response = Invoke-RestMethod -Uri $Uri -TimeoutSec 2
        return @{ reachable = $true; response = $response; error = $null }
    }
    catch {
        return @{ reachable = $false; response = $null; error = $_.Exception.Message }
    }
}

function Convert-WslGitPath {
    param([string]$Value)
    if ($Value -match '^/mnt/([a-zA-Z])/(.+)$') {
        $drive = $Matches[1].ToUpperInvariant()
        $tail = $Matches[2] -replace '/', '\'
        return "${drive}:\$tail"
    }
    return $Value
}

function Add-Reason {
    param([System.Collections.Generic.List[string]]$Reasons, [bool]$Condition, [string]$Reason)
    if (-not $Condition) {
        $Reasons.Add($Reason)
    }
}

$observedAt = (Get-Date).ToUniversalTime().ToString("o")
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$volume = Get-Volume -DriveLetter $ExpectedDriveLetter -ErrorAction SilentlyContinue
$driveAvailable = $null -ne $volume
$driveFreeGiB = if ($driveAvailable) { [math]::Round($volume.SizeRemaining / 1GB, 3) } else { 0.0 }
$driveFreePercent = if ($driveAvailable -and $volume.Size -gt 0) {
    [math]::Round(($volume.SizeRemaining / $volume.Size) * 100, 2)
} else { 0.0 }
$driveReady = (
    $driveAvailable -and
    $volume.FileSystemLabel -eq $ExpectedDriveLabel -and
    $volume.FileSystem -eq "NTFS" -and
    $driveFreeGiB -ge $MinimumFreeGiB -and
    $driveFreePercent -ge $MinimumFreePercent
)

$os = Get-CimInstance Win32_OperatingSystem
$processors = @(Get-CimInstance Win32_Processor)
$memoryTotalBytes = [double]$os.TotalVisibleMemorySize * 1KB
$memoryFreeBytes = [double]$os.FreePhysicalMemory * 1KB
$memoryUsedPercent = [math]::Round((($memoryTotalBytes - $memoryFreeBytes) / $memoryTotalBytes) * 100, 1)

$cpuCounter = Get-Counter '\Processor(_Total)\% Processor Time' `
    -SampleInterval $CpuSampleIntervalSeconds -MaxSamples $CpuSampleCount
$cpuPercent = [math]::Round(
    ($cpuCounter.CounterSamples.CookedValue | Measure-Object -Average).Average,
    1
)

$topProcesses = @(
    Get-Process |
        Sort-Object WorkingSet64 -Descending |
        Select-Object -First 12 `
            Id,
            ProcessName,
            @{ Name = "working_set_mib"; Expression = { [math]::Round($_.WorkingSet64 / 1MB, 1) } }
)

$dockerPipePresent = Test-Path '\\.\pipe\dockerDesktopLinuxEngine'
$dockerRunning = $false
$dockerVersion = $null
if ($dockerPipePresent) {
    try {
        $dockerVersion = (& docker version --format '{{.Server.Version}}' 2>$null | Select-Object -First 1)
        $dockerRunning = -not [string]::IsNullOrWhiteSpace($dockerVersion)
    }
    catch {
        $dockerRunning = $false
    }
}

$ollama = Test-LocalHttpJson -Uri "http://127.0.0.1:11434/api/version"
$ollamaModels = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")
$expectedModelRoot = "$ExpectedDriveLetter`:\ChaseOS-Runtime\Models\Ollama"
$modelRootReady = $ollamaModels -eq $expectedModelRoot -and (Test-Path $expectedModelRoot)
$cDriveModelCacheAbsent = -not (Test-Path "$env:USERPROFILE\.ollama\models")
$modelManifestRoot = Join-Path $expectedModelRoot "manifests\registry.ollama.ai\library"
$modelTags = @()
if (Test-Path $modelManifestRoot) {
    $modelTags = @(
        Get-ChildItem $modelManifestRoot -Recurse -File |
            ForEach-Object {
                $_.FullName.Substring($modelManifestRoot.Length + 1) -replace '\\', ':'
            } |
            Sort-Object
    )
}

$dockerVhdx = "$ExpectedDriveLetter`:\ChaseOS-Runtime\Docker\DockerDesktopWSL\disk\docker_data.vhdx"
$dockerStorageReady = Test-Path $dockerVhdx

$wslText = ""
try {
    $wslText = ((& wsl.exe --list --verbose 2>$null | Out-String) -replace "`0", "").Trim()
}
catch {
    $wslText = "unavailable"
}

$gitPointerFile = Join-Path $repoRoot ".git"
$gitPointerRaw = if (Test-Path $gitPointerFile -PathType Leaf) {
    (Get-Content $gitPointerFile -Raw).Trim()
} else { $null }
$gitTarget = $null
if ($gitPointerRaw -match '^gitdir:\s*(.+)$') {
    $gitTarget = Convert-WslGitPath $Matches[1].Trim()
}
$gitReady = if (Test-Path $gitPointerFile -PathType Container) {
    $true
} elseif ($gitTarget) {
    Test-Path $gitTarget
} else {
    $false
}

$memoryReady = $memoryUsedPercent -le $MaximumMemoryPercent
$cpuReady = $cpuPercent -le $MaximumCpuPercent
$resourceReady = $memoryReady -and $cpuReady
$dockerStartReasons = [System.Collections.Generic.List[string]]::new()
Add-Reason $dockerStartReasons $driveReady "external_runtime_drive_not_ready"
Add-Reason $dockerStartReasons $dockerStorageReady "external_docker_vhdx_missing"
Add-Reason $dockerStartReasons $memoryReady "host_memory_above_core_start_threshold"
Add-Reason $dockerStartReasons $cpuReady "host_cpu_above_core_start_threshold"
Add-Reason $dockerStartReasons $gitReady "tradesync_git_metadata_invalid"

$coreReasons = [System.Collections.Generic.List[string]]::new()
Add-Reason $coreReasons $driveReady "external_runtime_drive_not_ready"
Add-Reason $coreReasons $dockerStorageReady "external_docker_vhdx_missing"
Add-Reason $coreReasons $memoryReady "host_memory_above_core_start_threshold"
Add-Reason $coreReasons $cpuReady "host_cpu_above_core_start_threshold"
Add-Reason $coreReasons $gitReady "tradesync_git_metadata_invalid"
Add-Reason $coreReasons $dockerRunning "docker_engine_not_running"

$result = [ordered]@{
    schema_version = "market_command_phase0_readiness_v1"
    observed_at_utc = $observedAt
    mode = "paper_only"
    authority = [ordered]@{
        live_execution_authorized = $false
        wallet_authorized = $false
        credential_access_authorized = $false
        service_start_authorized = $false
    }
    thresholds = [ordered]@{
        minimum_free_gib = $MinimumFreeGiB
        minimum_free_percent = $MinimumFreePercent
        maximum_memory_percent = $MaximumMemoryPercent
        maximum_cpu_percent = $MaximumCpuPercent
        cpu_sample_interval_seconds = $CpuSampleIntervalSeconds
        cpu_sample_count = $CpuSampleCount
    }
    host = [ordered]@{
        computer_name = $env:COMPUTERNAME
        cpu_name = ($processors.Name -join "; ")
        physical_cores = ($processors.NumberOfCores | Measure-Object -Sum).Sum
        logical_processors = ($processors.NumberOfLogicalProcessors | Measure-Object -Sum).Sum
        cpu_percent = $cpuPercent
        memory_total_gib = [math]::Round($memoryTotalBytes / 1GB, 2)
        memory_used_gib = [math]::Round(($memoryTotalBytes - $memoryFreeBytes) / 1GB, 2)
        memory_used_percent = $memoryUsedPercent
        process_count = (Get-Process).Count
        top_processes = $topProcesses
    }
    storage = [ordered]@{
        expected_drive = "$ExpectedDriveLetter`:"
        available = $driveAvailable
        label = if ($driveAvailable) { $volume.FileSystemLabel } else { $null }
        filesystem = if ($driveAvailable) { $volume.FileSystem } else { $null }
        free_gib = $driveFreeGiB
        free_percent = $driveFreePercent
        ready = $driveReady
        docker_vhdx = $dockerVhdx
        docker_vhdx_present = $dockerStorageReady
        ollama_model_root = $ollamaModels
        ollama_model_root_ready = $modelRootReady
        c_drive_model_cache_absent = $cDriveModelCacheAbsent
        model_tags = $modelTags
    }
    runtimes = [ordered]@{
        docker_engine_running = $dockerRunning
        docker_server_version = $dockerVersion
        ollama_api_reachable = [bool]$ollama.reachable
        ollama_error = $ollama.error
        wsl_inventory = $wslText
    }
    repository = [ordered]@{
        root = $repoRoot
        git_pointer = $gitPointerRaw
        resolved_git_target = $gitTarget
        git_ready = $gitReady
    }
    gates = [ordered]@{
        external_storage_ready = $driveReady -and $dockerStorageReady -and $modelRootReady -and $cDriveModelCacheAbsent
        resource_headroom_ready = $resourceReady
        docker_engine_start_allowed = ($dockerStartReasons.Count -eq 0)
        docker_engine_start_block_reasons = @($dockerStartReasons)
        core_profile_start_allowed = ($coreReasons.Count -eq 0)
        core_profile_block_reasons = @($coreReasons)
        ai_profile_start_allowed = $resourceReady -and $ollama.reachable
        analytics_profile_start_allowed = $resourceReady -and $dockerRunning
        live_execution_allowed = $false
    }
}

$jsonText = $result | ConvertTo-Json -Depth 8

if (-not $NoEvidenceWrite) {
    if (-not $driveReady) {
        throw "Refusing evidence write because the expected external runtime drive is not ready."
    }
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $jsonPath = Join-Path $OutputRoot "market-command-readiness-$stamp.json"
    $markdownPath = Join-Path $OutputRoot "market-command-readiness-$stamp.md"
    Set-Content -LiteralPath $jsonPath -Value $jsonText -Encoding UTF8

    $status = if ($result.gates.core_profile_start_allowed) { "READY" } else { "BLOCKED" }
    $reasons = if ($coreReasons.Count -eq 0) { "- none" } else {
        ($coreReasons | ForEach-Object { "- " + $_ }) -join "`n"
    }
    $markdown = @"
# ChaseOS Market Command Phase 0 Readiness

- Observed: $observedAt
- Core profile: **$status**
- Mode: paper only
- Live execution authorized: **false**

## Host

- CPU: $($result.host.cpu_name)
- CPU sample: $cpuPercent%
- Memory: $($result.host.memory_used_gib) / $($result.host.memory_total_gib) GiB ($memoryUsedPercent%)
- Processes: $($result.host.process_count)

## External runtime

- Drive: $ExpectedDriveLetter`: / $($result.storage.label) / $($result.storage.filesystem)
- Free: $driveFreeGiB GiB ($driveFreePercent%)
- Docker VHDX present: $dockerStorageReady
- Ollama model root ready: $modelRootReady
- C-drive model cache absent: $cDriveModelCacheAbsent

## Runtime state

- Docker running: $dockerRunning
- Ollama reachable: $($ollama.reachable)
- Git metadata ready: $gitReady

## Block reasons

$reasons
"@
    Set-Content -LiteralPath $markdownPath -Value $markdown -Encoding UTF8
}

if ($Json) {
    Write-Output $jsonText
} else {
    $result
}

if ($EnforceCoreStartGate -and -not $result.gates.core_profile_start_allowed) {
    exit 2
}
