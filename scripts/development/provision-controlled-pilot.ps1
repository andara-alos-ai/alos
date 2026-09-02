[CmdletBinding()]
param(
    [string]$ApiBaseUrl = "http://localhost:8000/api/v1",
    [string]$FixturePath = "",
    [switch]$AllowRemote,
    [switch]$SkipScenarioData
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-AlosApi {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Token,
        [object]$Body = $null,
        [hashtable]$AdditionalHeaders = @{}
    )

    $headers = @{ Authorization = "Bearer $Token" }
    foreach ($key in $AdditionalHeaders.Keys) {
        $headers[$key] = $AdditionalHeaders[$key]
    }
    $request = @{
        Method = $Method
        Uri = "$ApiBaseUrl$Path"
        Headers = $headers
        ContentType = "application/json"
    }
    if ($null -ne $Body) {
        $request.Body = $Body | ConvertTo-Json -Depth 8 -Compress
    }
    $response = Invoke-RestMethod @request
    $response | ForEach-Object { $_ }
}

function New-AlosLocalToken {
    param(
        [Parameter(Mandatory = $true)][guid]$OrganizationId,
        [Parameter(Mandatory = $true)][string]$Role,
        [string[]]$DivisionCodes = @()
    )

    $response = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/auth/local-token" `
        -ContentType "application/json" -Body (@{
            user_id = [guid]::NewGuid()
            organization_id = $OrganizationId
            roles = @($Role)
            division_codes = @($DivisionCodes)
            project_ids = @()
        } | ConvertTo-Json -Compress)
    return $response.access_token
}

function New-AlosPilotToken {
    param([Parameter(Mandatory = $true)][guid]$UserId)

    $response = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/auth/pilot-login" `
        -ContentType "application/json" -Body (@{ user_id = $UserId } | ConvertTo-Json -Compress)
    return $response.access_token
}

function Get-AlosPageItems {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Token
    )

    $page = Invoke-AlosApi -Method Get -Path $Path -Token $Token
    @($page.items) | ForEach-Object { $_ }
}

function Get-OrCreateSyntheticDocument {
    param(
        [Parameter(Mandatory = $true)][string]$Token,
        [Parameter(Mandatory = $true)][guid]$ProjectId,
        [Parameter(Mandatory = $true)][string]$LogicalName,
        [Parameter(Mandatory = $true)][string]$ObjectKey,
        [Parameter(Mandatory = $true)][string]$Sha256
    )

    $search = [Uri]::EscapeDataString($LogicalName)
    $documents = Get-AlosPageItems -Path "/documents?page=1&page_size=100&project_id=$ProjectId&search=$search" -Token $Token
    $document = $documents | Where-Object { $_.logical_name -eq $LogicalName } | Select-Object -First 1
    if ($null -eq $document) {
        $document = Invoke-AlosApi -Method Post -Path "/documents" -Token $Token -Body @{
            project_id = $ProjectId
            logical_name = $LogicalName
            classification = "INTERNAL"
            object_key = $ObjectKey
            sha256 = $Sha256
            media_type = "application/pdf"
            size_bytes = 1024
        }
    }
    return $document
}

