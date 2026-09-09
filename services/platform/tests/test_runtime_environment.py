from alos.runtime.service import h3_fixture_runtime_enabled


def test_h3_fixture_runtime_is_available_in_staging_but_not_production() -> None:
    assert h3_fixture_runtime_enabled("local")
    assert h3_fixture_runtime_enabled("test")
    assert h3_fixture_runtime_enabled("staging")
    assert not h3_fixture_runtime_enabled("production")
