# Phase 4: Bridge prebuilt (no Rust prereq)

**Scope**: bridge install/run + setup
**Status**: completed
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- `ms setup` installs `oc-bridge` without requiring Rust/cargo.
- Default path is prebuilt download (GitHub releases).
- Build-from-source remains optional for bridge contributors.

## Planned commits (atomic)

1. `feat(bridge): install oc-bridge from GitHub releases`
   - Download correct asset for OS/arch.
   - Install to `bin/bridge/oc-bridge(.exe)`.
   - Copy `open-control/bridge/config` when available.

2. `refactor(setup): bridge step uses installer, not cargo`
   - Update `SetupService` and `PrereqsService` to not require Rust.

3. `refactor(check): remove rust/cargo as required tools`
   - `ToolsChecker`: rust/cargo become optional.
   - `WorkspaceChecker`: hint changes from `bridge build` to `bridge install`.

## Work log

- 2026-01-27: Phase created (no code changes yet).

- 2026-01-27:
  - Upstream: `open-control/bridge` release workflow now publishes prebuilt assets (win/linux/macos x64+arm64), released `v0.1.1`.
  - `ms setup` installs `oc-bridge` via GitHub releases (no Rust prereq).
  - Rust/cargo removed from required prereqs; still checked as optional tools when present.
  - `ms bridge` is now a subcommand group (`install` / `build`); default behavior installs prebuilt.
  - Updated workspace checker + tests to report `oc-bridge` as `missing`/`installed` instead of only `built`.
  - Verified (simulated no Rust in PATH): `ms setup --dry-run` ok; `ms check` shows rustc/cargo as optional warnings.

## Decisions

- Install destination: `bin/bridge/oc-bridge(.exe)`.
- Download source: `https://github.com/open-control/bridge/releases` (`latest` by default, optional pinned version).
- Asset names:
  - Windows x64: `oc-bridge-windows.exe`
  - Linux x64: `oc-bridge-linux`
  - macOS x64: `oc-bridge-macos-x64`
  - macOS arm64: `oc-bridge-macos-arm64`
- Keep build-from-source available via `ms bridge build` (Rust optional for contributors).

## Plan deviations

- Workspace bridge check now considers both installed (`bin/bridge/...`) and built (`open-control/bridge/target/release/...`) binaries.
- Bridge CLI refactored into a Typer sub-app (`ms bridge install|build`) instead of a single command.

## Verification (minimum)

```bash
uv run pytest ms/test -q
uv run ms bridge --help
uv run ms setup --dry-run
uv run ms check
```

Manual validation checklist:

- With no Rust installed: `ms setup` succeeds and installs `bin/bridge/oc-bridge`.

## Sources

- `ms/services/bridge.py`
- `ms/services/setup.py`
- `ms/services/prereqs.py`
- `ms/services/checkers/tools.py`
- `ms/services/checkers/workspace.py`
- `ms/cli/commands/bridge.py`
- `ms/cli/app.py`
- `open-control/bridge/README.md`
- `open-control/bridge/config/default.toml`
