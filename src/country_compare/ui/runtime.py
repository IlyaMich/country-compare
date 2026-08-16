from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from country_compare.clients.base import CountryCompareClient
from country_compare.services import AppContext


class UiMode(StrEnum):
    """Runtime mode used by the Streamlit UI."""

    LOCAL = "local"
    HTTP = "http"


@dataclass(frozen=True, slots=True)
class UiCapabilities:
    """Capabilities available to the UI in the current runtime mode."""

    config_editing: bool


@dataclass(frozen=True, slots=True)
class UiRuntimeContext:
    """Runtime dependencies and capabilities available to Streamlit views."""

    app_context: AppContext
    client: CountryCompareClient
    mode: UiMode
    capabilities: UiCapabilities

    @property
    def is_local(self) -> bool:
        return self.mode is UiMode.LOCAL

    @property
    def is_http(self) -> bool:
        return self.mode is UiMode.HTTP


def build_ui_runtime_context(
    *,
    app_context: AppContext,
    client: CountryCompareClient,
) -> UiRuntimeContext:
    """Build a UI runtime context from the selected client implementation."""

    try:
        mode = UiMode(str(client.mode).strip().lower())
    except ValueError as exc:
        raise ValueError(
            f"Unsupported Country Compare client mode: {client.mode!r}"
        ) from exc

    capabilities = UiCapabilities(
        config_editing=(mode is UiMode.LOCAL),
    )

    return UiRuntimeContext(
        app_context=app_context,
        client=client,
        mode=mode,
        capabilities=capabilities,
    )
