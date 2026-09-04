"""Single provider selection point for the ALOS Model Gateway."""

from collections.abc import Callable

from alos.config import Settings
from alos.gemini_gateway import GeminiModelGateway
from alos.model_gateway import ModelGateway, ModelGatewayPolicyError
from alos.openai_gateway import OpenAIModelGateway


def create_model_gateway(settings: Settings) -> tuple[ModelGateway, Callable[[], None]]:
    """Return the one configured provider adapter and its deterministic cleanup."""
    if settings.llm_provider == "gemini":
        gemini_gateway = GeminiModelGateway(settings)
        return gemini_gateway, gemini_gateway.close
    if settings.llm_provider == "openai":
        openai_gateway = OpenAIModelGateway(settings)
        return openai_gateway, openai_gateway.close
    raise ModelGatewayPolicyError(
        "PROVIDER_UNAVAILABLE", "no Model Gateway adapter is configured for this provider"
    )
