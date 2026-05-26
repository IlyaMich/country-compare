from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = "<redacted>"

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "password",
    "secret",
    "service_token",
    "token",
)

SAFE_METADATA_KEYS = frozenset(
    {
        "provider",
        "model",
        "prompt_version",
        "llm_calls",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "deployment_profile",
        "zdr_required",
        "zdr_confirmed",
        "max_horizon_years",
        "max_history_points",
        "max_input_chars",
        "max_output_tokens",
        "max_adjustment_pct",
    }
)


def is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if is_sensitive_key(key) else redact_value(nested)
            for key, nested in value.items()
        }

    if isinstance(value, list):
        return [redact_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)

    return value


def redact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    return dict(redact_value(payload))


def safe_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): redact_value(value)
        for key, value in metadata.items()
        if str(key) in SAFE_METADATA_KEYS
    }


def debug_payload_logging_enabled(
    *, deployment_profile: str, debug_log_payloads: bool
) -> bool:
    if deployment_profile == "public":
        return False
    return bool(debug_log_payloads)
