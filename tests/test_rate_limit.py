"""Regression tests for @rate_limit scoping its call budget per instance.

The `calls` deque used to live in the decorator's closure, shared by every
instance of the decorated method: send_wakeup_command's "6 per 20 min" budget
was shared across every vehicle of every account in the process, and
get_otp_code / refresh_oauth_token_request's budgets were shared across
unrelated Stellantis accounts. The fix tracks the deque per `self`
(WeakKeyDictionary) instead.
"""
from unittest.mock import patch

import pytest

from custom_components.stellantis_vehicles.exceptions import RateLimitException
from custom_components.stellantis_vehicles.utils import rate_limit


class Vehicle:
    def __init__(self, name):
        self.name = name
        self.calls = 0

    @rate_limit(2, 3600)
    async def send(self):
        self.calls += 1
        return self.name


@pytest.mark.asyncio
async def test_rate_limit_allows_up_to_the_limit():
    vehicle = Vehicle("A")

    assert await vehicle.send() == "A"
    assert await vehicle.send() == "A"
    assert vehicle.calls == 2


@pytest.mark.asyncio
async def test_rate_limit_blocks_once_the_limit_is_exceeded():
    vehicle = Vehicle("A")
    await vehicle.send()
    await vehicle.send()

    with pytest.raises(RateLimitException):
        await vehicle.send()

    assert vehicle.calls == 2


@pytest.mark.asyncio
async def test_rate_limit_is_scoped_per_instance():
    """Regression test: two instances of the same decorated method must not
    share one budget."""
    vehicle_a = Vehicle("A")
    vehicle_b = Vehicle("B")

    await vehicle_a.send()
    await vehicle_a.send()
    with pytest.raises(RateLimitException):
        await vehicle_a.send()

    # B's budget must be untouched by A having exhausted its own.
    assert await vehicle_b.send() == "B"
    assert await vehicle_b.send() == "B"
    with pytest.raises(RateLimitException):
        await vehicle_b.send()


@pytest.mark.asyncio
async def test_rate_limit_resets_after_the_window_elapses():
    vehicle = Vehicle("A")

    with patch("custom_components.stellantis_vehicles.utils.monotonic") as mock_monotonic:
        mock_monotonic.return_value = 1000.0
        await vehicle.send()
        await vehicle.send()

        mock_monotonic.return_value = 1000.0 + 3600 - 0.001
        with pytest.raises(RateLimitException):
            await vehicle.send()

        # At exactly `every` seconds, the oldest call falls outside the
        # window and is pruned before the limit check.
        mock_monotonic.return_value = 1000.0 + 3600
        assert await vehicle.send() == "A"


@pytest.mark.asyncio
async def test_rate_limit_does_not_pin_instances_in_memory():
    """The per-instance deque must not keep an otherwise-unreferenced instance
    (e.g. a removed vehicle's coordinator) alive."""
    import gc
    import weakref

    vehicle = Vehicle("A")
    await vehicle.send()
    ref = weakref.ref(vehicle)

    del vehicle
    gc.collect()

    assert ref() is None
