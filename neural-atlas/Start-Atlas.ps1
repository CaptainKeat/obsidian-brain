param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$atlasRoot = $PSScriptRoot
$atlasConfig = Get-Content -LiteralPath (Join-Path $atlasRoot 'config.json') -Raw | ConvertFrom-Json
$atlasUrl = 'http://127.0.0.1:' + $atlasConfig.port
try {
    $atlasHealth = Invoke-RestMethod -Uri ($atlasUrl + '/api/status') -TimeoutSec 3 -NoProxy
    if ($atlasHealth.app -ne 'neural-atlas') { throw 'Another application owns the atlas port.' }
} catch {
    # Binding inside atlas.py happens before any worker starts. Occupied ports fail safely.
    $atlasPython = Join-Path (Split-Path $atlasConfig.python) 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $atlasPython)) { $atlasPython = $atlasConfig.python }
    $atlasData = Join-Path $atlasRoot 'data'
    New-Item -ItemType Directory -Path $atlasData -Force | Out-Null
    $atlasArguments = '"' + (Join-Path $atlasRoot 'atlas.py') + '" serve --root "' + $atlasRoot + '"'
    Start-Process -FilePath $atlasPython -ArgumentList $atlasArguments -WorkingDirectory $atlasRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $atlasData 'server.log') -RedirectStandardError (Join-Path $atlasData 'server.err') | Out-Null
    $atlasReady = $false
    for ($atlasTry = 0; $atlasTry -lt 20; $atlasTry++) {
        Start-Sleep -Milliseconds 500
        try {
            $atlasHealth = Invoke-RestMethod -Uri ($atlasUrl + '/api/status') -TimeoutSec 2 -NoProxy
            if ($atlasHealth.app -eq 'neural-atlas') { $atlasReady = $true; break }
        } catch { }
    }
    if (-not $atlasReady) { throw 'Atlas did not become ready. See data/server.err. No other service was stopped.' }
}
if (-not $NoBrowser) { Start-Process $atlasUrl -WindowStyle Hidden }
Write-Output $atlasUrl
