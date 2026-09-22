<#
Keyword Check - Kobiga: register / update / remove the daily Windows scheduled task.

    powershell -ExecutionPolicy Bypass -File 10_automation\scheduler.ps1                          # register or update (08:45 + retries 10:45, 12:45, 14:45)
    powershell -ExecutionPolicy Bypass -File 10_automation\scheduler.ps1 -Times 09:00,11:00      # change the times
    powershell -ExecutionPolicy Bypass -File 10_automation\scheduler.ps1 -Status                  # show task, triggers, next run, last result
    powershell -ExecutionPolicy Bypass -File 10_automation\scheduler.ps1 -Unregister              # remove

The task runs:  python "<project>\10_automation\run.py"  with the project root as working directory.
Main run 08:45; the later slots are same-day RETRIES: run.py researches only the Product IDs not finished today (e.g. the
VPN was off at 08:45) and exits ALREADY_COMPLETE_TODAY without touching eBay when everything is done.
Idempotent: one fixed task name, registered with -Force, so running this again updates the same task (never a duplicate).
Runs as the current user, only while logged on, because eBay research needs the UK-VPN Chrome in this user's session
(CDP 127.0.0.1:9222). A missed slot (PC off) starts when the PC is next available; overlapping starts are ignored.
Each run is limited to 1 h 50 min so it can never overlap the next slot. No calendar date is hard-coded.
#>
param([string[]]$Times = @("08:45", "10:45", "12:45", "14:45"), [switch]$Unregister, [switch]$Status)
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
    $triggers = foreach ($tm in ($Times | ForEach-Object { $_ -split "," } | Where-Object { $_ })) {
        New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.Add([timespan]::ParseExact($tm.Trim(), "hh\:mm", $null)))   # exact HH:mm:00
    }
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -ExecutionTimeLimit (New-TimeSpan -Hours 1 -Minutes 50) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings -Principal $principal `
        -Description "Keyword Check - Kobiga daily refresh (08:45, same-day retries): live DB (approved Product IDs only) -> eBay UK research -> keywords/ranks -> validated standalone HTML -> PH Dashboard. Project: $Root" -Force | Out-Null
}
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $t) { "$TaskName is not registered"; return }
$i = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{ TaskName = $t.TaskName; State = $t.State
                   Triggers = "Daily at " + (($t.Triggers | ForEach-Object { ([datetime]$_.StartBoundary).ToString("HH:mm") }) -join ", ")
                   Action = $t.Actions[0].Execute + " " + $t.Actions[0].Arguments; NextRunTime = $i.NextRunTime; LastRunTime = $i.LastRunTime
                   LastResult = "$($i.LastTaskResult)  (0 ok, 2 PH publish failed, 3 already running, 4 eBay research failed - VPN/browser/CAPTCHA, 1 other)" } | Format-List
