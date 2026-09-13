"""Regression checks for deliberate compatibility imports after boundary moves."""


def test_legacy_genesis_conversation_imports_resolve_to_ara() -> None:
    from alos.ara.conversations.repository import GenesisHistoryRepository as AraHistory
    from alos.ara.conversations.service import GenesisChatService as AraChat
    from alos.genesis.chat import GenesisChatService as LegacyChat
    from alos.genesis.history import GenesisHistoryRepository as LegacyHistory

    assert LegacyChat is AraChat
    assert LegacyHistory is AraHistory


def test_legacy_model_gateway_imports_resolve_to_canonical_package() -> None:
    from alos.model_gateway import create_model_gateway as canonical_factory
    from alos.model_gateway.providers.openai import OpenAIModelGateway as CanonicalOpenAI
    from alos.model_gateway_factory import create_model_gateway as legacy_factory
    from alos.openai_gateway import OpenAIModelGateway as LegacyOpenAI

    assert legacy_factory is canonical_factory
    assert LegacyOpenAI is CanonicalOpenAI
