from pathlib import Path

from alos.persistence.migrations import discover_migrations


def test_hari_1_migrations_are_ordered_and_complete() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    migrations = discover_migrations(repository_root / "infra" / "database")
    assert [migration.name for migration in migrations] == [
        "001_genesis_mvp1_baseline.sql",
        "002_h1_policy_and_test_registry.sql",
        "003_h2_agent_registry.sql",
        "004_h3_runtime_budget.sql",
        "005_h4_release_governance.sql",
        "006_h5_source_evidence.sql",
        "007_h5_tool_permission_approvals.sql",
        "008_h6_staging_authentication.sql",
        "009_h5_source_vault_policy.sql",
        "010_document_center.sql",
        "011_genesis_document_workflows.sql",
        "012_genesis_document_uploads.sql",
        "013_genesis_upload_document_drafts.sql",
        "014_genesis_upload_withdrawal.sql",
        "015_genesis_semantic_analysis_runs.sql",
        "016_genesis_conversation_follow_ups.sql",
        "017_portfolio_dashboards.sql",
        "018_identity_capability_and_operational_core.sql",
        "019_division_capability_packs.sql",
        "020_capability_and_tool_catalog.sql",
        "021_integrations_and_software_change_governance.sql",
        "022_genesis_chat_and_governance_linkage.sql",
        "023_approved_action_execution.sql",
        "024_h5_final_readiness_controls.sql",
        "025_genesis_agentic_runtime.sql",
        "026_genesis_governed_foundations.sql",
        "027_genesis_factory_persistence.sql",
        "028_genesis_factory_governance_linkage.sql",
        "029_scoped_semantic_memory.sql",
        "030_governed_skill_persistence.sql",
        "031_persistent_delegation_lineage.sql",
        "032_generic_research_persistence.sql",
        "033_agent_eval_evidence.sql",
        "034_generated_agent_schedules.sql",
        "035_release_tenant_scope.sql",
    ]
