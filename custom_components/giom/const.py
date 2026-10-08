"""Constants for the GIOM 3000 integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "giom"

MANUFACTURER: Final = "Mikrovlny s.r.o."
DEFAULT_MODEL: Final = "GIOM"

CONF_USE_SNMP: Final = "use_snmp"
CONF_COMMUNITY: Final = "community"

DEFAULT_COMMUNITY: Final = "public"
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 3600

STATUS_PATH: Final = "/status.xml"

# Second endpoint, served by the 4000 series only. Short keys, and it is the
# only place the station reports its sensor-health flags (PSS/THS/SSS/TS).
DATA_PATH: Final = "/data.xml"

# The station answers SNMP only on OIDs carrying a leading zero. The plain
# 1.3.6.1.4.1.21287... form returns noSuchName - verified against firmware
# 1.0.3. This is not a typo.
OID_PREFIX: Final = "0.1.3.6.1.4.1.21287.15"
OID_ABSOLUTE_PRESSURE: Final = f"{OID_PREFIX}.2.0"
OID_WIND_SPEED_AVERAGE: Final = f"{OID_PREFIX}.6.0"
OID_TEMPERATURE: Final = f"{OID_PREFIX}.14.0"

# Wind direction is reported as an index on a 16-point compass rose,
# 0 = North, one step = 22.5 degrees. Verified against the station's own
# degree reading: index 3 -> 67.5 deg.
DEGREES_PER_STEP: Final = 22.5

# The station has no illuminance sensor. Its web UI derives lux from the
# solar-power reading with this coefficient hard-wired in the page source:
# get lux(){ return +(this.value * 126.7).toFixed(2); }
LUX_PER_WATT: Final = 126.7

COMPASS_POINTS: Final = [
    "n",
    "nne",
    "ne",
    "ene",
    "e",
    "ese",
    "se",
    "sse",
    "s",
    "ssw",
    "sw",
    "wsw",
    "w",
    "wnw",
    "nw",
    "nnw",
]

# Upper bound of each Beaufort force in m/s. Computed locally so the value is
# available even when SNMP is switched off on the station.
BEAUFORT_LIMITS: Final = [
    0.3,
    1.6,
    3.4,
    5.5,
    8.0,
    10.8,
    13.9,
    17.2,
    20.8,
    24.5,
    28.5,
    32.7,
]
