[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https?://')]
    [string]$BaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$BearerToken,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F-]{36}$')]
    [string]$WorkspaceId,

    [switch]$RunControlledWrites,

    [string]$OutputDirectory = "artifacts/governance-validation-smoke"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$commit = (git -C $root rev-parse HEAD).Trim()
$timestamp = (Get-Date).ToUniversalTime().ToString("o")
$results = [System.Collections.Generic.List[object]]::new()
$base = $BaseUrl.TrimEnd("/")
$headers = @{ Authorization = "Bearer $BearerToken" }

function Add-Result {
    param([string]$Name, [ValidateSet("PASS", "FAIL", "BLOCKED")][string]$Status, [string]$Detail)
    $script:results.Add([ordered]@{ name = $Name; status = $Status; detail = $Detail })
}

function Invoke-ALOS {
    param([string]$Method, [string]$Path, [object]$Body = $null, [hashtable]$RequestHeaders = $headers)
    $params = @{ Method = $Method; Uri = "$base$Path"; Headers = $RequestHeaders; TimeoutSec = 30 }
    if ($null -ne $Body) {
        $params.ContentType = "application/json"
        $params.Body = $Body | ConvertTo-Json -Depth 12
    }
    Invoke-RestMethod @params
}

foreach ($check in @(
    @{ name = "health"; path = "/health" },
    @{ name = "database_and_object_storage_readiness"; path = "/health/ready" }
)) {
    try { $null = Invoke-ALOS GET $check.path; Add-Result $check.name PASS "endpoint healthy" }
    catch { Add-Result $check.name FAIL $_.Exception.Message }
}

try { $whoami = Invoke-ALOS GET "/api/v1/whoami"; Add-Result "authentication_and_whoami" PASS "authenticated as $($whoami.user_id)" }
catch { Add-Result "authentication_and_whoami" FAIL $_.Exception.Message }
try { $null = Invoke-ALOS GET "/api/v1/workspaces"; Add-Result "workspace_access" PASS "workspace listing authorized" }
catch { Add-Result "workspace_access" FAIL $_.Exception.Message }

if ($RunControlledWrites) {
    try {
        $conversation = Invoke-ALOS POST "/api/v1/genesis/conversations" @{ workspace_id = $WorkspaceId; title = "Governance validation smoke $timestamp"; context_mode = "INTERNAL" }
        $turn = Invoke-ALOS POST "/api/v1/genesis/conversations/$($conversation.conversation_id)/turns" @{ content = "Ringkas data internal yang tersedia, tanpa membuat task."; context_mode = "INTERNAL"; attachments = @() }
        if ($turn.assistant_message.structured_content.response.reliability) {
            Add-Result "genesis_conversation_and_source_behavior" PASS "structured reliability persisted"
        } else { Add-Result "genesis_conversation_and_source_behavior" FAIL "response reliability missing" }
    } catch { Add-Result "genesis_conversation_and_source_behavior" FAIL $_.Exception.Message }
    try {
        $draft = Invoke-ALOS POST "/api/v1/genesis/agent-requests" @{ workspace_id = $WorkspaceId; requirement = "Buat agent read-only untuk memonitor task proyek overdue dan evidence yang belum lengkap. Jangan mengeksekusi tindakan."; deterministic = $false }
        if ($draft.draft.lifecycle_status -eq "DRAFT") {
            Add-Result "agent_designer_registry_test_governance" PASS "DRAFT $($draft.draft.agent.agent_key) created with audit-governed release request"
        } else { Add-Result "agent_designer_registry_test_governance" FAIL "designer did not return DRAFT" }
    } catch { Add-Result "agent_designer_registry_test_governance" FAIL $_.Exception.Message }
} else {
    Add-Result "genesis_conversation_and_source_behavior" BLOCKED "rerun with -RunControlledWrites using sanitized staging data"
    Add-Result "agent_designer_registry_test_governance" BLOCKED "rerun with -RunControlledWrites; this creates a governed DRAFT"
}

try { $null = Invoke-ALOS GET "/api/v1/workspaces/$WorkspaceId/runs"; Add-Result "agent_run_cost_and_audit_access" PASS "runtime history endpoint reachable" }
catch { Add-Result "agent_run_cost_and_audit_access" FAIL $_.Exception.Message }
Add-Result "activate_kill_switch_and_rollback" BLOCKED "requires a separately prepared approved release and independent human reviewers"

$overall = if ($results.status -contains "FAIL") { "FAIL" } elseif ($results.status -contains "BLOCKED") { "BLOCKED" } else { "PASS" }
New-Item -ItemType Directory -Force -Path (Join-Path $root $OutputDirectory) | Out-Null
$report = [ordered]@{
    status = $overall
    timestamp = $timestamp
    environment = $base
    commit_sha = $commit
    results = $results
}
$output = Join-Path $root $OutputDirectory "governance-validation-smoke-$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')).json"
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $output -Encoding utf8
Write-Output "Governance validation smoke: $overall"
Write-Output "Evidence: $output"
if ($overall -eq "FAIL") { exit 1 }
if ($overall -eq "BLOCKED") { exit 2 }
