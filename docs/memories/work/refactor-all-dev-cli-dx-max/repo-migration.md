# Repo migration: petitechose-audio/workspace -> midi-studio/ms-dev-env

**Scope**: repository ownership + naming + visibility
**Status**: started
**Created**: 2026-01-28
**Updated**: 2026-01-28

## Goal

- Transfer the dev environment repo into the `midi-studio` org for governance/coherence.
- Rename it to an explicit name: `ms-dev-env`.
- Make the repository public.

## Current state

- [x] Repo is public
- [x] GitHub Pages enabled (source: GitHub Actions)
- [ ] Transfer ownership to `midi-studio`
- [ ] Rename to `ms-dev-env`
- [ ] Update local `origin` and any documented URLs

## Notes

- This repository is the "dev env bootstrapper" for MIDI Studio (and its open-control dependencies).
  Keeping it in the `midi-studio` org matches the product scope.

- GitHub Pages base URL will change after transfer/rename.
  Plan for redirects if the old URL was shared publicly.

## What `gh` can and cannot do (verified)

- `gh repo rename` exists.
- `gh repo edit --visibility public` exists, but requires `--accept-visibility-change-consequences`.
- There is no `gh repo transfer` command.
  Transfer must be done via the GitHub web UI, or via the GitHub API (`gh api`).

## Procedure (testable)

### 0) Preconditions

- You must be admin/owner of the source repo and have permission to transfer into the target org.
- Confirm auth + scopes:

```bash
gh auth status
```

### 1) Transfer ownership to the org

Preferred (API via `gh api`):

```bash
gh api -X POST repos/petitechose-audio/workspace/transfer -f new_owner=midi-studio
```

If this fails with a 422 like:

- "You don’t have the permission to create public repositories on midi-studio"

Then an org owner must either:

- perform the transfer from the GitHub web UI using an owner account, or
- grant the initiating account permission to create public repositories in the org.

Notes:

- GitHub may require an org owner to accept the transfer.
- If required, use the web UI to accept.

### 2) Rename the repository to `ms-dev-env`

Once the repo is under the org:

```bash
gh repo rename -R midi-studio/workspace ms-dev-env -y
```

### 3) Make the repository public

```bash
gh repo edit midi-studio/ms-dev-env \
  --visibility public \
  --accept-visibility-change-consequences
```

Important: verify there are no committed secrets before doing this.

### 4) Update local git remotes

```bash
git remote set-url origin https://github.com/midi-studio/ms-dev-env.git
git remote -v
```

### 5) GitHub Pages URL update

- New base URL will be:
  - `https://midi-studio.github.io/ms-dev-env/`

If old links exist:

- Keep the old Pages site temporarily and publish a redirect page.
- Or communicate the new URL everywhere.

## Verification

- `gh repo view midi-studio/ms-dev-env --json nameWithOwner,visibility,url`
- Clone test:

```bash
git clone https://github.com/midi-studio/ms-dev-env.git
```

## Work log

- 2026-01-28:
  - Repository set to public.
  - GitHub Pages enabled (source: GitHub Actions).

- 2026-01-28:
  - Transfer attempt via API failed (HTTP 422): missing permission to create public repositories in `midi-studio`.
