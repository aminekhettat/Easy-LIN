"""Backend registry for LIN communication providers.

New LIN hardware adapters can call :func:`register` at import time so that
the GUI can discover and instantiate them without any code-level coupling.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.7.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

from __future__ import annotations

from typing import Any, Callable

BackendFactory = Callable[..., Any]

_registry: dict[str, BackendFactory] = {}


def register(name: str, factory: BackendFactory) -> None:
    """Register a backend factory under *name*.

    If *name* is already taken the old entry is replaced.

    Args:
        name: Display name used to look up the factory (e.g. ``"vector"``).
        factory: Callable that accepts keyword arguments and returns a
            ``CommunicationBackend``-compatible object.
    """
    _registry[name] = factory


def list_backends() -> list[str]:
    """Return the names of all registered backend factories."""
    return list(_registry.keys())


def create_backend(name: str, **kwargs: Any) -> Any:
    """Instantiate the named backend with *kwargs* forwarded to its factory.

    Args:
        name: Name previously passed to :func:`register`.
        **kwargs: Keyword arguments forwarded verbatim to the factory callable.

    Returns:
        A ``CommunicationBackend``-compatible instance.

    Raises:
        KeyError: If *name* has not been registered.
    """
    if name not in _registry:
        raise KeyError(f"No backend registered under '{name}'.")
    return _registry[name](**kwargs)
