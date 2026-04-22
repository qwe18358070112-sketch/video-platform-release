param(
    [string]$RepoRoot = "",
    [string]$ClientRoot = "D:\opsmgr\Infovision Foresight\client",
    [ValidateSet("publish-only", "probe-menu", "ipoint-probe", "ipoint-poc", "video-monitor-poc", "restore")]
    [string]$MenuMode = "publish-only",
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Ensure-Dir {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Copy-RequiredFile {
    param(
        [string]$Source,
        [string]$Target,
        [switch]$Optional
    )
    if (-not (Test-Path -LiteralPath $Source)) {
        if ($Optional) {
            return
        }
        throw "Missing source file: $Source"
    }
    $targetDir = Split-Path -Parent $Target
    Ensure-Dir -Path $targetDir
    Copy-Item -LiteralPath $Source -Destination $Target -Force
}

function Backup-Once {
    param(
        [string]$SourcePath,
        [string]$BackupPath
    )
    if (-not (Test-Path -LiteralPath $SourcePath)) {
        return
    }
    if (-not (Test-Path -LiteralPath $BackupPath)) {
        $backupDir = Split-Path -Parent $BackupPath
        Ensure-Dir -Path $backupDir
        Copy-Item -LiteralPath $SourcePath -Destination $BackupPath -Force
    }
}

function Get-MenuXml {
    param([string]$Path)
    [xml]$xml = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    return $xml
}

function Get-NamespaceManager {
    param([xml]$Xml)
    $nsmgr = New-Object System.Xml.XmlNamespaceManager($Xml.NameTable)
    $nsmgr.AddNamespace("m", "http://www.hikvision.com/compomentModel/0.5.0/menus")
    return $nsmgr
}

function Save-Xml {
    param(
        [xml]$Xml,
        [string]$Path
    )
    $settings = New-Object System.Xml.XmlWriterSettings
    $settings.Encoding = [System.Text.UTF8Encoding]::new($false)
    $settings.Indent = $true
    $writer = [System.Xml.XmlWriter]::Create($Path, $settings)
    $Xml.Save($writer)
    $writer.Dispose()
}

function Set-MenuExternal {
    param(
        [xml]$Xml,
        [string]$Code,
        [string]$ComponentMenuId,
        [string]$TargetUrl
    )
    $nsmgr = Get-NamespaceManager -Xml $Xml
    $node = $Xml.SelectSingleNode("//m:menu[@code='$Code']", $nsmgr)
    if (-not $node) {
        throw "Menu node not found: $Code"
    }
    $payload = @{
        componentId = $Code
        componentMenuId = $ComponentMenuId
        url = $TargetUrl
    } | ConvertTo-Json -Compress
    while ($node.Attributes.Count -gt 0) {
        $node.Attributes.RemoveAt(0)
    }
    $null = $node.SetAttribute("code", $Code)
    $null = $node.SetAttribute("type", "external")
    $null = $node.SetAttribute("url", $payload)
    $null = $node.SetAttribute("sort", "10")
    $null = $node.SetAttribute("openType", "embed")
}

function Ensure-ProbeMenu {
    param(
        [xml]$Xml,
        [string]$ProbeCode,
        [string]$ProbeMenuId,
        [string]$ProbeUrl
    )
    $nsUri = "http://www.hikvision.com/compomentModel/0.5.0/menus"
    $nsmgr = Get-NamespaceManager -Xml $Xml
    $video = $Xml.SelectSingleNode("//m:menu[@code='video']", $nsmgr)
    if (-not $video) {
        throw "Video root menu not found"
    }
    $existing = $Xml.SelectSingleNode("//m:menu[@code='$ProbeCode']", $nsmgr)
    $payload = @{
        componentId = $ProbeCode
        componentMenuId = $ProbeMenuId
        url = $ProbeUrl
    } | ConvertTo-Json -Compress
    if ($existing) {
        while ($existing.Attributes.Count -gt 0) {
            $existing.Attributes.RemoveAt(0)
        }
        $null = $existing.SetAttribute("code", $ProbeCode)
        $null = $existing.SetAttribute("type", "external")
        $null = $existing.SetAttribute("url", $payload)
        $null = $existing.SetAttribute("sort", "13")
        $null = $existing.SetAttribute("openType", "embed")
        return
    }

    $entry = $Xml.CreateElement("menu", $nsUri)
    $null = $entry.SetAttribute("code", $ProbeCode)
    $null = $entry.SetAttribute("type", "external")
    $null = $entry.SetAttribute("url", $payload)
    $null = $entry.SetAttribute("sort", "13")
    $null = $entry.SetAttribute("openType", "embed")

    $inserted = $false
    foreach ($child in @($video.ChildNodes)) {
        if ($child.Attributes -and $child.Attributes["code"] -and $child.Attributes["code"].Value -eq "ipoint") {
            $null = $video.InsertAfter($entry, $child)
            $inserted = $true
            break
        }
    }
    if (-not $inserted) {
        $null = $video.AppendChild($entry)
    }
}

function Ensure-TranslationEntry {
    param(
        [string]$Path,
        [hashtable]$RequiredEntries
    )
    $lines = @()
    if (Test-Path -LiteralPath $Path) {
        $lines = Get-Content -LiteralPath $Path -Encoding UTF8
    }
    $index = @{}
    for ($i = 0; $i -lt $lines.Count; $i += 1) {
        if ($lines[$i] -match '^\s*#' -or $lines[$i] -notmatch '=') {
            continue
        }
        $pair = $lines[$i].Split('=', 2)
        $index[$pair[0]] = $i
    }
    foreach ($key in $RequiredEntries.Keys) {
        $line = "$key=$($RequiredEntries[$key])"
        if ($index.ContainsKey($key)) {
            $lines[$index[$key]] = $line
        } else {
            $lines += $line
        }
    }
    Set-Content -LiteralPath $Path -Encoding UTF8 -Value ($lines -join [Environment]::NewLine)
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) {
    $RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "..\.."))
}
$srcDir = Join-Path $RepoRoot "platform_spike\web_demo"
$targetDir = Join-Path $ClientRoot "components\webcontainer.1\bin\webcontainer\webapp\platform_spike_probe"
$productDir = Join-Path $ClientRoot "product"
$menuFile = Join-Path $productDir "META-INF\menus.xml"
$translateFile = Join-Path $productDir "META-INF\language\zh_CN\translate.properties"
$iconDir = Join-Path $productDir "META-INF\icon\menu"
$backupDir = Join-Path $productDir "META-INF\.platform_spike_backup_windows"
$probeCode = "platform_spike_probe"
$probeMenuId = "platform_spike_probe_001"
$probeUrl = "http://127.0.0.1:36753/platform_spike_probe/index.html"
$pocUrl = "http://127.0.0.1:36753/platform_spike_probe/platform_spike_poc.html?autorun=1"

