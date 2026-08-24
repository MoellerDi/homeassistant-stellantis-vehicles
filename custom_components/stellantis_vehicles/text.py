import logging

from homeassistant.core import HomeAssistant
from homeassistant.components.text import TextEntityDescription
from homeassistant.const import EntityCategory

from .base import ( StellantisBaseText, StellantisPreconditioningProgramEntity )
from .utils import ( preconditioning_days_from_string, preconditioning_days_to_string )

from .const import (
    DOMAIN,
    VEHICLE_TYPE_ELECTRIC,
    VEHICLE_TYPE_HYBRID,
    PRECONDITIONING_PROGRAM_DAYS,
    PRECONDITIONING_PROGRAM_SLOTS
)

_LOGGER = logging.getLogger(__name__)

# Serialize command calls so a bulk action can't flood the Stellantis cloud.
PARALLEL_UPDATES = 1

# Comma separated day names, in any order, or an empty value for no day
DAY_NAMES_PATTERN = "|".join(PRECONDITIONING_PROGRAM_DAYS)
DAYS_PATTERN = f"^$|^({DAY_NAMES_PATTERN})(,({DAY_NAMES_PATTERN}))*$"

async def async_setup_entry(hass:HomeAssistant, entry, async_add_entities) -> None:
    stellantis = hass.data[DOMAIN][entry.entry_id]
    entities = []

    vehicles = await stellantis.get_user_vehicles()

    for vehicle in vehicles:
        coordinator = await stellantis.async_get_coordinator(vehicle)
        if coordinator.vehicle_type in [VEHICLE_TYPE_ELECTRIC, VEHICLE_TYPE_HYBRID]:
            description = TextEntityDescription(
                name = "abrp_token",
                key = "abrp_token",
                translation_key = "abrp_token",
                icon = "mdi:source-branch",
                entity_category = EntityCategory.CONFIG
            )
            entities.extend([StellantisBaseText(coordinator, description)])

            if stellantis.remote_commands:
                for slot in PRECONDITIONING_PROGRAM_SLOTS:
                    description = TextEntityDescription(
                        name = f"program{slot}_days",
                        key = f"program{slot}_days",
                        translation_key = f"program{slot}_days",
                        icon = "mdi:calendar-week",
                        pattern = DAYS_PATTERN
                    )
                    entities.extend([StellantisPreconditioningProgramDays(coordinator, description, slot)])

    async_add_entities(entities)


class StellantisPreconditioningProgramDays(StellantisPreconditioningProgramEntity, StellantisBaseText):
    @property
    def native_value(self):
        """ Native value. """
        return self._coordinator._sensors.get(self._sensor_key, "")

    async def async_set_value(self, value: str):
        """ Set value. """
        days = preconditioning_days_from_string(value)
        program = self.program
        await self.write_program(days, program["hour"], program["minute"], program["on"])
        self._attr_native_value = preconditioning_days_to_string(days)
        self._coordinator._sensors[self._sensor_key] = self._attr_native_value

    def coordinator_update(self):
        if not self.has_program_data:
            return
        self._coordinator._sensors[self._sensor_key] = preconditioning_days_to_string(self.program["day"])
