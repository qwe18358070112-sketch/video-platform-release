param(
    [string]$LogPath = "D:\opsmgr\Infovision Foresight\client\components\webcontainer.1\logs\webcontainer\webcontainer.webcontainer.debug.log",
    [string]$ClientFrameLogPath = "D:\opsmgr\Infovision Foresight\client\framework\infosightclient.1\logs\clientframe\clientframework.clientframe.debug.log",
    [string]$DatePrefix = "",
    [int]$TimeoutSec = 2,
    [int]$TailLines = 160,
    [int]$ClientFrameTailLines = 240,
    [string]$OutputRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$probeScript = Join-Path $scriptDir "platform_live_probe.ps1"
$envCheckScript = Join-Path $scriptDir "check_windows_platform_spike_env.ps1"

function Write-Utf8Json {
    param(
        [string]$Path,
        [object]$Value
    )

    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    ($Value | ConvertTo-Json -Depth 20) | Set-Content -LiteralPath $Path -Encoding UTF8
}

try {
    if (-not $DatePrefix) {
        $DatePrefix = (Get-Date).ToString("yyyy-MM-dd")
    }

    if (-not $OutputRoot) {
        $repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "..\.."))
        $OutputRoot = Join-Path $repoRoot "tmp\live_probe_bundles"
    }

    $stamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
    $bundleDir = Join-Path $OutputRoot ("bundle_" + $stamp)
    New-Item -ItemType Directory -Path $bundleDir -Force | Out-Null

    $probeOutputPath = Join-Path $bundleDir "platform_live_probe_last.json"
    $windowsEnvOutputPath = Join-Path $bundleDir "windows_env_report.json"

    Write-Output "[platform_spike] bundleDir=$bundleDir"
    Write-Output "[platform_spike] stage=live-probe"

    $probeExitCode = 0
    $probeInvocationError = ""
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $probeScript `
            -LogPath $LogPath `
            -DatePrefix $DatePrefix `
            -TimeoutSec $TimeoutSec `
            -ProbePreset quick `
            -OutputPath $probeOutputPath 2>$null | Out-Null
        $probeExitCode = $LASTEXITCODE
    } catch {
        $probeExitCode = if ($LASTEXITCODE) { $LASTEXITCODE } else { 1 }
        $probeInvocationError = $_.ToString()
    }

    $probeResult = $null
    if (Test-Path -LiteralPath $probeOutputPath) {
        $probeResult = Get-Content -LiteralPath $probeOutputPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }

    $logTailPath = Join-Path $bundleDir "webcontainer_tail.log"
    if (Test-Path -LiteralPath $LogPath) {
        Get-Content -LiteralPath $LogPath -Tail $TailLines -Encoding UTF8 | Set-Content -LiteralPath $logTailPath -Encoding UTF8
    } else {
        Set-Content -LiteralPath $logTailPath -Encoding UTF8 -Value ("Log file not found: " + $LogPath)
    }

    $clientFrameTailPath = Join-Path $bundleDir "clientframe_tail.log"
    if (Test-Path -LiteralPath $ClientFrameLogPath) {
        Get-Content -LiteralPath $ClientFrameLogPath -Tail $ClientFrameTailLines -Encoding UTF8 | Set-Content -LiteralPath $clientFrameTailPath -Encoding UTF8
    } else {
        Set-Content -LiteralPath $clientFrameTailPath -Encoding UTF8 -Value ("Log file not found: " + $ClientFrameLogPath)
    }

    $windowsEnvProbeExitCode = 0
    $windowsEnvInvocationError = ""
    if (Test-Path -LiteralPath $envCheckScript) {
        Write-Output "[platform_spike] stage=windows-env-check"
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $envCheckScript `
                -ClientRoot "D:\opsmgr\Infovision Foresight\client" `
                -OutputPath $windowsEnvOutputPath 2>$null | Out-Null
            $windowsEnvProbeExitCode = $LASTEXITCODE
        } catch {
            $windowsEnvProbeExitCode = if ($LASTEXITCODE) { $LASTEXITCODE } else { 1 }
            $windowsEnvInvocationError = $_.ToString()
        }
    }

    $windowsEnvReport = $null
    if (Test-Path -LiteralPath $windowsEnvOutputPath) {
        $windowsEnvReport = Get-Content -LiteralPath $windowsEnvOutputPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }

    $sessionSummary = [ordered]@{
        generatedAt = (Get-Date).ToString("s")
        bundleDir = $bundleDir
        logPath = $LogPath
        clientFrameLogPath = $ClientFrameLogPath
        datePrefix = $DatePrefix
        timeoutSec = $TimeoutSec
        tailLines = $TailLines
        clientFrameTailLines = $ClientFrameTailLines
        probePreset = "quick"
        probeOutputPath = $probeOutputPath
        windowsEnvOutputPath = $windowsEnvOutputPath
        logTailPath = $logTailPath
        clientFrameTailPath = $clientFrameTailPath
        session = if ($probeResult) { $probeResult.session } else { $null }
        serviceContexts = if ($probeResult) { $probeResult.serviceContexts } else { $null }
        connectivity = if ($probeResult) { $probeResult.connectivity } else { $null }
        windowsEnv = if ($windowsEnvReport) { $windowsEnvReport } else { $null }
        stage = if ($probeResult) { $probeResult.stage } else { "probe-not-written" }
        probePaths = if ($probeResult) { @($probeResult.probes | ForEach-Object { $_.path }) } else { @() }
        probeCount = if ($probeResult) { @($probeResult.probes).Count } else { 0 }
        probeExitCode = $probeExitCode
        probeInvocationError = $probeInvocationError
        windowsEnvProbeExitCode = $windowsEnvProbeExitCode
        windowsEnvInvocationError = $windowsEnvInvocationError
    }

    $summaryPath = Join-Path $bundleDir "bundle_summary.json"
    Write-Utf8Json -Path $summaryPath -Value $sessionSummary
    Write-Output "[platform_spike] stage=summary-written"

    $latestPointerPath = Join-Path $OutputRoot "latest_bundle.txt"
    Set-Content -LiteralPath $latestPointerPath -Encoding UTF8 -Value $bundleDir

    Write-Output ("BUNDLE_DIR=" + $bundleDir)
    Write-Output ("SUMMARY_PATH=" + $summaryPath)
    Write-Output ("LATEST_BUNDLE_PATH=" + $latestPointerPath)
    Write-Output ($sessionSummary | ConvertTo-Json -Depth 10)
} catch {
    Write-Error $_
    exit 1
}
