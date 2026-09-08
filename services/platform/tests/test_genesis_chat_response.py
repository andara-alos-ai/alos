import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from alos.genesis.chat import (
    ExternalResearchResult,
    GenesisChatService,
    _deterministic_response,
    _intent_for_prompt,
    _parse_model_response,
)
from alos.identity import HumanRole
from alos.model_gateway import ModelResponse, ModelUsage
from alos.security.tokens import ActorContext


def test_summary_response_is_not_forced_into_empty_sections() -> None:
    response = _deterministic_response(
        "Ringkas dokumen ini.",
        [{"source_kind": "INTERNAL_SOURCE", "output": {"document_id": "doc-1"}}],
        _external_not_requested(),
    )

    assert response.intent == "SUMMARY"
    assert response.reliability == "SUPPORTED"
    assert response.findings == []
    assert response.recommendations == []
    assert response.limitations == []


def test_no_source_response_is_short_and_unsupported() -> None:
    response = _deterministic_response(
        "Apakah dokumen ini punya isi?", [], _external_not_requested()
    )

    assert response.intent == "DIRECT_ANSWER"
    assert response.reliability == "UNSUPPORTED"
    assert len(response.answer) < 200
    assert response.limitations


def test_model_cannot_claim_supported_without_authorized_citation() -> None:
    response = _parse_model_response(
        json.dumps(
            {
                "answer": "Klaim ini didukung.",
                "intent": "DIRECT_ANSWER",
                "reliability": "SUPPORTED",
                "findings": [],
                "recommendations": [],
                "limitations": [],
                "actions": [],
            }
        ),
        prompt="Apakah dokumen ini punya isi?",
        has_authorized_sources=False,
    )

    assert response.reliability == "UNSUPPORTED"
    assert response.limitations


def test_malformed_model_output_is_safe_needs_info() -> None:
    response = _parse_model_response(
        "bukan json",
        prompt="Apa kekurangannya?",
        has_authorized_sources=True,
    )

    assert response.intent == "FINDINGS"
    assert response.reliability == "NEEDS_INFO"


def test_intent_selection_covers_pilot_conversation_behaviour() -> None:
    assert _intent_for_prompt("Buat checklist perbaikan") == "CHECKLIST"
    assert _intent_for_prompt("Apa yang perlu saya putuskan?") == "DECISION_BRIEF"
    assert _intent_for_prompt("Bandingkan dua dokumen") == "COMPARISON"
    assert _intent_for_prompt("Buat agent untuk memonitor task proyek overdue") == "AGENT_PROPOSAL"
    assert _intent_for_prompt("Jadikan perbaikan nomor 2 tugas Legal") == "ACTION_REQUEST"


def test_model_input_serializes_uuid_values_returned_by_governed_tools() -> None:
    captured: list[str] = []

    class Gateway:
        def generate(self, request):
            captured.append(request.input_text)
            return ModelResponse(
                provider="openai",
                model="test-model",
                output_text=json.dumps(
                    {
                        "answer": "Dokumen ditemukan.",
                        "intent": "DIRECT_ANSWER",
                        "reliability": "SUPPORTED",
                        "findings": [],
                        "recommendations": [],
                        "limitations": [],
                        "actions": [],
                    }
                ),
                usage=ModelUsage(input_tokens=1, output_tokens=1),
                latency_milliseconds=1,
            )

    now = datetime.now(UTC)
    service = GenesisChatService(
        history=SimpleNamespace(list_messages=lambda *_args, **_kwargs: []),
        capabilities=SimpleNamespace(),
        router=SimpleNamespace(),
        tools=SimpleNamespace(),
        external_research=SimpleNamespace(),
        operations=SimpleNamespace(),
        gateway=Gateway(),
        model="test-model",
        max_output_tokens=100,
    )
    source_id = uuid4()
    actor = ActorContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=[HumanRole.DIRECTOR],
        workspace_ids=[uuid4()],
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )

    response, _ = service._answer(
        uuid4(),
        "Apa isi dokumen ini?",
        actor,
        "INTERNAL",
        [{"source_kind": "INTERNAL_SOURCE", "output": {"document_id": source_id}}],
        True,
        [],
        ExternalResearchResult(status="NOT_REQUESTED"),
        uuid4(),
    )

    assert response.reliability == "SUPPORTED"
    assert str(source_id) in captured[0]


def _external_not_requested():
    from alos.genesis.chat import ExternalResearchResult

    return ExternalResearchResult(status="NOT_REQUESTED")
