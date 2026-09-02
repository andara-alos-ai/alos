from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError

from alos.agents.capabilities import CapabilityRegistry
from alos.config import Settings, get_settings
from alos.entrypoints.api import (
    LLMGatewayDependency,
    agent_registry_for_root,
    current_principal,
    database_for_url,
)
from alos.genesis import (
    GenesisAnalyzeRequest,
    GenesisAnalyzeResult,
    GenesisAnalyzeService,
    GenesisArtifactVersionView,
    GenesisConversationCreate,
    GenesisConversationListItem,
    GenesisConversationService,
    GenesisConversationView,
    GenesisDesignService,
    GenesisMessageCreate,
    GenesisPipelineService,
    GenesisPipelineView,
    GenesisSubmitRequest,
    PostgresGenesisConversationStore,
    PostgresGenesisStore,
    SourcePack,
    SourceRegistry,
)
from alos.genesis.models import GenesisReviewCreate
from alos.governance.configuration import (
    CanonicalConfigurationRegister,
    CanonicalConfigurationRegistry,
)
from alos.security import Principal, Role
from alos.security.authorization import AuthorizationDenied, require_any_role

router = APIRouter(prefix="/genesis", tags=["genesis", "design-time"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]
PrincipalDependency = Annotated[Principal, Depends(current_principal)]


def genesis_service(settings: SettingsDependency) -> GenesisPipelineService:
    # Use the same registry instance as the runtime.  Releasing a contract
    # invalidates its cache, so a later human activation or execution observes
    # the immutable generated version without process restart.
    agents = agent_registry_for_root(settings.definitions_root)
    return GenesisPipelineService(
        GenesisDesignService(agents),
        CapabilityRegistry(settings.definitions_root),
        PostgresGenesisStore(database_for_url(settings.database_url).engine),
        SourceRegistry(settings.definitions_root),
    )


GenesisDependency = Annotated[GenesisPipelineService, Depends(genesis_service)]


def genesis_analyze_service(
    settings: SettingsDependency,
    gateway: LLMGatewayDependency,
) -> GenesisAnalyzeService:
    agents = agent_registry_for_root(settings.definitions_root)
    sources = SourceRegistry(settings.definitions_root)
    return GenesisAnalyzeService(gateway, agents, sources)


GenesisAnalyzeDependency = Annotated[GenesisAnalyzeService, Depends(genesis_analyze_service)]


def genesis_conversation_service(
    settings: SettingsDependency,
    analyze_service: GenesisAnalyzeDependency,
) -> GenesisConversationService:
    store = PostgresGenesisConversationStore(
        database_for_url(settings.database_url).engine
    )
    return GenesisConversationService(store, analyze_service)


GenesisConversationDependency = Annotated[
    GenesisConversationService, Depends(genesis_conversation_service)
]


@router.get("/source-packs", response_model=list[SourcePack])
def list_source_packs(
    principal: PrincipalDependency,
    settings: SettingsDependency,
) -> tuple[SourcePack, ...]:
    try:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.DIVISION_HEAD,
            Role.IT_ADMIN,
            Role.AUDITOR,
        )
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return SourceRegistry(settings.definitions_root).load_all()


@router.get("/configuration-registers", response_model=list[CanonicalConfigurationRegister])
def list_configuration_registers(
    principal: PrincipalDependency,
    settings: SettingsDependency,
) -> tuple[CanonicalConfigurationRegister, ...]:
    try:
        require_any_role(
            principal,
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.DIVISION_HEAD,
            Role.IT_ADMIN,
            Role.AUDITOR,
        )
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return CanonicalConfigurationRegistry(settings.definitions_root).load_all()


@router.get("/requests", response_model=list[GenesisPipelineView])
def list_genesis_requests(
    principal: PrincipalDependency,
    service: GenesisDependency,
    limit: int = 50,
    offset: int = 0,
) -> tuple[GenesisPipelineView, ...]:
    return _execute(
        lambda: service.list_requests(principal, limit=limit, offset=offset)
    )


