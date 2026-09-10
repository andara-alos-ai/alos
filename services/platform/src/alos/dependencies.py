"""Application composition helpers for ALOS HTTP routes.

Centralising these factories prevents routers from importing ``alos.main``
to obtain their dependencies, which in turn breaks the circular dependency
between ``main`` and ``entrypoints``.
"""

from __future__ import annotations

from alos.agents.registry import (
    AgentDraftBuilder,
    AgentRegistryRepository,
    DeterministicAgentDraftGenerator,
)
from alos.audit.reader import AuditReader
from alos.config import get_settings
from alos.documents.center import DocumentCenterRepository
from alos.executive_dashboard import ExecutiveDashboardRepository
from alos.genesis.document_analysis import GenesisDocumentAnalysisService
from alos.genesis.document_workflow import GenesisDocumentWorkflowRepository
from alos.genesis.follow_up import GenesisFollowUpRepository, GenesisFollowUpService
from alos.genesis.history import GenesisHistoryRepository
from alos.genesis.semantic_analysis import (
    GenesisSemanticAnalysisRepository,
    GenesisSemanticAnalyzer,
)
from alos.genesis.uploads import (
    FilesystemGenesisUploadStorage,
    GenesisUploadRepository,
    GenesisUploadService,
    S3GenesisUploadStorage,
)
from alos.identity.authentication import IdentityAuthenticationRepository
from alos.model_gateway import (
    GuardedModelGateway,
    ModelGatewayPolicyError,
    RetryingModelGateway,
    UsageBudget,
)
from alos.model_gateway_factory import create_model_gateway
from alos.permissions.registry import PermissionRegistryRepository
from alos.portfolio import PortfolioRepository
from alos.release.governance import ReleaseGovernanceRepository
from alos.runtime.service import (
    AgentRuntime,
    AgentRuntimeBlocked,
    AgentRuntimeRepository,
)
from alos.sources.registry import SourceRegistryRepository
from alos.tools.registry import ToolRegistryRepository


def get_agent_registry_repository() -> AgentRegistryRepository:
    return AgentRegistryRepository(get_settings().database_url)


def get_identity_authentication_repository() -> IdentityAuthenticationRepository:
    return IdentityAuthenticationRepository(get_settings().database_url)


def get_agent_draft_builder() -> AgentDraftBuilder:
    return AgentDraftBuilder(DeterministicAgentDraftGenerator())


def get_agent_runtime() -> AgentRuntime:
    settings = get_settings()
    try:
        delegate, close_gateway = create_model_gateway(settings)
    except ModelGatewayPolicyError as error:
        raise AgentRuntimeBlocked(str(error)) from error
    gateway = GuardedModelGateway(
        RetryingModelGateway(delegate, settings.llm_max_retries),
        settings,
        UsageBudget(
            request_limit=settings.agentic_max_model_steps,
            output_token_limit=(
                settings.llm_max_output_tokens * settings.agentic_max_model_steps
            ),
        ),
    )
    return AgentRuntime(
        AgentRuntimeRepository(settings.database_url, settings),
        gateway,
        settings,
        close_gateway=close_gateway,
    )


def get_release_repository() -> ReleaseGovernanceRepository:
    return ReleaseGovernanceRepository(get_settings().database_url)


def get_source_registry_repository() -> SourceRegistryRepository:
    settings = get_settings()
    return SourceRegistryRepository(settings.database_url, settings=settings)


def get_audit_reader() -> AuditReader:
    return AuditReader(get_settings().database_url)


def get_genesis_history_repository() -> GenesisHistoryRepository:
    return GenesisHistoryRepository(get_settings().database_url)


def get_document_center_repository() -> DocumentCenterRepository:
    return DocumentCenterRepository(get_settings().database_url)


def get_executive_dashboard_repository() -> ExecutiveDashboardRepository:
    return ExecutiveDashboardRepository(get_settings().database_url)


def get_portfolio_repository() -> PortfolioRepository:
    return PortfolioRepository(get_settings().database_url)


def get_genesis_document_workflow_repository() -> GenesisDocumentWorkflowRepository:
    return GenesisDocumentWorkflowRepository(get_settings().database_url)


def get_genesis_semantic_analyzer() -> GenesisSemanticAnalyzer | None:
    """Build the opt-in external-model boundary for one Genesis request."""
    settings = get_settings()
    if not settings.genesis_semantic_analysis_enabled:
        return None
    return GenesisSemanticAnalyzer(
        settings,
        lambda: create_model_gateway(settings),
        GenesisSemanticAnalysisRepository(settings.database_url, settings),
    )


def get_genesis_document_analysis_service() -> GenesisDocumentAnalysisService:
    return GenesisDocumentAnalysisService(
        get_document_center_repository(),
        get_genesis_history_repository(),
        get_genesis_document_workflow_repository(),
        get_genesis_semantic_analyzer(),
    )


def get_genesis_follow_up_service() -> GenesisFollowUpService:
    settings = get_settings()
    return GenesisFollowUpService(
        settings,
        GenesisFollowUpRepository(settings.database_url, settings),
        lambda: create_model_gateway(settings),
    )


def get_genesis_upload_repository() -> GenesisUploadRepository:
    return GenesisUploadRepository(get_settings().database_url)


def get_genesis_upload_service() -> GenesisUploadService:
    settings = get_settings()
    storage = (
        S3GenesisUploadStorage(settings)
        if settings.object_storage_provider == "s3"
        else FilesystemGenesisUploadStorage(settings)
    )
    return GenesisUploadService(
        get_genesis_upload_repository(),
        storage,
        get_document_center_repository(),
    )


def get_tool_registry_repository() -> ToolRegistryRepository:
    return ToolRegistryRepository(get_settings().database_url)


def get_permission_registry_repository() -> PermissionRegistryRepository:
    return PermissionRegistryRepository(get_settings().database_url)
