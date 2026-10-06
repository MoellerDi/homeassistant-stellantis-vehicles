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
| `testing` | Installed on the user's HA instance to try new features and bugfixes, which are developed in separate branches. Never a base for new branches. |
| `local/changes` | Changes the user does **not** want upstream. Synced to `origin` only, never `upstream`. Permanently part of `testing` (merged in on every rebuild), except this `CLAUDE.md`, which is dropped from every such merge. |
| `develop` | Tracks `upstream/develop`. The base for upstream-PR branches. |
| `master` | Tracks releases. |

- **Remotes**: `origin` = this fork (`MoellerDi/homeassistant-stellantis-vehicles`, the only push target), `upstream` = original author (`andreadegiovine/...`, read-only, never push there). Check `git remote -v` before assuming where a branch or PR lives. `push.autoSetupRemote` is set globally, so push new branches to `origin` explicitly. If a branch tracks `upstream/...` by mistake: `git branch --set-upstream-to=origin/<branch> <branch>`.
- **Don't merge branches into `testing` or `develop` unless asked.**
- **Branch prefixes**: purpose prefix + short, lower-case, hyphen-separated description (e.g. `feature/add-user-profile`). `bugfix/…` / `feature/…` (also `hotfix/`, `refactor/`, `doc/`) = development with PR intent, becomes the PR when finished. `*-not-ready-yet/…` (e.g. `bugfix-not-ready-yet/…`) = development paused, may be resumed later; rename to `bugfix/` / `feature/` once work continues and a PR is planned soon. `investigation/…` = analysis without PR intent. `backup/…` = local safety copy before history rewrites. Each code branch may have a local-only `<branch>-tests` sibling (see Tests).
- **Workflow**: new work starts as a branch off `upstream/develop`. To try it on the HA instance, the user has it merged into `testing` (only when asked). Before the PR, Claude cleans up the branch history (rebase/squash) when asked. Once the PR is open, only add new commits so reviewers can follow the history; a force-push is an exception only: point out this rule and ask again whether the change should go into the PR via force-push. After the PR is merged upstream, delete the branch locally and on `origin`, together with its `-tests` sibling. `-tests` branches never get merged into `testing`.
- **Rebuilding `testing`**: the user requests it from time to time (e.g. after `develop` moved or a PR was merged). Claude may suggest it when it makes sense, but never starts it without asking. Steps:
  1. Check the old `testing` for commits that exist nowhere else and point them out; the user decides which branch they get cherry-picked onto before the rebuild, otherwise they are lost.
  2. Archive the old one as `archiv/testing_<YYYYMMDD>` (creating it locally is fine, but ask before pushing it to `origin`).
  3. Build the new `testing` from `develop` plus the active branches: all not-yet-merged `bugfix/`, `feature/`, `hotfix/`, `refactor/` branches, but not `*-tests` and not `*-not-ready-yet/`. Ask when in doubt.
  4. Merge `local/changes` last (minus `CLAUDE.md` and `PR-Info.md`), because it contains changes that must be applied on top of everything else.
  5. Resolve merge conflicts yourself and summarize them afterwards; on contradictions or logic conflicts between branches, ask first.
  6. Publishing the new `testing` to `origin` needs `--force-with-lease`: ask first, with a summary, and never push without the user's go-ahead.
- **Upstream-PR branches**: features and bugfixes are developed in their own branches off `upstream/develop`, not `testing` — `testing`-only commits would ride along and pollute the PR diff. `testing` only collects them for trying on the user's HA instance. Occasional quick-fixes committed directly on `testing` get cherry-picked onto a separate branch (or into an existing one) for the PR, only when asked. Ask if the correct base is unclear.
- **`PR-Info.md`**: a per-branch "remove before opening PR" scratch note. Must never land on `testing` — when a merge brings it along, `git rm PR-Info.md` as part of that merge or in a follow-up commit. Leave it untouched on the branch it came from. Don't use em-dashes (—) in its prose; use a comma, colon, semicolon, or parentheses instead.
- **PR / issue tracking**: on every new PR or issue, and when one is merged or closed, update the Claude memory: one minimal status line in `stellantis-pr-status`, details (causes, commits, review drafts) in `stellantis-pr-archive`. Not in this file.
- **`CLAUDE.md`** (this file): see the note at the top of this file — dropped from the `local/changes` → `testing` merge exactly like `PR-Info.md` above.
- **`README.md`** can be edited, but the `update_readme.yaml` workflow overwrites parts of it (support section, active installations badge), so check the workflow first.

## Releases

Releases are cut via GitHub releases/tags (`release.yaml` workflow), not by bumping anything in `home-assistant-core`. The `version` field in `manifest.json` must match the release tag.

## Commit messages

Commit messages are surfaced in this repo's GitHub release notes — keep them to a single, concise subject line, no lengthy body.
