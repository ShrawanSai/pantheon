from __future__ import annotations


_pricing_cache: dict[str, float] = {
    "deepseek": 0.5,
    "gemini-flash": 0.8,
    "gemini-pro": 1.2,
    "gpt-4o-mini": 1.0,
    "gpt-4o": 2.0,
    "claude-haiku": 0.8,
    "claude-sonnet": 1.5,
}


def get_model_multiplier(model_alias: str) -> float:
    return _pricing_cache.get(model_alias, 1.0)


def reload_pricing_cache(new_config: dict[str, float]) -> None:
    _pricing_cache.clear()
    _pricing_cache.update(new_config)


def compute_oe_tokens(input_tokens_fresh: int, input_tokens_cached: int, output_tokens: int) -> float:
    fresh = max(input_tokens_fresh, 0)
    cached = max(input_tokens_cached, 0)
    output = max(output_tokens, 0)
    return (fresh * 0.35) + (cached * 0.10) + output


def compute_credits_burned(oe_tokens: float, model_multiplier: float = 1.0) -> float:
    return max(oe_tokens, 0.0) * max(model_multiplier, 0.0) / 10_000.0
