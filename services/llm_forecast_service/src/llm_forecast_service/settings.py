from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw)


@dataclass(frozen=True)
class ServiceSettings:
    service_token: str = ""
    provider: str = "mistral"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    deployment_profile: str = "local"
    require_zdr: bool = False
    mistral_zdr_confirmed: bool = False
    timeout_seconds: float = 20.0
    max_retries: int = 1
    temperature: float = 0.0
    max_output_tokens: int = 800
    max_series_per_request: int = 3
    max_horizon_years: int = 10
    max_history_points: int = 80
    max_input_chars: int = 12_000
    max_adjustment_pct: float = 15.0
    log_level: str = "INFO"
    debug_log_payloads: bool = False

    @classmethod
    def from_env(cls) -> ServiceSettings:
        deployment_profile = (
            os.getenv("LLM_DEPLOYMENT_PROFILE", "local").strip().lower()
        )
        debug_log_payloads = _get_bool("LLM_DEBUG_LOG_PAYLOADS", False)
        if deployment_profile == "public":
            debug_log_payloads = False

        return cls(
            service_token=os.getenv("LLM_SERVICE_TOKEN", "").strip(),
            provider=os.getenv("LLM_PROVIDER", "mistral").strip().lower(),
            mistral_api_key=os.getenv("MISTRAL_API_KEY", "").strip(),
            mistral_model=os.getenv("MISTRAL_MODEL", "mistral-large-latest").strip(),
            deployment_profile=deployment_profile,
            require_zdr=_get_bool("LLM_REQUIRE_ZDR", False),
            mistral_zdr_confirmed=_get_bool("MISTRAL_ZDR_CONFIRMED", False),
            timeout_seconds=_get_float("LLM_TIMEOUT_SECONDS", 20.0),
            max_retries=_get_int("LLM_MAX_RETRIES", 1),
            temperature=_get_float("LLM_TEMPERATURE", 0.0),
            max_output_tokens=_get_int("LLM_MAX_OUTPUT_TOKENS", 800),
            max_series_per_request=_get_int("LLM_MAX_SERIES_PER_REQUEST", 3),
            max_horizon_years=_get_int("LLM_MAX_HORIZON_YEARS", 10),
            max_history_points=_get_int("LLM_MAX_HISTORY_POINTS", 80),
            max_input_chars=_get_int("LLM_MAX_INPUT_CHARS", 12_000),
            max_adjustment_pct=_get_float("LLM_MAX_ADJUSTMENT_PCT", 15.0),
            log_level=os.getenv("LLM_LOG_LEVEL", "INFO").strip().upper(),
            debug_log_payloads=debug_log_payloads,
        )

    def readiness_issues(self) -> list[str]:
        issues: list[str] = []

        if self.provider != "mistral":
            issues.append(f"Unsupported LLM_PROVIDER: {self.provider}")
        if not self.service_token:
            issues.append("LLM_SERVICE_TOKEN is not configured")
        if not self.mistral_api_key:
            issues.append("MISTRAL_API_KEY is not configured")
        if not self.mistral_model:
            issues.append("MISTRAL_MODEL is not configured")
        if self.deployment_profile not in {"local", "public"}:
            issues.append("LLM_DEPLOYMENT_PROFILE must be one of: local, public")
        if self.deployment_profile == "public" and not self.require_zdr:
            issues.append("LLM_REQUIRE_ZDR must be true for public deployment")
        if self.require_zdr and not self.mistral_zdr_confirmed:
            issues.append("MISTRAL_ZDR_CONFIRMED must be true when ZDR is required")

        return issues

    @property
    def is_ready(self) -> bool:
        return not self.readiness_issues()
