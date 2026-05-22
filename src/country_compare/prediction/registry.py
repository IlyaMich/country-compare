from __future__ import annotations

import copy
import inspect
from collections.abc import Callable
from dataclasses import dataclass

from country_compare.prediction.forecasters import (
    BaseForecaster,
    HoltLinearForecaster,
    LastObservedForecaster,
    LinearTrendForecaster,
    MovingAverageForecaster,
)


class ForecasterRegistryError(KeyError):
    """Raised when a forecaster method cannot be registered or resolved."""


@dataclass(frozen=True, slots=True)
class ForecasterRegistration:
    method_id: str
    factory: Callable[[], BaseForecaster]
    description: str | None = None


_REGISTRY: dict[str, ForecasterRegistration] = {}
_BUILTINS_REGISTERED = False


def _make_factory(
    forecaster: type[BaseForecaster] | BaseForecaster | Callable[[], BaseForecaster],
) -> Callable[[], BaseForecaster]:
    if inspect.isclass(forecaster):
        if not issubclass(forecaster, BaseForecaster):
            raise TypeError("forecaster class must inherit from BaseForecaster")
        return forecaster

    if isinstance(forecaster, BaseForecaster):

        def factory() -> BaseForecaster:
            return copy.deepcopy(forecaster)

        return factory

    if callable(forecaster):
        return forecaster

    raise TypeError(
        "forecaster must be a BaseForecaster subclass, instance, or factory"
    )


def _ensure_builtin_forecasters_registered() -> None:
    global _BUILTINS_REGISTERED
    if _BUILTINS_REGISTERED:
        return
    register_forecaster(
        LastObservedForecaster.method_id, LastObservedForecaster, replace=True
    )
    register_forecaster(
        LinearTrendForecaster.method_id, LinearTrendForecaster, replace=True
    )
    register_forecaster(
        MovingAverageForecaster.method_id, MovingAverageForecaster, replace=True
    )
    register_forecaster(
        HoltLinearForecaster.method_id, HoltLinearForecaster, replace=True
    )
    _BUILTINS_REGISTERED = True


def register_forecaster(
    method_id: str,
    forecaster: type[BaseForecaster] | BaseForecaster | Callable[[], BaseForecaster],
    *,
    description: str | None = None,
    replace: bool = False,
) -> None:
    normalized_id = str(method_id).strip()
    if not normalized_id:
        raise ValueError("method_id must be a non-empty string")
    if normalized_id in _REGISTRY and not replace:
        raise ForecasterRegistryError(f"forecaster already registered: {normalized_id}")
    _REGISTRY[normalized_id] = ForecasterRegistration(
        method_id=normalized_id,
        factory=_make_factory(forecaster),
        description=description,
    )


def unregister_forecaster(method_id: str) -> None:
    _REGISTRY.pop(str(method_id).strip(), None)


def clear_forecasters(*, keep_builtins: bool = True) -> None:
    global _BUILTINS_REGISTERED
    _REGISTRY.clear()
    _BUILTINS_REGISTERED = False
    if keep_builtins:
        _ensure_builtin_forecasters_registered()


def has_forecaster(method_id: str) -> bool:
    _ensure_builtin_forecasters_registered()
    return str(method_id).strip() in _REGISTRY


def resolve_forecaster(method_id: str) -> BaseForecaster:
    _ensure_builtin_forecasters_registered()
    normalized_id = str(method_id).strip()
    try:
        registration = _REGISTRY[normalized_id]
    except KeyError as exc:
        available = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise ForecasterRegistryError(
            f"unknown prediction forecaster '{normalized_id}'. Available forecasters: {available}"
        ) from exc
    forecaster = registration.factory()
    if not isinstance(forecaster, BaseForecaster):
        raise ForecasterRegistryError(
            f"forecaster factory for '{normalized_id}' did not return a BaseForecaster instance"
        )
    return forecaster


def list_forecasters() -> tuple[str, ...]:
    _ensure_builtin_forecasters_registered()
    return tuple(sorted(_REGISTRY))
