# PR: VIN-based brand/model fallback for device info

> **Note:** this file is only a helper for opening the upstream PR. Remove it (drop this last commit) before creating the PR.

## Summary

The Stellantis connected-car API never returns a human-readable vehicle model name — only VIN, `motorization` (engine type) and `brand`. `StellantisBaseEntity.device_info` (in `base.py`) worked around this by showing the translated engine type + VIN as `model`, and the user's selected mobile app (`FIELD_MOBILE_APP`) as `manufacturer`, discarding the API's own `brand` field entirely.

There is no public decode table for Stellantis' VDS (VIN positions 4-8), so a real model name can't be derived automatically. Instead, this PR adds a small manually-curated VIN lookup that improves `manufacturer` immediately (using data the API already sends) and lets `model` be filled in as users confirm their own vehicle's VIN prefix against their registration document.

## Change

### 1. New `vin.py`

- `WMI_BRANDS`: VIN positions 1-3 (World Manufacturer Identifier) → brand, seeded with known Stellantis-brand codes. Used only as a fallback when the API's own `brand` field is unavailable.
- `VIN_MODELS`: VIN positions 1-8 (WMI + VDS) → model name. Empty until a user confirms an entry; a few were seeded from owners who stated their model in public upstream issues, cross-checked against the free NHTSA vPIC API where possible (NHTSA has no data for EU-market Peugeot/Citroën/Opel/DS VINs — expected, not a bug).
- `get_brand_from_vin(vin)` / `get_model_from_vin(vin)` helpers.

### 2. `stellantis.py`: capture the API's `brand` field

`vehicle_data` (built from `_embedded.vehicles` in `get_user_vehicles`) now keeps `vehicle.get("brand")` instead of discarding it.

### 3. `base.py`: `device_info` fallback chain

- `manufacturer`: `vehicle["brand"]` (from the API) → `get_brand_from_vin(vin)` → `FIELD_MOBILE_APP` (previous behaviour), in that order.
- `model`: `get_model_from_vin(vin)` if a confirmed entry exists, else the previous `"{engine label} - {vin}"` display.

## Behaviour

- `identifiers` in `device_info` are unchanged, so no new device is created — existing devices get `manufacturer`/`model` updated in place the next time entities are (re-)added (integration reload or HA restart), per how Home Assistant's device registry picks up `device_info` changes.
- Vehicles with no matching `VIN_MODELS` entry, or whose API response has no `brand`, behave exactly as before.

## Scope / non-goals

- No automatic full VIN decoding — Stellantis doesn't publish the VDS table, so `VIN_MODELS` only grows from confirmed entries (registration document, or independently corroborated public reports).
- Doesn't touch `config_flow.py` or `FIELD_MOBILE_APP` itself — that fallback stays as the last resort.

## Manual verification (no test suite in this repo)

- `python -m py_compile` on all three touched/added files.
- Against a running instance: reload the integration and confirm the device card shows the expected `manufacturer` (from the API's `brand` field) and, for vehicles matching a `VIN_MODELS` entry, the expected `model` — with no duplicate device created.
