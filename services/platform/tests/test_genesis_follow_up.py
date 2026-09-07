import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from alos import main
from alos.config import Settings
from alos.genesis.follow_up import (
    GenesisFollowUpBlocked,
    GenesisFollowUpFailed,
    GenesisFollowUpModelExecution,
    GenesisFollowUpRequest,
    GenesisFollowUpResponse,
    GenesisFollowUpService,
    GenesisFollowUpSourceReference,
    GenesisFollowUpWorkflowReference,
    _FollowUpContext,
    _HistoryTurn,
    _PreparedFollowUp,
    build_follow_up_input,
)
from alos.genesis.history import GenesisMessageRecord
from alos.identity import HumanRole
from alos.main import app
from alos.model_gateway import FakeModelGateway, ModelGateway, ModelResponse, ModelUsage
from alos.security.tokens import ActorContext, get_current_actor


class FakeFollowUpRepository:
    def __init__(
        self,
        context: _FollowUpContext,
        *,
        reservation_block: GenesisFollowUpBlocked | None = None,
    ) -> None:
        self.context = context
        self.reservation_block = reservation_block
        self.failures: list[str] = []
        self.blocked: list[str] = []
        self.run_id = uuid4()
        self.human_message = message_record(
            context.conversation_id,
            "HUMAN",
            "Arahan Direktur",
        )

    def replay(self, **_: object) -> None:
        return None

    def load_context(self, *_: object, **__: object) -> _FollowUpContext:
        return self.context

    def record_blocked(self, *_: object, code: str, **__: object) -> GenesisFollowUpBlocked:
        self.blocked.append(code)
        return GenesisFollowUpBlocked(code, "Follow-up diblokir.", uuid4())

    def reserve(
        self, *_: object, **__: object
    ) -> _PreparedFollowUp | GenesisFollowUpBlocked:
        if self.reservation_block is not None:
            return self.reservation_block
        return _PreparedFollowUp(run_id=self.run_id, human_message=self.human_message)

    def complete(
        self,
        context: _FollowUpContext,
        prepared: _PreparedFollowUp,
        response: ModelResponse,
        *,
        correlation_id: UUID,
        answer: str,
        **_: object,
    ) -> GenesisFollowUpResponse:
        return GenesisFollowUpResponse(
            correlation_id=correlation_id,
            workflow=GenesisFollowUpWorkflowReference(
                workflow_id=context.workflow_id, status=context.workflow_status
            ),
            source=GenesisFollowUpSourceReference(
                document_id=context.source_document_id,
                title=context.source_title,
                version_number=context.source_version_number,
                content_sha256=context.source_content_sha256,
                classification=context.source_classification,
            ),
            human_message=prepared.human_message,
            genesis_message=message_record(context.conversation_id, "SYSTEM", answer),
            model_execution=GenesisFollowUpModelExecution(
                follow_up_run_id=prepared.run_id,
                provider=response.provider,
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_milliseconds=response.latency_milliseconds,
                estimated_cost_usd=response.estimated_cost_usd,
                history_turns_included=0,
                estimated_context_tokens=100,
            ),
        )

    def fail(self, *_: object, code: str, **__: object) -> None:
        self.failures.append(code)


def follow_up_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "test",
        "auth_signing_secret": "a" * 32,
        "llm_provider": "openai",
        "llm_api_key": "test-only-key",
        "llm_model": "test-model",
        "llm_max_output_tokens": 512,
        "llm_max_context_tokens": 12_000,
        "llm_max_retries": 0,
        "genesis_conversation_follow_up_enabled": True,
        "genesis_follow_up_max_output_tokens": 320,
    }
    values.update(overrides)
    return Settings(**values)


def valid_answer(citation: str = "L1-L2") -> str:
    return (
        f"## Jawaban ringkas\nArahan dipahami. [Sumber {citation}]\n\n"
        f"## Temuan dan kekurangan\nOwner belum tersedia. [Sumber {citation}]\n\n"
        "## Checklist perbaikan\n1. Rekomendasi: siapkan penetapan owner.\n\n"
        "## Batasan dan informasi yang belum tersedia\n"
        f"Keputusan final belum tersedia. [Sumber {citation}]\n\n"
        f"## Sumber\n- [Sumber {citation}]"
    )


def model_response(answer: str | None = None) -> ModelResponse:
    return ModelResponse(
        provider="openai",
        model="test-model",
        output_text=answer or valid_answer(),
        usage=ModelUsage(input_tokens=80, output_tokens=40),
        latency_milliseconds=12,
        estimated_cost_usd=Decimal("0.000123"),
    )


