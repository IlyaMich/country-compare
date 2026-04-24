from __future__ import annotations

from copy import deepcopy
from typing import Any

import pandas as pd
import streamlit as st

from country_compare.config.models import (
    MissingDataPolicy,
    NormalizationMethod,
    WeightHandlingStrategy,
    YearStrategy,
)
from country_compare.services.errors import AppError, error_from_exception
from country_compare.ui.bootstrap import get_ui_services, refresh_cached_services
from country_compare.ui.components.messages import render_app_error
from country_compare.ui.state import (
    commit_config_editor_saved_state,
    config_editor_is_dirty,
    get_config_editor_state,
    get_debug_mode,
    initialize_config_editor_draft,
    reset_config_editor_draft,
    set_catalog_state,
    set_config_editor_drafts,
    set_config_editor_save_status,
    set_config_editor_selection,
    set_config_editor_validation,
    set_config_editor_validation_preference,
)

EMPTY_OVERRIDE = "__use_default__"


def render_config_editor_view(context) -> None:
    st.title("Config Editor")
    st.caption(
        "Edit metrics and scoring profiles as drafts, validate them against the current rules, "
        "then save through the service layer."
    )

    services = get_ui_services(context)
    config_service = services["config_service"]

    load_error = _ensure_editor_state_loaded(config_service)
    if load_error is not None:
        render_app_error(load_error, debug=get_debug_mode())
        st.info("Fix the configuration files on disk first, then reload this page.")
        return

    editor_state = get_config_editor_state()
    _render_editor_status(editor_state)

    preference_value = bool(editor_state.get("validation_against_dataset", False))
    validate_against_dataset = st.checkbox(
        "Validate draft against current dataset",
        value=preference_value,
        help="Runs the optional metrics-vs-dataset consistency check before save.",
    )
    if validate_against_dataset != preference_value:
        set_config_editor_validation_preference(validate_against_dataset)

    action_cols = st.columns([1, 1, 1, 1])
    validate_clicked = action_cols[0].button("Validate draft", use_container_width=True)
    save_clicked = action_cols[1].button(
        "Save draft", type="primary", use_container_width=True
    )
    reset_clicked = action_cols[2].button("Reset draft", use_container_width=True)
    reload_clicked = action_cols[3].button("Reload from disk", use_container_width=True)

    if reload_clicked:
        reload_error = _reload_editor_state_from_disk(config_service)
        if reload_error is None:
            set_config_editor_save_status(
                "success",
                message="Draft reloaded from the current files on disk.",
            )
        else:
            set_config_editor_save_status(
                "error",
                message="Reload failed.",
                error=reload_error,
            )

    if reset_clicked:
        reset_config_editor_draft()
        set_config_editor_save_status(
            "success",
            message="Draft reset back to the last loaded configuration.",
        )

    editor_state = get_config_editor_state()
    draft_metrics = deepcopy(editor_state.get("draft_metrics_data") or {})
    draft_scoring = deepcopy(editor_state.get("draft_scoring_data") or {})

    if validate_clicked:
        validation = config_service.validate_bundle_data(
            metrics_data=draft_metrics,
            scoring_data=draft_scoring,
            against_dataset=validate_against_dataset,
        )
        set_config_editor_validation(
            validation, against_dataset=validate_against_dataset
        )
        if validation.valid:
            set_config_editor_save_status(
                "success",
                message="Draft validation succeeded.",
            )
        else:
            set_config_editor_save_status(
                "error",
                message="Draft validation failed.",
                error=validation.error,
            )

    if save_clicked:
        validation = config_service.validate_bundle_data(
            metrics_data=draft_metrics,
            scoring_data=draft_scoring,
            against_dataset=validate_against_dataset,
        )
        set_config_editor_validation(
            validation, against_dataset=validate_against_dataset
        )
        if not validation.valid:
            set_config_editor_save_status(
                "error",
                message="Save blocked because the draft is not valid.",
                error=validation.error,
            )
        else:
            try:
                bundle = config_service.build_bundle_from_data(
                    metrics_data=draft_metrics,
                    scoring_data=draft_scoring,
                    validate=True,
                )
                config_service.save_bundle(bundle)
                saved_payload = config_service.export_bundle_data(bundle=bundle)
                commit_config_editor_saved_state(
                    metrics_data=saved_payload["metrics"],
                    scoring_data=saved_payload["scoring"],
                )
                set_catalog_state({})
                refresh_cached_services()
                set_config_editor_save_status(
                    "success",
                    message="Configuration saved successfully.",
                )
            except Exception as exc:  # pragma: no cover - defensive save path
                error = error_from_exception(
                    exc,
                    default_title="Save failed",
                    default_user_message=(
                        "The validated configuration could not be written to disk."
                    ),
                )
                set_config_editor_save_status(
                    "error",
                    message="Save failed.",
                    error=error,
                )

    editor_state = get_config_editor_state()
    _render_feedback(editor_state)

    metrics_tab, scoring_tab = st.tabs(["Metrics", "Scoring profiles"])

    with metrics_tab:
        _render_metrics_editor(editor_state)

    with scoring_tab:
        _render_scoring_editor(editor_state)


