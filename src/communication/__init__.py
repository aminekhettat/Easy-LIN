"""Communication helpers exposed by the Easy-LIN package.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.6.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

from .vector_lin import VectorLINBus, LINFrame, LINError
from .exceptions import VectorError
from .hardware_discovery import HardwareDiscovery, LINChannel, VectorDevice
from .lin_controller import LINController, LINMode, ChecksumMode, BUSStatistics, ScheduleEntry
from . import backend_registry

__all__ = [
        "VectorLINBus",
        "LINFrame",
        "LINError",
        "VectorError",
        "HardwareDiscovery",
        "LINChannel",
        "VectorDevice",
        "LINController",
        "LINMode",
        "ChecksumMode",
        "BUSStatistics",
        "ScheduleEntry",
        "backend_registry",
]

