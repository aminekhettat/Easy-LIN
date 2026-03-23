"""Tests for communication exceptions."""

from src.communication.exceptions import LINError, VectorError


class TestExceptions:
    def test_vector_error_is_runtime_error(self):
        err = VectorError("vector")
        assert isinstance(err, RuntimeError)
        assert "vector" in str(err)

    def test_lin_error_is_runtime_error(self):
        err = LINError("lin")
        assert isinstance(err, RuntimeError)
        assert "lin" in str(err)
