"""Single extensible provider-adapter composition boundary."""

from collections.abc import Callable

from alos.config import Settings
from alos.model_gateway.gateway import ModelGateway, ModelGatewayPolicyError
from alos.model_gateway.providers.openai import OpenAIModelGateway

type GatewayFactory = Callable[[Settings], tuple[ModelGateway, Callable[[], None]]]


def _openai_factory(settings: Settings) -> tuple[ModelGateway, Callable[[], None]]:
    gateway = OpenAIModelGateway(settings)
    return gateway, gateway.close


_PROVIDER_FACTORIES: dict[str, GatewayFactory] = {"openai": _openai_factory}


def registered_providers() -> frozenset[str]:
    return frozenset(_PROVIDER_FACTORIES)


def create_model_gateway(settings: Settings) -> tuple[ModelGateway, Callable[[], None]]:
    """Build the configured adapter; disabled and unknown providers fail closed."""
    factory = _PROVIDER_FACTORIES.get(settings.llm_provider)
    if factory is None:
        raise ModelGatewayPolicyError(
            "PROVIDER_UNAVAILABLE", "no Model Gateway adapter is configured for this provider"
        )
    return factory(settings)
