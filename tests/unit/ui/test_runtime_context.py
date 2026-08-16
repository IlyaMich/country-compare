from __future__ import annotations

from dataclasses import dataclass

import pytest

from country_compare.ui.runtime import (
    UiMode,
    build_ui_runtime_context,
)


@dataclass
class _FakeClient:
    mode: str


def test_build_ui_runtime_context_for_local_client(
    fake_app_context,
) -> None:
    client = _FakeClient(mode="local")

    runtime = build_ui_runtime_context(
        app_context=fake_app_context,
        client=client,  # type: ignore[arg-type]
    )

    assert runtime.app_context is fake_app_context
    assert runtime.client is client
    assert runtime.mode is UiMode.LOCAL
    assert runtime.is_local is True
    assert runtime.is_http is False
    assert runtime.capabilities.config_editing is True


def test_build_ui_runtime_context_for_http_client(
    fake_app_context,
) -> None:
    client = _FakeClient(mode="http")

    runtime = build_ui_runtime_context(
        app_context=fake_app_context,
        client=client,  # type: ignore[arg-type]
    )

    assert runtime.app_context is fake_app_context
    assert runtime.client is client
    assert runtime.mode is UiMode.HTTP
    assert runtime.is_local is False
    assert runtime.is_http is True
    assert runtime.capabilities.config_editing is False


def test_build_ui_runtime_context_rejects_unknown_client_mode(
    fake_app_context,
) -> None:
    client = _FakeClient(mode="something-else")

    with pytest.raises(
        ValueError,
        match="Unsupported Country Compare client mode",
    ):
        build_ui_runtime_context(
            app_context=fake_app_context,
            client=client,  # type: ignore[arg-type]
        )
