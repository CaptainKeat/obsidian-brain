$ErrorActionPreference = 'Stop'
$atlasConfig = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config.json') -Raw | ConvertFrom-Json
$atlasUrl = 'http://127.0.0.1:' + $atlasConfig.port
$atlasStatus = Invoke-RestMethod -Uri ($atlasUrl + '/api/status') -NoProxy -TimeoutSec 3
if ($atlasStatus.app -ne 'neural-atlas') { throw 'The listener is not Neural Atlas.' }
$atlasPage = (Invoke-WebRequest -Uri $atlasUrl -NoProxy -TimeoutSec 3).Content
$atlasMatch = [regex]::Match($atlasPage, 'name="atlas-token" content="([a-f0-9]+)"')
if (-not $atlasMatch.Success) { throw 'Local control token not found.' }
Invoke-RestMethod -Uri ($atlasUrl + '/api/control') -Method Post -NoProxy -ContentType 'application/json' -Headers @{ 'X-Atlas-Token' = $atlasMatch.Groups[1].Value } -Body '{"action":"shutdown"}' -TimeoutSec 5 | Out-Null
Write-Output 'Atlas stopped; pause state and all evidence retained.'
