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
                        name = f"preconditioning_p{slot}_days",
                        key = f"preconditioning_p{slot}_days",
                        translation_key = f"preconditioning_p{slot}_days",
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
        """ Stage the days locally; sent to the vehicle with the send program button. """
        days = preconditioning_days_from_string(value)
        self._coordinator._sensors[self._sensor_key] = preconditioning_days_to_string(days)
        self._coordinator.stage_program(self._slot, day=days)
        self._coordinator.async_update_listeners()

    def coordinator_update(self):
        if not self.has_program_data or "day" in self.staged_program:
            return
        self._coordinator._sensors[self._sensor_key] = preconditioning_days_to_string(self.program["day"])