def test_follow_up_calls_model_with_source_initial_answer_and_recent_history() -> None:
    context = follow_up_context(
        history=(_HistoryTurn(human="Prioritaskan owner.", genesis=valid_answer()),)
    )
    repository = FakeFollowUpRepository(context)
    gateway = FakeModelGateway([model_response()])
    service = GenesisFollowUpService(
        follow_up_settings(),
        repository,  # type: ignore[arg-type]
        factory_for(gateway),
    )
    correlation_id = uuid4()

    result = service.follow_up(
        context.conversation_id,
        GenesisFollowUpRequest(
            correlation_id=correlation_id,
            content="Saya setuju. Apa yang perlu dipersiapkan berikutnya?",
        ),
        organization_id=context.organization_id,
        actor_user_id=uuid4(),
    )

    assert result.human_message.actor_kind == "HUMAN"
    assert result.genesis_message.actor_kind == "SYSTEM"
    assert result.genesis_message.system_actor == "GENESIS"
    assert len(gateway.requests) == 1
    request = gateway.requests[0]
    assert "SOURCE TEXT" in request.input_text
    assert context.initial_answer in request.input_text
    assert "Prioritaskan owner" in request.input_text
    assert "tools" not in type(request).model_fields


def test_context_overflow_is_blocked_before_provider_call() -> None:
    context = follow_up_context(source_content="isi " * 2_000)
    repository = FakeFollowUpRepository(context)
    gateway = FakeModelGateway([model_response()])
    service = GenesisFollowUpService(
        follow_up_settings(llm_max_context_tokens=256),
        repository,  # type: ignore[arg-type]
        factory_for(gateway),
    )

    with pytest.raises(GenesisFollowUpBlocked):
        service.follow_up(
            context.conversation_id,
            GenesisFollowUpRequest(
                correlation_id=uuid4(), content="Jelaskan prioritas perbaikannya."
            ),
            organization_id=context.organization_id,
            actor_user_id=uuid4(),
        )

    assert repository.blocked == ["CONTEXT_LIMIT_EXCEEDED"]
    assert gateway.requests == []


def test_budget_block_does_not_call_provider() -> None:
    context = follow_up_context()
    correlation_id = uuid4()
    repository = FakeFollowUpRepository(
        context,
        reservation_block=GenesisFollowUpBlocked(
            "DAILY_REQUEST_LIMIT_REACHED", "Budget habis.", correlation_id
        ),
    )
    gateway = FakeModelGateway([model_response()])
    service = GenesisFollowUpService(
        follow_up_settings(),
        repository,  # type: ignore[arg-type]
        factory_for(gateway),
    )

    with pytest.raises(GenesisFollowUpBlocked, match="Budget habis"):
        service.follow_up(
            context.conversation_id,
            GenesisFollowUpRequest(
                correlation_id=correlation_id, content="Berikan tindak lanjut singkat."
            ),
            organization_id=context.organization_id,
            actor_user_id=uuid4(),
        )

    assert gateway.requests == []


def test_follow_up_flag_blocks_without_disabling_initial_analysis_flag() -> None:
    context = follow_up_context()
    repository = FakeFollowUpRepository(context)
    gateway = FakeModelGateway([model_response()])
    service = GenesisFollowUpService(
        follow_up_settings(genesis_conversation_follow_up_enabled=False),
        repository,  # type: ignore[arg-type]
        factory_for(gateway),
    )

    with pytest.raises(GenesisFollowUpBlocked):
        service.follow_up(
            context.conversation_id,
            GenesisFollowUpRequest(
                correlation_id=uuid4(), content="Follow-up saat fitur dimatikan."
            ),
            organization_id=context.organization_id,
            actor_user_id=uuid4(),
        )

    assert repository.blocked == ["FOLLOW_UP_DISABLED"]
    assert gateway.requests == []


def test_invalid_follow_up_citation_is_failed_and_not_completed() -> None:
    context = follow_up_context()
    repository = FakeFollowUpRepository(context)
    gateway = FakeModelGateway([model_response(valid_answer("L8-L9"))])
    service = GenesisFollowUpService(
        follow_up_settings(),
        repository,  # type: ignore[arg-type]
        factory_for(gateway),
    )

    with pytest.raises(Exception, match="validasi struktur dan sitasi"):
        service.follow_up(
            context.conversation_id,
            GenesisFollowUpRequest(
                correlation_id=uuid4(), content="Konfirmasi temuan dari dokumen."
            ),
            organization_id=context.organization_id,
            actor_user_id=uuid4(),
        )

    assert repository.failures == ["MODEL_ANSWER_INVALID"]


