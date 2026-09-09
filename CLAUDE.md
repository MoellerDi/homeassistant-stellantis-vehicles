# Claude Code Instructions — Stellantis Vehicles (HACS custom component)

This directory is a **separate git repository**, checked in as a submodule of `home-assistant-core`. It is a standalone HACS custom integration (`custom_components/stellantis_vehicles/`), not part of `homeassistant/components`. Run every `git` command from inside this directory, not from the core repo root, or it targets the wrong repository.

**This `CLAUDE.md` lives only on `local/changes`.** It must never reach `testing`, `develop`, or any upstream-destined staging/PR branch — not via a direct commit, a merge, or a cherry-pick. `local/changes` merges into `testing`, so that merge is the one that would carry it: drop it there as part of the merge (`git rm CLAUDE.md`), exactly as with `PR-Info.md`. Unstage it when preparing any other branch.

**Never push without being asked.** No `git push` — and no `--force` / `--force-with-lease` — unless the user explicitly requests it in that turn. Reordering, squashing, or otherwise rewriting history locally is fine; publishing it is the user's call.

## The repository-root `CLAUDE.md` does NOT apply here

Ignore the Home Assistant Core conventions from the root file — specifically:

- **Integration Quality Scale** (`quality_scale.yaml`, Bronze/Silver/Gold tiers) — this repo has none.
- **Core-only scripts** `python -m script.hassfest` and `script.gen_requirements_all` — CI here runs the reusable `home-assistant/actions/hassfest` workflow (`.github/workflows/hassfest.yaml`) plus a `hacs.yaml` workflow for the HACS manifest; requirements are just the `requirements` list in `manifest.json`.
- **`codeowners`** — the manifest's `@andreadegiovine` is the upstream author, not this fork's maintainer. Don't touch it in unrelated work.

The root file's integration best practices still apply as *style* defaults (async I/O, `DataUpdateCoordinator`, entity unique IDs and `has_entity_name`, translation keys, lazy logging, specific exception types). Use them as defaults; don't block changes on Core enforcement mechanisms that don't exist here.

## Tests

Upstream has no test suite (no `tests/components/<domain>/`, no coverage gate, no snapshots) and CI runs none, so a green `pytest` or lint run is never proof a change works: before calling a change done, ask the user to verify it against their running Home Assistant instance (reload the integration, check logs, verify entity states).

Tests we write for a change stay off the upstream-PR branch — this is the standing workflow, not a per-change decision:

- The `bugfix/…` / `feature/…` branch that gets pushed to `origin` and becomes the PR stays test-free. Whether and how a suite lands upstream is the upstream author's call.
- Put the tests in a single commit on a parallel branch named `<code-branch>-tests`, rebased to sit directly on top of the code branch. It is local only: never push it, give it no upstream tracking, and rebase it again (`git rebase <code-branch>`) every time the code branch is amended.
- Write them as plain `pytest`, run via the local `.venv-test` (`pytest_homeassistant_custom_component` is available). Prefer standalone unit tests that need no HA harness where the code under test allows it.

## Type hints

The codebase is largely untyped and we are typing it incrementally. Whenever you touch a function or method, add complete hints to its whole signature (every parameter plus the return type) before moving on, even when the edit itself is unrelated to typing. Follow the local style: `name:type` (no space after the colon), `X | None` unions, and `Any` only where the value is genuinely heterogeneous (raw JSON responses, key-keyed config lookups). Where a clean hint needs a small change to match reality (a `-> None` method that still `return`s a value, a `None`-sentinel default of the wrong type), fix that rather than widening the annotation to cover it.

## Markdown style

Don't hard-wrap Markdown prose — one paragraph or list item per line, relying on the editor's soft wrap. No fixed wrapping column. Applies to all Markdown authored in this repo (generated `README.md` sections excepted).

## Branches

| Branch | Purpose |
|---|---|
| `testing` | Primary branch — new contributions are tried here first. Never a base for new branches. |
| `local/changes` | Changes the user does **not** want upstream. Synced to `origin` only, never `upstream`. Merges into `testing`, except this `CLAUDE.md`, which is dropped from every such merge. |
| `develop` | Tracks `upstream/develop`. The base for upstream-PR branches. |
| `master` | Tracks releases. |

- **Remotes**: `origin` = this fork (`MoellerDi/homeassistant-stellantis-vehicles`, the only push target), `upstream` = original author (`andreadegiovine/...`, read-only, never push there). Check `git remote -v` before assuming where a branch or PR lives. `push.autoSetupRemote` is set globally, so push new branches to `origin` explicitly. If a branch tracks `upstream/...` by mistake: `git branch --set-upstream-to=origin/<branch> <branch>`.
- **Don't merge branches into `testing` or `develop` unless asked.**
- **Upstream-PR branches**: branch off `upstream/develop`, not `testing` — `testing`-only commits would ride along and pollute the PR diff. When work on `testing` is ready it gets consolidated onto its own prefixed branch, which is then used to open the PR. Ask if the correct base is unclear.
- **`PR-Info.md`**: a per-branch "remove before opening PR" scratch note. Must never land on `testing` — when a merge brings it along, `git rm PR-Info.md` as part of that merge or in a follow-up commit. Leave it untouched on the branch it came from. Don't use em-dashes (—) in its prose; use a comma, colon, semicolon, or parentheses instead.
- **`CLAUDE.md`** (this file): see the note at the top of this file — dropped from the `local/changes` → `testing` merge exactly like `PR-Info.md` above.
- **`README.md` / `info.md`** are kept in sync (`render_readme: true` in `hacs.json`); an `update_readme.yaml` workflow may regenerate parts of `README.md`. Don't hand-edit generated sections without checking that workflow first.

## Branch naming

Purpose prefix + short, lower-case, hyphen-separated description: `feature/`, `bugfix/`, `hotfix/`, `refactor/`, `doc/`. E.g. `feature/add-user-profile`.

## Releases

Releases are cut via GitHub releases/tags (`release.yaml` workflow), not by bumping anything in `home-assistant-core`. The `version` field in `manifest.json` must match the release tag.

## Commit messages

Commit messages are surfaced in this repo's GitHub release notes — keep them to a single, concise subject line, no lengthy body.
