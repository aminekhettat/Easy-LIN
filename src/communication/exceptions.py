"""Communication-layer exceptions for Vector/LIN operations.

Defines custom exception types used by the communication backend.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.7.0
:date: 2026-03-23
"""


class VectorError(RuntimeError):
    """Base exception for Vector XL API related failures."""


class LINError(RuntimeError):
    """Base exception for LIN protocol and controller failures."""
