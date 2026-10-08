"""Setup, entity creation and unload against a mocked station."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.giom.const import CONF_COMMUNITY, CONF_USE_SNMP, DOMAIN

HOST = "192.168.0.100"


async def _setup(hass: HomeAssistant, aioclient_mock, payload: str) -> MockConfigEntry:
    aioclient_mock.get(f"http://{HOST}/status.xml", text=payload)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="GIOM",
        data={CONF_HOST: HOST, CONF_COMMUNITY: "public", CONF_USE_SNMP: False},
        unique_id=HOST,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_creates_entities_from_payload(
    hass: HomeAssistant, aioclient_mock, status_3000
):
    entry = await _setup(hass, aioclient_mock, status_3000)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.giom_temperature").state == "30.6"
    assert hass.states.get("sensor.giom_pressure").state == "1011.7"
    assert hass.states.get("sensor.giom_wind_direction").state == "ene"
    assert hass.states.get("sensor.giom_beaufort_force").state == "2"

    # Wind bearing renders as a compass card in the frontend.
    bearing = hass.states.get("sensor.giom_wind_bearing")
    assert bearing.state == "67.5"
    assert bearing.attributes["device_class"] == "wind_direction"
    assert bearing.attributes["state_class"] == "measurement_angle"

    # 3000-series payload carries no light or lightning readings, so those
    # entities must not exist at all - not even as unavailable.
    assert hass.states.get("sensor.giom_sunlight_intensity") is None
    assert hass.states.get("sensor.giom_illuminance") is None
    assert hass.states.get("sensor.giom_lightning_distance") is None

    # SNMP off: the SNMP-only sensors must not exist either.
    assert hass.states.get("sensor.giom_average_wind_speed") is None


async def test_setup_creates_4000_entities(
    hass: HomeAssistant, aioclient_mock, status_4000
):
    await _setup(hass, aioclient_mock, status_4000)

    assert hass.states.get("sensor.giom_sunlight_intensity").state == "512.3"
    assert hass.states.get("sensor.giom_uv_factor").state == "3.2"
    assert hass.states.get("sensor.giom_lightning_energy").state == "8541.0"

    illuminance = hass.states.get("sensor.giom_illuminance")
    assert illuminance.state == "1018.0"
    assert illuminance.attributes["device_class"] == "illuminance"
    assert illuminance.attributes["unit_of_measurement"] == "lx"

    # Event-like readings: no state_class, so no long-term statistics.
    lightning = hass.states.get("sensor.giom_lightning_distance")
    assert lightning.state == "12.0"
    assert "state_class" not in lightning.attributes


async def test_unique_ids_are_stable(
    hass: HomeAssistant, aioclient_mock, status_3000
):
    entry = await _setup(hass, aioclient_mock, status_3000)
    registry = er.async_get(hass)
    entity = registry.async_get("sensor.giom_temperature")
    assert entity is not None
    assert entity.unique_id == f"{entry.entry_id}_temperature"


async def test_unload(hass: HomeAssistant, aioclient_mock, status_3000):
    entry = await _setup(hass, aioclient_mock, status_3000)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get("sensor.giom_temperature").state == "unavailable"
