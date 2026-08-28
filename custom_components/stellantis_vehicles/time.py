import logging

from homeassistant.core import HomeAssistant
from homeassistant.components.time import TimeEntityDescription

from .base import ( StellantisBaseTime, StellantisPreconditioningProgramEntity )
from .utils import preconditioning_program_time

from .const import (
    DOMAIN,
    VEHICLE_TYPE_ELECTRIC,
    VEHICLE_TYPE_HYBRID,
    PRECONDITIONING_PROGRAM_SLOTS
)

_LOGGER = logging.getLogger(__name__)

# Serialize command calls so a bulk action can't flood the Stellantis cloud.
PARALLEL_UPDATES = 1

async def async_setup_entry(hass:HomeAssistant, entry, async_add_entities) -> None:
    stellantis = hass.data[DOMAIN][entry.entry_id]
    entities = []

    vehicles = await stellantis.get_user_vehicles()

    for vehicle in vehicles:
        coordinator = await stellantis.async_get_coordinator(vehicle)
        if coordinator.vehicle_type in [VEHICLE_TYPE_ELECTRIC, VEHICLE_TYPE_HYBRID] and stellantis.remote_commands:
            description = TimeEntityDescription(
                name = "battery_charging_start",
                key = "battery_charging_start",
                translation_key = "battery_charging_start",
                icon = "mdi:battery-clock"
            )
            entities.extend([StellantisBatteryChargingStart(coordinator, description)])

            for slot in PRECONDITIONING_PROGRAM_SLOTS:
                description = TimeEntityDescription(
                    name = f"preconditioning_p{slot}_time",
                    key = f"preconditioning_p{slot}_time",
                    translation_key = f"preconditioning_p{slot}_time",
                    icon = "mdi:calendar-clock"
                )
                entities.extend([StellantisPreconditioningProgramTime(coordinator, description, slot)])

    async_add_entities(entities)


class StellantisBatteryChargingStart(StellantisBaseTime):
    def __init__(self, coordinator, description) -> None:
        super().__init__(coordinator, description)
        self._value_map = ["energies", {"type":"Electric"}, "extension", "electric", "charging", "nextDelayedTime"]
        self._updated_at_map = ["energy", {"type":"Electric"}, "updatedAt"]

    @property
    def available(self):
        return self.available_command

    async def async_set_value(self, value):
        self._attr_native_value = value
        self._coordinator._sensors[self._sensor_key] = value
        await self._coordinator.send_charge_command(self.name, True)
        await self._coordinator.async_refresh()

    def coordinator_update(self):
        if self.value_was_updated():
            label = self._coordinator.get_translation("component.stellantis_vehicles.entity.sensor.mileage.state_attributes.last_updated.name", "last_updated")
            self._attr_extra_state_attributes[label] = self.get_updated_at_from_map(self._updated_at_map)
            self._attr_native_value = self.get_value(self._value_map)


class StellantisPreconditioningProgramTime(StellantisPreconditioningProgramEntity, StellantisBaseTime):
    async def async_set_value(self, value):
        """ Stage the time locally; sent to the vehicle with the send program button. """
        self._coordinator._sensors[self._sensor_key] = value
        self._coordinator.stage_program(self._slot, hour=value.hour, minute=value.minute)
        self._coordinator.async_update_listeners()

    def coordinator_update(self):
        if not self.has_program_data or self.staged_program.keys() & {"hour", "minute"}:
            return
        self._coordinator._sensors[self._sensor_key] = preconditioning_program_time(self.program)
