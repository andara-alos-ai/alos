from collections.abc import Callable
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from alos.config import Settings
from alos.genesis.semantic_analysis import (
    GenesisSemanticAnalysisError,
    GenesisSemanticAnalyzer,
)
from alos.model_gateway import FakeModelGateway, ModelGateway, ModelResponse, ModelUsage


class FakeSemanticUsage:
    """Database-free accounting double: no external request can happen in these tests."""

    def __init__(self) -> None:
        self.run_id = uuid4()
        self.reservations: list[dict[str, object]] = []
        self.completions: list[tuple[UUID, ModelResponse]] = []
        self.failures: list[tuple[UUID, Exception]] = []

    def reserve(self, **values: object) -> UUID:
        self.reservations.append(values)
        return self.run_id

    def complete(
        self,
        run_id: UUID,
        response: ModelResponse,
        **_: object,
    ) -> None:
        self.completions.append((run_id, response))

    def fail(self, run_id: UUID, error: Exception, **_: object) -> None:
        self.failures.append((run_id, error))


def semantic_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "test",
        "auth_signing_secret": "a" * 32,
        "llm_provider": "openai",
        "llm_api_key": "test-only-key",
        "llm_model": "test-model",
        "llm_max_output_tokens": 512,
        "llm_max_retries": 0,
        "genesis_semantic_analysis_enabled": True,
        "genesis_semantic_max_output_tokens": 320,
    }
    values.update(overrides)
    return Settings(**values)


def model_response() -> ModelResponse:
    return ModelResponse(
        provider="openai",
        model="test-model",
        output_text=(
            "## Jawaban ringkas\nOwner belum lengkap. [Sumber L1-L1]\n\n"
            "## Temuan dan kekurangan\nOwner implementasi belum disebut. [Sumber L1-L1]\n\n"
            "## Checklist perbaikan\n- [ ] Tetapkan owner.\n\n"
            "## Batasan dan informasi yang belum tersedia\n"
            "Tidak ada PIC pada sumber. [Sumber L1-L1]\n\n"
            "## Sumber\n- [Sumber L1-L1]"
        ),
        usage=ModelUsage(input_tokens=34, output_tokens=21),
        latency_milliseconds=18,
        estimated_cost_usd=Decimal("0.000123"),
    )


def test_semantic_analysis_uses_only_bounded_internal_source_text() -> None:
    usage = FakeSemanticUsage()
    gateway = FakeModelGateway([model_response()])
    analyzer = GenesisSemanticAnalyzer(
        semantic_settings(),
        factory_for(gateway),
        usage,  # type: ignore[arg-type]
    )
    ids = fixture_ids()

    result = analyzer.analyze(
        organization_id=ids["organization"],
        workspace_id=ids["workspace"],
        source_document_id=ids["document"],
        source_version_number=3,
        source_content_sha256="a" * 64,
        source_title="Rencana Operasional",
        source_content="Owner implementasi belum ditentukan.",
        prompt="Analisa kekurangan dokumen ini dan buatkan checklist perbaikan.",
        actor_user_id=ids["actor"],
        correlation_id=ids["correlation"],
    )

    assert result.analysis_run_id == usage.run_id
    assert result.answer.startswith("## Jawaban ringkas")
    assert len(usage.reservations) == 1
    assert len(gateway.requests) == 1
    request = gateway.requests[0]
    assert request.data_classification == "INTERNAL"
    assert request.max_output_tokens == 320
    assert "Owner implementasi belum ditentukan." in request.input_text
    assert "Analisa kekurangan dokumen" in request.input_text
    assert "tools" not in type(request).model_fields
    assert "external" not in request.input_text.lower()

    analyzer.complete(
        result,
        analysis_artifact_id=uuid4(),
        organization_id=ids["organization"],
        actor_user_id=ids["actor"],
        correlation_id=ids["correlation"],
    )
    assert usage.completions[0][0] == usage.run_id
    assert usage.completions[0][1].output_text == result.answer


