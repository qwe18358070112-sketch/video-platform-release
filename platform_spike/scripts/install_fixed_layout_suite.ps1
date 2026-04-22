param(
    [string]$SourceRoot = "",
    [string]$InstallDir = "",
    [switch]$Gui,
    [switch]$CreateDesktopFolder
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoScriptRoot = Resolve-Path (Join-Path $ScriptRoot "..\..")
$DefaultInstallDir = Join-Path $env:LOCALAPPDATA "Programs\VideoPlatformReleaseFixedLayouts"
$StartMenuRoot = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Video Platform Fixed Layouts"
$DesktopShortcutRoot = Join-Path ([Environment]::GetFolderPath("Desktop")) "Video Platform Fixed Layouts"
$UninstallRegistryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\VideoPlatformReleaseFixedLayouts"
$DisplayVersion = "2026.04-fixed-layout-freeze"
$InstallMetadataName = "fixed_layout_install_metadata.json"

function Resolve-SourceRoot {
    param([string]$ExplicitSourceRoot)

    if ($ExplicitSourceRoot) {
        return (Resolve-Path $ExplicitSourceRoot).Path
    }
    return $RepoScriptRoot.Path
}

function Ensure-PackagePayload {
    param([string]$CandidateRoot)

    $required = @(
        "app.py",
        "runtime\python\python.exe",
        "runtime\native_runtime\VideoPlatform.NativeProbe.exe",
        "fixed_layout_programs\fixed_layout_manifest.json",
        "install_fixed_layout_suite.cmd",
        "uninstall_fixed_layout_suite.cmd",
        "repair_fixed_layout_runtime.cmd",
        "verify_fixed_layout_runtime.cmd",
        "platform_spike\scripts\verify_fixed_layout_runtime.py",
        "platform_spike\scripts\repair_fixed_layout_runtime.ps1"
    )
    foreach ($relative in $required) {
        $path = Join-Path $CandidateRoot $relative
        if (-not (Test-Path $path)) {
            throw "Fixed-layout suite package is incomplete. Missing: $path"
        }
    }
}

function Show-InstallDialog {
    param(
        [string]$InitialInstallDir,
        [bool]$InitialCreateDesktopFolder
    )

    Add-Type -AssemblyName System.Windows.Forms
    $folderDialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $folderDialog.Description = "Select the installation directory for Video Platform Fixed Layouts"
    $folderDialog.SelectedPath = $InitialInstallDir
    $folderDialog.ShowNewFolderButton = $true
    if ($folderDialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        return $null
    }

    $createDesktop = [System.Windows.Forms.MessageBox]::Show(
        "Create a desktop shortcut folder with the validated fixed-layout launchers?",
        "Video Platform Fixed Layouts",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    ) -eq [System.Windows.Forms.DialogResult]::Yes

    return [pscustomobject]@{
        InstallDir = $folderDialog.SelectedPath
        CreateDesktopFolder = $createDesktop
    }
}

function Copy-PackageTree {
    param(
        [string]$PackageRoot,
        [string]$TargetRoot
    )

    New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
    $robocopyArgs = @(
        $PackageRoot,
        $TargetRoot,
        "/E",
        "/R:2",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/XD",
        "dist",
        "logs",
        "tmp",
        ".git",
        ".venv",
        "__pycache__"
    )
    & robocopy @robocopyArgs | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with exit code $LASTEXITCODE"
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $TargetRoot "logs") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $TargetRoot "tmp") | Out-Null
}

function Invoke-PortableRuntimeSmokeChecks {
    param(
        [string]$TargetRoot,
        [string]$SourceRoot
    )

    & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File (Join-Path $TargetRoot "platform_spike\scripts\repair_fixed_layout_runtime.ps1") `
        -TargetRoot $TargetRoot `
        -SourceRoot $SourceRoot | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Portable runtime verification/repair failed."
    }
}

