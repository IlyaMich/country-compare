from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import streamlit as st

from country_compare.config.models import YearStrategy


def render_country_selector(
    countries: Sequence[Any],
    *,
    default: list[str] | None = None,
    key: str = "compare_selected_countries",
) -> list[str]:
    options, labels = _resolve_country_options(countries)
    valid_default = [value for value in (default or []) if value in options]

    selected = st.multiselect(
        "Countries",
        options=options,
        default=valid_default,
        format_func=lambda code: labels.get(code, code),
        key=key,
    )
    return [str(code).upper() for code in selected]


def render_country_single_selector(
    countries: Sequence[Any],
    *,
    default: str | None = None,
    label: str = "Country",
    key: str = "prediction_country_code",
) -> str:
    options, labels = _resolve_country_options(countries)
    if not options:
        return ""

    safe_default = str(default).upper() if default is not None else options[0]
    if safe_default not in options:
        safe_default = options[0]
    index = options.index(safe_default)

    selected = st.selectbox(
        label,
        options=options,
        index=index,
        format_func=lambda code: labels.get(code, code),
        key=key,
    )
    return str(selected).upper() if selected is not None else ""


def render_year_strategy_selector(
    *,
    default: YearStrategy | str = YearStrategy.LATEST_PER_METRIC,
    key: str = "compare_year_strategy",
) -> YearStrategy:
    options = [
        YearStrategy.LATEST_PER_METRIC,
        YearStrategy.TARGET_YEAR,
        YearStrategy.COMMON_YEAR,
    ]
    default_value = YearStrategy(default)
    default_index = options.index(default_value)
    labels = {
        YearStrategy.LATEST_PER_METRIC: "Latest per metric",
        YearStrategy.TARGET_YEAR: "Target year",
        YearStrategy.COMMON_YEAR: "Common year",
    }
    return st.selectbox(
        "Year strategy",
        options=options,
        index=default_index,
        format_func=lambda value: labels[value],
        key=key,
    )


def render_target_year_input(
    years: Sequence[int],
    *,
    enabled: bool,
    default: int | None = None,
    key: str = "compare_target_year",
) -> int | None:
    if not enabled:
        st.number_input(
            "Target year",
            value=int(default or 2000),
            step=1,
            disabled=True,
            key=key,
        )
        return default

    if years:
        min_year = int(min(years))
        max_year = int(max(years))
        return int(
            st.number_input(
                "Target year",
                min_value=min_year,
                max_value=max_year,
                value=int(default if default is not None else max_year),
                step=1,
                key=key,
            )
        )

    return int(
        st.number_input(
            "Target year",
            value=int(default or 2000),
            step=1,
            key=key,
        )
    )


def render_positive_integer_input(
    label: str,
    *,
    default: int,
    min_value: int = 1,
    max_value: int | None = None,
    key: str,
    help: str | None = None,
) -> int:
    kwargs: dict[str, Any] = {
        "label": label,
        "min_value": int(min_value),
        "value": int(max(default, min_value)),
        "step": 1,
        "key": key,
    }
    if max_value is not None:
        kwargs["max_value"] = int(max_value)
    if help is not None:
        kwargs["help"] = help
    return int(st.number_input(**kwargs))


def render_single_metric_selector(
    metrics: Sequence[Any],
    *,
    default: str | None = None,
    key: str = "compare_single_metric_id",
) -> str:
    options, labels = _resolve_metric_options(metrics)

    if not options:
        return ""

    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]

    safe_default = default if default in options else options[0]
    index = options.index(safe_default)

    selected = st.selectbox(
        "Metric",
        options=options,
        index=index,
        format_func=lambda value: labels.get(value, value),
        key=key,
    )

    return str(selected).strip() if selected is not None else ""


def render_multi_metric_selector(
    metrics: Sequence[Any],
    *,
    default: list[str] | None = None,
    key: str = "compare_multi_metric_ids",
) -> list[str]:
    options, labels = _resolve_metric_options(metrics)
    valid_default = [metric_id for metric_id in (default or []) if metric_id in options]
    selected = st.multiselect(
        "Metrics",
        options=options,
        default=valid_default,
        format_func=lambda value: labels.get(value, value),
        key=key,
    )
    return [str(metric_id).strip() for metric_id in selected]


