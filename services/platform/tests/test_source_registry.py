from pathlib import Path

import pytest

from alos.genesis.source import SourceRecord, SourceRegistry, SourceRegistryError, SourceUse

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def registry() -> SourceRegistry:
    return SourceRegistry(REPOSITORY_ROOT / "definitions")


def test_source_registry_tracks_master_and_annexes_as_unratified_draft() -> None:
    source_pack = registry().get_pack("ALOS-SP-MASTER-AN-DRAFT", "0.1.0")

    assert source_pack.status == "DRAFT"
    assert source_pack.contains_unratified_values is True
    assert len(source_pack.sources) == 15
    assert {source.source_code for source in source_pack.sources} == {
        "MASTER",
        *tuple("ABCDEFGHIJKLMN"),
    }
    assert all(source.status == "DRAFT" for source in source_pack.sources)
    assert all(
        source.sha256 is not None and len(source.sha256) == 64 for source in source_pack.sources
    )


def test_draft_source_pack_allows_design_but_blocks_staging_and_release() -> None:
    source_reference = ("ALOS-SP-MASTER-AN-DRAFT@0.1.0",)

    registry().validate_references(source_reference, SourceUse.GENERATE)
    with pytest.raises(SourceRegistryError, match="tidak mengizinkan STAGE"):
        registry().validate_references(source_reference, SourceUse.STAGE)
    with pytest.raises(SourceRegistryError, match="tidak mengizinkan RELEASE"):
        registry().validate_references(source_reference, SourceUse.RELEASE)


def test_source_registry_resolves_individual_source_and_rejects_unknown_reference() -> None:
    registry().validate_references(("ALOS-SRC-APP-I-V40",), SourceUse.ANALYZE)

    with pytest.raises(SourceRegistryError, match="tidak terdaftar"):
        registry().validate_references(("ALOS-SRC-UNKNOWN",), SourceUse.GENERATE)


def test_synthetic_pilot_can_release_design_package_but_not_activate_production() -> None:
    source_reference = ("ALOS-SP-SYNTHETIC-PILOT@1.0.0",)

    registry().validate_references(source_reference, SourceUse.STAGE)
    registry().validate_references(source_reference, SourceUse.RELEASE)
    with pytest.raises(SourceRegistryError, match="tidak mengizinkan PRODUCTION_ACTIVATION"):
        registry().validate_references(source_reference, SourceUse.PRODUCTION_ACTIVATION)


def test_source_code_accepts_future_annex_without_code_change() -> None:
    source = SourceRecord.model_validate(
        {
            "source_id": "ALOS-SRC-APP-P-V10",
            "source_code": "LAMPIRAN-P",
            "title": "Lampiran baru untuk pengujian registry dinamis",
            "source_type": "SYSTEM_BASELINE",
            "version": "1.0",
            "status": "DRAFT",
            "authority": "DESIGN_BASELINE",
            "domains": ["all-divisions"],
            "notes": ["Tidak memerlukan perubahan regex atau kode aplikasi."],
        }
    )

    assert source.source_code == "LAMPIRAN-P"
