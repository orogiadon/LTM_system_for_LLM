# setup_scheduler.ps1 - Windows Task Scheduler setup script
#
# Usage:
#   1. Open PowerShell as Administrator
#   2. Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
#   3. cd c:\Users\XXX\Desktop\work\LTM_system
#   4. .\scripts\setup_scheduler.ps1
#
# To remove:
#   .\scripts\setup_scheduler.ps1 -Remove

param(
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = $null
if ($PSScriptRoot) {
    $ScriptDir = $PSScriptRoot
}
if (-not $ScriptDir -and $MyInvocation.MyCommand.Path) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if (-not $ScriptDir) {
    $CurrentDir = (Get-Location).Path
    if (Test-Path (Join-Path $CurrentDir "scripts\setup_scheduler.ps1")) {
        $ScriptDir = Join-Path $CurrentDir "scripts"
    } else {
        $ScriptDir = $CurrentDir
    }
}

# Project root (parent of scripts directory)
$ProjectRoot = Split-Path -Parent $ScriptDir

# Configuration
$TaskName = "LTM_System_Compression"
$TaskDescription = "Long-term Memory System - Daily compression batch"
$ScriptPath = Join-Path $ProjectRoot "src\compression.py"
$ConfigPath = Join-Path $ProjectRoot "config\config.json"
$PythonPath = "python"

# Read schedule hour from config
$ScheduleHour = 3
if (Test-Path $ConfigPath) {
    try {
        $Config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        if ($Config.compression.schedule_hour) {
            $ScheduleHour = $Config.compression.schedule_hour
        }
    } catch {
        Write-Host "Warning: Could not read config.json, using default schedule_hour: $ScheduleHour" -ForegroundColor Yellow
    }
}

if ($Remove) {
    Write-Host "Removing scheduled task: $TaskName" -ForegroundColor Yellow
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Task removed successfully." -ForegroundColor Green
    } else {
        Write-Host "Task not found." -ForegroundColor Gray
    }
    exit 0
}

# Create task
Write-Host "Setting up scheduled task: $TaskName" -ForegroundColor Cyan
Write-Host "  Script: $ScriptPath"
Write-Host "  Python: $PythonPath"
Write-Host "  Schedule: Daily at ${ScheduleHour}:00"

# Check script exists
if (-not (Test-Path $ScriptPath)) {
    Write-Host "Error: Script not found: $ScriptPath" -ForegroundColor Red
    exit 1
}

# Remove existing task if present
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Task already exists. Removing old task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Action: Run Python script
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$ScriptPath`""

# Trigger: Daily at scheduled hour
$Trigger = New-ScheduledTaskTrigger -Daily -At "${ScheduleHour}:00"

# Settings: StartWhenAvailable for missed schedules
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Principal: Current user
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# Register task
$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description $TaskDescription
Register-ScheduledTask -TaskName $TaskName -InputObject $Task

Write-Host ""
Write-Host "Task created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "To verify:" -ForegroundColor Cyan
Write-Host "  Get-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To run manually:" -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To remove:" -ForegroundColor Cyan
Write-Host "  .\scripts\setup_scheduler.ps1 -Remove"
