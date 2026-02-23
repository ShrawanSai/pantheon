from __future__ import annotations

_enforcement_override: bool | None = None


def get_enforcement_enabled(default: bool) -> bool:
    """Returns in-memory override if set, else the config default."""
    if _enforcement_override is not None:
        return _enforcement_override
    return default


def set_enforcement_override(value: bool | None) -> None:
    """Set to True/False to override config. Set to None to clear override."""
    global _enforcement_override
    _enforcement_override = value


def get_enforcement_source() -> str:
    """Returns where the effective setting comes from."""
    return "override" if _enforcement_override is not None else "config"
