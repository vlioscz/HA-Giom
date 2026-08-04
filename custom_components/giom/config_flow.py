"""Config flow for the GIOM 3000 integration."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientError, ClientTimeout
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_COMMUNITY,
    CONF_USE_SNMP,
    DEFAULT_COMMUNITY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    OID_TEMPERATURE,
)
from .coordinator import GiomConfigEntry, parse_status, status_url
from .snmp import SnmpError, get

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_COMMUNITY, default=DEFAULT_COMMUNITY): str,
    }
)


async def _async_probe_http(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """Confirm the host serves a readable status.xml and return its readings."""
    session = async_get_clientsession(hass)
    async with session.get(
        status_url(host), timeout=ClientTimeout(total=10)
    ) as response:
        response.raise_for_status()
        payload = await response.text()
    return parse_status(payload)


def _probe_snmp(host: str, community: str) -> bool:
    """Return True when the station answers SNMP with the community given."""
    try:
        return get(host, OID_TEMPERATURE, community, timeout=3.0) is not None
    except SnmpError:
        return False


class GiomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Walk the user through adding a station."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the address, then verify we can actually read the station."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            community = user_input.get(CONF_COMMUNITY, DEFAULT_COMMUNITY).strip()

            self._async_abort_entries_match({CONF_HOST: host})

            try:
                readings = await _async_probe_http(self.hass, host)
            except (ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "invalid_response"
            else:
                if not readings:
                    errors["base"] = "invalid_response"
                else:
                    await self.async_set_unique_id(host)
                    self._abort_if_unique_id_configured()

                    # SNMP carries two values status.xml leaves out. Probe once
                    # here so the user never has to know it exists.
                    use_snmp = await self.hass.async_add_executor_job(
                        _probe_snmp, host, community
                    )
                    _LOGGER.debug("SNMP available on %s: %s", host, use_snmp)

                    return self.async_create_entry(
                        title=readings.get("devname") or "GIOM 3000",
                        data={
                            CONF_HOST: host,
                            CONF_COMMUNITY: community,
                            CONF_USE_SNMP: use_snmp,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: GiomConfigEntry) -> GiomOptionsFlow:
        """Return the options handler."""
        return GiomOptionsFlow()


class GiomOptionsFlow(OptionsFlow):
    """Let the user retune polling and SNMP after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_USE_SNMP: user_input[CONF_USE_SNMP],
                    CONF_COMMUNITY: user_input[CONF_COMMUNITY].strip(),
                }
            )

        entry = self.config_entry
        current = {
            CONF_SCAN_INTERVAL: entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
            ),
            CONF_USE_SNMP: entry.options.get(
                CONF_USE_SNMP, entry.data.get(CONF_USE_SNMP, False)
            ),
            CONF_COMMUNITY: entry.options.get(
                CONF_COMMUNITY, entry.data.get(CONF_COMMUNITY, DEFAULT_COMMUNITY)
            ),
        }

        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_USE_SNMP): bool,
                vol.Required(CONF_COMMUNITY): str,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, current),
        )
