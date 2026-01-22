# CLI Contract

This document is the contract for the workspace tooling.

## Goals

- One safe bootstrap entrypoint: `./setup.sh`
- One explicit update entrypoint: `ms update`
- One build/setup entrypoint: `ms setup`
- High signal diagnostics: `ms doctor` + `ms verify`

## Safety Rules

- `setup.sh`:
  - installs missing tools only
  - never upgrades tools
  - never runs `git pull`
  - never builds project artifacts
  - never runs `sudo` by default
- `ms update`:
  - is the only command that upgrades tools and dependencies
  - is the only command that may update git repos
  - repo updates run only when the worktree is clean (otherwise: skip + instructions)
- `ms doctor` / `ms verify`:
  - do not modify the environment (read-only)
- Destructive actions require explicit flags (examples: `--fix-midi`, `--pull`, `--upgrade`).

## Tooling Policy

- Latest stable by default.
- Hard constraints:
  - SDL2 (legacy required)
  - JDK 25 installed, but Bitwig extension must compile with Java 21 compatibility (`--release 21`).

## Command Surface (stable)

- `ms` (no args): interactive mode (menu)
- `ms help`

- `ms doctor` (read-only)
- `ms verify [--full]` (read-only)

- `ms update [--repos] [--tools] [--python]` (explicitly modifies environment)
- `ms setup` (build from source)
- `ms bridge` (oc-bridge TUI / service management)

- `ms list`
- `ms clean [codebase]`

- `ms build <codebase> [teensy|native|wasm]`
- `ms run <codebase>`
- `ms web <codebase> [--no-watch]`
- `ms upload <codebase> [--release]`
- `ms monitor <codebase> [--release]`

Aliases:

- `ms r` == `ms run`
- `ms w` == `ms web`
- `ms b` == `ms build`

## Exit Codes

- `0`: success
- `1`: user error (bad args, missing tool, missing config)
- `2`: environment problem (deps missing, incompatible versions)
- `3`: build failure (compilation/build step failed)

## JSON Mode

Commands that support `--json` must output a single JSON object to stdout and keep human output on stderr.

- `ms doctor --json`
- `ms verify --json`
- `ms update --json`