def get_prediction_method_options(
    methods: Sequence[Any],
) -> tuple[list[str], dict[str, str]]:
    options: list[str] = []
    labels: dict[str, str] = {}

    for item in methods:
        if isinstance(item, dict):
            method_id = str(item.get("method_id") or item.get("id") or "").strip()
            display_name = str(
                item.get("display_name") or item.get("name") or method_id
            ).strip()
            description = str(item.get("description") or "").strip()
        else:
            method_id = str(getattr(item, "method_id", getattr(item, "id", ""))).strip()
            display_name = str(
                getattr(item, "display_name", getattr(item, "name", method_id))
            ).strip()
            description = str(getattr(item, "description", "") or "").strip()

        if not method_id:
            continue

        options.append(method_id)
        labels[method_id] = (
            f"{display_name} — {description}"
            if description
            else display_name or method_id
        )

    return list(dict.fromkeys(options)), labels


def render_prediction_method_selector(
    methods: Sequence[Any],
    *,
    default: str | None = None,
    label: str = "Prediction method",
    key: str = "prediction_method",
) -> str:
    options, labels = get_prediction_method_options(methods)
    if not options:
        return ""

    safe_default = str(default).strip() if default is not None else options[0]
    if safe_default not in options:
        safe_default = options[0]
    index = options.index(safe_default)

    selected = st.selectbox(
        label,
        options=options,
        index=index,
        format_func=lambda value: labels.get(value, value),
        key=key,
    )
    return str(selected).strip() if selected is not None else ""


def render_profile_selector(
    profiles: Sequence[Any],
    *,
    default: str | None = None,
    key: str = "compare_profile_name",
) -> str:
    options: list[str] = []
    labels: dict[str, str] = {}

    for item in profiles:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
        elif hasattr(item, "name"):
            name = str(getattr(item, "name", "")).strip()
            description = str(getattr(item, "description", "") or "").strip()
        else:
            name = str(item).strip()
            description = ""

        if not name:
            continue

        options.append(name)
        labels[name] = f"{name} — {description}" if description else name

    options = list(dict.fromkeys(options))
    if not options:
        return ""

    safe_default = default if default in options else options[0]
    index = options.index(safe_default)

    selected = st.selectbox(
        "Scoring profile",
        options=options,
        index=index,
        format_func=lambda value: labels.get(value, value),
        key=key,
    )
    return str(selected).strip() if selected is not None else ""


def _resolve_country_options(
    countries: Sequence[Any],
) -> tuple[list[str], dict[str, str]]:
    options: list[str] = []
    labels: dict[str, str] = {}

    for item in countries:
        if isinstance(item, dict):
            code = str(item.get("country_code") or item.get("code") or "").upper()
            name = str(item.get("country_name") or item.get("name") or code)
        elif hasattr(item, "country_code"):
            code = str(item.country_code).upper()
            name = str(getattr(item, "country_name", code))
        elif hasattr(item, "code"):
            code = str(item.code).upper()
            name = str(getattr(item, "name", code))
        else:
            code = str(item).upper()
            name = code

        if not code:
            continue

        labels[code] = f"{name} ({code})" if name != code else code
        options.append(code)

    return list(dict.fromkeys(options)), labels


def _resolve_metric_options(metrics: Sequence[Any]) -> tuple[list[str], dict[str, str]]:
    options: list[str] = []
    labels: dict[str, str] = {}

    for item in metrics:
        if isinstance(item, dict):
            metric_id = str(item.get("metric_id") or item.get("id") or "").strip()
            display_name = str(
                item.get("display_name") or item.get("metric_name") or metric_id
            ).strip()
        elif hasattr(item, "metric_id"):
            metric_id = str(getattr(item, "metric_id", "")).strip()
            display_name = str(getattr(item, "display_name", metric_id)).strip()
        elif hasattr(item, "id"):
            metric_id = str(getattr(item, "id", "")).strip()
            display_name = str(getattr(item, "name", metric_id)).strip()
        else:
            metric_id = str(item).strip()
            display_name = metric_id

        if not metric_id:
            continue

        labels[metric_id] = (
            f"{display_name} ({metric_id})" if display_name != metric_id else metric_id
        )
        options.append(metric_id)

    return list(dict.fromkeys(options)), labels
