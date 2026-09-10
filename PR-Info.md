# PR: Keep the sensitive-data log filter bounded, per config entry, and byte-safe

> **Note:** this file is only a helper for opening the upstream PR. Remove it (drop this last commit) before creating the PR.

## Summary

`SensitiveDataFilter` is one shared instance attached to the `base` and `stellantis` module loggers. Two problems made it both leak CPU and miss values it should have masked:

- Over the lifetime of a running Home Assistant process its set of masked values only ever grew, which is the steadily rising `_async_update_data` CPU time reported in issue #414 (the time is spent inside the log filter, not in the HTTP call). `refresh_token_request` and `refresh_mqtt_token_request` registered every rotated oauth or mqtt token through `add_custom_value`; each rotation produces genuinely new strings, so the value list kept growing, the compiled mask pattern kept getting longer, and `re.sub` over every debug record kept getting slower.
- With more than one account configured, `add_entry_values` merged each entry's config into a single flat dict. The keys collide (`oauth`, `mqtt`, `customer_id`), so the last entry to call `save_config` overwrote the other accounts' tokens in the mask, and those tokens were then logged unmasked.
- `_mask_value` only handled `str`, `dict`, `list` and `tuple`. MQTT message payloads are logged as raw `bytes` (`_on_mqtt_message`), so a VIN or token inside the JSON payload passed through completely unmasked, even when it was in the compiled pattern. This gap predates issue #414 and is present on `develop`.

This branch carries three commits:

1. `Attach the sensitive-data log filter once per module logger`: the filter used to be rebuilt and re-added to the module loggers on every `StellantisBase.__init__` and every coordinator init, with nothing ever removing them, so filters stacked up on the loggers. It is now a module-level singleton attached exactly once at import.
2. `Scope the sensitive-data log filter per config entry and bound its value set`: per-entry masked values, a bounded extras FIFO, thread-safe rebinds, and the `save_config` / `async_shutdown` wiring (below).
3. `Mask bytes log payloads and register account VINs per entry`: the `bytes` handling, plus a dedicated per-entry store for the account's VINs so they are not evicted by the bounded FIFO (below).

## Change

`utils.py`, `SensitiveDataFilter`:

- Masked values are kept per `entry_id` in `_entry_values`. `set_entry_values(entry_id, entry_data)` replaces that entry's snapshot wholesale, so a rotated token supersedes the previous one and several accounts no longer overwrite each other. It also collects the VINs that are keys of the per-vehicle config node.
- `_entry_extra` holds, per `entry_id`, the account's VINs and vehicle ids from the live vehicle list (`set_entry_extra_values`). It is separate from `_entry_values` so a later config snapshot cannot drop it, and out of the FIFO so it is never evicted while the entry is loaded.
- `remove_entry_values(entry_id)` forgets an entry (both stores) so the compiled pattern shrinks back and that entry's now invalid tokens stop being masked.
- `add_custom_value` is a bounded FIFO (`CUSTOM_VALUES_LIMIT = 128`) for values seen outside the stored config (the OAuth code and id_token during the auth flow). Anything that must stay masked for an entry's lifetime is in `_entry_values` or `_entry_extra`.
- `_mask_value` now also handles `bytes` and `bytearray`: it masks the decoded UTF-8 text and re-encodes, returning the original object unchanged when nothing matched.
- Every mutating method rebinds its container instead of mutating in place, so the filter can be read from the paho-mqtt network thread while the event loop updates it, without a "dictionary changed size during iteration".
- The anonymize check is `any(self._entry_anonymize.values())`. A per-module logger cannot tell which entry a record came from, so masking is on whenever any loaded entry enabled it.

`stellantis.py`:

- `save_config` is the single point through which oauth or mqtt token rotations and per-vehicle settings reach `self._config`, so it refreshes the filter snapshot for the entry (a no-op until `set_entry` has run, that is during the config flow).
- `update_vehicle_stored_config` and `prune_stored_vehicle_configs` now write `_config["vehicles"]` through `save_config({"vehicles": ...})` instead of a direct assignment, so a per-vehicle config change made after setup also refreshes the snapshot.
- `get_user_vehicles` registers the account's VINs and vehicle ids with `set_entry_extra_values` (or, during the config flow when there is no entry yet, the bounded FIFO).
- `async_shutdown` calls `remove_entry_values` for the entry.
- `refresh_token_request` and `refresh_mqtt_token_request` persist the new config before logging the raw response, so the freshly issued tokens are masked through the refreshed snapshot instead of a hand-written `add_custom_value` per rotation. `refresh_mqtt_token_request` keeps one targeted `add_custom_value` in the "no access_token in response" branch, where there is no config to persist.

## Behaviour

| | Before | After |
|---|---|---|
| Long-running process, periodic token refresh | masked value set grows without bound, log filter CPU per record keeps rising | value set is bounded by the loaded entries, constant over time |
| Two or more accounts | last `save_config` wins, other accounts' tokens logged unmasked | each entry's values kept separately, all masked |
| Entry unload or reload | filter kept the removed entry's tokens forever | entry's values dropped, pattern shrinks |
| `anonymize_logs` differing between entries | effectively "last writer wins" | masking on if any loaded entry enabled it |
| VIN or token inside an MQTT payload (`bytes`) | never masked | masked (payload stays `bytes`) |
| VIN of a vehicle with no stored per-vehicle config | only in the FIFO, evicted after roughly a day of token rotations, then reappears unmasked | in `_entry_extra`, masked for the entry's whole lifetime |
| Single account, anonymize on, normal run | works, but degrades over time | works, stable |

## Scope and non-goals

- No change to which requests are made, to entity states, or to config entry data.
- The filter still only covers the `base` and `stellantis` module loggers, not `config_flow`, `otp`, or `utils`. Widening its reach is out of scope here.
- No new config option. The existing `anonymize_logs` toggle is untouched; this change makes leaving it on cheap enough that it no longer needs to be worked around.

## Manual verification (no test suite in this repo)

1. Enable `custom_components.stellantis_vehicles: debug`, keep `anonymize_logs` on, reload the integration. Entities populate, and tokens and VIN appear masked (first five characters kept, then `###`) in the log.
2. Wait for an MQTT `state` message. The VIN inside the `b'{"vin":"..."}'` payload is masked.
3. Let the integration run through at least one oauth and one mqtt token refresh. The freshly issued tokens are masked in the `_log_http_exchange` line, and the `_async_update_data` duration does not climb over successive updates.
4. With two accounts configured, both accounts' tokens and VINs are masked in the log.
5. Reload one entry, then unload it. No stray errors, and after unload that entry's former token no longer appears (masked or not) in new log lines.
6. `hassfest` passes.