def _ensure_editor_state_loaded(config_service) -> AppError | None:
    editor_state = get_config_editor_state()
    if (
        editor_state.get("draft_metrics_data") is not None
        and editor_state.get("draft_scoring_data") is not None
    ):
        return None
    return _reload_editor_state_from_disk(config_service)


def _reload_editor_state_from_disk(config_service) -> AppError | None:
    try:
        bundle_data = config_service.load_bundle_data(validate=False)
        initialize_config_editor_draft(
            metrics_data=bundle_data["metrics"],
            scoring_data=bundle_data["scoring"],
            force=True,
        )
        return None
    except Exception as exc:
        return error_from_exception(
            exc,
            default_title="Configuration could not be loaded",
            default_user_message="The current configuration files could not be opened for editing.",
        )


def _render_editor_status(editor_state: dict[str, Any]) -> None:
    draft_metrics = editor_state.get("draft_metrics_data") or {}
    draft_scoring = editor_state.get("draft_scoring_data") or {}
    metrics_count = len((draft_metrics.get("metrics") or {}).keys())
    profiles_count = len((draft_scoring.get("profiles") or {}).keys())

    cols = st.columns(4)
    cols[0].metric("Draft metrics", metrics_count)
    cols[1].metric("Draft profiles", profiles_count)
    cols[2].metric("Default profile", draft_scoring.get("default_profile") or "—")
    cols[3].metric("Unsaved changes", "Yes" if config_editor_is_dirty() else "No")

    if config_editor_is_dirty():
        st.warning("You have unsaved draft changes.")
    else:
        st.success("Draft matches the last loaded configuration.")


def _render_feedback(editor_state: dict[str, Any]) -> None:
    validation = editor_state.get("validation_report")
    if validation is not None:
        if validation.valid:
            st.success("Validation passed.")
        elif validation.error is not None:
            render_app_error(validation.error, debug=get_debug_mode())
        else:
            st.error("Validation failed.")

        messages = tuple(getattr(validation, "messages", ()) or ())
        if messages:
            with st.expander("Validation details", expanded=not validation.valid):
                for message in messages:
                    st.write(f"- {message}")

    save_status = editor_state.get("save_status")
    save_message = editor_state.get("save_message")
    save_error = editor_state.get("save_error")
    if save_status == "success" and save_message:
        st.success(save_message)
    elif save_status == "error":
        if save_error is not None:
            render_app_error(save_error, debug=get_debug_mode())
        elif save_message:
            st.error(save_message)


