"""Tests for the config and options flows."""

from unittest.mock import patch

from aiohttp import ClientError
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.giom.const import (
    CONF_COMMUNITY,
    CONF_USE_SNMP,
    DOMAIN,
)

HOST = "192.168.0.100"
READINGS = {"temperature": 30.6, "windspeed": 2.5, "devname": "GIOM 3000AE"}


async def _submit(hass: HomeAssistant, user_input):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )


async def test_user_flow_creates_entry(hass: HomeAssistant):
    with (
        patch(
            "custom_components.giom.config_flow._async_probe_http",
            return_value=READINGS,
        ),
        patch(
            "custom_components.giom.config_flow._probe_snmp", return_value=True
        ),
        patch("custom_components.giom.async_setup_entry", return_value=True),
    ):
        result = await _submit(hass, {CONF_HOST: f" {HOST} ", CONF_COMMUNITY: "public"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "GIOM"
    assert result["data"] == {
        CONF_HOST: HOST,  # stripped
        CONF_COMMUNITY: "public",
        CONF_USE_SNMP: True,
    }
    assert result["result"].unique_id == HOST


async def test_user_flow_without_snmp(hass: HomeAssistant):
    with (
        patch(
            "custom_components.giom.config_flow._async_probe_http",
            return_value=READINGS,
        ),
        patch(
            "custom_components.giom.config_flow._probe_snmp", return_value=False
        ),
        patch("custom_components.giom.async_setup_entry", return_value=True),
    ):
        result = await _submit(hass, {CONF_HOST: HOST, CONF_COMMUNITY: "public"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USE_SNMP] is False


async def test_user_flow_cannot_connect(hass: HomeAssistant):
    with patch(
        "custom_components.giom.config_flow._async_probe_http",
        side_effect=ClientError,
    ):
        result = await _submit(hass, {CONF_HOST: HOST, CONF_COMMUNITY: "public"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_not_a_giom(hass: HomeAssistant):
    with patch(
        "custom_components.giom.config_flow._async_probe_http",
        side_effect=ValueError("malformed status.xml"),
    ):
        result = await _submit(hass, {CONF_HOST: HOST, CONF_COMMUNITY: "public"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_response"}


async def test_user_flow_empty_payload(hass: HomeAssistant):
    with patch(
        "custom_components.giom.config_flow._async_probe_http", return_value={}
    ):
        result = await _submit(hass, {CONF_HOST: HOST, CONF_COMMUNITY: "public"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_response"}


async def test_duplicate_host_aborts(hass: HomeAssistant):
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_COMMUNITY: "public", CONF_USE_SNMP: False},
        unique_id=HOST,
    ).add_to_hass(hass)

    result = await _submit(hass, {CONF_HOST: HOST, CONF_COMMUNITY: "public"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, aioclient_mock, status_3000):
    aioclient_mock.get(f"http://{HOST}/status.xml", text=status_3000)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="GIOM",
        data={CONF_HOST: HOST, CONF_COMMUNITY: "public", CONF_USE_SNMP: False},
        unique_id=HOST,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 60, CONF_USE_SNMP: False, CONF_COMMUNITY: " public "},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_SCAN_INTERVAL: 60,
        CONF_USE_SNMP: False,
        CONF_COMMUNITY: "public",  # stripped
    }
