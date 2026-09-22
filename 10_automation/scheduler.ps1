<#
Keyword Check - Kobiga: register / update / remove the daily Windows scheduled task.

    powershell -ExecutionPolicy Bypass -File 10_automation\scheduler.ps1              # register or update (daily 08:45)
    powershell -ExecutionPolicy Bypass -File 10_automation\scheduler.ps1 -Time 09:30  # change the time
    powershell -ExecutionPolicy Bypass -File 10_automation\scheduler.ps1 -Status      # show task + next run
    powershell -ExecutionPolicy Bypass -File 10_automation\scheduler.ps1 -Unregister  # remove

The task runs:  python "<project>\automation\run.py"  with the project root as working directory.
Idempotent: one fixed task name, registered with -Force, so running this again updates the same task (never a duplicate).
Runs as the current user, only while logged on, because eBay research needs the UK-VPN Chrome in this user's session
(CDP 127.0.0.1:9222). If the PC is off at 08:45 the task starts when it is next available.
No calendar date is hard-coded: the trigger is daily at -Time.
#>
param([string]$Time = "08:45", [switch]$Unregister, [switch]$Status)
$ErrorActionPreference = "Stop"
$TaskName = "KeywordCheckKobiga_Daily"
$Root = Split-Path -Parent $PSScriptRoot
$RunPy = Join-Path $Root "10_automation\run.py"

if ($Unregister) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false; "Removed $TaskName" }
    else { "$TaskName is not registered" }
    return
}
if (-not $Status) {
    if (-not (Test-Path $RunPy)) { throw "run.py not found at $RunPy" }
    $Python = (Get-Command python -ErrorAction Stop).Source
    $action = New-ScheduledTaskAction -Execute $Python -Argument "`"$RunPy`"" -WorkingDirectory $Root
    $at = [datetime]::Today.Add([timespan]::ParseExact($Time, "hh\:mm", $null))   # exact HH:mm:00, no stray seconds
    $trigger = New-ScheduledTaskTrigger -Daily -At $at
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description "Keyword Check - Kobiga daily refresh: live DB (approved Product IDs only) -> eBay UK research -> keywords/ranks -> validated standalone HTML -> PH Dashboard. Project: $Root" -Force | Out-Null
}
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $t) { "$TaskName is not registered"; return }
$i = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{ TaskName = $t.TaskName; State = $t.State; Trigger = "Daily at " + ([datetime]$t.Triggers[0].StartBoundary).ToString("HH:mm");
                   Action = $t.Actions[0].Execute + " " + $t.Actions[0].Arguments; NextRunTime = $i.NextRunTime; LastRunTime = $i.LastRunTime; LastResult = $i.LastTaskResult } | Format-List