@router.post("/requests", response_model=GenesisPipelineView, status_code=201)
def submit_genesis_request(
    request: GenesisSubmitRequest,
    principal: PrincipalDependency,
    service: GenesisDependency,
) -> GenesisPipelineView:
    return _execute(lambda: service.submit(request, principal))


@router.get("/requests/{request_id}", response_model=GenesisPipelineView)
def get_genesis_request(
    request_id: UUID,
    principal: PrincipalDependency,
    service: GenesisDependency,
) -> GenesisPipelineView:
    return _execute(lambda: service.get(request_id, principal))


@router.post("/requests/{request_id}/reviews", response_model=GenesisPipelineView)
def review_genesis_request(
    request_id: UUID,
    request: GenesisReviewCreate,
    principal: PrincipalDependency,
    service: GenesisDependency,
) -> GenesisPipelineView:
    return _execute(lambda: service.review(request_id, request, principal))


@router.post("/requests/{request_id}/stage", response_model=GenesisPipelineView)
def stage_genesis_request(
    request_id: UUID,
    principal: PrincipalDependency,
    service: GenesisDependency,
) -> GenesisPipelineView:
    return _execute(lambda: service.stage(request_id, principal))


@router.post("/requests/{request_id}/release", response_model=GenesisPipelineView)
def release_genesis_request(
    request_id: UUID,
    principal: PrincipalDependency,
    service: GenesisDependency,
) -> GenesisPipelineView:
    return _execute(lambda: service.release(request_id, principal))


@router.post("/analyze", response_model=GenesisAnalyzeResult)
def analyze_genesis_request(
    request: GenesisAnalyzeRequest,
    principal: PrincipalDependency,
    service: GenesisAnalyzeDependency,
) -> GenesisAnalyzeResult:
    return _execute(lambda: service.analyze(request, principal))


@router.post("/conversations", response_model=GenesisConversationView, status_code=201)
def create_genesis_conversation(
    request: GenesisConversationCreate,
    principal: PrincipalDependency,
    service: GenesisConversationDependency,
) -> GenesisConversationView:
    return _execute(lambda: service.create_conversation(request, principal))


@router.get("/conversations", response_model=list[GenesisConversationListItem])
def list_genesis_conversations(
    principal: PrincipalDependency,
    service: GenesisConversationDependency,
    limit: int = 50,
    offset: int = 0,
) -> tuple[GenesisConversationListItem, ...]:
    return _execute(
        lambda: service.list_conversations(principal, limit=limit, offset=offset)
    )


@router.get("/conversations/{conversation_id}", response_model=GenesisConversationView)
def get_genesis_conversation(
    conversation_id: UUID,
    principal: PrincipalDependency,
    service: GenesisConversationDependency,
) -> GenesisConversationView:
    return _execute(lambda: service.get_conversation(conversation_id, principal))


@router.post(
    "/conversations/{conversation_id}/messages", response_model=GenesisConversationView
)
def post_genesis_message(
    conversation_id: UUID,
    request: GenesisMessageCreate,
    principal: PrincipalDependency,
    service: GenesisConversationDependency,
) -> GenesisConversationView:
    return _execute(lambda: service.post_message(conversation_id, request, principal))


@router.get(
    "/conversations/{conversation_id}/artifacts",
    response_model=list[GenesisArtifactVersionView],
)
def get_genesis_artifacts(
    conversation_id: UUID,
    principal: PrincipalDependency,
    service: GenesisConversationDependency,
) -> tuple[GenesisArtifactVersionView, ...]:
    return _execute(lambda: service.get_artifact_versions(conversation_id, principal))


def _execute[T](action: Callable[[], T]) -> T:
    try:
        return action()
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Genesis gate sudah diproses") from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database belum tersedia") from exc
