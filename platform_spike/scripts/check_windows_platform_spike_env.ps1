param(
    [string]$ClientRoot = "D:\opsmgr\Infovision Foresight\client",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-DirIfMissing {
    param([string]$Path)
    if ($Path -and -not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Write-Utf8Json {
    param(
        [string]$Path,
        [object]$Value
    )
    $dir = Split-Path -Parent $Path
    New-DirIfMissing -Path $dir
    ($Value | ConvertTo-Json -Depth 20) | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Test-HttpUrl {
    param([string]$Url)
    try {
        $null = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 2 -UseBasicParsing
        return $true
    } catch {
        return $false
    }
}

function Get-LastRegexValue {
    param(
        [string]$Path,
        [string]$Pattern,
        [string]$GroupName = "value",
        [int]$TailLines = 4000
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $regex = [regex]$Pattern
    $value = $null
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8 -Tail $TailLines) {
        $match = $regex.Match($line)
        if ($match.Success) {
            $value = $match.Groups[$GroupName].Value
        }
    }
    return $value
}

function Get-LastRegexMatch {
    param(
        [string]$Path,
        [string]$Pattern,
        [int]$TailLines = 4000
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $regex = [regex]$Pattern
    $value = $null
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8 -Tail $TailLines) {
        $match = $regex.Match($line)
        if ($match.Success) {
            $groups = [ordered]@{}
            foreach ($groupName in $regex.GetGroupNames()) {
                if ($groupName -eq "0") {
                    continue
                }
                $groups[$groupName] = $match.Groups[$groupName].Value
            }
            $value = [ordered]@{
                line = $line
                groups = $groups
            }
        }
    }
    return $value
}

function Get-LastContextValue {
    param(
        [string]$Path,
        [string]$ComponentId,
        [string]$ServiceType
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    } catch {
        return $null
    }
    $pattern = '"componentId":\s*"' + [regex]::Escape($ComponentId) + '".+?"serviceType":\s*"' + [regex]::Escape($ServiceType) + '".+?"context":\s*"(?<value>/[^"]+)"'
    $matches = [regex]::Matches($content, $pattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if ($matches.Count -eq 0) {
        return $null
    }
    return $matches[$matches.Count - 1].Groups["value"].Value
}

function Test-LogPattern {
    param(
        [string]$Path,
        [string]$Pattern,
        [int]$TailLines = 4000
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    $regex = [regex]$Pattern
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8 -Tail $TailLines) {
        if ($regex.IsMatch($line)) {
            return $true
        }
    }
    return $false
}

function Get-XmlNodeText {
    param(
        [string]$Path,
        [string]$XPath
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        [xml]$xml = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        $node = $xml.SelectSingleNode($XPath)
        if ($node) {
            return $node.InnerText
        }
    } catch {
    }
    return $null
}

$productDir = Join-Path $ClientRoot "product"
$frameworkDir = Join-Path $ClientRoot "framework\infosightclient.1"
$componentsDir = Join-Path $ClientRoot "components"
$webcontainerDir = Join-Path $componentsDir "webcontainer.1"
$menuFile = Join-Path $productDir "META-INF\menus.xml"
$translateFile = Join-Path $productDir "META-INF\language\zh_CN\translate.properties"
$iconDir = Join-Path $productDir "META-INF\icon\menu"
$webappRoot = Join-Path $webcontainerDir "bin\webcontainer\webapp"
$probeWebappDir = Join-Path $webappRoot "platform_spike_probe"
$webLogPath = Join-Path $webcontainerDir "logs\webcontainer\webcontainer.webcontainer.debug.log"
$clientLogPath = Join-Path $frameworkDir "logs\clientframe\clientframework.clientframe.debug.log"
$localServiceConfig = Join-Path $frameworkDir "bin\ClientFrame\containocx\ChromeContainer\LocalServiceConfig.xml"
$webControlExe = Join-Path $frameworkDir "bin\ClientFrame\containocx\ChromeContainer\WebControl.exe"
$mainBrowserExe = Join-Path $webcontainerDir "bin\webcontainer\MainBrowser.exe"
$simpleWebServerExe = Join-Path $webcontainerDir "bin\webcontainer\SimpleWebServer.exe"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutputPath) {
    $repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "..\.."))
    $reportRoot = Join-Path $repoRoot "tmp\windows_env_reports"
    New-DirIfMissing -Path $reportRoot
    $OutputPath = Join-Path $reportRoot ("windows_env_" + (Get-Date).ToString("yyyyMMdd_HHmmss") + ".json")
}

$probeStaticUrl = "http://127.0.0.1:36753/platform_spike_probe/index.html"
$probePocUrl = "http://127.0.0.1:36753/platform_spike_probe/platform_spike_poc.html?autorun=1"

$servicePortStart = Get-XmlNodeText -Path $localServiceConfig -XPath "/Config/WebSocket/ServicePortStart"
$servicePortEnd = Get-XmlNodeText -Path $localServiceConfig -XPath "/Config/WebSocket/ServicePortEnd"
$loginUrl = Get-LastRegexValue -Path $webLogPath -Pattern 'loginUrl:(?<value>https://[^\s]+)'
$xresContext = Get-LastContextValue -Path $clientLogPath -ComponentId "xres" -ServiceType "xres-search"
$tvmsContext = Get-LastContextValue -Path $clientLogPath -ComponentId "tvms" -ServiceType "tvms"
$serverDeliveredVideoMonitor = Test-LogPattern -Path $clientLogPath -Pattern 'permissionCode":"vsclient_client0101"|AddAppTab:AppID=client0101,ComponentID=vsclient'
$latestClient0101Tab = Get-LastRegexMatch -Path $clientLogPath -Pattern 'AddAppTab:AppID=client0101,ComponentID=(?<component>[^,\s]+)'
$latestVideoPermission = Get-LastRegexMatch -Path $clientLogPath -Pattern 'permissionCode":"(?<permission>vsclient_client0101[^"]*)"'
$latestProbeMenuSignal = Get-LastRegexMatch -Path $clientLogPath -Pattern '(?<value>platform_spike_probe|platform_spike_poc\.html)'
$localMenuPatched = $false
$videoMonitorRedirected = $false
$probeMenuPresent = $false
$ipointRedirected = $false
$videoMonitorRedirectTarget = $null
$videoMonitorMenuSourceAssessment = "unknown"
$videoMonitorMenuEvidence = New-Object System.Collections.Generic.List[string]

if (Test-Path -LiteralPath $menuFile) {
    $menuText = Get-Content -LiteralPath $menuFile -Raw -Encoding UTF8
    $probeMenuPresent = $menuText -match 'code="platform_spike_probe"'
    $videoMonitorRedirected = $menuText -match 'code="client0101".*127\.0\.0\.1:36753/platform_spike_probe/'
    $ipointRedirected = $menuText -match 'code="ipoint".*127\.0\.0\.1:36753/platform_spike_probe/'
    $localMenuPatched = $probeMenuPresent -or $videoMonitorRedirected -or $ipointRedirected
    $redirectMatch = [regex]::Match(
        $menuText,
        'code="client0101".*?url="(?<payload>\{[^"]+\})"',
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )
    if ($redirectMatch.Success) {
        $videoMonitorRedirectTarget = $redirectMatch.Groups["payload"].Value
    }
}

if ($latestClient0101Tab) {
    $videoMonitorMenuEvidence.Add($latestClient0101Tab.line) | Out-Null
}
if ($latestVideoPermission) {
    $videoMonitorMenuEvidence.Add($latestVideoPermission.line) | Out-Null
}
if ($latestProbeMenuSignal) {
    $videoMonitorMenuEvidence.Add($latestProbeMenuSignal.line) | Out-Null
}
if ($serverDeliveredVideoMonitor -or (($latestClient0101Tab) -and $latestClient0101Tab.groups["component"] -eq "vsclient")) {
    $videoMonitorMenuSourceAssessment = "server-vsclient"
} elseif ($videoMonitorRedirected) {
    $videoMonitorMenuSourceAssessment = "local-client0101-redirect"
} elseif ($probeMenuPresent) {
    $videoMonitorMenuSourceAssessment = "local-probe-menu-only"
}

$probeFiles = @(
    "index.html",
    "webcontainer_probe.js",
    "platform_spike_poc.html",
    "platform_spike_poc.js",
    "implementation_package_harness.html",
    "implementation_package_harness.js"
)
$missingProbeFiles = @()
foreach ($fileName in $probeFiles) {
    $candidate = Join-Path $probeWebappDir $fileName
    if (-not (Test-Path -LiteralPath $candidate)) {
        $missingProbeFiles += $fileName
    }
}

$recommendations = New-Object System.Collections.Generic.List[string]
if (-not (Test-Path -LiteralPath $probeWebappDir)) {
    $recommendations.Add("Publish the platform_spike web demo to the local webcontainer webapp directory.") | Out-Null
}
if ($missingProbeFiles.Count -gt 0) {
    $recommendations.Add("Republish the probe assets because some platform_spike web demo files are missing.") | Out-Null
}
if (-not (Test-HttpUrl -Url $probeStaticUrl)) {
    $recommendations.Add("The local webcontainer static URL is not responding on 127.0.0.1:36753; start the client/webcontainer before relying on page-side probe collection.") | Out-Null
}
if ($serverDeliveredVideoMonitor) {
    $recommendations.Add("This host is still showing evidence of server-delivered vsclient menus. Prefer quick capture bundle as the primary online collection path; treat local client0101 redirects as best effort only.") | Out-Null
}
if ($videoMonitorMenuSourceAssessment -eq "server-vsclient") {
    $recommendations.Add("Video monitor is still resolving to the server-delivered vsclient menu. Use inspect_client_menu_sources.ps1 before relying on page-side Container Auth Probe.") | Out-Null
}
if (-not $xresContext -or -not $tvmsContext) {
    $recommendations.Add("Service contexts are incomplete in client logs; keep the client logged in and rerun quick capture bundle during the next live gov-network window.") | Out-Null
}
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    $recommendations.Add("WSL is not available. Use the PowerShell deployment and capture scripts directly on this Windows host.") | Out-Null
}

$result = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    host = [ordered]@{
        computerName = $env:COMPUTERNAME
        userName = $env:USERNAME
        clientRoot = $ClientRoot
        wslAvailable = [bool](Get-Command wsl.exe -ErrorAction SilentlyContinue)
    }
    paths = [ordered]@{
        productDir = $productDir
        frameworkDir = $frameworkDir
        webcontainerDir = $webcontainerDir
        menuFile = $menuFile
        translateFile = $translateFile
        iconDir = $iconDir
        probeWebappDir = $probeWebappDir
        webLogPath = $webLogPath
        clientLogPath = $clientLogPath
        localServiceConfig = $localServiceConfig
        webControlExe = $webControlExe
        mainBrowserExe = $mainBrowserExe
        simpleWebServerExe = $simpleWebServerExe
    }
    checks = [ordered]@{
        productDirExists = Test-Path -LiteralPath $productDir
        menuFileExists = Test-Path -LiteralPath $menuFile
        translateFileExists = Test-Path -LiteralPath $translateFile
        iconDirExists = Test-Path -LiteralPath $iconDir
        probeWebappDirExists = Test-Path -LiteralPath $probeWebappDir
        webLogExists = Test-Path -LiteralPath $webLogPath
        clientLogExists = Test-Path -LiteralPath $clientLogPath
        localServiceConfigExists = Test-Path -LiteralPath $localServiceConfig
        webControlExeExists = Test-Path -LiteralPath $webControlExe
        mainBrowserExeExists = Test-Path -LiteralPath $mainBrowserExe
        simpleWebServerExeExists = Test-Path -LiteralPath $simpleWebServerExe
        localProbeStaticUrlReachable = Test-HttpUrl -Url $probeStaticUrl
    }
    localService = [ordered]@{
        portStart = $servicePortStart
        portEnd = $servicePortEnd
        probeStaticUrl = $probeStaticUrl
        probePocUrl = $probePocUrl
    }
    menu = [ordered]@{
        localMenuPatched = $localMenuPatched
        probeMenuPresent = $probeMenuPresent
        videoMonitorRedirected = $videoMonitorRedirected
        videoMonitorRedirectTarget = $videoMonitorRedirectTarget
        ipointRedirected = $ipointRedirected
        missingProbeFiles = $missingProbeFiles
        serverDeliveredVideoMonitor = $serverDeliveredVideoMonitor
        latestClient0101Component = if ($latestClient0101Tab) { $latestClient0101Tab.groups["component"] } else { $null }
        latestClient0101TabLine = if ($latestClient0101Tab) { $latestClient0101Tab.line } else { $null }
        latestVideoPermissionCode = if ($latestVideoPermission) { $latestVideoPermission.groups["permission"] } else { $null }
        latestVideoPermissionLine = if ($latestVideoPermission) { $latestVideoPermission.line } else { $null }
        latestProbeMenuSignal = if ($latestProbeMenuSignal) { $latestProbeMenuSignal.groups["value"] } else { $null }
        latestProbeMenuSignalLine = if ($latestProbeMenuSignal) { $latestProbeMenuSignal.line } else { $null }
        videoMonitorMenuSourceAssessment = $videoMonitorMenuSourceAssessment
        videoMonitorMenuEvidence = $videoMonitorMenuEvidence.ToArray()
    }
    liveSignals = [ordered]@{
        loginUrl = $loginUrl
        xresSearchContext = $xresContext
        tvmsContext = $tvmsContext
    }
    recommendations = $recommendations.ToArray()
}

