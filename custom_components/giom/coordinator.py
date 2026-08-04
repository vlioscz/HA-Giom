"""Polling coordinator for the GIOM 3000 weather station."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any
from xml.etree import ElementTree

from aiohttp import ClientError, ClientTimeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BEAUFORT_LIMITS,
    COMPASS_POINTS,
    CONF_COMMUNITY,
    CONF_USE_SNMP,
    DEFAULT_COMMUNITY,
    DEFAULT_SCAN_INTERVAL,
    DEGREES_PER_STEP,
    OID_ABSOLUTE_PRESSURE,
    OID_WIND_SPEED_AVERAGE,
    STATUS_PATH,
)
from .snmp import SnmpError, get_float

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = ClientTimeout(total=10)

type GiomConfigEntry = ConfigEntry[GiomCoordinator]

# Fields we read straight out of status.xml. Anything the station omits simply
# stays absent from the resulting dict; the matching entity then reports
# unknown rather than a made-up zero.
_NUMERIC_FIELDS = (
    "windspeed",
    "windgust",
    "pressure",
    "systemp",
    "temperature",
    "baraltitude",
    "windchill",
    "relhumidity",
    "abshumidity",
    "dewpoint",
    # Only the IQWS-4000 / GIOM 4000NG reports the following. A GIOM 3000
    # simply omits them and the matching entities are never created.
    "spower",  # sunlight intensity, W/m2
    "uf",  # UV factor
    "sdist",  # distance of the last lightning strike, km
    "senr",  # energy of the last lightning strike
)


def url_host(host: str) -> str:
    """Return the host wrapped in brackets when it is a bare IPv6 address."""
    bare = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    return f"[{bare}]" if ":" in bare else bare


def status_url(host: str) -> str:
    """Build the status.xml URL for a host."""
    return f"http://{url_host(host)}{STATUS_PATH}"


def beaufort(speed: float) -> int:
    """Convert a wind speed in m/s to the Beaufort scale."""
    for force, limit in enumerate(BEAUFORT_LIMITS):
        if speed < limit:
            return force
    return len(BEAUFORT_LIMITS)


def parse_status(payload: str) -> dict[str, Any]:
    """Turn a status.xml document into a flat dict of values.

    Kept free of Home Assistant imports so it can be exercised on its own.
    """
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as err:
        raise ValueError(f"malformed status.xml: {err}") from err

    raw = {child.tag: (child.text or "").strip() for child in root}
    data: dict[str, Any] = {}

    for field in _NUMERIC_FIELDS:
        value = raw.get(field)
        if not value:
            continue
        try:
            data[field] = float(value.replace(",", "."))
        except ValueError:
            _LOGGER.debug("Ignoring non-numeric %s=%r", field, value)

    if devname := raw.get("devname", "").strip():
        data["devname"] = devname

    # winddir is an index on a 16-point rose, not a bearing in degrees.
    if (index := raw.get("winddir")) not in (None, ""):
        try:
            step = int(float(index.replace(",", ".")))
        except ValueError:
            _LOGGER.debug("Ignoring non-numeric winddir=%r", index)
        else:
            data["wind_bearing"] = round(step * DEGREES_PER_STEP, 1)
            data["wind_direction"] = COMPASS_POINTS[step % len(COMPASS_POINTS)]

    if (speed := data.get("windspeed")) is not None:
        data["beaufort"] = beaufort(speed)

    return data


class GiomCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch station readings on a schedule."""

    config_entry: GiomConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GiomConfigEntry,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialise the coordinator from a config entry."""
        self.host: str = entry.data[CONF_HOST]
        self.use_snmp: bool = entry.options.get(
            CONF_USE_SNMP, entry.data.get(CONF_USE_SNMP, False)
        )
        self.community: str = entry.options.get(
            CONF_COMMUNITY, entry.data.get(CONF_COMMUNITY, DEFAULT_COMMUNITY)
        )
        self._session = async_get_clientsession(hass)
        self._snmp_failures = 0

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"GIOM 3000 ({self.host})",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll status.xml, then top it up with SNMP-only values."""
        try:
            async with self._session.get(
                status_url(self.host), timeout=REQUEST_TIMEOUT
            ) as response:
                response.raise_for_status()
                payload = await response.text()
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Cannot reach the station: {err}") from err

        try:
            data = parse_status(payload)
        except ValueError as err:
            raise UpdateFailed(str(err)) from err

        if not data:
            raise UpdateFailed("status.xml contained no usable readings")

        if self.use_snmp:
            data.update(await self._async_fetch_snmp())

        return data

    async def _async_fetch_snmp(self) -> dict[str, Any]:
        """Read the two values status.xml does not carry.

        SNMP is a bonus, never a reason to fail the whole update - if it stops
        answering the HTTP readings still go through.
        """
        try:
            extras = await self.hass.async_add_executor_job(self._fetch_snmp)
        except SnmpError as err:
            self._snmp_failures += 1
            if self._snmp_failures in (1, 10):
                _LOGGER.warning(
                    "SNMP readings from %s are unavailable (%s); the values from "
                    "status.xml keep working. Disable SNMP in the integration "
                    "options to silence this",
                    self.host,
                    err,
                )
            return {}

        self._snmp_failures = 0
        return extras

    def _fetch_snmp(self) -> dict[str, Any]:
        """Blocking SNMP reads, run in an executor."""
        extras: dict[str, Any] = {}

        average = get_float(
            self.host, OID_WIND_SPEED_AVERAGE, self.community, request_id=11
        )
        if average is not None:
            extras["windspeed_average"] = average

        absolute = get_float(
            self.host, OID_ABSOLUTE_PRESSURE, self.community, request_id=12
        )
        if absolute is not None:
            extras["pressure_absolute"] = absolute

        return extras
