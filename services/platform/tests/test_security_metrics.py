from alos.security.middleware import RequestMetrics


def test_request_metrics_normalize_entity_identifiers() -> None:
    metrics = RequestMetrics()
    metrics.observe(
        "POST",
        "/api/v1/proposed-actions/7f4dc29f-0df9-43ad-bb24-df5d48370aa6/execute",
        200,
        0.12,
    )
    metrics.observe("GET", "/api/v1/reports/123456", 200, 0.03)

    exposition = metrics.prometheus()

    assert 'path="/api/v1/proposed-actions/:id/execute"' in exposition
    assert 'path="/api/v1/reports/:id"' in exposition