def _render_metrics_editor(editor_state: dict[str, Any]) -> None:
    metrics_data = deepcopy(editor_state.get("draft_metrics_data") or {"metrics": {}})
    scoring_data = deepcopy(editor_state.get("draft_scoring_data") or {"profiles": {}})
    metrics_map = metrics_data.setdefault("metrics", {})
    metric_ids = list(metrics_map.keys())
    selected_metric_id = (
        editor_state.get("selected_metric_id")
        if editor_state.get("selected_metric_id") in metric_ids
        else (metric_ids[0] if metric_ids else None)
    )

    control_cols = st.columns([2, 1, 1])
    if metric_ids:
        chosen_metric = control_cols[0].selectbox(
            "Metric draft",
            options=metric_ids,
            index=metric_ids.index(selected_metric_id),
            key="config_editor_metric_selector",
        )
        if chosen_metric != selected_metric_id:
            set_config_editor_selection(selected_metric_id=chosen_metric)
            selected_metric_id = chosen_metric
    else:
        control_cols[0].info("No metric drafts available yet.")

    if control_cols[1].button("New metric draft", use_container_width=True):
        new_metric_id = _make_unique_name(metric_ids, base_name="new_metric")
        metrics_map[new_metric_id] = _default_metric_entry(new_metric_id)
        set_config_editor_drafts(metrics_data=metrics_data, scoring_data=scoring_data)
        set_config_editor_selection(selected_metric_id=new_metric_id)
        return

    delete_disabled = selected_metric_id is None
    if control_cols[2].button(
        "Delete metric draft", disabled=delete_disabled, use_container_width=True
    ):
        metrics_data, scoring_data, next_metric_id = _delete_metric_from_draft(
            metrics_data=metrics_data,
            scoring_data=scoring_data,
            metric_id=selected_metric_id,
        )
        set_config_editor_drafts(metrics_data=metrics_data, scoring_data=scoring_data)
        set_config_editor_selection(selected_metric_id=next_metric_id)
        return

    if not selected_metric_id:
        st.info("Add a metric draft to begin editing metrics.")
        return

    metric_payload = deepcopy(metrics_map[selected_metric_id])
    normalization_options = [item.value for item in NormalizationMethod]

    with st.form(key=f"config_editor_metric_form::{selected_metric_id}"):
        form_col1, form_col2 = st.columns(2)
        metric_id_input = form_col1.text_input("Metric ID", value=selected_metric_id)
        display_name_input = form_col2.text_input(
            "Display name",
            value=str(metric_payload.get("display_name") or ""),
        )
        category_input = form_col1.text_input(
            "Category", value=str(metric_payload.get("category") or "")
        )
        default_weight_input = form_col2.number_input(
            "Default weight",
            min_value=0.000001,
            value=float(metric_payload.get("default_weight", 1.0) or 1.0),
            step=0.1,
            format="%.6f",
        )
        higher_is_better_input = form_col1.checkbox(
            "Higher is better",
            value=bool(metric_payload.get("higher_is_better", True)),
        )
        normalization_value = str(
            metric_payload.get("normalization_method")
            or NormalizationMethod.MINMAX.value
        )
        normalization_input = form_col2.selectbox(
            "Normalization method",
            options=normalization_options,
            index=(
                normalization_options.index(normalization_value)
                if normalization_value in normalization_options
                else 0
            ),
        )
        unit_input = form_col1.text_input(
            "Unit", value=str(metric_payload.get("unit") or "")
        )
        source_input = form_col2.text_input(
            "Source", value=str(metric_payload.get("source") or "")
        )
        description_input = st.text_area(
            "Description",
            value=str(metric_payload.get("description") or ""),
            height=120,
        )
        submitted = st.form_submit_button("Apply metric changes")

    if submitted:
        updated_metric = _compact_mapping(
            {
                "display_name": display_name_input,
                "category": category_input,
                "higher_is_better": bool(higher_is_better_input),
                "default_weight": float(default_weight_input),
                "description": description_input,
                "unit": unit_input,
                "source": source_input,
                "normalization_method": normalization_input,
            }
        )
        metrics_data, scoring_data, next_metric_id, error = _apply_metric_changes(
            metrics_data=metrics_data,
            scoring_data=scoring_data,
            current_metric_id=selected_metric_id,
            new_metric_id=metric_id_input,
            updated_metric=updated_metric,
        )
        if error is not None:
            set_config_editor_save_status(
                "error",
                message="Metric draft update failed.",
                error=error,
            )
        else:
            set_config_editor_drafts(
                metrics_data=metrics_data, scoring_data=scoring_data
            )
            set_config_editor_selection(selected_metric_id=next_metric_id)
            set_config_editor_save_status(
                "success",
                message="Metric draft updated.",
            )
            return

    summary_df = _metrics_summary_dataframe(metrics_data)
    if not summary_df.empty:
        st.markdown("### Metric draft summary")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)


