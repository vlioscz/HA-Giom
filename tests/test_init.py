"""Setup, entity creation and unload against a mocked station."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.giom.const import CONF_COMMUNITY, CONF_USE_SNMP, DOMAIN

HOST = "192.168.0.100"


async def _setup(
    hass: HomeAssistant,
    aioclient_mock,
    payload: str,
    data_payload: str | None = None,
) -> MockConfigEntry:
    aioclient_mock.get(f"http://{HOST}/status.xml", text=payload)
    # A 3000-series station has no data.xml endpoint at all.
    if data_payload is None:
        aioclient_mock.get(f"http://{HOST}/data.xml", status=404)
    else:
        aioclient_mock.get(f"http://{HOST}/data.xml", text=data_payload)
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

    # SNMP off and no data.xml: none of their sensors must exist either.
    assert hass.states.get("sensor.giom_average_wind_speed") is None
    assert hass.states.get("sensor.giom_light_sensor_status") is None


async def test_setup_creates_4000_entities(
    hass: HomeAssistant, aioclient_mock, status_4000, data_4000
):
    await _setup(hass, aioclient_mock, status_4000, data_payload=data_4000)

    assert hass.states.get("sensor.giom_sunlight_intensity").state == "512.3"
    assert hass.states.get("sensor.giom_uv_factor").state == "3.2"
    assert hass.states.get("sensor.giom_lightning_energy").state == "8541.0"

    # Illuminance mirrors the station web UI: spower x 126.7, two decimals.
    illuminance = hass.states.get("sensor.giom_illuminance")
    assert illuminance.state == "64908.41"
    assert illuminance.attributes["device_class"] == "illuminance"
    assert illuminance.attributes["unit_of_measurement"] == "lx"

    # Event-like readings: no state_class, so no long-term statistics.
    lightning = hass.states.get("sensor.giom_lightning_distance")
    assert lightning.state == "12.0"
    assert "state_class" not in lightning.attributes

    # The daily strike counter comes from status.xml's lpd field.
    assert hass.states.get("sensor.giom_lightning_strikes_per_day").state == "1018.0"

    # data.xml extras: average wind speed over HTTP (SNMP is off here) and
    # the four sensor-health flags. Home Assistant's metric unit system
    # presents wind speeds in km/h, so 0.6 m/s reads back as 2.16.
    assert hass.states.get("sensor.giom_average_wind_speed").state == "2.16"
    assert hass.states.get("sensor.giom_pressure_sensor_status").state == "OK"
    assert (
        hass.states.get("sensor.giom_temperature_humidity_sensor_status").state
        == "OK"
    )
    assert hass.states.get("sensor.giom_light_sensor_status").state == "OK"
    assert hass.states.get("sensor.giom_lightning_sensor_status").state == "OK"


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
