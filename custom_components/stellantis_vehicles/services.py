import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .utils import preconditioning_days_from_string

from .const import (
    DOMAIN,
    PRECONDITIONING_PROGRAM_SLOTS,
    SERVICE_SET_PRECONDITIONING_PROGRAM
)

_LOGGER = logging.getLogger(__name__)

ATTR_SLOT = "slot"
ATTR_DAYS = "days"
ATTR_TIME = "time"
ATTR_ENABLED = "enabled"

SET_PRECONDITIONING_PROGRAM_SCHEMA = vol.Schema({
    vol.Required(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
    vol.Required(ATTR_SLOT): vol.All(vol.Coerce(int), vol.In(PRECONDITIONING_PROGRAM_SLOTS)),
    vol.Optional(ATTR_DAYS): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_TIME): cv.time,
    vol.Optional(ATTR_ENABLED): cv.boolean
})


def get_coordinator_for_device(hass: HomeAssistant, device):
    """ Get the coordinator of the Stellantis vehicle behind a device entry. """
    if not device:
        return None
    domain_data = hass.data.get(DOMAIN, {})
    for identifier in device.identifiers:
        # A device can carry identifiers from other integrations too, and some of
        # those are not the plain (domain, id) pair, so index instead of unpack.
        if identifier[0] != DOMAIN:
            continue
        vin = identifier[1]
        for entry_id in device.config_entries:
            stellantis = domain_data.get(entry_id)
            if stellantis and (coordinator := stellantis.async_get_coordinator_by_vin(vin)):
                return coordinator
    return None


def get_coordinators(hass: HomeAssistant, device_ids):
    """ Get the coordinators of the vehicles targeted by a service call. """
    registry = dr.async_get(hass)
    coordinators = []
    for device_id in device_ids:
        coordinator = get_coordinator_for_device(hass, registry.async_get(device_id))
        if not coordinator:
            raise ServiceValidationError(
                translation_domain = DOMAIN,
                translation_key = "device_not_found",
                translation_placeholders = {"device_id": device_id}
            )
        coordinators.append(coordinator)
    return coordinators


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """ Register the integration services. """

    async def async_set_preconditioning_program(call: ServiceCall) -> None:
        """ Write one preconditioning program slot of one or more vehicles. """
        slot = call.data[ATTR_SLOT]
        if not any(attr in call.data for attr in (ATTR_DAYS, ATTR_TIME, ATTR_ENABLED)):
            raise ServiceValidationError(
                translation_domain = DOMAIN,
                translation_key = "preconditioning_program_no_changes"
            )
        for coordinator in get_coordinators(hass, call.data[ATTR_DEVICE_ID]):
            # This service works on the vehicle values only; UI staging is a
            # separate, UI-only workflow and is left untouched here.
            program = coordinator.get_programs()[f"program{slot}"]
            day = program["day"]
            hour = program["hour"]
            minute = program["minute"]
            on = program["on"]
            if ATTR_DAYS in call.data:
                day = preconditioning_days_from_string(",".join(call.data[ATTR_DAYS]))
            if ATTR_TIME in call.data:
                hour = call.data[ATTR_TIME].hour
                minute = call.data[ATTR_TIME].minute
            if ATTR_ENABLED in call.data:
                on = call.data[ATTR_ENABLED]
            name = coordinator.get_translation(f"component.{DOMAIN}.entity.switch.program{slot}_enabled.name", f"program{slot}_enabled")
            await coordinator.send_preconditioning_program(name, slot, day, hour, minute, on)
            await coordinator.async_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_SET_PRECONDITIONING_PROGRAM):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_PRECONDITIONING_PROGRAM,
            async_set_preconditioning_program,
            schema = SET_PRECONDITIONING_PROGRAM_SCHEMA
        )
