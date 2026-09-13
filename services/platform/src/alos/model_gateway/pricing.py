"""Server-owned model pricing used for conservative budget estimates."""

from decimal import ROUND_UP, Decimal

_COST_PRECISION = Decimal("0.000001")
_OPENAI_TEXT_PRICING_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-5.6-luna": (Decimal("0.20"), Decimal("1.20")),
    "gpt-5.6-terra": (Decimal("2.00"), Decimal("12.00")),
    "gpt-5.6-sol": (Decimal("4.00"), Decimal("20.00")),
}


def has_openai_pricing(model: str) -> bool:
    return model in _OPENAI_TEXT_PRICING_PER_MILLION


def estimate_openai_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts cannot be negative")
    pricing = _OPENAI_TEXT_PRICING_PER_MILLION.get(model)
    if pricing is None:
        raise ValueError("OpenAI model pricing is not configured")
    input_price, output_price = pricing
    estimated = (
        Decimal(input_tokens) * input_price + Decimal(output_tokens) * output_price
    ) / Decimal(1_000_000)
    return estimated.quantize(_COST_PRECISION, rounding=ROUND_UP)
