from __future__ import annotations

import copy
import inspect
from collections.abc import Callable

from country_compare.data.ingestion.base import SourceAdapter
from country_compare.data.ingestion.specs import AdapterRegistration


class AdapterRegistryError(KeyError):
    """Raised when a source adapter cannot be registered or resolved."""


_REGISTRY: dict[str, AdapterRegistration] = {}
_BUILTINS_REGISTERED = False


def _ensure_builtin_adapters_registered() -> None:
    global _BUILTINS_REGISTERED
    if _BUILTINS_REGISTERED:
        return

    _BUILTINS_REGISTERED = True
    try:
        from country_compare.data.ingestion.adapters import passthrough  # noqa: F401
    except Exception:
        # Keep import lazy and tolerant. Resolution will still fail clearly if the
        # requested adapter is unavailable.
        pass


def _make_factory(
    adapter: type[SourceAdapter] | SourceAdapter | Callable[[], SourceAdapter],
) -> Callable[[], SourceAdapter]:
    if inspect.isclass(adapter):
        if not issubclass(adapter, SourceAdapter):
            raise TypeError("adapter class must inherit from SourceAdapter")
        return adapter

    if isinstance(adapter, SourceAdapter):
        return lambda adapter=adapter: copy.deepcopy(adapter)

    if callable(adapter):
        return adapter

    raise TypeError("adapter must be a SourceAdapter subclass, instance, or factory")


def register_source_adapter(
    adapter_id: str,
    adapter: type[SourceAdapter] | SourceAdapter | Callable[[], SourceAdapter],
    *,
    description: str | None = None,
    replace: bool = False,
) -> None:
    normalized_id = str(adapter_id).strip()
    if not normalized_id:
        raise ValueError("adapter_id must be a non-empty string")

    if normalized_id in _REGISTRY and not replace:
        raise AdapterRegistryError(f"adapter already registered: {normalized_id}")

    _REGISTRY[normalized_id] = AdapterRegistration(
        adapter_id=normalized_id,
        factory=_make_factory(adapter),
        description=description,
    )


def unregister_source_adapter(adapter_id: str) -> None:
    _REGISTRY.pop(str(adapter_id).strip(), None)


def clear_source_adapters(*, keep_builtins: bool = True) -> None:
    _REGISTRY.clear()
    global _BUILTINS_REGISTERED
    _BUILTINS_REGISTERED = False
    if keep_builtins:
        _ensure_builtin_adapters_registered()


def has_source_adapter(adapter_id: str) -> bool:
    _ensure_builtin_adapters_registered()
    return str(adapter_id).strip() in _REGISTRY


def resolve_source_adapter(adapter_id: str) -> SourceAdapter:
    _ensure_builtin_adapters_registered()
    normalized_id = str(adapter_id).strip()
    try:
        registration = _REGISTRY[normalized_id]
    except KeyError as exc:
        available = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise AdapterRegistryError(
            f"unknown source adapter '{normalized_id}'. Available adapters: {available}"
        ) from exc

    adapter = registration.factory()
    if not isinstance(adapter, SourceAdapter):
        raise AdapterRegistryError(
            f"adapter factory for '{normalized_id}' did not return a SourceAdapter instance"
        )
    return adapter


def list_registered_source_adapters() -> tuple[str, ...]:
    _ensure_builtin_adapters_registered()
    return tuple(sorted(_REGISTRY))
