"""Logical route resolution independent of provider SDKs."""

from alos.model_gateway.models import ModelRoute


def resolve_model_route(
    route: ModelRoute,
    *,
    default_model: str,
    light_model: str = "",
    standard_model: str = "",
    critical_model: str = "",
) -> str:
    configured = {
        "light": light_model,
        "standard": standard_model,
        "critical": critical_model,
    }[route]
    return configured.strip() or default_model.strip()
