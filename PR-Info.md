# PR: Rename refresh_token_request to refresh_oauth_token_request

> **Note:** this file is only a helper for opening the upstream PR. Remove it (drop this last commit) before creating the PR.

## Problem

`StellantisOauth.refresh_token_request` refreshes the OAuth access token, but its name does not say so. The surrounding code already uses the `oauth` qualifier consistently (`scheduled_oauth_token_refresh`, `reset_scheduled_oauth_token`, `_oauth_token_scheduled`), so the bare `refresh_token_request` reads as if it refreshes some generic "token request" rather than the OAuth token pair.

## Change

- Rename the method `refresh_token_request` to `refresh_oauth_token_request` in `custom_components/stellantis_vehicles/stellantis.py`.
- Update both call sites in `scheduled_oauth_token_refresh`.

Pure rename: no behaviour change, no signature change, no decorator change (`@log_call`, `@rate_limit(6, 1800)` stay as they are).

## Scope / non-goals

- No other identifiers renamed.
- No translation strings, no config, no manifest change.

## Rebase note

Single file, three lines. Overlaps with any branch that adds a caller of `refresh_token_request` (for example a 401-retry path in `make_http_request`); such a branch needs the new name after this lands.

## Manual verification (no test suite in this repo)

1. Reload the integration against a running Home Assistant instance.
2. Wait for a scheduled OAuth token refresh (or force one by shortening `expires_in`), confirm the `DEBUG "Next oauth token refresh scheduled for ..."` line still appears and entities stay available.
3. Grep the loaded component for `refresh_token_request`, expect no matches.
