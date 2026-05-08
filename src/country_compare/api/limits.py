from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import Request

from country_compare.services.errors import AppError, AppServiceError


def enforce_country_limit(request: Request, country_codes: Sequence[str]) -> None:
    _enforce_sequence_limit(
        request,
        field_name="country_codes",
        values=country_codes,
        setting_name="max_countries",
        display_name="countries",
    )


def enforce_metric_limit(request: Request, metric_ids: Sequence[str]) -> None:
    _enforce_sequence_limit(
        request,
        field_name="metric_ids",
        values=metric_ids,
        setting_name="max_metrics",
        display_name="metrics",
    )


def enforce_horizon_limit(request: Request, horizon_years: int) -> None:
    _enforce_int_limit(
        request,
        field_name="horizon_years",
        value=horizon_years,
        setting_name="max_horizon_years",
        display_name="forecast horizon years",
    )


def enforce_holdout_limit(request: Request, holdout_years: int) -> None:
    _enforce_int_limit(
        request,
        field_name="holdout_years",
        value=holdout_years,
        setting_name="max_holdout_years",
        display_name="backtest holdout years",
    )


def enforce_top_n_limit(request: Request, top_n: int | None) -> None:
    if top_n is None:
        return
    _enforce_int_limit(
        request,
        field_name="top_n",
        value=top_n,
        setting_name="max_top_n",
        display_name="top rows",
    )


def _enforce_int_limit(
    request: Request,
    *,
    field_name: str,
    value: int,
    setting_name: str,
    display_name: str,
) -> None:
    limit = _positive_int_setting(request, setting_name)
    int_value = int(value)
    if int_value <= limit:
        return

    _raise_limit_error(
        field_name=field_name,
        value=int_value,
        limit=limit,
        display_name=display_name,
    )


def _enforce_sequence_limit(
    request: Request,
    *,
    field_name: str,
    values: Sequence[Any],
    setting_name: str,
    display_name: str,
) -> None:
    limit = _positive_int_setting(request, setting_name)
    count = len(values)
    if count <= limit:
        return

    _raise_limit_error(
        field_name=field_name,
        value=count,
        limit=limit,
        display_name=display_name,
    )


def _positive_int_setting(request: Request, name: str) -> int:
    api_settings = getattr(request.app.state, "api_settings", None)
    value = int(getattr(api_settings, name, 1))
    return max(value, 1)


def _raise_limit_error(
    *,
    field_name: str,
    value: int,
    limit: int,
    display_name: str,
) -> None:
    message = f"Requested {value} {display_name}; the configured API limit is {limit}."
    raise AppServiceError(
        AppError(
            code="input_limit_exceeded",
            title="Input limit exceeded",
            user_message=message,
            technical_detail=message,
            field_errors={field_name: message},
        )
    )