Write-Utf8Json -Path $OutputPath -Value $result
$summaryPath = [System.IO.Path]::ChangeExtension($OutputPath, ".txt")
$summary = @(
    "=== WINDOWS_ENV_RESULT ===",
    "outputPath=$OutputPath",
    "computerName=$($env:COMPUTERNAME)",
    "clientRoot=$ClientRoot",
    "probeWebappDir=$probeWebappDir",
    "localProbeStaticUrlReachable=$($result.checks.localProbeStaticUrlReachable)",
    "probeMenuPresent=$probeMenuPresent",
    "videoMonitorRedirected=$videoMonitorRedirected",
    "videoMonitorMenuSourceAssessment=$videoMonitorMenuSourceAssessment",
    "latestClient0101Component=$(if ($latestClient0101Tab) { $latestClient0101Tab.groups["component"] } else { '' })",
    "ipointRedirected=$ipointRedirected",
    "serverDeliveredVideoMonitor=$serverDeliveredVideoMonitor",
    "xresSearchContext=$xresContext",
    "tvmsContext=$tvmsContext",
    "loginUrl=$loginUrl",
    "recommendationCount=$($recommendations.Count)",
    "WINDOWS_ENV_RESULT_END"
)
$summary | Set-Content -LiteralPath $summaryPath -Encoding UTF8
$summary | ForEach-Object { Write-Output $_ }
Write-Output "SUMMARY_PATH=$summaryPath"
