from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from alos.platform import SalesInteraction
from alos.platform.operations import CapaTransition, WorkItemDeadlineUpdate


def test_reserved_interaction_requires_reservation_reference() -> None:
    with pytest.raises(ValidationError, match="Referensi reservasi wajib"):
        SalesInteraction(
            outcome="reserved",
            channel="site-visit",
            notes="Pelanggan menyatakan akan melakukan reservasi.",
        )


def test_follow_up_cannot_carry_reservation_reference() -> None:
    with pytest.raises(ValidationError, match="hanya boleh"):
        SalesInteraction(
            outcome="follow_up",
            channel="phone",
            notes="Pelanggan meminta tindak lanjut.",
            reservation_reference="RSV-NOT-ALLOWED",
        )


def test_operational_deadline_requires_timezone() -> None:
    with pytest.raises(ValidationError, match="zona waktu"):
        WorkItemDeadlineUpdate(
            due_at=datetime(2026, 8, 30, 9, 0),
            reason="Deadline tanpa zona waktu harus ditolak",
        )


def test_capa_closure_requires_verification_notes_and_evidence() -> None:
    with pytest.raises(ValidationError, match="evidence verifikasi"):
        CapaTransition(
            target_status="CLOSED",
            reason="CAPA dinyatakan siap ditutup",
        )

    command = CapaTransition(
        target_status="CLOSED",
        reason="CAPA dinyatakan siap ditutup",
        verification_notes="Reviewer telah memeriksa efektivitas tindakan",
        evidence_document_version_id=uuid4(),
    )
    assert command.target_status == "CLOSED"
