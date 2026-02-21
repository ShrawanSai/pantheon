from __future__ import annotations


def compute_oe_tokens(input_tokens_fresh: int, input_tokens_cached: int, output_tokens: int) -> float:
    fresh = max(input_tokens_fresh, 0)
    cached = max(input_tokens_cached, 0)
    output = max(output_tokens, 0)
    return (fresh * 0.35) + (cached * 0.10) + output


def compute_credits_burned(oe_tokens: float) -> float:
    return max(oe_tokens, 0.0) / 10_000.0

