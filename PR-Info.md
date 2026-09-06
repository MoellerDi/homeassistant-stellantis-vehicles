# PR: Use `ConfigEntry.runtime_data` instead of `hass.data[DOMAIN]`

> **Note:** this file is only a helper for opening the upstream PR. Remove it (drop this last commit) before creating the PR.

## Summary

The per config entry `StellantisVehicles` object is kept in `hass.data[DOMAIN][entry.entry_id]` and popped again on unload. That pattern predates `ConfigEntry.runtime_data`, and it leaves a small window during an unload or reload where a platform can still read `hass.data[DOMAIN]` after the key was popped and raise `KeyError`.

This PR moves the object onto `entry.runtime_data`. Home Assistant owns that slot: it is set during setup and cleared after a successful unload, so the manual bookkeeping (and the race it allowed) goes away. There are no user facing changes, no new entities, and no migrations.

## Change

- `__init__.py`
  - `async_setup_entry`: `config.runtime_data = stellantis` replaces `hass.data.setdefault(DOMAIN, {})` plus `hass.data[DOMAIN][config.entry_id] = stellantis`.
  - Both setup failure paths set `config.runtime_data = None` instead of `hass.data[DOMAIN].pop(...)`, keeping the existing "drop this attempt's state" intent.
  - `async_unload_entry` reads `config.runtime_data`; the manual `hass.data[DOMAIN].pop(config.entry_id)` is removed (Home Assistant resets `runtime_data` after a successful unload).
  - `async_remove_config_entry_device` reads `config.runtime_data`, which is `None` when the entry is not loaded, so the existing `if stellantis is None: return True` guard still holds.
- Platform files (`sensor`, `binary_sensor`, `button`, `number`, `switch`, `text`, `time`, `device_tracker`): `stellantis = entry.runtime_data`, and the now unused `DOMAIN` import is dropped from each `const` import block. Function signatures are untouched.
- `diagnostics.py`: `async_get_config_entry_diagnostics` uses `stellantis = entry.runtime_data`, and the now unused `DOMAIN` import is dropped. The `hass` parameter stays (the diagnostics platform signature requires it).
- `config_flow.py`: the reconfigure step uses `self._get_reconfigure_entry().runtime_data` instead of `self.hass.data[DOMAIN][self._reconfigure_entry_id]`.

After this change `git grep "hass.data\[DOMAIN\]"` returns nothing in the integration.

## Behaviour

| | Before | After |
|---|---|---|
| Normal setup / unload | object stored and popped by hand in `hass.data[DOMAIN]` | object held in `entry.runtime_data`, lifecycle managed by Home Assistant |
| Unload or reload racing a platform read | possible `KeyError` on the popped key | not possible, `runtime_data` is always a valid attribute |
| "No vehicles found" entry, reconfigure, device delete | unchanged | unchanged |

## Scope / non-goals

- Storage location only. No typed `ConfigEntry` alias is introduced and no `async_setup_entry` signatures are annotated.
- No change to control flow, requests made, entity states, or config entry data.

## Note for the `testing` merge (not part of this upstream PR)

This branch only converts files that exist on `upstream/develop`. When it is merged into `testing`, a follow-up commit is required: `services.py` lives only on `testing` and still reads `hass.data[DOMAIN]`. Since `__init__.py` no longer populates it after the merge, it would break. The follow-up does:

- `services.py` `get_coordinator_for_device`: instead of the central `hass.data.get(DOMAIN, {})`, it now uses `hass.config_entries.async_get_entry(entry_id)` with an `entry.domain` and `ConfigEntryState.LOADED` guard, then `entry.runtime_data`.

After that follow-up, `git grep "hass.data\[DOMAIN\]"` is empty across the whole repo, and `python -m py_compile` plus `ruff check --select F,E9` on the changed files are clean.

(`diagnostics.py` was in this list until `upstream/develop` gained it via PR #591; it is now converted as part of this branch.)

## Manual verification (no test suite in this repo)

1. Reload the integration several times in a row; no `KeyError` or stray errors in the log.
2. Remove and re-add the config entry.
3. Run the reconfigure flow (remote commands, OAuth mode, and options paths).
4. Delete a vehicle's device from the UI: allowed for a vehicle no longer on the account, blocked for one still on it.
5. Confirm entity states for all platforms look correct after a fresh start, and that `hassfest` and lint pass.
