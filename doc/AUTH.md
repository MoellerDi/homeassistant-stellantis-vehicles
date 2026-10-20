# Authentication & token lifecycle

This integration juggles three independent credential domains: the account **OAuth** session, the device-bound **OTP** (one-time password) second factor, and the **MQTT** virtual-key token used for remote commands. This document explains how each one is obtained, stored, refreshed and how they depend on each other. Code references point at `stellantis.py` unless noted otherwise.

## 1. Overview

| Domain | What it authenticates | Lifetime | Stored under |
|---|---|---|---|
| OAuth | The Stellantis account (login/password) against the CVS API (vehicle list, status, trips, maintenance) | Short-lived access token + longer-lived refresh token | `config["oauth"]` |
| OTP | This specific device, via the InWebo "MAC" protocol (SMS + PIN activation) | Persistent device credential, not itself expiring | Pickle file `.storage/stellantis_vehicles/{customer_id}_otp.pickle` |
| MQTT | The "virtual key" used to connect to the RemoteServices MQTT broker and send/receive remote commands | Short-lived access token + refresh token (refresh token itself expires after a few days) | `config["mqtt"]` |

The OTP device credential is the root of trust for MQTT: whenever the MQTT refresh token has expired, a fresh MQTT token can only be minted by generating a new OTP code and using it as the password in an OAuth "password" grant. The OAuth session is independent of the other two - it is only needed for the plain HTTPS CVS API calls (`CAR_API_*`, `GET_USER_INFO_URL`, ...).

## 2. Initial setup (config flow)

Driven from `config_flow.py`, in order:

1. **OAuth code** - `StellantisOauth.get_oauth_code(email, password)` posts the account credentials to `OAUTH_CODE_URL` (a small proxy service, not Stellantis directly) together with the app's `get_oauth_url()`, and gets back an authorization `code`.
2. **OAuth tokens** - `get_access_token()` exchanges that code at `OAUTH_TOKEN_URL` (`grant_type=authorization_code`) for `access_token` / `refresh_token` / `expires_in`, using the app's Basic auth (`basic_token`, built from `client_id:client_secret` in `set_mobile_app()`). Result is stored via `save_config({"oauth": ...})`.
3. **User info** - `get_user_info()` reads the account's `customer_id` from `GET_USER_INFO_URL`, used from here on as the OTP file name and as a placeholder in MQTT topics.
4. **OTP activation** - `get_otp_sms()` asks Stellantis to send an activation SMS; the user then supplies the SMS code and a PIN they choose. `new_otp(sms_code, pin_code)` creates an `Otp` instance (`otp/otp.py`), runs the InWebo `activation_start()` / `activation_finalyze()` exchange directly against `https://otp.mpsa.com/iwws/MAC` (not a Stellantis endpoint), and persists the resulting device keys to the pickle file via `save_otp()`. This step only ever runs once per install, at config-flow time.
5. **First MQTT token** - `get_mqtt_access_token()` derives an OTP code from the freshly-activated device (`get_otp_code()`) and exchanges it for the first `mqtt.access_token` / `refresh_token` at `GET_MQTT_TOKEN_URL` (`grant_type=password`, `password=<otp code>`).

From here on, `StellantisVehicles.scheduled_tokens_refresh()` takes over and keeps both the OAuth and MQTT tokens alive for as long as the config entry lives.

## 3. OAuth access/refresh token

* **Where it's used**: `Authorization: Bearer {#oauth|access_token#}` on every CVS API call (`CAR_API_HEADERS`, `GET_OTP_HEADERS`).
* **Proactive refresh**: `scheduled_oauth_token_refresh()` reads `oauth["expires_in"]` (an ISO timestamp) and schedules itself, via `async_track_point_in_time`, 5 minutes before that expiry. When it fires, `refresh_oauth_token_request()` posts `grant_type=refresh_token` with the stored `oauth|refresh_token` to `OAUTH_TOKEN_URL` and stores the new `access_token` / `refresh_token` / `expires_in`.
* **Reactive refresh**: any HTTP call going through `make_http_request()` that comes back `401` triggers one immediate `refresh_oauth_token_request()` and a single retry with the new token (`_retried=True` guards against a refresh loop). This covers the short window right after an out-of-band rotation where the cached token is briefly stale.
* **Rate limit**: `refresh_oauth_token_request()` is capped at 6 calls / 30 minutes (`@rate_limit`); hitting it reschedules the next attempt 30 minutes out instead of raising.
* **Terminal failure**: a `400 invalid_grant` response (dead refresh token) is raised as `ConfigEntryAuthFailed`, which Home Assistant turns into a reauth flow - the user has to log in again from step 1.

## 4. OTP device credential

The OTP object is not a token in the OAuth sense - it's a small piece of persistent client state (RSA/AES key material from the InWebo protocol) that lets the integration act as "the same phone" indefinitely, without asking the user for another SMS.

