# Claude Code Instructions — Stellantis Vehicles (HACS custom component)

This directory is a **separate git repository**, checked in as a submodule of
`home-assistant-core`. It is a standalone HACS custom integration
(`custom_components/stellantis_vehicles`), not part of
`homeassistant/components` in Home Assistant Core.

**The repository-root `CLAUDE.md` (Home Assistant Core conventions) does NOT
apply here.** In particular, ignore its rules about:

- `quality_scale.yaml` / Integration Quality Scale tiers — this repo has none.
- `hassfest` via `python -m script.hassfest` (Core's own script) — CI here
  runs the reusable `home-assistant/actions/hassfest` workflow instead
  (`.github/workflows/hassfest.yaml`), and there's a separate `hacs.yaml`
  workflow validating the HACS manifest.
- `tests/components/<domain>/`, pytest coverage ≥95%, snapshot testing — **no
  test suite exists in this repo**. Don't assume test scaffolding or try to
  run `pytest` unless you add it from scratch, and confirm with the user
  first since that's a substantial addition.
- `python -m script.gen_requirements_all` — that's a Core-repo-wide script;
  requirements here are just the `requirements` list in `manifest.json`.
- `codeowners` guidance ("add your GitHub username") — the manifest's
  `codeowners` (`@andreadegiovine`) points at the upstream author, not this
  fork's maintainer. Don't change it as part of unrelated work.

## What still applies

General Home Assistant integration best practices from the root file remain
good guidance as *style*, since this is still a real HA integration:
async I/O, `DataUpdateCoordinator` usage, entity unique IDs,
`has_entity_name`, translation keys, avoiding blocking calls, lazy logging,
specific exception types, etc. Apply them as sensible defaults, but don't
block changes on Core-specific enforcement mechanisms that don't exist here.

## Repo layout & branches

- Single integration: `custom_components/stellantis_vehicles/`.
- This directory is a submodule of `home-assistant-core`: run `git` commands
  from inside this directory, not from the core repo root, or they'll target
  the wrong repository.
- Remotes: `origin` = this fork (`MoellerDi/homeassistant-stellantis-vehicles`),
  `upstream` = original author (`andreadegiovine/...`).
  Check `git remote -v` before assuming where a branch or PR lives.
- `testing` is the primary branch: new contributions are tried out here
  first. Once a change on `testing` is ready, it gets consolidated into a
  dedicated staging branch (see naming convention below), which is later
  used to open the actual pull request upstream. Don't assume these
  branches are just cherry-picks of *other* people's PRs — they may also be
  this workflow's staging branches for the user's own contributions.
  `develop` tracks upstream's development branch; `master` tracks releases.
  Don't merge branches into `testing` or `develop` without being asked.
- `local/changes` holds changes the user does **not** want to publish
  upstream — it's synced to `origin` only (never to `upstream`). It gets
  merged into `testing` as part of the staging step described above, so its
  content (including this `CLAUDE.md`) legitimately ends up on `testing`
  too. It must still never reach `develop` or any upstream-destined
  staging/PR branch.
- `README.md` and `info.md` are kept in sync (`render_readme: true` in
  `hacs.json`) — an `update_readme.yaml` workflow may regenerate parts of
  `README.md`. Don't hand-edit generated sections without checking that
  workflow first.

## Push target: always `origin`

`upstream` is a read-only reference remote (for pulling in `develop`), never
a push target. Every `git push` — new branch or existing one — must go to
`origin`, and the local branch's tracking must point at `origin/<branch>`,
not `upstream/<branch>`. Double-check with `git branch -vv` after creating
or pushing a branch; a branch that ends up tracking `upstream/...` (e.g. by
running `git push upstream ...` or `git branch --track` against the wrong
remote by mistake) is a bug — fix it with
`git branch --set-upstream-to=origin/<branch> <branch>` rather than leaving
it. `push.autoSetupRemote` is set globally, so a plain `git push` on a new
branch auto-configures tracking — but only for whichever remote is named in
that push command, so still push to `origin` explicitly.

## Branching name convention

New branches use purpose prefixes:

- `feature/`: new features or functionality.
- `bugfix/`: bug fixes.
- `hotfix/`: urgent patches.
- `refactor/`: structural changes with no behavior change.
- `doc/`: documentation only.

Keep the description short, lower-case, hyphen-separated, e.g.
`feature/add-user-profile`, `bugfix/fix-404-error`.

**Branch off `upstream/develop`, not `testing`.** A branch destined for an
upstream PR must not carry `testing`-only commits — if it's created off
`testing`, those commits ride along and pollute the PR's diff once opened
against upstream. `testing` is only for trying out changes locally (see
above), never a branch base. If it's unclear which base is correct for a
given change, ask before creating the branch.

## This file must stay local

This `CLAUDE.md` originates on `local/changes` — that's where edits to it
are made and committed. From there it is merged into `testing` as part of
the normal staging flow (see "Repo layout & branches" above), so `testing`
carries it too. **`local/changes` and `testing` are the only two branches
this file may exist on and be pushed to `origin` from.** It must never
reach `develop` or any upstream-destined staging/PR branch (per the naming
convention above), whether via a direct commit, a merge, or a cherry-pick.
When preparing such a branch, make sure this file is excluded/unstaged
before pushing to `origin` or `upstream`.

## No automated tests — validate manually

There is no test suite (see above), so nothing catches a regression before
it ships. Before considering a change done, ask the user to confirm it
manually against their running Home Assistant instance (reload the
integration, check logs, verify entity states) rather than treating a clean
`hassfest`/lint run as proof the change works.

## Releases

`hacs.json` has `"zip_release": true` and there's a `release.yaml` workflow —
releases are cut via GitHub releases/tags, not via bumping anything in
`home-assistant-core`. The `version` field in `manifest.json` must match the
release tag.

## Commit messages

Commit messages get surfaced in the GitHub release notes for this repo, so
keep them short — a single, concise subject line, no lengthy body.
