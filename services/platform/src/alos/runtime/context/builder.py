"""Build and bound model context without provider-specific knowledge."""

import json
from math import ceil
from typing import Any

from alos.runtime.models import AgentRunRequest


def model_input_text(
    request: AgentRunRequest,
    fixture_context: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> str:
    return json.dumps(
        {"input": request.input, "read_only_fixture_context": fixture_context},
        ensure_ascii=False,
    )


def conservative_input_token_bound(instructions: str, input_text: str) -> int:
    """Upper-bound text tokens by UTF-8 bytes before a provider call."""
    return len((instructions + input_text).encode("utf-8"))


def estimated_context_tokens(instructions: str, input_text: str) -> int:
    """Estimate context use with the documented four-bytes-per-token heuristic."""
    return max(1, ceil(len((instructions + input_text).encode("utf-8")) / 4))
