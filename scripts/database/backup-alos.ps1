[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$BackupDirectory,

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

if (-not (Test-Path -LiteralPath $BackupDirectory)) {
    New-Item -ItemType Directory -Path $BackupDirectory | Out-Null
}
$backupRoot = (Resolve-Path $BackupDirectory).Path
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$backupName = "alos-$timestamp.dump"
$backupPath = Join-Path $backupRoot $backupName
$manifestPath = "$backupPath.manifest.json"
$containerPath = "/tmp/$backupName"

try {
    Invoke-Docker @(
        "compose", "-f", $composePath, "exec", "-T", "postgres",
        "pg_dump", "-U", "alos", "-d", "alos", "--format=custom",
        "--no-owner", "--no-privileges", "--file=$containerPath"
    )
    Invoke-Docker @(
        "compose", "-f", $composePath, "cp", "postgres:$containerPath", $backupPath
    )

    $hash = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifest = [ordered]@{
        schema_version = "1.0.0"
        system = "ALOS"
        source_database = "alos"
        backup_file = $backupName
        sha256 = $hash
        created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        format = "postgres-custom"
        contains_business_data = $true
        handling = "RESTRICTED"
    }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8
}
finally {
    & docker compose -f $composePath exec -T postgres rm -f $containerPath | Out-Null
}

Write-Output "Backup selesai: $backupPath"
Write-Output "Manifest checksum: $manifestPath"
