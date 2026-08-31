[CmdletBinding()]
param(
    [string]$ApiBaseUrl = "http://localhost:8000/api/v1",
    [string]$FixturePath = "",
    [switch]$AllowRemote
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-AlosApi {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Token,
        [object]$Body = $null
    )

    $request = @{
        Method = $Method
        Uri = "$ApiBaseUrl$Path"
        Headers = @{ Authorization = "Bearer $Token" }
        ContentType = "application/json"
    }
    if ($null -ne $Body) {
        $request.Body = $Body | ConvertTo-Json -Depth 8 -Compress
    }
    Invoke-RestMethod @request
}

$apiUri = [Uri]$ApiBaseUrl
$isLocal = $apiUri.Host -in @("localhost", "127.0.0.1", "::1")
if (-not $isLocal -and -not $AllowRemote) {
    throw "Target non-lokal memerlukan -AllowRemote setelah environment diverifikasi."
}

$adminToken = $env:ALOS_PILOT_ADMIN_TOKEN
$directorToken = $env:ALOS_PILOT_DIRECTOR_TOKEN
if ([string]::IsNullOrWhiteSpace($adminToken) -or [string]::IsNullOrWhiteSpace($directorToken)) {
    throw "Set ALOS_PILOT_ADMIN_TOKEN dan ALOS_PILOT_DIRECTOR_TOKEN pada sesi terminal."
}

if ([string]::IsNullOrWhiteSpace($FixturePath)) {
    $repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
    $FixturePath = Join-Path $repositoryRoot "tests\fixtures\synthetic\controlled-pilot.json"
}
$resolvedFixture = Resolve-Path -LiteralPath $FixturePath
$fixture = Get-Content -LiteralPath $resolvedFixture -Raw | ConvertFrom-Json
if ($fixture.data_policy -ne "SYNTHETIC_OR_SANITIZED" -or $fixture.production_effect) {
    throw "Fixture ditolak: hanya data sintetis/tersanitasi tanpa production effect yang diizinkan."
}
if (@($fixture.users | Where-Object { $_.email -notlike "*@example.test" }).Count -gt 0) {
    throw "Fixture ditolak: identitas pilot wajib menggunakan domain example.test."
}

$health = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/health"
if ($health.environment -eq "production") {
    throw "Provisioning fixture sintetis tidak diizinkan pada production."
}

$projects = @(Invoke-AlosApi -Method Get -Path "/projects" -Token $adminToken)
$project = $projects | Where-Object { $_.code -eq $fixture.project.code } | Select-Object -First 1
if ($null -eq $project) {
    $project = Invoke-AlosApi -Method Post -Path "/projects" -Token $adminToken -Body @{
        code = $fixture.project.code
        name = $fixture.project.name
    }
    Write-Host "Proyek pilot dibuat sebagai DRAFT."
} else {
    Write-Host "Proyek pilot sudah tersedia; pembuatan dilewati."
}

foreach ($definition in $fixture.users) {
    $encodedEmail = [Uri]::EscapeDataString($definition.email)
    $directory = Invoke-AlosApi -Method Get -Path "/users?page=1&page_size=100&search=$encodedEmail" -Token $adminToken
    $user = @($directory.items) | Where-Object { $_.email -eq $definition.email } | Select-Object -First 1
    if ($null -eq $user) {
        $user = Invoke-AlosApi -Method Post -Path "/users" -Token $adminToken -Body @{
            email = $definition.email
            display_name = $definition.display_name
            role = $definition.role
            division_code = $definition.division_code
        }
        $user = Invoke-AlosApi -Method Get -Path "/users/$($user.user_id)" -Token $adminToken
        Write-Host "Pengguna sintetis dibuat: $($definition.email)"
    }

    if ($user.status -ne "ACTIVE") {
        $user = Invoke-AlosApi -Method Patch -Path "/users/$($user.user_id)/status" -Token $adminToken -Body @{
            status = "ACTIVE"
            reason = "Aktivasi controlled pilot sintetis."
        }
    }

    $hasRole = @($user.roles | Where-Object {
        $_.role -eq $definition.role -and $_.division_code -eq $definition.division_code
    }).Count -gt 0
    if (-not $hasRole) {
        Invoke-AlosApi -Method Post -Path "/users/$($user.user_id)/role-assignments" -Token $adminToken -Body @{
            role = $definition.role
            division_code = $definition.division_code
            valid_until = $null
            reason = "Provisioning controlled pilot sintetis."
        } | Out-Null
    }

    if ($definition.project_assigned) {
        $hasProject = @($user.projects | Where-Object { $_.project_id -eq $project.project_id }).Count -gt 0
        if (-not $hasProject) {
            Invoke-AlosApi -Method Post -Path "/users/$($user.user_id)/project-assignments" -Token $adminToken -Body @{
                project_id = $project.project_id
                valid_until = $null
                reason = "Penugasan controlled pilot sintetis."
            } | Out-Null
        }
    }
}

if ($project.status -in @("DRAFT", "ON_HOLD")) {
    $project = Invoke-AlosApi -Method Patch -Path "/projects/$($project.project_id)/status" -Token $directorToken -Body @{
        status = "ACTIVE"
        reason = "Aktivasi controlled pilot sintetis oleh Direktur Utama."
    }
    Write-Host "Proyek pilot diaktifkan melalui otorisasi Direktur."
} elseif ($project.status -eq "CLOSED") {
    throw "Proyek pilot berstatus CLOSED. Gunakan siklus proyek baru."
}

Write-Host "Provisioning selesai: $($project.code) · $($project.status)."
Write-Host "Lanjutkan pemeriksaan /system/pilot-readiness sebelum memulai UAT."