def _render_scoring_editor(editor_state: dict[str, Any]) -> None:
    metrics_data = deepcopy(editor_state.get("draft_metrics_data") or {"metrics": {}})
    scoring_data = deepcopy(editor_state.get("draft_scoring_data") or {"profiles": {}})
    metric_ids = list((metrics_data.get("metrics") or {}).keys())
    profiles_map = scoring_data.setdefault("profiles", {})
    profile_names = list(profiles_map.keys())
    selected_profile_name = (
        editor_state.get("selected_profile_name")
        if editor_state.get("selected_profile_name") in profile_names
        else (profile_names[0] if profile_names else None)
    )

    st.markdown("### Global scoring settings")
    with st.form("config_editor_scoring_defaults_form"):
        defaults_col1, defaults_col2 = st.columns(2)
        defaults_col3, defaults_col4 = st.columns(2)
        default_profile_value = str(
            scoring_data.get("default_profile")
            or (profile_names[0] if profile_names else "")
        )
        default_profile_input = defaults_col1.selectbox(
            "Default profile",
            options=profile_names if profile_names else [""],
            index=(
                profile_names.index(default_profile_value)
                if profile_names and default_profile_value in profile_names
                else 0
            ),
            disabled=not bool(profile_names),
        )
        weight_handling_options = [item.value for item in WeightHandlingStrategy]
        weight_handling_value = str(
            scoring_data.get("weight_handling")
            or WeightHandlingStrategy.NORMALIZE.value
        )
        weight_handling_input = defaults_col2.selectbox(
            "Weight handling",
            options=weight_handling_options,
            index=(
                weight_handling_options.index(weight_handling_value)
                if weight_handling_value in weight_handling_options
                else 0
            ),
        )
        year_strategy_options = [item.value for item in YearStrategy]
        default_year_strategy_value = str(
            scoring_data.get("default_year_strategy")
            or YearStrategy.LATEST_PER_METRIC.value
        )
        default_year_strategy_input = defaults_col3.selectbox(
            "Default year strategy",
            options=year_strategy_options,
            index=(
                year_strategy_options.index(default_year_strategy_value)
                if default_year_strategy_value in year_strategy_options
                else 0
            ),
        )
        missing_policy_options = [item.value for item in MissingDataPolicy]
        default_missing_policy_value = str(
            scoring_data.get("default_missing_data_policy")
            or MissingDataPolicy.RENORMALIZE_WEIGHTS.value
        )
        default_missing_policy_input = defaults_col4.selectbox(
            "Default missing-data policy",
            options=missing_policy_options,
            index=(
                missing_policy_options.index(default_missing_policy_value)
                if default_missing_policy_value in missing_policy_options
                else 0
            ),
        )
        defaults_submitted = st.form_submit_button("Apply scoring defaults")

    if defaults_submitted:
        scoring_data["default_profile"] = default_profile_input
        scoring_data["weight_handling"] = weight_handling_input
        scoring_data["default_year_strategy"] = default_year_strategy_input
        scoring_data["default_missing_data_policy"] = default_missing_policy_input
        set_config_editor_drafts(metrics_data=metrics_data, scoring_data=scoring_data)
        set_config_editor_save_status(
            "success",
            message="Scoring defaults updated in the draft.",
        )
        return

    st.markdown("### Profiles")
    control_cols = st.columns([2, 1, 1])
    if profile_names:
        chosen_profile = control_cols[0].selectbox(
            "Profile draft",
            options=profile_names,
            index=profile_names.index(selected_profile_name),
            key="config_editor_profile_selector",
        )
        if chosen_profile != selected_profile_name:
            set_config_editor_selection(selected_profile_name=chosen_profile)
            selected_profile_name = chosen_profile
    else:
        control_cols[0].info("No profile drafts available yet.")

    if control_cols[1].button("New profile draft", use_container_width=True):
        new_profile_name = _make_unique_name(profile_names, base_name="new_profile")
        default_metric = metric_ids[:1]
        profiles_map[new_profile_name] = _default_profile_entry(default_metric)
        if not scoring_data.get("default_profile"):
            scoring_data["default_profile"] = new_profile_name
        set_config_editor_drafts(metrics_data=metrics_data, scoring_data=scoring_data)
        set_config_editor_selection(selected_profile_name=new_profile_name)
        return

    delete_disabled = selected_profile_name is None
    if control_cols[2].button(
        "Delete profile draft", disabled=delete_disabled, use_container_width=True
    ):
        scoring_data, next_profile_name = _delete_profile_from_draft(
            scoring_data=scoring_data,
            profile_name=selected_profile_name,
        )
        set_config_editor_drafts(metrics_data=metrics_data, scoring_data=scoring_data)
        set_config_editor_selection(selected_profile_name=next_profile_name)
        return

    if not selected_profile_name:
        st.info("Add a profile draft to begin editing scoring profiles.")
        return

    profile_payload = deepcopy(profiles_map[selected_profile_name])
    selected_metrics = [
        metric_id
        for metric_id in profile_payload.get("metrics", [])
        if metric_id in metric_ids
    ]
    weights = dict(profile_payload.get("weights") or {})
    normalization_overrides = dict(profile_payload.get("normalization_overrides") or {})

    override_year_options = [EMPTY_OVERRIDE, *[item.value for item in YearStrategy]]
    override_missing_options = [
        EMPTY_OVERRIDE,
        *[item.value for item in MissingDataPolicy],
    ]
    override_norm_options = [
        EMPTY_OVERRIDE,
        *[item.value for item in NormalizationMethod],
    ]

    with st.form(key=f"config_editor_profile_form::{selected_profile_name}"):
        form_col1, form_col2 = st.columns(2)
        profile_name_input = form_col1.text_input(
            "Profile name", value=selected_profile_name
        )
        description_input = form_col2.text_input(
            "Description",
            value=str(profile_payload.get("description") or ""),
        )
        metrics_input = st.multiselect(
            "Metrics in this profile",
            options=metric_ids,
            default=selected_metrics,
            help="Choose the metrics included in this scoring profile.",
        )
        profile_year_value = str(profile_payload.get("year_strategy") or EMPTY_OVERRIDE)
        profile_year_input = form_col1.selectbox(
            "Year strategy override",
            options=override_year_options,
            index=(
                override_year_options.index(profile_year_value)
                if profile_year_value in override_year_options
                else 0
            ),
            format_func=lambda value: (
                "Use scoring default" if value == EMPTY_OVERRIDE else value
            ),
        )
        profile_missing_value = str(
            profile_payload.get("missing_data_policy") or EMPTY_OVERRIDE
        )
        profile_missing_input = form_col2.selectbox(
            "Missing-data policy override",
            options=override_missing_options,
            index=(
                override_missing_options.index(profile_missing_value)
                if profile_missing_value in override_missing_options
                else 0
            ),
            format_func=lambda value: (
                "Use scoring default" if value == EMPTY_OVERRIDE else value
            ),
        )

        st.markdown("#### Per-metric overrides")
        resolved_weights: dict[str, float] = {}
        resolved_normalization_overrides: dict[str, str] = {}
        for metric_id in metrics_input:
            with st.container(border=True):
                metric_cols = st.columns([1, 1, 1, 1])
                metric_cols[0].write(f"**{metric_id}**")
                weight_enabled = metric_cols[1].checkbox(
                    "Weight override",
                    value=metric_id in weights,
                    key=f"profile_weight_enabled::{selected_profile_name}::{metric_id}",
                )
                weight_value = metric_cols[2].number_input(
                    f"Weight for {metric_id}",
                    min_value=0.000001,
                    value=float(weights.get(metric_id, 1.0) or 1.0),
                    step=0.1,
                    format="%.6f",
                    disabled=not weight_enabled,
                    key=f"profile_weight_value::{selected_profile_name}::{metric_id}",
                )
                norm_value = str(
                    normalization_overrides.get(metric_id) or EMPTY_OVERRIDE
                )
                normalization_value = metric_cols[3].selectbox(
                    f"Normalization for {metric_id}",
                    options=override_norm_options,
                    index=(
                        override_norm_options.index(norm_value)
                        if norm_value in override_norm_options
                        else 0
                    ),
                    format_func=lambda value: (
                        "Use metric default" if value == EMPTY_OVERRIDE else value
                    ),
                    key=f"profile_norm_value::{selected_profile_name}::{metric_id}",
                )
                if weight_enabled:
                    resolved_weights[metric_id] = float(weight_value)
                if normalization_value != EMPTY_OVERRIDE:
                    resolved_normalization_overrides[metric_id] = normalization_value

        submitted = st.form_submit_button("Apply profile changes")

    if submitted:
        updated_profile = {
            "metrics": list(metrics_input),
            "weights": resolved_weights,
            "normalization_overrides": resolved_normalization_overrides,
        }
        if profile_year_input != EMPTY_OVERRIDE:
            updated_profile["year_strategy"] = profile_year_input
        if profile_missing_input != EMPTY_OVERRIDE:
            updated_profile["missing_data_policy"] = profile_missing_input
        if description_input.strip():
            updated_profile["description"] = description_input.strip()

        scoring_data, next_profile_name, error = _apply_profile_changes(
            scoring_data=scoring_data,
            current_profile_name=selected_profile_name,
            new_profile_name=profile_name_input,
            updated_profile=updated_profile,
        )
        if error is not None:
            set_config_editor_save_status(
                "error",
                message="Profile draft update failed.",
                error=error,
            )
        else:
            set_config_editor_drafts(
                metrics_data=metrics_data, scoring_data=scoring_data
            )
            set_config_editor_selection(selected_profile_name=next_profile_name)
            set_config_editor_save_status(
                "success",
                message="Profile draft updated.",
            )
            return

    summary_df = _profiles_summary_dataframe(scoring_data)
    if not summary_df.empty:
        st.markdown("### Profile draft summary")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)