* **Storage**: pickled per `customer_id` at `.storage/stellantis_vehicles/{customer_id}_otp.pickle` (`OTP_FILENAME`), loaded lazily into `self.otp` the first time it's needed (`get_otp_code()`).
* **Generating a code**: `get_otp_code()` calls `Otp.get_otp_code()`, which runs a short `activation_start()` / `activation_finalyze()` round-trip against the InWebo server using the stored device keys (no SMS/PIN needed at this point) and derives a fresh one-time code from the resulting session material. The updated `Otp` state is re-pickled after every call, since the protocol advances a counter/challenge each time.
* **Rate limit**: capped at 6 calls / 24h (`@rate_limit`) - this mirrors an InWebo-side limit, not something Stellantis or this integration imposes voluntarily.
* **What it's used for**: exclusively as the `password` in the `grant_type=password` request to `GET_MQTT_TOKEN_URL` (both for the very first MQTT token and whenever the MQTT refresh token has expired - see below). It never touches the CVS/OAuth API.
* **Failure modes** - two distinct exception types come out of this, and they're handled differently by their callers:
  * A missing pickle file, or `Otp.get_otp_code()` returning `None`, is raised by `StellantisOauth.get_otp_code()` itself as `ConfigEntryAuthFailed`.
  * A protocol-level problem inside the InWebo exchange (bad/unexpected server response during `activation_start()`/`activation_finalyze()`) surfaces from the `Otp` object as `ConfigException` (`otp/otp.py`).
  * `scheduled_mqtt_token_refresh()` only catches `ConfigException`: it resets the retry counter, calls `disable_remote_commands()` and sends a `reconfigure_otp` persistent notification, so the user knows to run the config flow's reconfigure step (new SMS + PIN). A `ConfigEntryAuthFailed` from the missing-file path is **not** caught there, so it propagates out of the scheduled job uncaught (Home Assistant logs it as a job error) - crucially, execution never reaches the reschedule call at the bottom of `scheduled_mqtt_token_refresh()`, so the periodic MQTT-token refresh loop simply stops, with no user-facing notification, until the entry is reloaded or reconfigured.

## 5. MQTT access/refresh token

* **Where it's used**: as the MQTT username/password pair (`username_pw_set("IMA_OAUTH_ACCESS_TOKEN", mqtt["access_token"])`) when connecting to the RemoteServices broker (`connect_mqtt()`), and inlined into every published command payload (`send_mqtt_message()`).
* **Proactive refresh**: `scheduled_mqtt_token_refresh()` reads `mqtt["expires_in"]` and reschedules itself 3 minutes before expiry (only while `remote_commands` is enabled - it's a no-op otherwise).
* **Two refresh paths inside `refresh_mqtt_token_request()`**:
  * **Refresh-token path (cheap, no OTP)**: if `mqtt["refresh_token_expires_at"]` is still in the future, the request uses `grant_type=refresh_token` with the stored `mqtt|refresh_token` (`MQTT_REFRESH_TOKEN_JSON_DATA`). No OTP code is generated for this path, so it doesn't touch the 6/24h OTP rate limit.
  * **Password-grant path (needs a fresh OTP code)**: once the MQTT refresh token itself has expired (`refresh_token_expires_at` unset or in the past - it's given a fixed TTL of `MQTT_REFRESH_TOKEN_TTL` = 3 days from the moment it was issued), a new OTP code is generated and exchanged via `grant_type=password`, exactly like the initial setup in step 5 of §2. If that attempt itself gets rejected as `ConfigEntryAuthFailed`, the code falls back once to `access_token_only=True`, which forces the refresh-token path using whatever refresh token is still on file - this is expected to fail occasionally and is logged as a warning, not an error, as long as the fallback succeeds.
* **What gets stored on success**: `mqtt["access_token"]` and `mqtt["expires_in"]` always; `mqtt["refresh_token"]` and a new `mqtt["refresh_token_expires_at"]` (now + 3 days) only when the response actually included a `refresh_token` (the plain access-token-only fallback response may not).
* **Retry/backoff on transient failure**: a `CommunicationError` during refresh increments `_mqtt_token_retry` and backs off through `MQTT_TOKEN_RETRY_BACKOFF` (60s, 120s, 300s, 600s, 900s, capping at the last value), plus up to 10% random jitter to avoid thundering-herd reconnects across installs.
* **Rate limit exceeded**: `RateLimitException` (the 6/24h OTP cap) resets the retry counter and pushes the next attempt out by a full day rather than hammering the backoff schedule.
* **Reactive (broker-driven) refresh**: two independent triggers outside the scheduled loop can also force a refresh, both via `do_async(..., wait=False)` because they run on paho-mqtt's own network thread and must not block it:
  * `_on_mqtt_disconnect()` sees result code `11` (`MQTT_ERR_AUTH`) and calls `scheduled_mqtt_token_refresh(force=True)`.
  * `_on_mqtt_message()` sees a command response with `return_code`/`process_code` `400`: if the `reason` is specifically `[authorization.denied.cvs.response.no.matching.service.key]`, that's treated as a "vehicle doesn't support this feature" outcome (`not_compatible`), *not* a token problem. For any other `400` reason, if a previous request is still on file (`self._mqtt_last_request`), it's treated as a stale-token symptom: the same request is re-sent once via `send_mqtt_message(..., store=False, ...)`, which forces a token refresh itself (see below) before publishing again. A second consecutive `400` with no request left on file is reported as `failed` instead of retrying again.
* **`send_mqtt_message()`** always calls `scheduled_mqtt_token_refresh()` before publishing (forced when the call itself is a retry, i.e. `store == False`), so a stale token is caught before the command round-trip rather than only after a `400` comes back.

## 6. Persistence and log masking

Both token domains funnel through the same two calls on every rotation:

1. `save_config({...})` - updates the in-memory `self._config` dict and re-registers every value under `oauth`/`mqtt` (and other config) with the shared sensitive-data log filter, so a freshly rotated token is masked in debug logs immediately, without any refresh code having to register it by hand.
2. `update_stored_config("oauth"|"mqtt", ...)` - writes the same data into `ConfigEntry.data` via `hass.config_entries.async_update_entry()`, so tokens survive a Home Assistant restart.

`save_config()` is always called before the raw HTTP exchange is debug-logged (`_log_http_exchange()`), specifically so the log line for the response that just delivered a new token already masks it.
