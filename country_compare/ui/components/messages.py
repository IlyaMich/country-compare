from __future__ import annotations

from typing import Any

import streamlit as st


def render_app_error(error: Any, *, debug: bool = False) -> None:
    if error is None:
        return

    title = getattr(error, "title", "Error")
    user_message = getattr(error, "user_message", str(error))
    field_errors = getattr(error, "field_errors", None) or {}
    technical_detail = getattr(error, "technical_detail", None)
    code = getattr(error, "code", None)

    st.error(f"{title}: {user_message}")

    if field_errors:
        st.markdown("**Fields to review**")
        for field_name, message in field_errors.items():
            st.caption(f"{field_name}: {message}")

    if debug and (technical_detail or code):
        with st.expander("Technical details"):
            if code:
                st.write(f"**Code:** {code}")
            if technical_detail:
                st.code(str(technical_detail))


def render_messages(messages: list[Any]) -> None:
    for message in messages:
        level = getattr(message, "level", "info")
        text = getattr(message, "text", str(message))
        detail = getattr(message, "detail", None)
        payload = text if not detail else f"{text}\n\n{detail}"
        if level == "success":
            st.success(payload)
        elif level == "warning":
            st.warning(payload)
        elif level == "error":
            st.error(payload)
        else:
            st.info(payload)
