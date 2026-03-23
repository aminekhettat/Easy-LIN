"""Tests for src/communication/backend_registry.py.

Covers register, list_backends, create_backend (success & KeyError), and
overwrite semantics.  Each test runs against an isolated copy of the registry
so that the Vector backend registered at import time does not interfere.
"""

from __future__ import annotations

import pytest

from src.communication import backend_registry


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot and restore the registry around every test."""
    snapshot = dict(backend_registry._registry)
    backend_registry._registry.clear()
    yield
    backend_registry._registry.clear()
    backend_registry._registry.update(snapshot)


class TestListBackends:
    def test_empty_when_nothing_registered(self):
        assert backend_registry.list_backends() == []

    def test_returns_registered_names(self):
        backend_registry.register("alpha", lambda: None)
        backend_registry.register("beta", lambda: None)
        names = backend_registry.list_backends()
        assert "alpha" in names
        assert "beta" in names
        assert len(names) == 2


class TestRegister:
    def test_register_adds_entry(self):
        backend_registry.register("my_backend", lambda: "v1")
        assert "my_backend" in backend_registry.list_backends()

    def test_register_overwrites_existing(self):
        backend_registry.register("dup", lambda: "v1")
        backend_registry.register("dup", lambda: "v2")
        result = backend_registry.create_backend("dup")
        assert result == "v2"


class TestCreateBackend:
    def test_creates_from_registered_factory(self):
        created = []

        def factory(**kwargs):
            created.append(kwargs)
            return "instance"

        backend_registry.register("test", factory)
        result = backend_registry.create_backend("test", x=1, y=2)
        assert result == "instance"
        assert created == [{"x": 1, "y": 2}]

    def test_unknown_name_raises_key_error(self):
        with pytest.raises(KeyError, match="unknown"):
            backend_registry.create_backend("unknown")

    def test_no_kwargs_calls_factory_with_empty_kwargs(self):
        calls = []

        def factory(**kwargs):
            calls.append(kwargs)
            return "ok"

        backend_registry.register("bare", factory)
        backend_registry.create_backend("bare")
        assert calls == [{}]
