# Claude Code Instructions — Stellantis Vehicles (HACS custom component)

This directory is a **separate git repository**, checked in as a submodule of `home-assistant-core`. It is a standalone HACS custom integration (`custom_components/stellantis_vehicles/`), not part of `homeassistant/components`. Run every `git` command from inside this directory, not from the core repo root, or it targets the wrong repository.

## The repository-root `CLAUDE.md` does NOT apply here

Ignore the Home Assistant Core conventions from the root file — specifically:

- **Integration Quality Scale** (`quality_scale.yaml`, Bronze/Silver/Gold tiers) — this repo has none.
- **Core-only scripts** `python -m script.hassfest` and `script.gen_requirements_all` — CI here runs the reusable `home-assistant/actions/hassfest` workflow (`.github/workflows/hassfest.yaml`) plus a `hacs.yaml` workflow for the HACS manifest; requirements are just the `requirements` list in `manifest.json`.
- **`codeowners`** — the manifest's `@andreadegiovine` is the upstream author, not this fork's maintainer. Don't touch it in unrelated work.

General HA integration best practices from the root file still apply as *style*, since this is a real HA integration: async I/O, `DataUpdateCoordinator`, entity unique IDs, `has_entity_name`, translation keys, no blocking calls, lazy logging, specific exception types. Use them as defaults; don't block changes on Core enforcement mechanisms that don't exist here.

## No automated tests

There is no test suite (`tests/components/<domain>/`, ≥95% coverage, snapshots — none of it exists), so nothing catches a regression before release. Don't run `pytest` or assume test scaffolding; adding a suite is a substantial change — confirm with the user first. Before calling a change done, ask the user to verify it against their running Home Assistant instance (reload the integration, check logs, verify entity states) — a clean `hassfest`/lint run is not proof the change works.

## Markdown style

Don't hard-wrap Markdown prose — one paragraph or list item per line, relying on the editor's soft wrap. No fixed wrapping column. Applies to all Markdown authored in this repo (generated `README.md` sections excepted).

## Branches

| Branch | Purpose |
|---|---|
| `testing` | Primary branch — new contributions are tried here first. Never a base for new branches. |
| `local/changes` | Changes the user does **not** want upstream. Synced to `origin` only, never `upstream`. Merges into `testing`. |
| `develop` | Tracks `upstream/develop`. The base for upstream-PR branches. |
| `master` | Tracks releases. |

- **Remotes**: `origin` = this fork (`MoellerDi/homeassistant-stellantis-vehicles`, the only push target), `upstream` = original author (`andreadegiovine/...`, read-only, never push there). Check `git remote -v` before assuming where a branch or PR lives. `push.autoSetupRemote` is set globally, so push new branches to `origin` explicitly. If a branch tracks `upstream/...` by mistake: `git branch --set-upstream-to=origin/<branch> <branch>`.
- **This `CLAUDE.md` may only live on `local/changes` and `testing`.** It must never reach `develop` or any upstream-destined staging/PR branch — not via a direct commit, a merge, or a cherry-pick. Unstage it when preparing such a branch.
- **Don't merge branches into `testing` or `develop` unless asked.**
- **Upstream-PR branches**: branch off `upstream/develop`, not `testing` — `testing`-only commits would ride along and pollute the PR diff. When work on `testing` is ready it gets consolidated onto its own prefixed branch, which is then used to open the PR. Ask if the correct base is unclear.
- **`PR-Info.md`**: a per-branch "remove before opening PR" scratch note. Must never land on `testing` — when a merge brings it along, `git rm PR-Info.md` as part of that merge or in a follow-up commit. Leave it untouched on the branch it came from. Don't use em-dashes (—) in its prose; use a comma, colon, semicolon, or parentheses instead.
- **`README.md` / `info.md`** are kept in sync (`render_readme: true` in `hacs.json`); an `update_readme.yaml` workflow may regenerate parts of `README.md`. Don't hand-edit generated sections without checking that workflow first.

## Branch naming

Purpose prefix + short, lower-case, hyphen-separated description: `feature/`, `bugfix/`, `hotfix/`, `refactor/`, `doc/`. E.g. `feature/add-user-profile`, `bugfix/fix-404-error`.

## Releases

Releases are cut via GitHub releases/tags (`release.yaml` workflow), not by bumping anything in `home-assistant-core`. The `version` field in `manifest.json` must match the release tag. (`hacs.json` currently has `zip_release: false`.)

## Commit messages

Commit messages are surfaced in this repo's GitHub release notes — keep them to a single, concise subject line, no lengthy body.
