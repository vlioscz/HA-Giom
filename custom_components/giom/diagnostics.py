"""Diagnostics support for the GIOM integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_COMMUNITY
from .coordinator import GiomConfigEntry

# The address of the station and its community string are the only things in
# here worth hiding - diagnostics routinely get pasted into public issues.
TO_REDACT = {CONF_HOST, CONF_COMMUNITY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GiomConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "use_snmp": coordinator.use_snmp,
            "update_interval": str(coordinator.update_interval),
        },
        "readings": coordinator.data,
    }
