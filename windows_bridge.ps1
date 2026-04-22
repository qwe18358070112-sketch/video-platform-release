param(
    [Parameter(Mandatory = $true)]
    [string]$RepoPath,

    [Parameter(Mandatory = $true)]
    [ValidateSet("install-deps", "self-test", "build-release", "run", "calibrate", "inspect-calibration", "inspect-runtime", "dump-favorites", "switch-layout", "native-probe")]
    [string]$Action,

    [switch]$AllowAutoElevate,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = "utf-8"
$ExtraArgs = @($ExtraArgs | Where-Object { $_ -ne $null -and $_ -ne "" })

Set-Location -LiteralPath $RepoPath

function Invoke-BatchFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    & cmd.exe /d /c "`"$Path`""
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Get-WindowsPython {
    $pythonExe = Join-Path $RepoPath ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        Invoke-BatchFile (Join-Path $RepoPath "install_deps.bat")
    }

    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw "Windows virtual environment is still missing after install_deps.bat: $pythonExe"
    }

    return $pythonExe
}

function Invoke-WindowsPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$PythonArgs
    )

    $pythonExe = Get-WindowsPython
    & $pythonExe @PythonArgs
    exit $LASTEXITCODE
}

function Get-DotNetExe {
    $dotnet = Get-Command dotnet.exe -ErrorAction SilentlyContinue
    if ($null -eq $dotnet) {
        throw "dotnet.exe not found. Install .NET SDK 8 on Windows before running native-probe."
    }
    return $dotnet.Source
}

function Invoke-DotNetProject {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath,

        [Parameter(Mandatory = $true)]
        [string[]]$ProjectArgs
    )

    $dotnetExe = Get-DotNetExe
    & $dotnetExe run --project $ProjectPath --framework net8.0-windows -- @ProjectArgs
    exit $LASTEXITCODE
}

switch ($Action) {
    "install-deps" {
        Invoke-BatchFile (Join-Path $RepoPath "install_deps.bat")
        exit 0
    }
    "self-test" {
        Invoke-WindowsPython -PythonArgs (@("self_test.py") + $ExtraArgs)
    }
    "build-release" {
        if ($ExtraArgs.Count -eq 0) {
            Invoke-WindowsPython -PythonArgs @("build_release.py", "--output", "dist/video_platform_release.zip")
        }
        else {
            Invoke-WindowsPython -PythonArgs (@("build_release.py") + $ExtraArgs)
        }
    }
    "run" {
        $pythonArgs = @("app.py", "--run")
        if (-not $AllowAutoElevate) {
            $pythonArgs += "--no-auto-elevate"
        }
        if ($ExtraArgs.Count -eq 0) {
            $pythonArgs += @("--mode", "auto")
        }
        else {
            $pythonArgs += $ExtraArgs
        }
        Invoke-WindowsPython -PythonArgs $pythonArgs
    }
    "calibrate" {
        if ($ExtraArgs.Count -lt 1) {
            throw "Usage: windows_bridge.ps1 -Action calibrate windowed|fullscreen [extra app args]"
        }
        $pythonArgs = @("app.py", "--calibrate", $ExtraArgs[0])
        if (-not $AllowAutoElevate) {
            $pythonArgs += "--no-auto-elevate"
        }
        if ($ExtraArgs.Count -gt 1) {
            $pythonArgs += $ExtraArgs[1..($ExtraArgs.Count - 1)]
        }
        Invoke-WindowsPython -PythonArgs $pythonArgs
    }
    "inspect-calibration" {
        if ($ExtraArgs.Count -lt 1) {
            throw "Usage: windows_bridge.ps1 -Action inspect-calibration windowed|fullscreen [extra app args]"
        }
        $pythonArgs = @("app.py", "--inspect-calibration", $ExtraArgs[0])
        if (-not $AllowAutoElevate) {
            $pythonArgs += "--no-auto-elevate"
        }
        if ($ExtraArgs.Count -gt 1) {
            $pythonArgs += $ExtraArgs[1..($ExtraArgs.Count - 1)]
        }
        Invoke-WindowsPython -PythonArgs $pythonArgs
    }
    "inspect-runtime" {
        $pythonArgs = @("app.py", "--inspect-runtime")
        if (-not $AllowAutoElevate) {
            $pythonArgs += "--no-auto-elevate"
        }
        if ($ExtraArgs.Count -gt 0) {
            $pythonArgs += $ExtraArgs
        }
        Invoke-WindowsPython -PythonArgs $pythonArgs
    }
    "dump-favorites" {
        $pythonArgs = @("app.py", "--dump-favorites")
        if (-not $AllowAutoElevate) {
            $pythonArgs += "--no-auto-elevate"
        }
        if ($ExtraArgs.Count -gt 0) {
            $pythonArgs += $ExtraArgs
        }
        Invoke-WindowsPython -PythonArgs $pythonArgs
    }
    "switch-layout" {
        if ($ExtraArgs.Count -lt 1) {
            throw "Usage: windows_bridge.ps1 -Action switch-layout 4|6|9|12|13 [extra app args]"
        }
        $pythonArgs = @("app.py", "--switch-layout", $ExtraArgs[0])
        if (-not $AllowAutoElevate) {
            $pythonArgs += "--no-auto-elevate"
        }
        if ($ExtraArgs.Count -gt 1) {
            $pythonArgs += $ExtraArgs[1..($ExtraArgs.Count - 1)]
        }
        Invoke-WindowsPython -PythonArgs $pythonArgs
    }
    "native-probe" {
        $projectPath = Join-Path $RepoPath "native_runtime\VideoPlatform.NativeProbe\VideoPlatform.NativeProbe.csproj"
        if (-not (Test-Path -LiteralPath $projectPath)) {
            throw "native probe project not found: $projectPath"
        }
        $probeArgs = @("--repo-root", $RepoPath)
        if ($ExtraArgs.Count -gt 0) {
            $probeArgs += $ExtraArgs
        }
        Invoke-DotNetProject -ProjectPath $projectPath -ProjectArgs $probeArgs
    }
}
