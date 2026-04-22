param(
    [string]$TargetRoot = "",
    [string]$SourceRoot = "",
    [switch]$Gui
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptRoot "..\..")).Path
$InstallMetadataName = "fixed_layout_install_metadata.json"
$ExcludedRepairDirs = @("dist", "logs", "tmp", ".git", ".venv", "__pycache__")

function Resolve-Root {
    param(
        [string]$ExplicitRoot,
        [string]$FallbackRoot
    )

    if ($ExplicitRoot) {
        return (Resolve-Path $ExplicitRoot).Path
    }
    return $FallbackRoot
}

function Ensure-StateDirectories {
    param([string]$Root)

    foreach ($relative in @("logs", "tmp", "fixed_layout_programs\logs", "fixed_layout_programs\tmp")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Root $relative) | Out-Null
    }
}

function Resolve-RecordedSourceRoot {
    param([string]$Root)

    $metadataPath = Join-Path $Root $InstallMetadataName
    if (-not (Test-Path $metadataPath)) {
        return ""
    }

    try {
        $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
        $candidate = [string]$metadata.sourceRoot
        if ($candidate -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    } catch {
    }

    return ""
}

function Get-RequiredPaths {
    param([string]$Root)

    return [ordered]@{
        "app.py" = (Join-Path $Root "app.py")
        "portablePython" = (Join-Path $Root "runtime\python\python.exe")
        "nativeRuntime" = (Join-Path $Root "runtime\native_runtime\VideoPlatform.NativeProbe.exe")
        "visualShellDetector" = (Join-Path $Root "visual_shell_detector.py")
        "statusOverlay" = (Join-Path $Root "status_overlay.py")
        "statusRuntime" = (Join-Path $Root "status_runtime.py")
        "verifyWrapper" = (Join-Path $Root "verify_fixed_layout_runtime.cmd")
        "verifyScript" = (Join-Path $Root "platform_spike\scripts\verify_fixed_layout_runtime.py")
        "layoutManifest" = (Join-Path $Root "fixed_layout_programs\fixed_layout_manifest.json")
    }
}

function Assert-RequiredPaths {
    param([string]$Root)

    $required = Get-RequiredPaths -Root $Root
    $missing = @()
    foreach ($name in $required.Keys) {
        if (-not (Test-Path $required[$name])) {
            $missing += [pscustomobject]@{
                name = $name
                path = $required[$name]
            }
        }
    }
    if ($missing.Count -gt 0) {
        $rendered = $missing | ForEach-Object { "{0} => {1}" -f $_.name, $_.path }
        throw "Missing required runtime files: $($rendered -join '; ')"
    }
    return $required
}

function Invoke-VerifyRuntime {
    param([string]$Root)

    $pythonExe = Join-Path $Root "runtime\python\python.exe"
    if (-not (Test-Path $pythonExe)) {
        throw "Portable Python runtime was not found: $pythonExe"
    }

    $verifyScript = Join-Path $Root "platform_spike\scripts\verify_fixed_layout_runtime.py"
    & $pythonExe $verifyScript --repo-root $Root --quick --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Portable runtime verification script failed with exit code $LASTEXITCODE."
    }

    Push-Location $Root
    try {
        & $pythonExe "app.py" --help | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Portable app.py help invocation failed."
        }
    } finally {
        Pop-Location
    }
}

function Repair-FromSource {
    param(
        [string]$Source,
        [string]$Target
    )

    if (-not $Source) {
        throw "No repair source is available."
    }
    if (-not (Test-Path $Source)) {
        throw "Repair source root was not found: $Source"
    }

    $args = @(
        $Source,
        $Target,
        "/E",
        "/R:2",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS"
    )
    foreach ($excluded in $ExcludedRepairDirs) {
        $args += "/XD"
        $args += $excluded
    }

    & robocopy @args | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with exit code $LASTEXITCODE"
    }
}

function Show-ResultDialog {
    param(
        [bool]$Ok,
        [string]$Message
    )

    if (-not $Gui) {
        return
    }

    Add-Type -AssemblyName System.Windows.Forms
    $icon = [System.Windows.Forms.MessageBoxIcon]::Information
    if (-not $Ok) {
        $icon = [System.Windows.Forms.MessageBoxIcon]::Error
    }
    [System.Windows.Forms.MessageBox]::Show(
        $Message,
        "Video Platform Fixed Layouts",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        $icon
    ) | Out-Null
}

function Main {
    $resolvedTargetRoot = Resolve-Root -ExplicitRoot $TargetRoot -FallbackRoot $RepoRoot
    Ensure-StateDirectories -Root $resolvedTargetRoot

    $resolvedSourceRoot = ""
    if ($SourceRoot) {
        $resolvedSourceRoot = (Resolve-Path $SourceRoot).Path
    } else {
        $resolvedSourceRoot = Resolve-RecordedSourceRoot -Root $resolvedTargetRoot
    }

    $result = [ordered]@{
        ok = $false
        repaired = $false
        targetRoot = $resolvedTargetRoot
        sourceRoot = $resolvedSourceRoot
        initialError = ""
        repairDetail = ""
    }

    try {
        Assert-RequiredPaths -Root $resolvedTargetRoot | Out-Null
        Invoke-VerifyRuntime -Root $resolvedTargetRoot
        $result.ok = $true
        $result.repairDetail = "Runtime verification passed without needing repair."
    } catch {
        $result.initialError = $_.Exception.Message
        if (-not $resolvedSourceRoot) {
            throw
        }

        Repair-FromSource -Source $resolvedSourceRoot -Target $resolvedTargetRoot
        Assert-RequiredPaths -Root $resolvedTargetRoot | Out-Null
        Invoke-VerifyRuntime -Root $resolvedTargetRoot
        $result.ok = $true
        $result.repaired = $true
        $result.repairDetail = "Missing runtime files were restored from the original package source."
    }

    if ($result.ok) {
        Show-ResultDialog -Ok $true -Message "Fixed-layout runtime verification completed successfully."
    }

    $result | ConvertTo-Json -Depth 4
}

try {
    Main
    exit 0
} catch {
    $targetRootValue = ""
    if ($TargetRoot) {
        try {
            $targetRootValue = (Resolve-Path $TargetRoot).Path
        } catch {
            $targetRootValue = $TargetRoot
        }
    } else {
        $targetRootValue = $RepoRoot
    }

    $message = $_.Exception.Message
    $result = [ordered]@{
        ok = $false
        repaired = $false
        targetRoot = $targetRootValue
        sourceRoot = $SourceRoot
        initialError = $message
        repairDetail = ""
    }
    $result | ConvertTo-Json -Depth 4
    Show-ResultDialog -Ok $false -Message $message
    exit 1
}
