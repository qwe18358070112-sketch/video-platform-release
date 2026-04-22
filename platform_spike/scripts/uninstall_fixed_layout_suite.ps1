param(
    [string]$InstallRoot = "",
    [switch]$Gui
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DefaultInstallRoot = (Resolve-Path (Join-Path $ScriptRoot "..\..")).Path
$StartMenuRoot = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Video Platform Fixed Layouts"
$DesktopShortcutRoot = Join-Path ([Environment]::GetFolderPath("Desktop")) "Video Platform Fixed Layouts"
$UninstallRegistryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\VideoPlatformReleaseFixedLayouts"
$BackupRoot = Join-Path $env:LOCALAPPDATA "VideoPlatformReleaseFixedLayouts_Backups"

function Resolve-InstallRoot {
    param([string]$ExplicitInstallRoot)

    if ($ExplicitInstallRoot) {
        return (Resolve-Path $ExplicitInstallRoot).Path
    }
    return $DefaultInstallRoot
}

function Confirm-Uninstall {
    param([string]$TargetRoot)

    if (-not $Gui) {
        return $true
    }

    Add-Type -AssemblyName System.Windows.Forms
    $message = "Uninstall Video Platform Fixed Layouts from:`n$TargetRoot`n`nLogs and tmp data will be backed up under:`n$BackupRoot"
    return [System.Windows.Forms.MessageBox]::Show(
        $message,
        "Video Platform Fixed Layouts",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    ) -eq [System.Windows.Forms.DialogResult]::Yes
}

function Backup-StateDirectory {
    param(
        [string]$TargetRoot,
        [string]$RelativeName
    )

    $source = Join-Path $TargetRoot $RelativeName
    if (-not (Test-Path $source)) {
        return $null
    }
    $hasFiles = @(Get-ChildItem -Path $source -Recurse -Force -ErrorAction SilentlyContinue).Count -gt 0
    if (-not $hasFiles) {
        return $null
    }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $destination = Join-Path (Join-Path $BackupRoot $timestamp) $RelativeName
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Move-Item -Path $source -Destination $destination -Force
    return $destination
}

function Remove-ShortcutRoots {
    foreach ($path in @($StartMenuRoot, $DesktopShortcutRoot)) {
        if (Test-Path $path) {
            Remove-Item -Path $path -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Remove-UninstallRegistration {
    if (Test-Path $UninstallRegistryPath) {
        Remove-Item -Path $UninstallRegistryPath -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Schedule-InstallRootRemoval {
    param([string]$TargetRoot)

    $cleanupPath = Join-Path $env:TEMP ("video_platform_release_fixed_layout_cleanup_{0}.ps1" -f ([guid]::NewGuid().ToString("N")))
    $targetRootLiteral = $TargetRoot.Replace("'", "''")
    $lines = @(
        '$ErrorActionPreference = "SilentlyContinue"',
        "Start-Sleep -Seconds 4",
        ('$target = ''{0}''' -f $targetRootLiteral),
        "for (`$i = 0; `$i -lt 10; `$i++) {",
        "    if (-not (Test-Path -LiteralPath `$target)) { break }",
        "    Remove-Item -LiteralPath `$target -Recurse -Force -ErrorAction SilentlyContinue",
        "    if (-not (Test-Path -LiteralPath `$target)) { break }",
        "    Start-Sleep -Seconds 2",
        "}",
        'Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue'
    )
    Set-Content -Path $cleanupPath -Value $lines -Encoding ASCII
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $cleanupPath `
        -WorkingDirectory $env:TEMP `
        -WindowStyle Hidden
}

function Main {
    $resolvedInstallRoot = Resolve-InstallRoot -ExplicitInstallRoot $InstallRoot
    if (-not (Test-Path $resolvedInstallRoot)) {
        throw "Install root was not found: $resolvedInstallRoot"
    }

    if (-not (Confirm-Uninstall -TargetRoot $resolvedInstallRoot)) {
        Write-Output '{"ok": false, "cancelled": true}'
        return
    }

    $logBackup = Backup-StateDirectory -TargetRoot $resolvedInstallRoot -RelativeName "logs"
    $tmpBackup = Backup-StateDirectory -TargetRoot $resolvedInstallRoot -RelativeName "tmp"
    Remove-ShortcutRoots
    Remove-UninstallRegistration
    Schedule-InstallRootRemoval -TargetRoot $resolvedInstallRoot

    $logBackupValue = ""
    if ($null -ne $logBackup) {
        $logBackupValue = $logBackup
    }
    $tmpBackupValue = ""
    if ($null -ne $tmpBackup) {
        $tmpBackupValue = $tmpBackup
    }

    $result = [ordered]@{
        ok = $true
        installRoot = $resolvedInstallRoot
        logBackup = $logBackupValue
        tmpBackup = $tmpBackupValue
    }

    if ($Gui) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "Video Platform Fixed Layouts uninstall has been scheduled.",
            "Video Platform Fixed Layouts",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    }

    $result | ConvertTo-Json -Depth 4
}

Main
