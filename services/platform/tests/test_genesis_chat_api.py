from types import SimpleNamespace
from typing import cast

from alos.config import Settings
from alos.entrypoints import genesis_chat_api
from alos.model_gateway import ModelGatewayPolicyError


def test_chat_service_keeps_context_api_available_when_staging_provider_is_unavailable(
    monkeypatch,
) -> None:
    def unavailable(_: Settings):
        raise ModelGatewayPolicyError("PROVIDER_UNAVAILABLE", "provider is not configured")

    monkeypatch.setattr(genesis_chat_api, "create_model_gateway", unavailable)
    settings = cast(
        Settings,
        SimpleNamespace(
            environment="staging",
            database_url="postgresql://unused/alos",
            llm_model_standard="demo-model",
            llm_max_output_tokens=512,
        ),
    )

    service, close_gateway = genesis_chat_api._chat_service(settings)

    assert service._gateway is None
    close_gateway()
