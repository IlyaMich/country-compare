from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import streamlit as st

from country_compare.config.models import YearStrategy


# def render_country_selector(
#     countries: Sequence[dict[str, Any]] | Sequence[str],
#     *,
#     default: list[str] | None = None,
#     key: str = "compare_selected_countries",
# ) -> list[str]:
#     options: list[str] = []
#     labels: dict[str, str] = {}

#     for item in countries:
#         if isinstance(item, dict):
#             code = str(item.get("country_code") or item.get("code") or "").upper()
#             name = str(item.get("country_name") or item.get("name") or code)
#         else:
#             code = str(item).upper()
#             name = code
#         if not code:
#             continue
#         label = f"{name} ({code})" if name != code else code
#         labels[code] = label
#         options.append(code)

#     selected = st.multiselect(
#         "Countries",
#         options=options,
#         default=default or [],
#         format_func=lambda code: labels.get(code, code),
#         key=key,
#     )
#     return [str(code).upper() for code in selected]
def render_country_selector(
    countries,
    *,
    default: list[str] | None = None,
    key: str = "compare_selected_countries",
) -> list[str]:
    import streamlit as st

    options: list[str] = []
    labels: dict[str, str] = {}

    for item in countries:
        if isinstance(item, dict):
            code = str(item.get("country_code") or item.get("code") or "").upper()
            name = str(item.get("country_name") or item.get("name") or code)
        elif hasattr(item, "country_code"):
            code = str(getattr(item, "country_code")).upper()
            name = str(getattr(item, "country_name", code))
        elif hasattr(item, "code"):
            code = str(getattr(item, "code")).upper()
            name = str(getattr(item, "name", code))
        else:
            code = str(item).upper()
            name = code

        if not code:
            continue

        labels[code] = f"{name} ({code})" if name != code else code
        options.append(code)

    valid_default = [value for value in (default or []) if value in options]

    selected = st.multiselect(
        "Countries",
        options=options,
        default=valid_default,
        format_func=lambda code: labels.get(code, code),
        key=key,
    )
    return [str(code).upper() for code in selected]


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
            value=default or 2000,
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


# def render_single_metric_selector(
#     metrics: Sequence[dict[str, Any]] | Sequence[str],
#     *,
#     default: str | None = None,
#     key: str = "compare_single_metric_id",
# ) -> str:
#     options: list[str] = []
#     labels: dict[str, str] = {}

#     for item in metrics:
#         if isinstance(item, dict):
#             metric_id = str(item.get("metric_id") or item.get("id") or "")
#             display_name = str(item.get("display_name") or item.get("metric_name") or metric_id)
#         else:
#             metric_id = str(item)
#             display_name = metric_id
#         if not metric_id:
#             continue
#         labels[metric_id] = f"{display_name} ({metric_id})" if display_name != metric_id else metric_id
#         options.append(metric_id)

#     index = options.index(default) if default in options else 0 if options else None
#     if not options:
#         return ""

#     return st.selectbox(
#         "Metric",
#         options=options,
#         index=index,
#         format_func=lambda value: labels.get(value, value),
#         key=key,
#     )
def render_single_metric_selector(
    metrics,
    *,
    default: str | None = None,
    key: str = "compare_single_metric_id",
) -> str:
    import streamlit as st

    options: list[str] = []
    labels: dict[str, str] = {}
    
    for item in metrics:
        if isinstance(item, dict):
            metric_id = str(item.get("metric_id") or item.get("id") or "").strip()
            display_name = str(item.get("display_name") or item.get("metric_name") or metric_id).strip()
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

        labels[metric_id] = f"{display_name} ({metric_id})" if display_name != metric_id else metric_id
        options.append(metric_id)

    if not options:
        return ""

    options = list(dict.fromkeys(options))

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