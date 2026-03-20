"""Communication helpers exposed by the Easy-LIN package.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.2
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

from .vector_lin import VectorLINBus, LINFrame, LINError

__all__ = ["VectorLINBus", "LINFrame", "LINError"]

