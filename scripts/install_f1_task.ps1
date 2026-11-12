# Registers the hourly Windows scheduled task that runs the F1 forward paper test.
# Paper trading only: it reads public Kraken data and never places real orders.
#
# Run from the project root:   powershell -ExecutionPolicy Bypass -File scripts\install_f1_task.ps1
# Remove later with:           Unregister-ScheduledTask -TaskName "algorhythm F1" -Confirm:$false

$root = Split-Path -Parent $PSScriptRoot
$pythonw = "C:\Users\j2lab\AppData\Local\Programs\Python\Python313\pythonw.exe"

$action = New-ScheduledTaskAction -Execute $pythonw `
    -Argument "`"$root\scripts\run_f1_scheduled.py`"" -WorkingDirectory $root

# Every hour at :10, starting at the next :10. Hourly runs mean a sleeping or rebooted
# machine catches up within the hour; each daily candle is only processed once.
$first = (Get-Date).Date.AddHours((Get-Date).Hour + 1).AddMinutes(10)
$trigger = New-ScheduledTaskTrigger -Once -At $first -RepetitionInterval (New-TimeSpan -Hours 1)

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "algorhythm F1" -Action $action -Trigger $trigger -Settings $settings `
    -Description "F1 forward paper test (algorhythm): processes newly closed daily candles hourly. Paper only." | Out-Null

Get-ScheduledTask -TaskName "algorhythm F1" | Get-ScheduledTaskInfo |
    Select-Object TaskName, NextRunTime | Format-List
