param(
    [string]$ClientRoot = "D:\opsmgr\Infovision Foresight\client",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$checkScript = Join-Path $scriptDir "check_windows_platform_spike_env.ps1"
if (-not (Test-Path -LiteralPath $checkScript)) {
    throw "Missing dependency: $checkScript"
}

$checkArgs = @{
    ClientRoot = $ClientRoot
}
if ($OutputPath) {
    $checkArgs.OutputPath = $OutputPath
}

$result = & $checkScript @checkArgs | Out-String
$summaryPath = ($result -split "`r?`n" | Where-Object { $_ -like "SUMMARY_PATH=*" } | Select-Object -Last 1)
if (-not $summaryPath) {
    throw "check_windows_platform_spike_env.ps1 did not return SUMMARY_PATH"
}
$summaryFile = $summaryPath.Substring("SUMMARY_PATH=".Length)
$jsonPath = [System.IO.Path]::ChangeExtension($summaryFile, ".json")
if (-not (Test-Path -LiteralPath $jsonPath)) {
    throw "Missing JSON report: $jsonPath"
}

$report = Get-Content -LiteralPath $jsonPath -Raw -Encoding UTF8 | ConvertFrom-Json -Depth 20
$menu = $report.menu
$recommendations = @()
if ($report.recommendations) {
    $recommendations = @($report.recommendations)
}

$output = @(
    "=== CLIENT_MENU_SOURCE_RESULT ===",
    "outputPath=$jsonPath",
    "videoMonitorMenuSourceAssessment=$($menu.videoMonitorMenuSourceAssessment)",
    "localMenuPatched=$($menu.localMenuPatched)",
    "videoMonitorRedirected=$($menu.videoMonitorRedirected)",
    "probeMenuPresent=$($menu.probeMenuPresent)",
    "ipointRedirected=$($menu.ipointRedirected)",
    "serverDeliveredVideoMonitor=$($menu.serverDeliveredVideoMonitor)",
    "latestClient0101Component=$($menu.latestClient0101Component)",
    "latestVideoPermissionCode=$($menu.latestVideoPermissionCode)",
    "latestProbeMenuSignal=$($menu.latestProbeMenuSignal)",
    "recommendationCount=$($recommendations.Count)"
)

foreach ($line in @($menu.videoMonitorMenuEvidence)) {
    if ($line) {
        $output += "evidence=$line"
    }
}
foreach ($line in $recommendations) {
    $output += "recommendation=$line"
}

$output += "CLIENT_MENU_SOURCE_RESULT_END"
$output | ForEach-Object { Write-Output $_ }
