"""Sensor entities for the GIOM 3000 weather station."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    CONCENTRATION_GRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    EntityCategory,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COMPASS_POINTS, DEFAULT_MODEL, DOMAIN, MANUFACTURER
from .coordinator import GiomConfigEntry, GiomCoordinator, url_host


@dataclass(frozen=True, kw_only=True)
class GiomSensorDescription(SensorEntityDescription):
    """Describes a GIOM sensor."""

    value_fn: Callable[[dict[str, Any]], Any] = lambda data: None
    source_key: str


def _plain(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda data: data.get(key)


SENSORS: tuple[GiomSensorDescription, ...] = (
    GiomSensorDescription(
        key="temperature",
        source_key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_plain("temperature"),
    ),
    GiomSensorDescription(
        key="dewpoint",
        source_key="dewpoint",
        translation_key="dewpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_plain("dewpoint"),
    ),
    GiomSensorDescription(
        key="windchill",
        source_key="windchill",
        translation_key="windchill",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_plain("windchill"),
    ),
    GiomSensorDescription(
        key="humidity",
        source_key="relhumidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_plain("relhumidity"),
    ),
    GiomSensorDescription(
        key="absolute_humidity",
        source_key="abshumidity",
        translation_key="absolute_humidity",
        native_unit_of_measurement=CONCENTRATION_GRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=_plain("abshumidity"),
    ),
    # The station recomputes this for the altitude configured in its own web
    # UI, so it is a relative (QNH) figure, not what the barometer measured.
    GiomSensorDescription(
        key="pressure",
        source_key="pressure",
        translation_key="pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_plain("pressure"),
    ),
    GiomSensorDescription(
        key="wind_speed",
        source_key="windspeed",
        translation_key="wind_speed",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_plain("windspeed"),
    ),
    # Maximum since the previous read, not a rolling window.
    GiomSensorDescription(
        key="wind_gust",
        source_key="windgust",
        translation_key="wind_gust",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_plain("windgust"),
    ),
    GiomSensorDescription(
        key="wind_bearing",
        source_key="wind_bearing",
        translation_key="wind_bearing",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:compass-outline",
        value_fn=_plain("wind_bearing"),
    ),
    GiomSensorDescription(
        key="wind_direction",
        source_key="wind_direction",
        translation_key="wind_direction",
        device_class=SensorDeviceClass.ENUM,
        options=list(COMPASS_POINTS),
        icon="mdi:compass-rose",
        value_fn=_plain("wind_direction"),
    ),
    GiomSensorDescription(
        key="beaufort",
        source_key="beaufort",
        translation_key="beaufort",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
        value_fn=_plain("beaufort"),
    ),
    # Derived from the measured pressure against a standard atmosphere, so it
    # drifts with the weather. Not the altitude configured in the station.
    GiomSensorDescription(
        key="barometric_altitude",
        source_key="baraltitude",
        translation_key="barometric_altitude",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_plain("baraltitude"),
    ),
    GiomSensorDescription(
        key="system_temperature",
        source_key="systemp",
        translation_key="system_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_plain("systemp"),
    ),
    # Reported only by the IQWS-4000 / GIOM 4000NG. Field names come from the
    # manufacturer's manual and have not been checked against real hardware -
    # on a GIOM 3000 these keys never appear, so no entity is created.
    GiomSensorDescription(
        key="irradiance",
        source_key="spower",
        translation_key="irradiance",
        device_class=SensorDeviceClass.IRRADIANCE,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_plain("spower"),
    ),
    GiomSensorDescription(
        key="uv_factor",
        source_key="uf",
        translation_key="uv_factor",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sun-wireless",
        value_fn=_plain("uf"),
    ),
    GiomSensorDescription(
        key="lightning_distance",
        source_key="sdist",
        translation_key="lightning_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash",
        value_fn=_plain("sdist"),
    ),
    GiomSensorDescription(
        key="lightning_energy",
        source_key="senr",
        translation_key="lightning_energy",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash-alert",
        value_fn=_plain("senr"),
    ),
    # SNMP-only below. status.xml does not carry these.
    GiomSensorDescription(
        key="wind_speed_average",
        source_key="windspeed_average",
        translation_key="wind_speed_average",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_plain("windspeed_average"),
    ),
    GiomSensorDescription(
        key="pressure_absolute",
        source_key="pressure_absolute",
        translation_key="pressure_absolute",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_plain("pressure_absolute"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GiomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create entities for whatever this particular station reports.

    Models differ in what they expose - the 3000AE has no light or lightning
    sensors, for instance - so entities are created only for keys that showed
    up in the first poll.
    """
    coordinator = entry.runtime_data
    available = set(coordinator.data)

    async_add_entities(
        GiomSensor(coordinator, description)
        for description in SENSORS
        if description.source_key in available
    )


class GiomSensor(CoordinatorEntity[GiomCoordinator], SensorEntity):
    """A single reading from the station."""

    _attr_has_entity_name = True
    entity_description: GiomSensorDescription

    def __init__(
        self, coordinator: GiomCoordinator, description: GiomSensorDescription
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=coordinator.data.get("devname", DEFAULT_MODEL),
            name=entry.title,
            configuration_url=f"http://{url_host(coordinator.host)}/",
        )

    @property
    def native_value(self) -> Any:
        """Return the current reading."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Report unavailable when the value drops out of the payload.

        SNMP-backed readings can vanish on their own while HTTP keeps working.
        """
        return (
            super().available
            and self.entity_description.value_fn(self.coordinator.data) is not None
        )
