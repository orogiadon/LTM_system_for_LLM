# backup.ps1 - SQLite database backup script
#
# Usage:
#   .\scripts\backup.ps1                    # Default (save to backup directory)
#   .\scripts\backup.ps1 -OutputDir D:\bak  # Specify output directory
#   .\scripts\backup.ps1 -Keep 7            # Keep 7 generations (default: 5)

param(
    [string]$OutputDir = "",
    [int]$Keep = 5
)

$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if (-not $ScriptDir) {
    $CurrentDir = (Get-Location).Path
    if (Test-Path (Join-Path $CurrentDir "scripts\backup.ps1")) {
        $ScriptDir = Join-Path $CurrentDir "scripts"
    } else {
        $ScriptDir = $CurrentDir
    }
}

$ProjectRoot = Split-Path -Parent $ScriptDir
$DbPath = Join-Path $ProjectRoot "data\memories.db"

# Output directory
if (-not $OutputDir) {
    $OutputDir = Join-Path $ProjectRoot "backup"
}

# Create directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    Write-Host "Created backup directory: $OutputDir" -ForegroundColor Cyan
}

# Check DB exists
if (-not (Test-Path $DbPath)) {
    Write-Host "Error: Database not found: $DbPath" -ForegroundColor Red
    exit 1
}

# Backup filename
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupName = "memories_$Timestamp.db"
$BackupPath = Join-Path $OutputDir $BackupName

Write-Host "Backing up database..." -ForegroundColor Cyan
Write-Host "  Source: $DbPath"
Write-Host "  Target: $BackupPath"

# Simple file copy (works with WAL mode)
Copy-Item $DbPath $BackupPath -Force

$WalPath = "$DbPath-wal"
$ShmPath = "$DbPath-shm"

if (Test-Path $WalPath) {
    Copy-Item $WalPath "$BackupPath-wal" -Force
}
if (Test-Path $ShmPath) {
    Copy-Item $ShmPath "$BackupPath-shm" -Force
}

Write-Host "Backup completed." -ForegroundColor Green

# Show backup size
$BackupSize = (Get-Item $BackupPath).Length / 1024 / 1024
Write-Host "  Size: $([math]::Round($BackupSize, 2)) MB"

# Delete old backups
$Backups = Get-ChildItem $OutputDir -Filter "memories_*.db" | Sort-Object Name -Descending
if ($Backups.Count -gt $Keep) {
    $ToDelete = $Backups | Select-Object -Skip $Keep
    foreach ($file in $ToDelete) {
        Remove-Item $file.FullName -Force
        $walFile = "$($file.FullName)-wal"
        $shmFile = "$($file.FullName)-shm"
        if (Test-Path $walFile) { Remove-Item $walFile -Force }
        if (Test-Path $shmFile) { Remove-Item $shmFile -Force }
        Write-Host "  Deleted old backup: $($file.Name)" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Backup successful! Kept: $Keep backups" -ForegroundColor Green