def _default_metric_entry(metric_id: str) -> dict[str, Any]:
    return {
        "display_name": metric_id.replace("_", " ").title(),
        "category": "Uncategorized",
        "higher_is_better": True,
        "default_weight": 1.0,
        "normalization_method": NormalizationMethod.MINMAX.value,
    }


def _default_profile_entry(metric_ids: list[str]) -> dict[str, Any]:
    return {
        "metrics": list(metric_ids),
        "weights": {},
        "normalization_overrides": {},
    }


def _metrics_summary_dataframe(metrics_data: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for metric_id, payload in (metrics_data.get("metrics") or {}).items():
        rows.append(
            {
                "metric_id": metric_id,
                "display_name": payload.get("display_name"),
                "category": payload.get("category"),
                "higher_is_better": payload.get("higher_is_better"),
                "default_weight": payload.get("default_weight"),
                "normalization_method": payload.get("normalization_method"),
                "unit": payload.get("unit"),
            }
        )
    return pd.DataFrame(rows)


def _profiles_summary_dataframe(scoring_data: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    default_profile = scoring_data.get("default_profile")
    for profile_name, payload in (scoring_data.get("profiles") or {}).items():
        rows.append(
            {
                "profile_name": profile_name,
                "is_default": profile_name == default_profile,
                "metric_count": len(payload.get("metrics") or []),
                "year_strategy": payload.get("year_strategy"),
                "missing_data_policy": payload.get("missing_data_policy"),
                "description": payload.get("description"),
            }
        )
    return pd.DataFrame(rows)


def _compact_mapping(values: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                continue
        if value is None:
            continue
        compacted[key] = value
    return compacted


def _make_unique_name(existing: list[str], *, base_name: str) -> str:
    if base_name not in existing:
        return base_name
    suffix = 2
    while f"{base_name}_{suffix}" in existing:
        suffix += 1
    return f"{base_name}_{suffix}"


def _apply_metric_changes(
    *,
    metrics_data: dict[str, Any],
    scoring_data: dict[str, Any],
    current_metric_id: str,
    new_metric_id: str,
    updated_metric: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str, AppError | None]:
    resolved_metric_id = str(new_metric_id).strip()
    if not resolved_metric_id:
        return (
            metrics_data,
            scoring_data,
            current_metric_id,
            AppError(
                code="input_invalid",
                title="Metric ID is required",
                user_message="Metric ID cannot be blank.",
                field_errors={"metric_id": "Metric ID cannot be blank."},
            ),
        )
    if " " in resolved_metric_id:
        return (
            metrics_data,
            scoring_data,
            current_metric_id,
            AppError(
                code="input_invalid",
                title="Metric ID is invalid",
                user_message="Metric ID must not contain spaces.",
                field_errors={
                    "metric_id": "Use underscores or another space-free identifier."
                },
            ),
        )
    existing_metrics = metrics_data.setdefault("metrics", {})
    if (
        resolved_metric_id != current_metric_id
        and resolved_metric_id in existing_metrics
    ):
        return (
            metrics_data,
            scoring_data,
            current_metric_id,
            AppError(
                code="input_invalid",
                title="Metric ID already exists",
                user_message="Choose a different metric ID.",
                field_errors={
                    "metric_id": f"'{resolved_metric_id}' is already used by another metric."
                },
            ),
        )

    updated_metrics = deepcopy(metrics_data)
    updated_scoring = deepcopy(scoring_data)
    updated_metrics.setdefault("metrics", {})[resolved_metric_id] = deepcopy(
        updated_metric
    )
    if resolved_metric_id != current_metric_id:
        updated_metrics["metrics"].pop(current_metric_id, None)
        updated_scoring = _rename_metric_references(
            scoring_data=updated_scoring,
            old_metric_id=current_metric_id,
            new_metric_id=resolved_metric_id,
        )
    return updated_metrics, updated_scoring, resolved_metric_id, None


def _rename_metric_references(
    *,
    scoring_data: dict[str, Any],
    old_metric_id: str,
    new_metric_id: str,
) -> dict[str, Any]:
    updated = deepcopy(scoring_data)
    for profile_payload in (updated.get("profiles") or {}).values():
        metrics = [
            new_metric_id if metric_id == old_metric_id else metric_id
            for metric_id in profile_payload.get("metrics", [])
        ]
        profile_payload["metrics"] = metrics

        weights = dict(profile_payload.get("weights") or {})
        if old_metric_id in weights:
            weights[new_metric_id] = weights.pop(old_metric_id)
        profile_payload["weights"] = weights

        normalization_overrides = dict(
            profile_payload.get("normalization_overrides") or {}
        )
        if old_metric_id in normalization_overrides:
            normalization_overrides[new_metric_id] = normalization_overrides.pop(
                old_metric_id
            )
        profile_payload["normalization_overrides"] = normalization_overrides
    return updated


def _delete_metric_from_draft(
    *,
    metrics_data: dict[str, Any],
    scoring_data: dict[str, Any],
    metric_id: str,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    updated_metrics = deepcopy(metrics_data)
    updated_scoring = deepcopy(scoring_data)
    metrics_map = updated_metrics.setdefault("metrics", {})
    metrics_map.pop(metric_id, None)

    for profile_payload in (updated_scoring.get("profiles") or {}).values():
        profile_payload["metrics"] = [
            value for value in profile_payload.get("metrics", []) if value != metric_id
        ]
        profile_payload["weights"] = {
            key: value
            for key, value in (profile_payload.get("weights") or {}).items()
            if key != metric_id
        }
        profile_payload["normalization_overrides"] = {
            key: value
            for key, value in (
                profile_payload.get("normalization_overrides") or {}
            ).items()
            if key != metric_id
        }

    next_metric_id = next(iter(metrics_map.keys()), None)
    return updated_metrics, updated_scoring, next_metric_id


def _apply_profile_changes(
    *,
    scoring_data: dict[str, Any],
    current_profile_name: str,
    new_profile_name: str,
    updated_profile: dict[str, Any],
) -> tuple[dict[str, Any], str, AppError | None]:
    resolved_profile_name = str(new_profile_name).strip()
    if not resolved_profile_name:
        return (
            scoring_data,
            current_profile_name,
            AppError(
                code="input_invalid",
                title="Profile name is required",
                user_message="Profile name cannot be blank.",
                field_errors={"profile_name": "Profile name cannot be blank."},
            ),
        )

    updated = deepcopy(scoring_data)
    profiles = updated.setdefault("profiles", {})
    if (
        resolved_profile_name != current_profile_name
        and resolved_profile_name in profiles
    ):
        return (
            scoring_data,
            current_profile_name,
            AppError(
                code="input_invalid",
                title="Profile already exists",
                user_message="Choose a different profile name.",
                field_errors={
                    "profile_name": f"'{resolved_profile_name}' is already used by another profile."
                },
            ),
        )

    profiles[resolved_profile_name] = deepcopy(updated_profile)
    if resolved_profile_name != current_profile_name:
        profiles.pop(current_profile_name, None)
        if updated.get("default_profile") == current_profile_name:
            updated["default_profile"] = resolved_profile_name

    if not updated.get("default_profile") and resolved_profile_name in profiles:
        updated["default_profile"] = resolved_profile_name

    return updated, resolved_profile_name, None


def _delete_profile_from_draft(
    *,
    scoring_data: dict[str, Any],
    profile_name: str,
) -> tuple[dict[str, Any], str | None]:
    updated = deepcopy(scoring_data)
    profiles = updated.setdefault("profiles", {})
    profiles.pop(profile_name, None)

    next_profile_name = next(iter(profiles.keys()), None)
    if updated.get("default_profile") == profile_name:
        updated["default_profile"] = next_profile_name or ""
    return updated, next_profile_name
