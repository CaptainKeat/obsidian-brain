param(
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$DailyAt = '03:00',
    [switch]$PlanOnly,
    [switch]$Start,
    [switch]$Remove
)
$ErrorActionPreference = 'Stop'
$configPath = (Resolve-Path -LiteralPath $Config).Path
$stack = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$statePath = [System.IO.Path]::GetFullPath($stack.state)
if ($DailyAt -notmatch '^([01]\d|2[0-3]):[0-5]\d$') { throw 'DailyAt must be HH:mm in local Windows time.' }
$marker = 'ObsidianBrainStack/' + $stack.instance_id + '/' + $configPath
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$taskFolder = Join-Path $statePath 'scheduler'
New-Item -ItemType Directory -Path $taskFolder -Force | Out-Null
function Escape-Xml([string]$Value) { [System.Security.SecurityElement]::Escape($Value) }
$plans = @()
foreach ($kind in @('brain','atlas','graph')) {
    $taskName = 'Obsidian Brain Stack ' + $stack.instance_id + ' ' + $kind
    $pythonPath = if ($kind -eq 'graph') { $stack.graph_python } else { $stack.python }
    $pythonwPath = Join-Path (Split-Path $pythonPath) 'pythonw.exe'
    if (Test-Path -LiteralPath $pythonwPath) { $pythonPath = $pythonwPath }
    $runner = if ($kind -eq 'graph') { 'graph_refresh.py' } else { 'supervise_stack.py' }
    $scriptPath = Join-Path $stack.repo ('scripts\' + $runner)
    if (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $scriptPath)) { throw 'Configured Python or runner is missing.' }
    $arguments = '-B "' + $scriptPath + '" --config "' + $configPath + '"'
    if ($kind -ne 'graph') { $arguments += ' --kind ' + $kind }
    $triggers = if ($kind -eq 'graph') {
        '<CalendarTrigger><StartBoundary>' + (Get-Date -Format 'yyyy-MM-dd') + 'T' + $DailyAt + ':00</StartBoundary><Enabled>true</Enabled><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>'
    } else {
        '<LogonTrigger><Enabled>true</Enabled><UserId>' + $sid + '</UserId><Delay>PT20S</Delay></LogonTrigger>'
    }
    $limit = if ($kind -eq 'graph') { 'PT45M' } else { 'PT0S' }
    $restart = if ($kind -eq 'graph') { '' } else { '<RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>' }
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<RegistrationInfo><Description>$(Escape-Xml $marker)</Description></RegistrationInfo>
<Triggers>$triggers</Triggers>
<Principals><Principal id="User"><UserId>$sid</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><ExecutionTimeLimit>$limit</ExecutionTimeLimit>$restart</Settings>
<Actions Context="User"><Exec><Command>$(Escape-Xml $pythonPath)</Command><Arguments>$(Escape-Xml $arguments)</Arguments><WorkingDirectory>$(Escape-Xml $stack.repo)</WorkingDirectory></Exec></Actions>
</Task>
"@
    $xmlPath = Join-Path $taskFolder ($kind + '.xml')
    [System.IO.File]::WriteAllText($xmlPath, $xml, [System.Text.Encoding]::Unicode)
    $plans += [pscustomobject]@{name=$taskName;kind=$kind;xml=$xmlPath}
}
if ($PlanOnly) { $plans | ConvertTo-Json; return }
# Validate every collision before changing any task.
foreach ($plan in $plans) {
    $existing = Get-ScheduledTask -TaskName $plan.name -ErrorAction SilentlyContinue
    if ($existing -and $existing.Description -ne $marker) { throw ('Refusing foreign task: ' + $plan.name) }
}
if ($Remove) {
    foreach ($kind in @('brain','atlas')) { New-Item -ItemType File -Path (Join-Path $statePath ($kind + '.stop')) -Force | Out-Null }
    Start-Sleep -Seconds 2
    foreach ($plan in $plans) {
        if (Get-ScheduledTask -TaskName $plan.name -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $plan.name -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $plan.name -Confirm:$false
        }
    }
    Write-Output 'Removed only this configured stack tasks; state and backups retained.'
    return
}
$newTasks = @()
try {
    foreach ($plan in $plans) {
        $existing = Get-ScheduledTask -TaskName $plan.name -ErrorAction SilentlyContinue
        if ($existing) { Export-ScheduledTask -TaskName $plan.name | Set-Content -LiteralPath ($plan.xml + '.previous.xml') -Encoding Unicode }
        Register-ScheduledTask -TaskName $plan.name -Xml (Get-Content -LiteralPath $plan.xml -Raw) -Force | Out-Null
        if (-not $existing) { $newTasks += $plan.name }
    }
} catch {
    foreach ($task in $newTasks) { Unregister-ScheduledTask -TaskName $task -Confirm:$false }
    throw
}
$plans | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskFolder 'installed.json') -Encoding UTF8
if ($Start) {
    foreach ($kind in @('brain','atlas')) {
        $stopPath = Join-Path $statePath ($kind + '.stop')
        if (Test-Path -LiteralPath $stopPath) { Remove-Item -LiteralPath $stopPath }
    }
    foreach ($plan in $plans) { Start-ScheduledTask -TaskName $plan.name }
}
$plans | ConvertTo-Json