$apiUri = [Uri]$ApiBaseUrl
$isLocal = $apiUri.Host -in @("localhost", "127.0.0.1", "::1")
if (-not $isLocal -and -not $AllowRemote) {
    throw "Target non-lokal memerlukan -AllowRemote setelah environment diverifikasi."
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

$adminToken = $env:ALOS_PILOT_ADMIN_TOKEN
$directorToken = $env:ALOS_PILOT_DIRECTOR_TOKEN
if ([string]::IsNullOrWhiteSpace($adminToken) -or [string]::IsNullOrWhiteSpace($directorToken)) {
    if (-not $isLocal -or $health.environment -notin @("local", "test")) {
        throw "Target non-lokal memerlukan ALOS_PILOT_ADMIN_TOKEN dan ALOS_PILOT_DIRECTOR_TOKEN."
    }
    $context = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/auth/pilot-bootstrap-context"
    if ($context.organization_code -ne $fixture.organization_code) {
        throw "Organisasi API tidak sesuai dengan fixture controlled pilot."
    }
    $adminToken = New-AlosLocalToken -OrganizationId $context.organization_id -Role "IT_ADMIN" -DivisionCodes @("IT")
    $directorToken = New-AlosLocalToken -OrganizationId $context.organization_id -Role "DIRECTOR"
    Write-Host "Token bootstrap lokal dibuat sementara tanpa menyimpan credential."
}

$projects = @(
    Invoke-AlosApi -Method Get -Path "/projects" -Token $adminToken |
        Where-Object { $null -ne $_ }
)
$project = $projects | Where-Object {
    $null -ne $_ -and
    $_.PSObject.Properties.Name -contains "code" -and
    $_.code -eq $fixture.project.code
} | Select-Object -First 1
if ($null -eq $project) {
    $project = Invoke-AlosApi -Method Post -Path "/projects" -Token $adminToken -Body @{
        code = $fixture.project.code
        name = $fixture.project.name
    }
    Write-Host "Proyek pilot dibuat sebagai DRAFT."
} else {
    Write-Host "Proyek pilot sudah tersedia; pembuatan dilewati."
}

$usersByEmail = @{}
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
    $usersByEmail[$definition.email] = Invoke-AlosApi -Method Get -Path "/users/$($user.user_id)" -Token $adminToken
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

if (-not $SkipScenarioData) {
    if (-not $isLocal -or $health.environment -notin @("local", "test")) {
        throw "Data skenario metadata-only hanya boleh diprovisikan pada environment local/test."
    }

    $salesToken = New-AlosPilotToken -UserId $usersByEmail["sales.a.pilot@example.test"].user_id
    $financeToken = New-AlosPilotToken -UserId $usersByEmail["finance.a.pilot@example.test"].user_id
    $propertyToken = New-AlosPilotToken -UserId $usersByEmail["property.a.pilot@example.test"].user_id
    $legalToken = New-AlosPilotToken -UserId $usersByEmail["legal.a.pilot@example.test"].user_id
    $hrToken = New-AlosPilotToken -UserId $usersByEmail["hr.a.pilot@example.test"].user_id
    $executiveToken = New-AlosPilotToken -UserId $usersByEmail["executive.pilot@example.test"].user_id

    $salesScenario = $fixture.scenarios.sales
    $leadSearch = [Uri]::EscapeDataString($salesScenario.lead_alias)
    $leads = Get-AlosPageItems -Path "/leads?page=1&page_size=100&project_id=$($project.project_id)&search=$leadSearch" -Token $salesToken
    if (@($leads | Where-Object { $_.full_name -eq $salesScenario.lead_alias }).Count -eq 0) {
        Invoke-AlosApi -Method Post -Path "/leads" -Token $salesToken -AdditionalHeaders @{
            "Idempotency-Key" = "pilot-sales-lead-syn-001"
        } -Body @{
            project_id = $project.project_id
            full_name = $salesScenario.lead_alias
            phone = $salesScenario.phone
            source = $salesScenario.source
            consent_recorded = $salesScenario.consent_recorded
            priority = "NORMAL"
        } | Out-Null
    }

    $financeDocument = Get-OrCreateSyntheticDocument -Token $financeToken -ProjectId $project.project_id `
        -LogicalName "PAY-SYN-001 - Dokumen Permintaan Pembayaran" `
        -ObjectKey "synthetic/finance/PAY-SYN-001.pdf" `
        -Sha256 "1111111111111111111111111111111111111111111111111111111111111111"
    $budgetSearch = [Uri]::EscapeDataString("BUD-SYN-001")
    $budgets = Get-AlosPageItems -Path "/finance/budgets?page=1&page_size=100&project_id=$($project.project_id)&search=$budgetSearch" -Token $financeToken
    $budget = $budgets | Where-Object { $_.code -eq "BUD-SYN-001" } | Select-Object -First 1
    if ($null -eq $budget) {
        $budget = Invoke-AlosApi -Method Post -Path "/finance/budgets" -Token $financeToken -Body @{
            project_id = $project.project_id
            code = "BUD-SYN-001"
            name = "Anggaran Operasional Sintetis"
            currency = $fixture.scenarios.finance.currency
            allocated_amount = 100000000
        }
    }
    $paymentSearch = [Uri]::EscapeDataString($fixture.scenarios.finance.request_code)
    $payments = Get-AlosPageItems -Path "/finance/payment-requests?page=1&page_size=100&project_id=$($project.project_id)&search=$paymentSearch" -Token $financeToken
    if (@($payments).Count -eq 0) {
        Invoke-AlosApi -Method Post -Path "/finance/payment-requests" -Token $financeToken -AdditionalHeaders @{
            "Idempotency-Key" = "pilot-finance-pay-syn-001"
        } -Body @{
            project_id = $project.project_id
            budget_id = $budget.budget_id
            document_version_id = $financeDocument.document_version_id
            payee_name = "Vendor Sintetis ALOS"
            vendor_reference = $fixture.scenarios.finance.vendor_reference
            category_code = $fixture.scenarios.finance.category_code
            purpose = "Permintaan pembayaran sintetis $($fixture.scenarios.finance.request_code)"
            amount = $fixture.scenarios.finance.amount
            currency = $fixture.scenarios.finance.currency
            requested_payment_date = (Get-Date).AddDays(1).ToString("yyyy-MM-dd")
        } | Out-Null
    }

    $propertyDocument = Get-OrCreateSyntheticDocument -Token $propertyToken -ProjectId $project.project_id `
        -LogicalName "WP-SYN-001 - Bukti Progres Lapangan" `
        -ObjectKey "synthetic/property/WP-SYN-001.pdf" `
        -Sha256 "2222222222222222222222222222222222222222222222222222222222222222"
    $propertySearch = [Uri]::EscapeDataString($fixture.scenarios.property.work_package_code)
    $siteEvidence = Get-AlosPageItems -Path "/property/site-evidence?page=1&page_size=100&project_id=$($project.project_id)&search=$propertySearch" -Token $propertyToken
    if (@($siteEvidence).Count -eq 0) {
        Invoke-AlosApi -Method Post -Path "/property/site-evidence" -Token $propertyToken -AdditionalHeaders @{
            "Idempotency-Key" = "pilot-property-wp-syn-001"
        } -Body @{
            project_id = $project.project_id
            document_version_id = $propertyDocument.document_version_id
            work_package_code = $fixture.scenarios.property.work_package_code
            claim_date = (Get-Date).ToString("yyyy-MM-dd")
            claimed_progress = $fixture.scenarios.property.claimed_progress
            measured_progress = $fixture.scenarios.property.measured_progress
            measurement_note = "Pengukuran progres sintetis untuk controlled pilot."
        } | Out-Null
    }

    $legalDocument = Get-OrCreateSyntheticDocument -Token $legalToken -ProjectId $project.project_id `
        -LogicalName "PERMIT-SYN-001 - Dokumen Izin" `
        -ObjectKey "synthetic/legal/PERMIT-SYN-001.pdf" `
        -Sha256 "3333333333333333333333333333333333333333333333333333333333333333"
    $legalSearch = [Uri]::EscapeDataString($fixture.scenarios.legal.permit_reference)
    $legalCases = Get-AlosPageItems -Path "/legal/cases?page=1&page_size=100&project_id=$($project.project_id)&search=$legalSearch" -Token $legalToken
    if (@($legalCases).Count -eq 0) {
        Invoke-AlosApi -Method Post -Path "/legal/documents" -Token $legalToken -AdditionalHeaders @{
            "Idempotency-Key" = "pilot-legal-permit-syn-001"
        } -Body @{
            project_id = $project.project_id
            document_version_id = $legalDocument.document_version_id
            document_type = "PERMIT"
            reference_code = $fixture.scenarios.legal.permit_reference
            title = "Izin Operasional Sintetis"
            source_authority = "Instansi Sintetis Pengujian"
            effective_date = (Get-Date).ToString("yyyy-MM-dd")
            expiry_date = (Get-Date).AddYears(1).ToString("yyyy-MM-dd")
        } | Out-Null
    }

    $hrDocument = Get-OrCreateSyntheticDocument -Token $hrToken -ProjectId $project.project_id `
        -LogicalName "CAND-SYN-001 - Dokumen Kandidat" `
        -ObjectKey "synthetic/hr/CAND-SYN-001.pdf" `
        -Sha256 "4444444444444444444444444444444444444444444444444444444444444444"
    $hrSearch = [Uri]::EscapeDataString($fixture.scenarios.hr.candidate_alias)
    $recruitment = Get-AlosPageItems -Path "/hr/recruitment-requests?page=1&page_size=100&project_id=$($project.project_id)&search=$hrSearch" -Token $hrToken
    if (@($recruitment).Count -eq 0) {
        Invoke-AlosApi -Method Post -Path "/hr/recruitment-requests" -Token $hrToken -AdditionalHeaders @{
            "Idempotency-Key" = "pilot-hr-cand-syn-001"
        } -Body @{
            project_id = $project.project_id
            candidate_document_version_id = $hrDocument.document_version_id
            position_title = "$($fixture.scenarios.hr.position_title) ($($fixture.scenarios.hr.candidate_alias))"
            requesting_division_code = "PROPERTY"
            employment_type = "CONTRACT"
            headcount = 1
            justification = "Kebutuhan personel sintetis untuk menguji workflow rekrutmen ALOS."
            criteria_version = "0.1.0"
            candidate_alias = $fixture.scenarios.hr.candidate_alias
            required_criteria = @($fixture.scenarios.hr.required_criteria)
            met_criteria = @("DOC_COMPLETE")
        } | Out-Null
    }

    $briefSearch = [Uri]::EscapeDataString($fixture.scenarios.executive.title)
    $briefs = Get-AlosPageItems -Path "/executive/briefs?page=1&page_size=100&project_id=$($project.project_id)&search=$briefSearch" -Token $executiveToken
    if (@($briefs).Count -eq 0) {
        Invoke-AlosApi -Method Post -Path "/executive/briefs" -Token $executiveToken -AdditionalHeaders @{
            "Idempotency-Key" = "pilot-executive-brief-syn-001"
        } -Body @{
            title = $fixture.scenarios.executive.title
            period_start = (Get-Date).AddDays(-7).ToString("yyyy-MM-dd")
            period_end = (Get-Date).ToString("yyyy-MM-dd")
            project_id = $project.project_id
        } | Out-Null
    }

    Write-Host "Data awal enam workflow berhasil disiapkan tanpa menduplikasi record."
}

Write-Host "Provisioning selesai: $($project.code) · $($project.status)."
Write-Host "Lanjutkan pemeriksaan /system/pilot-readiness sebelum memulai UAT."
