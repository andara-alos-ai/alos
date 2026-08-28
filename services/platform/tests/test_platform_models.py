import pytest
from pydantic import ValidationError

from alos.platform import SalesInteraction


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
