"""Regression tests: send_charge_command must not crash when
time_battery_charging_start is unset.

current_hour.hour/.minute used to raise an unhandled AttributeError when
that sensor was still None (e.g. before the vehicle ever reported
nextDelayedTime and nothing was restored/set manually). That crashed the
whole coordinator refresh when reached from the automatic charge-limit
stop, and gave the charge_stop/charge_start buttons a raw traceback
instead of a clear error.
"""
from datetime import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stellantis_vehicles.base import StellantisVehicleCoordinator
from custom_components.stellantis_vehicles.const import DOMAIN, INTEGRATION_VERSION

VEHICLE = {
    "vehicle_id": "abcdef0123456789",
    "vin": "VR7BCTEST00000001",
    "type": "Electric",
}


@pytest.fixture
def stellantis_client() -> MagicMock:
    """A ``StellantisVehicles`` stand-in for direct coordinator construction."""
    client = MagicMock()
    client.send_mqtt_message = AsyncMock(return_value="action-id")
    return client


@pytest.fixture
def coordinator(
    hass: HomeAssistant, stellantis_client: MagicMock
) -> StellantisVehicleCoordinator:
    """A coordinator wired to the fixture client, with no charging start time."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=INTEGRATION_VERSION,
        minor_version=1,
        data={"vehicles": {}},
    )
    entry.add_to_hass(hass)
    return StellantisVehicleCoordinator(
        hass, {}, dict(VEHICLE), stellantis_client, {}, entry
    )


async def test_send_charge_command_raises_when_start_time_missing(
    coordinator: StellantisVehicleCoordinator, stellantis_client: MagicMock
) -> None:
    """A missing charging start time raises a clean, translated error."""
    assert "time_battery_charging_start" not in coordinator._sensors

    with pytest.raises(ServiceValidationError) as excinfo:
        await coordinator.send_charge_command("Charge stop", False, "delayed")

    assert excinfo.value.translation_key == "charge_command_time_missing"
    stellantis_client.send_mqtt_message.assert_not_awaited()


async def test_send_charge_command_sends_when_start_time_present(
    coordinator: StellantisVehicleCoordinator, stellantis_client: MagicMock
) -> None:
    """The known-good path (a time is set) still sends the command as before."""
    coordinator._sensors["time_battery_charging_start"] = time(8, 30)

    await coordinator.send_charge_command("Charge start", False, "immediate")

    stellantis_client.send_mqtt_message.assert_awaited_once()
    _service, message, _vehicle = stellantis_client.send_mqtt_message.await_args.args
    assert message["program"] == {"hour": 8, "minute": 30}
    assert message["type"] == "immediate"


def _prime_charge_limit_reached(coordinator: StellantisVehicleCoordinator) -> None:
    """Set every sensor _auto_stop_charge_at_limit checks before the time guard."""
    coordinator._sensors.update(
        {
            "battery_charging": "InProgress",
            "battery_charging_limit": "Full",
            "switch_battery_charging_limit": True,
            "number_battery_charging_limit": 80,
            "battery": 85,
        }
    )


async def test_auto_stop_skips_instead_of_crashing_when_start_time_missing(
    coordinator: StellantisVehicleCoordinator, stellantis_client: MagicMock
) -> None:
    """Reaching the charge limit with no known start time must not blow up
    the coordinator refresh; it should just retry on a later update."""
    _prime_charge_limit_reached(coordinator)
    assert "time_battery_charging_start" not in coordinator._sensors

    await coordinator._auto_stop_charge_at_limit()

    stellantis_client.send_mqtt_message.assert_not_awaited()
    # Not marked as sent, so the next update retries once a time is known.
    assert coordinator._manage_charge_limit_sent is False


async def test_auto_stop_sends_when_start_time_present(
    coordinator: StellantisVehicleCoordinator, stellantis_client: MagicMock
) -> None:
    """Unchanged behaviour: the auto-stop still fires once a time is known."""
    _prime_charge_limit_reached(coordinator)
    coordinator._sensors["time_battery_charging_start"] = time(22, 0)

    await coordinator._auto_stop_charge_at_limit()

    stellantis_client.send_mqtt_message.assert_awaited_once()
    assert coordinator._manage_charge_limit_sent is True
