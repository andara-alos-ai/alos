import json

from alos.genesis.chat import _deterministic_response, _intent_for_prompt, _parse_model_response


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


def _external_not_requested():
    from alos.genesis.chat import ExternalResearchResult

    return ExternalResearchResult(status="NOT_REQUESTED")