Ensure-Dir -Path $targetDir
Copy-RequiredFile -Source (Join-Path $srcDir "webcontainer_probe.html") -Target (Join-Path $targetDir "index.html")
Copy-RequiredFile -Source (Join-Path $srcDir "webcontainer_probe.js") -Target (Join-Path $targetDir "webcontainer_probe.js")
Copy-RequiredFile -Source (Join-Path $srcDir "platform_spike_poc.html") -Target (Join-Path $targetDir "platform_spike_poc.html")
Copy-RequiredFile -Source (Join-Path $srcDir "platform_spike_poc.js") -Target (Join-Path $targetDir "platform_spike_poc.js")
Copy-RequiredFile -Source (Join-Path $srcDir "implementation_package_harness.html") -Target (Join-Path $targetDir "implementation_package_harness.html")
Copy-RequiredFile -Source (Join-Path $srcDir "implementation_package_harness.js") -Target (Join-Path $targetDir "implementation_package_harness.js")

$harnessSourceDir = Join-Path $srcDir "harness_packages"
if (Test-Path -LiteralPath $harnessSourceDir) {
    $harnessTargetDir = Join-Path $targetDir "harness_packages"
    if (Test-Path -LiteralPath $harnessTargetDir) {
        Remove-Item -LiteralPath $harnessTargetDir -Recurse -Force
    }
    Copy-Item -LiteralPath $harnessSourceDir -Destination $harnessTargetDir -Recurse -Force
}

if ($MenuMode -eq "restore") {
    $menuBackup = Join-Path $backupDir "menus.xml.orig"
    $translateBackup = Join-Path $backupDir "translate.properties.orig"
    if (-not (Test-Path -LiteralPath $menuBackup)) {
        throw "Missing menu backup: $menuBackup"
    }
    Copy-Item -LiteralPath $menuBackup -Destination $menuFile -Force
    if (Test-Path -LiteralPath $translateBackup) {
        Copy-Item -LiteralPath $translateBackup -Destination $translateFile -Force
    }
} elseif ($MenuMode -ne "publish-only") {
    Backup-Once -SourcePath $menuFile -BackupPath (Join-Path $backupDir "menus.xml.orig")
    Backup-Once -SourcePath $translateFile -BackupPath (Join-Path $backupDir "translate.properties.orig")

    [xml]$xml = Get-MenuXml -Path $menuFile
    switch ($MenuMode) {
        "probe-menu" {
            Ensure-ProbeMenu -Xml $xml -ProbeCode $probeCode -ProbeMenuId $probeMenuId -ProbeUrl $probeUrl
            Ensure-TranslationEntry -Path $translateFile -RequiredEntries @{
                "menu.$probeCode.displayName" = "平台联调探针"
                "menu.$probeCode.description" = "本地 OpenAPI 与预览链路联调页"
                "menu.$probeMenuId.displayName" = "平台联调探针"
                "menu.$probeMenuId.description" = "本地 OpenAPI 与预览链路联调页"
            }
            $sourceIcon = Join-Path $iconDir "Infovision Foresight_ipoint.png"
            $targetIcon = Join-Path $iconDir "Infovision Foresight_platform_spike_probe.png"
            if ((Test-Path -LiteralPath $sourceIcon) -and (-not (Test-Path -LiteralPath $targetIcon))) {
                Copy-Item -LiteralPath $sourceIcon -Destination $targetIcon -Force
            }
        }
        "ipoint-probe" {
            Set-MenuExternal -Xml $xml -Code "ipoint" -ComponentMenuId "ipoint_001" -TargetUrl $probeUrl
        }
        "ipoint-poc" {
            Set-MenuExternal -Xml $xml -Code "ipoint" -ComponentMenuId "ipoint_001" -TargetUrl $pocUrl
        }
        "video-monitor-poc" {
            Set-MenuExternal -Xml $xml -Code "client0101" -ComponentMenuId "client0101" -TargetUrl $pocUrl
        }
    }
    Save-Xml -Xml $xml -Path $menuFile
}

$summary = @(
    "=== WINDOWS_DEPLOY_RESULT ===",
    "repoRoot=$RepoRoot",
    "clientRoot=$ClientRoot",
    "targetDir=$targetDir",
    "menuMode=$MenuMode",
    "menuFile=$menuFile",
    "translateFile=$translateFile",
    "backupDir=$backupDir",
    "WINDOWS_DEPLOY_RESULT_END"
)
$summary | ForEach-Object { Write-Output $_ }
