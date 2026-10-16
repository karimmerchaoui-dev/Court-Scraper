"""
counties/
---------
One module per county (or per state if counties share a portal).
Each module calls registry.register(...) so that the rest of the system
can look up counties by name without importing specific modules directly.

Import this package once at startup to populate the global registry.
"""

# counties/__init__.py
from . import (  # noqa: F401  (side-effects)
    atlantic_county,
    bergen_county,
    brevard_county,
    broward_county,
    burlington_county,
    camden_county,
    cape_may_county,
    cumberland_county,
    duval_county,
    essex_county,
    hudson_county,
    mercer_county,
    middlesex_county,
    monmouth_county,
    morris_county,
    ocean_county,
    osceola_county,
    passaic_county,
    polk_county,
    sussex_county,
    union_county,
    volusia_county,
)
