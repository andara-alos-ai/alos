[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$BackupFile,

    [string]$ComposeFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Docker {
    param([Parameter(Mandatory = $true)][string[]]$DockerArguments)

    & docker @DockerArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Perintah Docker gagal dengan exit code $LASTEXITCODE."
    }
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$composePath = if ($ComposeFile) {
    (Resolve-Path $ComposeFile).Path
} else {
    (Resolve-Path (Join-Path $repositoryRoot "infra\compose\compose.yaml")).Path
}
$resolvedBackup = (Resolve-Path $BackupFile).Path
$manifestPath = "$resolvedBackup.manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Manifest checksum tidak ditemukan: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$backupLeaf = Split-Path -Leaf $resolvedBackup
if ($manifest.backup_file -ne $backupLeaf) {
    throw "Nama file backup tidak cocok dengan manifest. Restore dibatalkan."
}
$actualHash = (Get-FileHash -LiteralPath $resolvedBackup -Algorithm SHA256).Hash.ToLowerInvariant()
if ($manifest.sha256 -ne $actualHash) {
    throw "Checksum backup tidak cocok. Restore dibatalkan."
}

$suffix = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
$restoreDatabase = "alos_restore_check_$suffix"
if ($restoreDatabase -notmatch '^alos_restore_check_[0-9]{14}$') {
    throw "Nama database uji restore tidak memenuhi guard keselamatan."
}
$containerPath = "/tmp/$backupLeaf"
$databaseCreated = $false

try {
    Invoke-Docker @(
        "compose", "-f", $composePath, "cp", $resolvedBackup, "postgres:$containerPath"
    )
    Invoke-Docker @(
        "compose", "-f", $composePath, "exec", "-T", "postgres",
        "createdb", "-U", "alos", $restoreDatabase
    )
    $databaseCreated = $true
    Invoke-Docker @(
        "compose", "-f", $composePath, "exec", "-T", "postgres",
        "pg_restore", "-U", "alos", "--dbname=$restoreDatabase",
        "--no-owner", "--no-privileges", $containerPath
    )

    $migrationCount = & docker compose -f $composePath exec -T postgres psql `
        -U alos -d $restoreDatabase -v ON_ERROR_STOP=1 -tAc `
        "SELECT count(*) FROM platform.schema_migrations"
    if ($LASTEXITCODE -ne 0 -or [int]$migrationCount.Trim() -lt 1) {
        throw "Integrity check migration pada database hasil restore gagal."
    }
    Write-Output "Restore drill lulus pada database terisolasi: $restoreDatabase"
    Write-Output "Migration records terverifikasi: $($migrationCount.Trim())"
}
finally {
    if ($databaseCreated) {
        & docker compose -f $composePath exec -T postgres dropdb `
            --if-exists --force -U alos $restoreDatabase | Out-Null
    }
    & docker compose -f $composePath exec -T postgres rm -f $containerPath | Out-Null
}