def test_context_window_keeps_at_most_eight_latest_complete_turns() -> None:
    history = tuple(
        _HistoryTurn(human=f"Arahan {index}", genesis=f"Jawaban {index}")
        for index in range(10)
    )
    window = build_follow_up_input(
        follow_up_context(history=history),
        "Arahan terbaru",
        max_context_tokens=12_000,
    )

    assert window.history_turns_included == 8
    assert "Arahan 0" not in window.input_text
    assert "Arahan 1" not in window.input_text
    assert "Arahan 2" in window.input_text
    assert "Arahan 9" in window.input_text


def test_non_director_is_rejected_before_repository_access() -> None:
    now = datetime.now(UTC)
    actor = ActorContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=[HumanRole.IT_LEAD],
        workspace_ids=[uuid4()],
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    app.dependency_overrides[get_current_actor] = lambda: actor
    try:
        response = TestClient(app).post(
            f"/api/v1/genesis/conversations/{uuid4()}/follow-ups",
            json={"correlation_id": str(uuid4()), "content": "Arahan tidak sah."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"].startswith("Director authority")


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (GenesisFollowUpBlocked("CONTEXT_LIMIT_EXCEEDED", "Konteks terlalu besar.", uuid4()), 409),
        (
            GenesisFollowUpFailed("MODEL_ANSWER_INVALID", "Jawaban tidak valid.", uuid4()),
            502,
        ),
    ],
    ids=["blocked", "failed"],
)
def test_api_returns_structured_blocked_and_failed_errors(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_status: int,
) -> None:
    now = datetime.now(UTC)
    workspace_id = uuid4()
    actor = ActorContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=[HumanRole.DIRECTOR],
        workspace_ids=[workspace_id],
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )

    class History:
        def get_conversation(self, *_: object, **__: object) -> SimpleNamespace:
            return SimpleNamespace(workspace_id=workspace_id)

    class Service:
        def follow_up(self, *_: object, **__: object) -> None:
            raise failure

    monkeypatch.setattr(main, "get_genesis_history_repository", lambda: History())
    monkeypatch.setattr(main, "get_genesis_follow_up_service", lambda: Service())
    app.dependency_overrides[get_current_actor] = lambda: actor
    try:
        response = TestClient(app).post(
            f"/api/v1/genesis/conversations/{uuid4()}/follow-ups",
            json={"correlation_id": str(uuid4()), "content": "Arahan Direktur."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == expected_status
    assert response.json()["status"] in {"BLOCKED", "FAILED"}
    assert set(response.json()["error"]) == {"code", "message"}


def follow_up_context(
    *,
    source_content: str = "Owner belum ditetapkan.\nKPI tersedia.",
    history: tuple[_HistoryTurn, ...] = (),
) -> _FollowUpContext:
    source_sha256 = hashlib.sha256(source_content.encode("utf-8")).hexdigest()
    return _FollowUpContext(
        workflow_id=uuid4(),
        workflow_status="ANALYSIS_DRAFT",
        organization_id=uuid4(),
        workspace_id=uuid4(),
        conversation_id=uuid4(),
        source_document_id=uuid4(),
        source_title="Rencana Operasional",
        source_version_number=2,
        source_content_sha256=source_sha256,
        source_classification="INTERNAL",
        source_origin="MANUAL",
        source_status="APPROVED",
        source_content=source_content,
        stored_source_sha256=source_sha256,
        initial_answer=valid_answer(),
        history=history,
    )


def message_record(
    conversation_id: UUID,
    actor_kind: str,
    content: str,
) -> GenesisMessageRecord:
    is_human = actor_kind == "HUMAN"
    return GenesisMessageRecord(
        message_id=uuid4(),
        conversation_id=conversation_id,
        actor_kind="HUMAN" if is_human else "SYSTEM",
        actor_user_id=uuid4() if is_human else None,
        system_actor=None if is_human else "GENESIS",
        content=content,
        created_at=datetime.now(UTC),
    )


def factory_for(gateway: ModelGateway) -> Callable[[], tuple[ModelGateway, Callable[[], None]]]:
    return lambda: (gateway, lambda: None)
