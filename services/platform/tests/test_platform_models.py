from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from alos.platform import LeadIntake, PaymentRecordCreate, SalesInteraction
from alos.platform.operations import CapaTransition, WorkItemDeadlineUpdate
from alos.security import Role, UserCreate


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


def test_reserved_interaction_requires_document_evidence() -> None:
    with pytest.raises(ValidationError, match="Dokumen evidence wajib"):
        SalesInteraction(
            outcome="reserved",
            channel="site-visit",
            notes="Pelanggan menyatakan reservasi dan referensi telah dibuat.",
            reservation_reference="RSV-EVIDENCE-REQUIRED",
        )


def test_lead_contact_is_normalized_before_deduplication() -> None:
    command = LeadIntake(
        project_id=uuid4(),
        full_name="  Calon   Pelanggan  ",
        phone="0812-3456 7890",
        email=" CUSTOMER@EXAMPLE.COM ",
        source="  Meta   Ads ",
        consent_recorded=True,
    )

    assert command.full_name == "Calon Pelanggan"
    assert command.phone == "081234567890"
    assert command.email == "customer@example.com"
    assert command.source == "Meta Ads"


def test_payment_timestamp_requires_timezone() -> None:
    with pytest.raises(ValidationError, match="zona waktu"):
        PaymentRecordCreate(
            payment_reference="TRX-NO-TIMEZONE",
            amount="100000.00",
            paid_at=datetime(2026, 8, 30, 9, 0),
            evidence_document_version_id=uuid4(),
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


def test_user_identity_is_normalized_before_persistence() -> None:
    command = UserCreate(
        email="  Reynald.Example@Example.COM ",
        display_name="  Reynald   Aryansyah  ",
        division_code="IT",
        role=Role.IT_ADMIN,
    )

    assert command.email == "reynald.example@example.com"
    assert command.display_name == "Reynald Aryansyah"


@pytest.mark.parametrize(
    "email",
    ["tidak-valid", "@example.com", "user@invalid", "user..name@example.com"],
)
def test_user_identity_rejects_invalid_email(email: str) -> None:
    with pytest.raises(ValidationError, match="Format email"):
        UserCreate(
            email=email,
            display_name="Pengguna Sintetis",
            division_code="IT",
            role=Role.IT_ADMIN,
        )
