from alos.runtime.service import validation_fixture_runtime_enabled


def test_h3_fixture_runtime_is_available_in_staging_but_not_production() -> None:
    assert validation_fixture_runtime_enabled("local")
    assert validation_fixture_runtime_enabled("test")
    assert validation_fixture_runtime_enabled("staging")
    assert not validation_fixture_runtime_enabled("production")
