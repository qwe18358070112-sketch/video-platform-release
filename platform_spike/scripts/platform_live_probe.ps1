param(
    [string]$LogPath = "D:\opsmgr\Infovision Foresight\client\components\webcontainer.1\logs\webcontainer\webcontainer.webcontainer.debug.log",
    [string]$ClientFrameLogPath = "D:\opsmgr\Infovision Foresight\client\framework\infosightclient.1\logs\clientframe\clientframework.clientframe.debug.log",
    [string]$DatePrefix = "",
    [int]$TimeoutSec = 5,
    [string]$OutputPath = "",
    [ValidateSet("quick", "full")]
    [string]$ProbePreset = "full",
    [switch]$SkipLocalProxy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Save-ProbeOutput {
    param(
        [string]$Path,
        [hashtable]$Result,
        [string]$Stage
    )

    $Result["stage"] = $Stage
    $Result["updatedAt"] = (Get-Date).ToString("s")

    $outputDir = Split-Path -Parent $Path
    if ($outputDir -and -not (Test-Path -LiteralPath $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    }

    ($Result | ConvertTo-Json -Depth 20) | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-LatestSessionInfo {
    param(
        [string]$Path,
        [string]$Prefix
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Log file not found: $Path"
    }

    $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $lines = $content -split "`r?`n"

    $session = [ordered]@{
        logPath = $Path
        datePrefix = $Prefix
        loginUrl = $null
        portalAddress = $null
        portalPort = $null
        userIndexCode = $null
        ticket = $null
        lastLoginLine = $null
        lastTicketLine = $null
    }

    foreach ($line in $lines) {
        if ($Prefix -and (-not $line.StartsWith($Prefix))) {
            continue
        }

        if ($line -match 'loginFinish.*"portalAddress":"([^"]+)".*"portalPort":([0-9]+).+"userIndexCode":"([^"]+)"') {
            $session.portalAddress = $matches[1]
            $session.portalPort = [int]$matches[2]
            $session.userIndexCode = $matches[3]
            $session.loginUrl = "https://$($session.portalAddress):$($session.portalPort)"
            $session.lastLoginLine = $line
        }

        if ($line -match 'loginUrl:(https://[^\s]+)') {
            $session.loginUrl = $matches[1]
            $session.lastLoginLine = $line
        }

        if (($line -match 'portalAddress":"([^"]+)"') -and (-not $session.portalAddress)) {
            $session.portalAddress = $matches[1]
        }

        if (($line -match 'portalPort":([0-9]+)') -and (-not $session.portalPort)) {
            $session.portalPort = [int]$matches[1]
        }

        if (($line -match 'userIndexCode":"([^"]+)') -and (-not $session.userIndexCode)) {
            $session.userIndexCode = $matches[1]
        }

        if ($line -match 'ticket":"([^"]+)"') {
            $session.ticket = $matches[1]
            $session.lastTicketLine = $line
        }

        if ($line -match 'Set Cookie tgt\[([^\]]+)\]') {
            $session.ticket = $matches[1]
            $session.lastTicketLine = $line
        }
    }

    return [pscustomobject]$session
}

function Get-ServiceContexts {
    param(
        [string]$Path
    )

    $contexts = [ordered]@{
        xresSearch = "/xres-search"
        tvms = "/tvms"
    }

    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]$contexts
    }

    $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8

    $xresMatches = [regex]::Matches(
        $content,
        '"componentId":\s*"xres".+?"serviceType":\s*"xres-search".+?"context":\s*"(?<context>/[^"]+)"',
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )
    if ($xresMatches.Count -gt 0) {
        $contexts.xresSearch = $xresMatches[$xresMatches.Count - 1].Groups["context"].Value
    }

    $tvmsMatches = [regex]::Matches(
        $content,
        '"componentId":\s*"tvms".+?"serviceType":\s*"tvms".+?"context":\s*"(?<context>/[^"]+)"',
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )
    if ($tvmsMatches.Count -gt 0) {
        $contexts.tvms = $tvmsMatches[$tvmsMatches.Count - 1].Groups["context"].Value
    }

    return [pscustomobject]$contexts
}

function Get-RecentContextTokens {
    param(
        [string]$Path,
        [string]$Prefix,
        [int]$TailLines = 12000,
        [int]$MaxCount = 6
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return @()
    }

    $pattern = [regex]'GetClientTicket log (?:push back|map_context_token_ insert): (?<token>[A-Fa-f0-9]{32,})'
    $tokens = New-Object System.Collections.Generic.List[string]
    $lines = Get-Content -LiteralPath $Path -Encoding UTF8 -Tail $TailLines
    foreach ($line in $lines) {
        if ($Prefix -and (-not $line.StartsWith($Prefix))) {
            continue
        }
        $match = $pattern.Match($line)
        if (-not $match.Success) {
            continue
        }
        $token = $match.Groups["token"].Value
        if ($token -and (-not $tokens.Contains($token))) {
            $tokens.Add($token) | Out-Null
        }
    }

    if ($tokens.Count -le $MaxCount) {
        return [string[]]$tokens.ToArray()
    }
    return [string[]]$tokens.GetRange($tokens.Count - $MaxCount, $MaxCount).ToArray()
}

function Parse-LogTimestamp {
    param([string]$Line)

    if (-not $Line -or $Line.Length -lt 23) {
        return $null
    }

    try {
        return [datetime]::ParseExact(
            $Line.Substring(0, 23),
            "yyyy-MM-dd HH:mm:ss.fff",
            [System.Globalization.CultureInfo]::InvariantCulture
        )
    } catch {
        return $null
    }
}

function Get-ServiceSpecificContextTokens {
    param(
        [string]$Path,
        [string]$Prefix,
        [string]$ComponentId,
        [string]$ServiceType,
        [int]$TailLines = 12000,
        [int]$BeforeWindowSec = 12,
        [int]$AfterWindowSec = 2,
        [int]$MaxCount = 6
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return @()
    }

    $tokenPattern = [regex]'GetClientTicket log (?:push back|map_context_token_ insert): (?<token>[A-Fa-f0-9]{32,})'
    $servicePattern = [regex]('"componentId":"{0}".+?"serviceType":"{1}"' -f [regex]::Escape($ComponentId), [regex]::Escape($ServiceType))
    $tokenEvents = New-Object System.Collections.Generic.List[object]
    $serviceEvents = New-Object System.Collections.Generic.List[datetime]
    $lines = Get-Content -LiteralPath $Path -Encoding UTF8 -Tail $TailLines

    foreach ($line in $lines) {
        if ($Prefix -and (-not $line.StartsWith($Prefix))) {
            continue
        }
        $timestamp = Parse-LogTimestamp -Line $line
        if ($null -eq $timestamp) {
            continue
        }

        $tokenMatch = $tokenPattern.Match($line)
        if ($tokenMatch.Success) {
            $tokenEvents.Add([pscustomobject]@{
                time = $timestamp
                token = $tokenMatch.Groups["token"].Value
            }) | Out-Null
        }

        if ($servicePattern.IsMatch($line)) {
            $serviceEvents.Add($timestamp) | Out-Null
        }
    }

    if ($serviceEvents.Count -eq 0 -or $tokenEvents.Count -eq 0) {
        return @()
    }

    $ranked = New-Object System.Collections.Generic.List[object]
    foreach ($eventTime in $serviceEvents) {
        foreach ($tokenEvent in $tokenEvents) {
            $beforeDelta = ($eventTime - $tokenEvent.time).TotalSeconds
            if ($beforeDelta -ge 0 -and $beforeDelta -le $BeforeWindowSec) {
                $ranked.Add([pscustomobject]@{
                    token = $tokenEvent.token
                    score = [math]::Abs($beforeDelta)
                    tokenTime = $tokenEvent.time
                }) | Out-Null
                continue
            }

            $afterDelta = ($tokenEvent.time - $eventTime).TotalSeconds
            if ($afterDelta -ge 0 -and $afterDelta -le $AfterWindowSec) {
                $ranked.Add([pscustomobject]@{
                    token = $tokenEvent.token
                    score = [math]::Abs($afterDelta) + 0.25
                    tokenTime = $tokenEvent.time
                }) | Out-Null
            }
        }
    }

    $ordered = $ranked |
        Sort-Object @{ Expression = "score"; Ascending = $true }, @{ Expression = "tokenTime"; Ascending = $false }

    $tokens = New-Object System.Collections.Generic.List[string]
    foreach ($item in $ordered) {
        if ($item.token -and (-not $tokens.Contains($item.token))) {
            $tokens.Add($item.token) | Out-Null
        }
        if ($tokens.Count -ge $MaxCount) {
            break
        }
    }

    return [string[]]$tokens.ToArray()
}

function Merge-ContextTokens {
    param(
        [string[]]$Preferred,
        [string[]]$Fallback,
        [int]$MaxCount = 6
    )

    $result = New-Object System.Collections.Generic.List[string]
    foreach ($group in @($Preferred, $Fallback)) {
        foreach ($token in @($group)) {
            if (-not $token) {
                continue
            }
            if (-not $result.Contains($token)) {
                $result.Add($token) | Out-Null
            }
            if ($result.Count -ge $MaxCount) {
                return [string[]]$result.ToArray()
            }
        }
    }
    return [string[]]$result.ToArray()
}

function Convert-ProbePayloadToText {
    param(
        [object]$Payload
    )

    if ($null -eq $Payload) {
        return ""
    }
    if ($Payload -is [string]) {
        return $Payload
    }
    if ($Payload -is [System.Array]) {
        $allBytes = $true
        $buffer = New-Object byte[] ($Payload.Count)
        for ($index = 0; $index -lt $Payload.Count; $index += 1) {
            try {
                $buffer[$index] = [byte]$Payload[$index]
            } catch {
                $allBytes = $false
                break
            }
        }
        if ($allBytes) {
            try {
                return [System.Text.Encoding]::UTF8.GetString($buffer)
            } catch {
            }
        }
    }

    if ($Payload.PSObject -and $Payload.PSObject.Properties["content"]) {
        $contentText = Convert-ProbePayloadToText -Payload $Payload.content
        if ($contentText) {
            return $contentText
        }
    }

    try {
        return ($Payload | ConvertTo-Json -Depth 20 -Compress)
    } catch {
        return [string]$Payload
    }
}

function Test-AppAuthFailure {
    param(
        [object]$Payload
    )

    $text = (Convert-ProbePayloadToText -Payload $Payload).ToLowerInvariant()
    return ($text -match 'token is null' -or $text -match 'token check failure' -or $text -match 'request forbidden' -or $text -match '0x11900001')
}

function Get-DirectAuthAttempts {
    param(
        [string]$Ticket,
        [string[]]$ContextTokens
    )

    $attempts = New-Object System.Collections.Generic.List[object]
    $attempts.Add([ordered]@{
        name = "cookie_only"
        headers = @{
            "Content-Type" = "application/json"
            "Cookie" = "tgt=$Ticket"
        }
    }) | Out-Null
    $attempts.Add([ordered]@{
        name = "token_only"
        headers = @{
            "Content-Type" = "application/json"
            "Token" = $Ticket
        }
    }) | Out-Null
    $attempts.Add([ordered]@{
        name = "bearer_only"
        headers = @{
            "Content-Type" = "application/json"
            "Authorization" = "Bearer $Ticket"
        }
    }) | Out-Null
    $attempts.Add([ordered]@{
        name = "cookie_and_token"
        headers = @{
            "Content-Type" = "application/json"
            "Cookie" = "tgt=$Ticket"
            "Token" = $Ticket
        }
    }) | Out-Null
    $attempts.Add([ordered]@{
        name = "cookie_and_bearer"
        headers = @{
            "Content-Type" = "application/json"
            "Cookie" = "tgt=$Ticket"
            "Authorization" = "Bearer $Ticket"
        }
    }) | Out-Null

    $candidateTokens = @()
    foreach ($contextToken in ($ContextTokens | Where-Object { $_ -and $_ -ne $Ticket })) {
        if (-not ($candidateTokens -contains $contextToken)) {
            $candidateTokens += $contextToken
        }
    }

    $index = 0
    foreach ($contextToken in $candidateTokens) {
        $index += 1
        $attempts.Add([ordered]@{
            name = "context_token_only_$index"
            headers = @{
                "Content-Type" = "application/json"
                "Token" = $contextToken
            }
        }) | Out-Null
        $attempts.Add([ordered]@{
            name = "context_bearer_only_$index"
            headers = @{
                "Content-Type" = "application/json"
                "Authorization" = "Bearer $contextToken"
            }
        }) | Out-Null
        $attempts.Add([ordered]@{
            name = "cookie_and_context_token_$index"
            headers = @{
                "Content-Type" = "application/json"
                "Cookie" = "tgt=$Ticket"
                "Token" = $contextToken
            }
        }) | Out-Null
    }

    return $attempts.ToArray()
}

function Get-LocalProxyAuthAttempts {
    param(
        [string]$Ticket,
        [string[]]$ContextTokens
    )

    $attempts = New-Object System.Collections.Generic.List[object]
    $attempts.Add([ordered]@{
        name = "local_proxy_auto_token"
        heads = @{
            "Content-Type" = "application/json"
            "Token" = ""
        }
    }) | Out-Null
    $attempts.Add([ordered]@{
        name = "local_proxy_no_auth_headers"
        heads = @{
            "Content-Type" = "application/json"
        }
    }) | Out-Null
    $attempts.Add([ordered]@{
        name = "local_proxy_token_only"
        heads = @{
            "Content-Type" = "application/json"
            "Token" = $Ticket
        }
    }) | Out-Null
    $attempts.Add([ordered]@{
        name = "local_proxy_bearer_only"
        heads = @{
            "Content-Type" = "application/json"
            "Authorization" = "Bearer $Ticket"
        }
    }) | Out-Null
    $attempts.Add([ordered]@{
        name = "local_proxy_cookie_and_token"
        heads = @{
            "Content-Type" = "application/json"
            "Token" = $Ticket
            "Cookie" = "tgt=$Ticket"
        }
    }) | Out-Null
    $attempts.Add([ordered]@{
        name = "local_proxy_cookie_and_bearer"
        heads = @{
            "Content-Type" = "application/json"
            "Authorization" = "Bearer $Ticket"
            "Cookie" = "tgt=$Ticket"
        }
    }) | Out-Null

    $candidateTokens = @()
    foreach ($contextToken in ($ContextTokens | Where-Object { $_ -and $_ -ne $Ticket })) {
        if (-not ($candidateTokens -contains $contextToken)) {
            $candidateTokens += $contextToken
        }
    }

    $index = 0
    foreach ($contextToken in $candidateTokens) {
        $index += 1
        $attempts.Add([ordered]@{
            name = "local_proxy_context_token_$index"
            heads = @{
                "Content-Type" = "application/json"
                "Token" = $contextToken
            }
        }) | Out-Null
        $attempts.Add([ordered]@{
            name = "local_proxy_context_bearer_$index"
            heads = @{
                "Content-Type" = "application/json"
                "Authorization" = "Bearer $contextToken"
            }
        }) | Out-Null
        $attempts.Add([ordered]@{
            name = "local_proxy_cookie_and_context_token_$index"
            heads = @{
                "Content-Type" = "application/json"
                "Cookie" = "tgt=$Ticket"
                "Token" = $contextToken
            }
        }) | Out-Null
    }

    return $attempts.ToArray()
}

function Invoke-ProbeRequest {
    param(
        [string]$BaseUrl,
        [string]$Ticket,
        [string[]]$ContextTokens,
        [string]$ProbeKey,
        [string]$Path,
        [string]$Method = "Post",
        [object]$Body,
        [int]$TimeoutSeconds
    )

    $uri = ($BaseUrl.TrimEnd("/") + $Path)
    $attempts = Get-DirectAuthAttempts -Ticket $Ticket -ContextTokens $ContextTokens

    $lastAuthFailure = $null

    foreach ($attempt in $attempts) {
        try {
            $requestArgs = @{
                Uri = $uri
                Method = $Method
                Headers = $attempt.headers
                TimeoutSec = $TimeoutSeconds
                UseBasicParsing = $true
            }
            if ($Method -ne "Get" -and $null -ne $Body) {
                $requestArgs["Body"] = ($Body | ConvertTo-Json -Depth 20 -Compress)
            }
            $response = Invoke-WebRequest @requestArgs
            $parsed = $null
            try {
                $parsed = $response.Content | ConvertFrom-Json -Depth 20
            } catch {
                $parsed = $response.Content
            }

            $contentText = Convert-ProbePayloadToText -Payload $parsed

            if (Test-AppAuthFailure -Payload $parsed) {
                $lastAuthFailure = [pscustomobject]@{
                    key = $ProbeKey
                    path = $Path
                    url = $uri
                    method = $Method
                    authMode = $attempt.name
                    ok = $false
                    statusCode = [int]$response.StatusCode
                    error = "Application-level auth rejected current header shape"
                    responseBody = $contentText
                }
                continue
            }

            return [pscustomobject]@{
                key = $ProbeKey
                path = $Path
                url = $uri
                method = $Method
                authMode = $attempt.name
                ok = $true
                statusCode = [int]$response.StatusCode
                content = $parsed
            }
        } catch {
            $resp = $_.Exception.Response
            $statusCode = $null
            $rawBody = $null

            if ($resp) {
                try {
                    $statusCode = [int]$resp.StatusCode
                } catch {
                    $statusCode = $null
                }

                try {
                    $stream = $resp.GetResponseStream()
                    if ($stream) {
                        $reader = New-Object System.IO.StreamReader($stream)
                        $rawBody = $reader.ReadToEnd()
                        $reader.Dispose()
                    }
                } catch {
                    $rawBody = $null
                }
            }

            $errorObject = [pscustomobject]@{
                key = $ProbeKey
                path = $Path
                url = $uri
                method = $Method
                authMode = $attempt.name
                ok = $false
                statusCode = $statusCode
                error = $_.Exception.Message
                responseBody = $rawBody
            }

            if ($statusCode -and $statusCode -ne 401 -and $statusCode -ne 403) {
                return $errorObject
            }
        }
    }

    if ($null -ne $lastAuthFailure) {
        return $lastAuthFailure
    }

    return [pscustomobject]@{
        key = $ProbeKey
        path = $Path
        url = $uri
        method = $Method
        authMode = "none_succeeded"
        ok = $false
        statusCode = $null
        error = "All auth modes failed"
        responseBody = $null
    }
}

function Invoke-LocalProxyProbe {
    param(
        [string]$BaseUrl,
        [string]$Ticket,
        [string[]]$ContextTokens,
        [string]$ProbeKey,
        [string]$Path,
        [string]$Method = "Post",
        [object]$Body,
        [int]$TimeoutSeconds
    )

    $targetUrl = ($BaseUrl.TrimEnd("/") + $Path)
    $attempts = Get-LocalProxyAuthAttempts -Ticket $Ticket -ContextTokens $ContextTokens

    $effectiveTimeout = [Math]::Max($TimeoutSeconds, 4)
    $lastAuthFailure = $null

    foreach ($attempt in $attempts) {
        $proxyPayload = @{
            method = $Method.ToUpperInvariant()
            timeout = $effectiveTimeout
            url = $targetUrl
            heads = $attempt.heads
            body = $Body
        }

        try {
            $jsonBody = ($proxyPayload | ConvertTo-Json -Depth 20 -Compress)
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:36753/proxy" -Method Post -Headers @{ "Content-Type" = "application/json" } -Body $jsonBody -TimeoutSec $effectiveTimeout -UseBasicParsing
            $parsed = $null
            try {
                $parsed = $response.Content | ConvertFrom-Json -Depth 20
            } catch {
                $parsed = $response.Content
            }

            $contentText = Convert-ProbePayloadToText -Payload $parsed

            if (Test-AppAuthFailure -Payload $parsed) {
                $lastAuthFailure = [pscustomobject]@{
                    key = $ProbeKey
                    path = $Path
                    url = $targetUrl
                    method = $Method
                    authMode = $attempt.name
                    ok = $false
                    statusCode = [int]$response.StatusCode
                    error = "Application-level auth rejected current proxy header shape"
                    responseBody = $contentText
                }
                continue
            }

            return [pscustomobject]@{
                key = $ProbeKey
                path = $Path
                url = $targetUrl
                method = $Method
                authMode = $attempt.name
                ok = $true
                statusCode = [int]$response.StatusCode
                content = $parsed
            }
        } catch {
            $resp = $_.Exception.Response
            $statusCode = $null
            $rawBody = $null

            if ($resp) {
                try {
                    $statusCode = [int]$resp.StatusCode
                } catch {
                    $statusCode = $null
                }

                try {
                    $stream = $resp.GetResponseStream()
                    if ($stream) {
                        $reader = New-Object System.IO.StreamReader($stream)
                        $rawBody = $reader.ReadToEnd()
                        $reader.Dispose()
                    }
                } catch {
                    $rawBody = $null
                }
            }

            if ($statusCode -and $statusCode -ne 401 -and $statusCode -ne 403) {
                return [pscustomobject]@{
                    key = $ProbeKey
                    path = $Path
                    url = $targetUrl
                    method = $Method
                    authMode = $attempt.name
                    ok = $false
                    statusCode = $statusCode
                    error = $_.Exception.Message
                    responseBody = $rawBody
                }
            }
        }
    }

    if ($null -ne $lastAuthFailure) {
        return $lastAuthFailure
    }

    return [pscustomobject]@{
        key = $ProbeKey
        path = $Path
        url = $targetUrl
        method = $Method
        authMode = "local_proxy_none_succeeded"
        ok = $false
        statusCode = $null
        error = "All local proxy auth modes failed"
        responseBody = $null
    }
}

function Get-ProbeDefinitions {
    param(
        [string]$Preset,
        [pscustomobject]$Session,
        [pscustomobject]$ServiceContexts
    )

    if ($Preset -eq "quick") {
        return @(
            [ordered]@{
                key = "legacy-resource-tree"
                path = "/api/resource/v1/unit/getAllTreeCode"
                method = "Post"
                body = @{}
            },
            [ordered]@{
                key = "xres-org-tree"
                path = "$($ServiceContexts.xresSearch)/service/rs/orgTree/v1/findOrgTreesByAuthAndParam?userId=$($Session.userIndexCode)"
                method = "Post"
                body = @{
                    resourceType = "CAMERA"
                    catalogDictionaryCode = @("basic_tree", "bvideo_basic_tree", "imp_tree")
                }
            },
            [ordered]@{
                key = "legacy-tvwall-allResources"
                path = "/api/tvms/v1/tvwall/allResources"
                method = "Post"
                body = @{}
            },
            [ordered]@{
                key = "tvms-ruok"
                path = "$($ServiceContexts.tvms)/v1/ruok?method=GET"
                method = "Get"
                body = $null
            },
            [ordered]@{
                key = "tvms-all"
                path = "$($ServiceContexts.tvms)/v1/all?method=GET&userIndexCode=$($Session.userIndexCode)"
                method = "Get"
                body = $null
            }
        )
    }

    return @(
        [ordered]@{ key = "legacy-resource-tree"; path = "/api/resource/v1/unit/getAllTreeCode"; method = "Post"; body = @{} },
        [ordered]@{ key = "xres-org-tree"; path = "$($ServiceContexts.xresSearch)/service/rs/orgTree/v1/findOrgTreesByAuthAndParam?userId=$($Session.userIndexCode)"; method = "Post"; body = @{ resourceType = "CAMERA"; catalogDictionaryCode = @("basic_tree", "bvideo_basic_tree", "imp_tree") } },
        [ordered]@{ key = "legacy-cameras"; path = "/api/resource/v1/cameras"; method = "Post"; body = @{ pageNo = 1; pageSize = 5; treeCode = "0" } },
        [ordered]@{ key = "legacy-preview-urls"; path = "/api/video/v1/cameras/previewURLs"; method = "Post"; body = @{ cameraIndexCodes = @("33099952001320100537"); streamType = 0; protocol = "hls" } },
        [ordered]@{ key = "legacy-tvwall-allResources"; path = "/api/tvms/v1/tvwall/allResources"; method = "Post"; body = @{} },
        [ordered]@{ key = "tvms-ruok"; path = "$($ServiceContexts.tvms)/v1/ruok?method=GET"; method = "Get"; body = $null },
        [ordered]@{ key = "tvms-all"; path = "$($ServiceContexts.tvms)/v1/all?method=GET&userIndexCode=$($Session.userIndexCode)"; method = "Get"; body = $null }
    )
}

$result = $null

try {
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }

    if (-not $DatePrefix) {
        $DatePrefix = (Get-Date).ToString("yyyy-MM-dd")
    }

    if (-not $OutputPath) {
        $repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
        $OutputPath = Join-Path $repoRoot "tmp\platform_live_probe_last.json"
    }

    $session = Get-LatestSessionInfo -Path $LogPath -Prefix $DatePrefix
    $serviceContexts = Get-ServiceContexts -Path $ClientFrameLogPath
    $contextTokens = Get-RecentContextTokens -Path $ClientFrameLogPath -Prefix $DatePrefix
    $contextTokensByService = [ordered]@{
        xresSearch = Get-ServiceSpecificContextTokens -Path $ClientFrameLogPath -Prefix $DatePrefix -ComponentId "xres" -ServiceType "xres-search"
        tvms = Get-ServiceSpecificContextTokens -Path $ClientFrameLogPath -Prefix $DatePrefix -ComponentId "tvms" -ServiceType "tvms"
    }
    if (-not $session.loginUrl) {
        throw "No loginUrl found in log for prefix $DatePrefix"
    }
    if (-not $session.ticket) {
        throw "No ticket found in log for prefix $DatePrefix"
    }

    $session | Add-Member -NotePropertyName "contextTokens" -NotePropertyValue @($contextTokens) -Force
    $session | Add-Member -NotePropertyName "contextTokensByService" -NotePropertyValue $contextTokensByService -Force

    $result = [ordered]@{
        generatedAt = (Get-Date).ToString("s")
        probePreset = $ProbePreset
        timeoutSec = $TimeoutSec
        localProxyEnabled = (-not $SkipLocalProxy.IsPresent)
        session = $session
        serviceContexts = $serviceContexts
        connectivity = $null
        probes = @()
    }
    Save-ProbeOutput -Path $OutputPath -Result $result -Stage "session_loaded"

    try {
        $connectResponse = Invoke-WebRequest -Uri $session.loginUrl -Method Head -TimeoutSec $TimeoutSec -UseBasicParsing
        $result.connectivity = [ordered]@{
            ok = $true
            statusCode = [int]$connectResponse.StatusCode
            url = $session.loginUrl
        }
    } catch {
        $result.connectivity = [ordered]@{
            ok = $false
            statusCode = $null
            url = $session.loginUrl
            error = $_.Exception.Message
        }
    }
    Save-ProbeOutput -Path $OutputPath -Result $result -Stage "connectivity_checked"

    $probes = Get-ProbeDefinitions -Preset $ProbePreset -Session $session -ServiceContexts $serviceContexts

    foreach ($probe in $probes) {
        $serviceScopedTokens = $contextTokens
        if ($probe.key -like "xres-*") {
            $serviceScopedTokens = Merge-ContextTokens -Preferred $contextTokensByService.xresSearch -Fallback $contextTokens
        } elseif ($probe.key -like "tvms-*") {
            $serviceScopedTokens = Merge-ContextTokens -Preferred $contextTokensByService.tvms -Fallback $contextTokens
        }
        $result.probes += Invoke-ProbeRequest -BaseUrl $session.loginUrl -Ticket $session.ticket -ContextTokens $serviceScopedTokens -ProbeKey $probe.key -Path $probe.path -Method $probe.method -Body $probe.body -TimeoutSeconds $TimeoutSec
        Save-ProbeOutput -Path $OutputPath -Result $result -Stage ("probe_completed:" + $probe.key)
    }

    if (-not $SkipLocalProxy.IsPresent) {
        $proxyCandidates = @(
            [ordered]@{ key = "xres-org-tree-proxy"; path = "$($ServiceContexts.xresSearch)/service/rs/orgTree/v1/findOrgTreesByAuthAndParam?userId=$($Session.userIndexCode)"; method = "Post"; body = @{ resourceType = "CAMERA"; catalogDictionaryCode = @("basic_tree", "bvideo_basic_tree", "imp_tree") } },
            [ordered]@{ key = "tvms-ruok-proxy"; path = "$($ServiceContexts.tvms)/v1/ruok?method=GET"; method = "Get"; body = $null },
            [ordered]@{ key = "tvms-all-proxy"; path = "$($ServiceContexts.tvms)/v1/all?method=GET&userIndexCode=$($Session.userIndexCode)"; method = "Get"; body = $null }
        )
        foreach ($proxyProbe in $proxyCandidates) {
            $serviceScopedTokens = $contextTokens
            if ($proxyProbe.key -like "xres-*") {
                $serviceScopedTokens = Merge-ContextTokens -Preferred $contextTokensByService.xresSearch -Fallback $contextTokens
            } elseif ($proxyProbe.key -like "tvms-*") {
                $serviceScopedTokens = Merge-ContextTokens -Preferred $contextTokensByService.tvms -Fallback $contextTokens
            }
            $result.probes += Invoke-LocalProxyProbe -BaseUrl $session.loginUrl -Ticket $session.ticket -ContextTokens $serviceScopedTokens -ProbeKey $proxyProbe.key -Path $proxyProbe.path -Method $proxyProbe.method -Body $proxyProbe.body -TimeoutSeconds $TimeoutSec
            Save-ProbeOutput -Path $OutputPath -Result $result -Stage ("proxy_probe_completed:" + $proxyProbe.key)
        }
    }
    Save-ProbeOutput -Path $OutputPath -Result $result -Stage "complete"
    Write-Output "OUTPUT=$OutputPath"
    Write-Output ($result | ConvertTo-Json -Depth 6)
} catch {
    if ($result) {
        $result["error"] = $_.Exception.Message
        $result["errorType"] = $_.Exception.GetType().FullName
        $result["errorDetail"] = $_.Exception.ToString()
        $result["scriptStackTrace"] = $_.ScriptStackTrace
        Save-ProbeOutput -Path $OutputPath -Result $result -Stage "error"
    }
    Write-Error $_
    exit 1
}
