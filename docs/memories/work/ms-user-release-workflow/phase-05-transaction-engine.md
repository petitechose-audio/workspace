# Phase 05: Transaction Engine - Atomic current/ Swap + Rollback

Status: TODO

## Goal

Make installs/updates safe and atomic, including ms-manager self-updates.

Key requirements:
- Never leave `current/` half-installed.
- Stop/start services at the right times.
- Roll back to the previous `current` on failure.

Prerequisites:
- Phase 03 is complete (service name + `--service-exec`), so oc-bridge can be installed/restarted using a stable service definition that points to `current/`.

## Recommended Implementation

Use a separate helper binary (ship as sidecar):
- `ms-updater`

Why:
- Windows cannot replace a running exe reliably (file locks).
- A helper can run elevated only when required.

High-level flow:
1) ms-manager downloads + verifies everything.
2) ms-manager spawns ms-updater with an “apply plan” file.
3) ms-updater:
    - stops oc-bridge service (if running; use the dedicated MIDI Studio service name)
    - extracts/stages new version into `versions/<tag>`
    - atomically switches `current` (junction/symlink)
    - restarts service (service should already reference the stable `current/` exec path)
    - relaunches ms-manager

## Atomicity Details

- Use a staging directory:
  - `versions/<tag>.staging/` then rename to `versions/<tag>/`.

- Switch `current` atomically:
  - Windows: junction swap (requires admin)
  - macOS/Linux: symlink swap

- Always keep:
  - `previous` pointer (or store last tag in state) to roll back.

## Anti-rollback

- Default update path must refuse downgrades.
- Downgrade allowed only via advanced UI with confirmation.

## Exit Criteria

- Update/install is atomic and recoverable.
- ms-manager self-update works.
- Service restart and path changes are consistent.

## Tests

Local (fast):
- Unit tests for:
  - transaction plan parsing
  - filesystem operations (staging -> final)
  - rollback logic

Local (full):
- End-to-end simulated upgrade:
  - install tag A
  - upgrade to tag B
  - intentionally fail midway (simulate extraction failure)
  - verify rollback to A