def test_semantic_analysis_rejects_a_model_answer_with_invalid_source_citation() -> None:
    usage = FakeSemanticUsage()
    invalid = model_response().model_copy(
        update={"output_text": model_response().output_text.replace("L1-L1", "L7-L9")}
    )
    gateway = FakeModelGateway([invalid])
    analyzer = GenesisSemanticAnalyzer(
        semantic_settings(),
        factory_for(gateway),
        usage,  # type: ignore[arg-type]
    )
    ids = fixture_ids()

    with pytest.raises(GenesisSemanticAnalysisError, match="outside the approved source"):
        analyzer.analyze(
            organization_id=ids["organization"],
            workspace_id=ids["workspace"],
            source_document_id=ids["document"],
            source_version_number=1,
            source_content_sha256="d" * 64,
            source_title="Internal",
            source_content="Satu baris sumber yang disetujui.",
            prompt="Analisa dokumen internal ini untuk menentukan kekurangannya.",
            actor_user_id=ids["actor"],
            correlation_id=ids["correlation"],
        )

    assert len(usage.failures) == 1


@pytest.mark.parametrize(
    ("source_content", "case"),
    [("", "empty"), ("x" * 60_001, "oversized")],
    ids=["empty", "oversized"],
)
def test_semantic_analysis_rejects_empty_or_oversized_source_before_reservation(
    source_content: str, case: str
) -> None:
    assert case in {"empty", "oversized"}
    usage = FakeSemanticUsage()
    gateway = FakeModelGateway([model_response()])
    analyzer = GenesisSemanticAnalyzer(
        semantic_settings(),
        factory_for(gateway),
        usage,  # type: ignore[arg-type]
    )
    ids = fixture_ids()

    with pytest.raises(GenesisSemanticAnalysisError):
        analyzer.analyze(
            organization_id=ids["organization"],
            workspace_id=ids["workspace"],
            source_document_id=ids["document"],
            source_version_number=1,
            source_content_sha256="b" * 64,
            source_title="Kosong",
            source_content=source_content,
            prompt="Analisa dokumen internal ini untuk menentukan kekurangannya.",
            actor_user_id=ids["actor"],
            correlation_id=ids["correlation"],
        )

    assert usage.reservations == []
    assert gateway.requests == []


def test_semantic_analysis_is_off_until_explicitly_enabled() -> None:
    usage = FakeSemanticUsage()
    factory_called = False

    def unavailable_factory() -> tuple[ModelGateway, Callable[[], None]]:
        nonlocal factory_called
        factory_called = True
        raise AssertionError("the provider must not be constructed while disabled")

    analyzer = GenesisSemanticAnalyzer(
        semantic_settings(genesis_semantic_analysis_enabled=False),
        unavailable_factory,
        usage,  # type: ignore[arg-type]
    )
    ids = fixture_ids()

    with pytest.raises(GenesisSemanticAnalysisError, match="not enabled"):
        analyzer.analyze(
            organization_id=ids["organization"],
            workspace_id=ids["workspace"],
            source_document_id=ids["document"],
            source_version_number=1,
            source_content_sha256="c" * 64,
            source_title="Internal",
            source_content="Sumber internal yang disetujui.",
            prompt="Analisa dokumen internal ini untuk menentukan kekurangannya.",
            actor_user_id=ids["actor"],
            correlation_id=ids["correlation"],
        )

    assert not factory_called
    assert usage.reservations == []


def factory_for(gateway: ModelGateway) -> Callable[[], tuple[ModelGateway, Callable[[], None]]]:
    return lambda: (gateway, lambda: None)


def fixture_ids() -> dict[str, UUID]:
    return {
        "organization": uuid4(),
        "workspace": uuid4(),
        "document": uuid4(),
        "actor": uuid4(),
        "correlation": uuid4(),
    }