function Write-InstallMetadata {
    param(
        [string]$TargetRoot,
        [string]$SourceRoot
    )

    $payload = [ordered]@{
        installRoot = $TargetRoot
        sourceRoot = $SourceRoot
        installedAt = (Get-Date).ToString("s")
        version = $DisplayVersion
    }
    $payload | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $TargetRoot $InstallMetadataName) -Encoding UTF8
}

function New-Shortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$WorkingDirectory,
        [string]$Arguments = "",
        [string]$Description = ""
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    if ($Arguments) {
        $shortcut.Arguments = $Arguments
    }
    $shortcut.WorkingDirectory = $WorkingDirectory
    if ($Description) {
        $shortcut.Description = $Description
    }
    $shortcut.Save()
}

function Get-ShortcutEntries {
    param([string]$TargetRoot)

    $manifestPath = Join-Path $TargetRoot "fixed_layout_programs\fixed_layout_manifest.json"
    $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
    $entries = @($manifest.entries)
    $modeEntries = @($entries | Where-Object { $_.mode -eq "windowed" -or $_.mode -eq "fullscreen" })
    if ($modeEntries.Count -gt 0) {
        return $modeEntries
    }
    return $entries
}

function Sync-ShortcutRoot {
    param(
        [string]$TargetRoot,
        [string]$ShortcutRoot
    )

    New-Item -ItemType Directory -Force -Path $ShortcutRoot | Out-Null
    Get-ChildItem -Path $ShortcutRoot -Filter *.lnk -Force -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

    foreach ($entry in (Get-ShortcutEntries -TargetRoot $TargetRoot | Sort-Object @{Expression = {[int]$_.layout}}, @{Expression = {$_.mode}})) {
        $launcher = Join-Path $TargetRoot ("fixed_layout_programs\" + $entry.launcher)
        $modeLabel = "Auto"
        if ($entry.mode -eq "fullscreen") {
            $modeLabel = "Fullscreen"
        } elseif ($entry.mode -eq "windowed") {
            $modeLabel = "Windowed"
        }
        $shortcutName = "Fixed Layout {0} Grid ({1}).lnk" -f $entry.layout, $modeLabel
        New-Shortcut `
            -ShortcutPath (Join-Path $ShortcutRoot $shortcutName) `
            -TargetPath $launcher `
            -WorkingDirectory (Join-Path $TargetRoot "fixed_layout_programs") `
            -Description "Launch fixed layout $($entry.layout) / $($entry.mode)"
    }

    New-Shortcut `
        -ShortcutPath (Join-Path $ShortcutRoot "Fixed Layout Deployment Guide.lnk") `
        -TargetPath (Join-Path $TargetRoot "FIXED_LAYOUT_DEPLOY.md") `
        -WorkingDirectory $TargetRoot `
        -Description "Open the fixed-layout deployment guide"

    New-Shortcut `
        -ShortcutPath (Join-Path $ShortcutRoot "Fixed Layout Install and Use Guide.lnk") `
        -TargetPath (Join-Path $TargetRoot "FIXED_LAYOUT_INSTALL_AND_USE.md") `
        -WorkingDirectory $TargetRoot `
        -Description "Open the fixed-layout install and use guide"

    New-Shortcut `
        -ShortcutPath (Join-Path $ShortcutRoot "Fixed Layout Program Folder.lnk") `
        -TargetPath "$env:WINDIR\explorer.exe" `
        -Arguments ('"{0}"' -f (Join-Path $TargetRoot "fixed_layout_programs")) `
        -WorkingDirectory $TargetRoot `
        -Description "Open the installed fixed-layout launcher directory"

    New-Shortcut `
        -ShortcutPath (Join-Path $ShortcutRoot "Verify Fixed Layout Installation.lnk") `
        -TargetPath (Join-Path $TargetRoot "verify_fixed_layout_runtime.cmd") `
        -WorkingDirectory $TargetRoot `
        -Description "Run the fixed-layout runtime verification checks"

    New-Shortcut `
        -ShortcutPath (Join-Path $ShortcutRoot "Repair Fixed Layout Installation.lnk") `
        -TargetPath (Join-Path $TargetRoot "repair_fixed_layout_runtime.cmd") `
        -WorkingDirectory $TargetRoot `
        -Description "Verify and repair the fixed-layout runtime from the original package"

    New-Shortcut `
        -ShortcutPath (Join-Path $ShortcutRoot "Uninstall Fixed Layout Programs.lnk") `
        -TargetPath (Join-Path $TargetRoot "uninstall_fixed_layout_suite.cmd") `
        -WorkingDirectory $TargetRoot `
        -Description "Uninstall the fixed-layout suite"
}

function Register-UninstallEntry {
    param([string]$TargetRoot)

    New-Item -Path $UninstallRegistryPath -Force | Out-Null
    Set-ItemProperty -Path $UninstallRegistryPath -Name DisplayName -Value "Video Platform Fixed Layouts"
    Set-ItemProperty -Path $UninstallRegistryPath -Name DisplayVersion -Value $DisplayVersion
    Set-ItemProperty -Path $UninstallRegistryPath -Name Publisher -Value "video_platform_release"
    Set-ItemProperty -Path $UninstallRegistryPath -Name InstallLocation -Value $TargetRoot
    Set-ItemProperty -Path $UninstallRegistryPath -Name DisplayIcon -Value (Join-Path $TargetRoot "runtime\python\python.exe")
    Set-ItemProperty -Path $UninstallRegistryPath -Name UninstallString -Value ('"{0}"' -f (Join-Path $TargetRoot "uninstall_fixed_layout_suite.cmd"))
    Set-ItemProperty -Path $UninstallRegistryPath -Name NoModify -Value 1 -Type DWord
    Set-ItemProperty -Path $UninstallRegistryPath -Name NoRepair -Value 1 -Type DWord
}

function Main {
    $resolvedSourceRoot = Resolve-SourceRoot -ExplicitSourceRoot $SourceRoot
    Ensure-PackagePayload -CandidateRoot $resolvedSourceRoot

    $createDesktop = $true
    if ($PSBoundParameters.ContainsKey("CreateDesktopFolder")) {
        $createDesktop = [bool]$CreateDesktopFolder
    }

    if ($Gui) {
        $initialInstallDir = $DefaultInstallDir
        if ($InstallDir) {
            $initialInstallDir = $InstallDir
        }
        $selection = Show-InstallDialog -InitialInstallDir $initialInstallDir -InitialCreateDesktopFolder $createDesktop
        if ($null -eq $selection) {
            Write-Output '{"ok": false, "cancelled": true}'
            return
        }
        $InstallDir = $selection.InstallDir
        $createDesktop = [bool]$selection.CreateDesktopFolder
    } elseif (-not $InstallDir) {
        $InstallDir = $DefaultInstallDir
    }

    Copy-PackageTree -PackageRoot $resolvedSourceRoot -TargetRoot $InstallDir
    Write-InstallMetadata -TargetRoot $InstallDir -SourceRoot $resolvedSourceRoot
    Invoke-PortableRuntimeSmokeChecks -TargetRoot $InstallDir -SourceRoot $resolvedSourceRoot
    Sync-ShortcutRoot -TargetRoot $InstallDir -ShortcutRoot $StartMenuRoot
    if ($createDesktop) {
        Sync-ShortcutRoot -TargetRoot $InstallDir -ShortcutRoot $DesktopShortcutRoot
    }
    Register-UninstallEntry -TargetRoot $InstallDir

    $desktopShortcutRootValue = ""
    if ($createDesktop) {
        $desktopShortcutRootValue = $DesktopShortcutRoot
    }

    $result = [ordered]@{
        ok = $true
        installDir = $InstallDir
        startMenuRoot = $StartMenuRoot
        desktopShortcutRoot = $desktopShortcutRootValue
        portablePython = (Join-Path $InstallDir "runtime\python\python.exe")
        nativeRuntime = (Join-Path $InstallDir "runtime\native_runtime\VideoPlatform.NativeProbe.exe")
    }

    if ($Gui) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "Video Platform Fixed Layouts has been installed successfully.",
            "Video Platform Fixed Layouts",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    }

    $result | ConvertTo-Json -Depth 4
}

Main
