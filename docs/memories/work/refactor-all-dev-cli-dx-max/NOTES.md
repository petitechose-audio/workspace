# Notes - Dev CLI DX Max

**Created**: 2026-01-22
**Updated**: 2026-01-22

## 2026-01-22

- Decision: move existing internal docs under `docs/memories/` and create new user docs under `docs/ms-cli/`.
- Execution: moved `docs/{README.md,global/,work/,_OLD/}` to `docs/memories/` using `git mv`.
- Execution: added `docs/README.md` as an index and created `docs/ms-cli/` skeleton.
- Execution: wrote initial CLI contract in `docs/ms-cli/CONTRACT.md`.
- Decision: JDK 25 (LTS) portable, but compile Bitwig extension with Java 21 compatibility (`--release 21`).
- Note: PlatformIO install should follow official guidance (installer script / isolated env).
- Next: refactor `setup.sh` to be bootstrap-only and add portable tool installs (uv, bun, jdk, maven, PlatformIO).

### setup.sh refactor (in progress)

- Added portable installs and wrappers:
  - uv + workspace `.venv` (Python 3.13 via uv-managed Python)
  - bun (+ `bunx` wrapper)
  - Temurin JDK 25 (LTS) + Maven 3.9.x
  - PlatformIO via official installer script (plus `tools/bin/pio` wrapper)
  - cmake/ninja/zig wrappers in `tools/bin/`
- Removed default sudo flows from bootstrap (MIDI/virmidi will be handled later via explicit CLI actions).
- Made shell config idempotent via a marker block (`# >>> petitechose-audio workspace >>>`).
- Added `--skip-shell` to allow safe test runs.

Validation run (no side effects):

- `./setup.sh --skip-repos --skip-tools --skip-shell` (Linux)

#### Issues / fixes

- uv: `uv venv --managed-python --python 3.13` failed because uv python downloads were set to manual.
  - Fix: explicitly run `uv python install 3.13` (installed under `tools/python/`) before creating `.venv`.
- JDK download: Adoptium binary endpoint resolved to a GitHub URL with query params (no file extension), which broke archive detection.
  - Fix: resolve download URL via Adoptium assets API and parse `binary.package.link` (direct `.tar.gz`/`.zip`).
- Zig: initial implementation pulled the Zig `master` dev build.
  - Fix: parse `index.json` and pick the latest stable semver; reinstall if a dev build is detected.

#### Validation (Linux)

- `bash -n setup.sh`
- `./setup.sh --skip-repos --skip-shell` (tool install) succeeded.
- `./setup.sh --skip-repos --skip-shell` ran again and was idempotent.

### ms python foundation (done)

- Added a new Python-based `ms` CLI:
  - new wrapper: `commands/ms`
  - old bash CLI preserved as `commands/ms-legacy` (delegation layer during migration)
- Added workspace config: `config.toml`.
- Added Python project + lock:
  - `pyproject.toml`
  - `uv.lock`
- Installed CLI deps into `.venv` via `uv sync --frozen` (rich + typer).
- Updated `setup.sh` to sync Python deps after venv creation.

Validation (Linux):

- `./commands/ms --help`
- `./commands/ms doctor`
- `./commands/ms verify`
- `./commands/ms list` delegates to legacy and works

### ms doctor (done)

- Expanded `ms doctor` diagnostics:
  - workspace: clones present + config.toml parse
  - tools: versions + gh auth status + uv sync check
  - project: emsdk present, oc-bridge binary, bitwig host pom.xml, Bitwig Extensions dir detection
  - runtime: Linux virmidi loaded status + PlatformIO udev rules presence
  - assets: inkscape/fontforge presence + official links
  - system deps: SDL2 + ALSA (Linux), SDL2 via brew (macOS)

Validation:

- `./commands/ms doctor` (Linux)

### ms verify (done)

- Expanded `ms verify` beyond tool versions:
  - parses `config.toml`
  - checks `uv sync --check`
  - verifies emsdk presence
  - runs `pio device list`
  - reports PlatformIO udev rules status (Linux)

Validation:

- `./commands/ms verify`

### ms update (done)

- Implemented `ms update`:
  - `--python`: `uv lock --upgrade` + `uv sync --frozen`
  - `--repos`: `git pull --ff-only` on each clean repo under `open-control/` and `midi-studio/`
  - `--tools`: refresh selected tool dirs into `tools/.old/<timestamp>/` then re-run `./setup.sh --skip-repos --skip-shell`
  - `--dry-run`: prints planned actions only

Validation (Linux):

- `./commands/ms update --dry-run`
- `./commands/ms update --python`
- `./commands/ms update --tools` then `./commands/ms verify`
- `./commands/ms update --repos`

Notes:

- `open-control/.github` repo was dirty so repo update skipped it (as designed).

### ms setup (done)

- Implemented `ms setup`:
  - builds `open-control/bridge` via `cargo build --release`
  - builds Bitwig host extension via Maven and deploys it to the detected Bitwig Extensions dir
  - enforces Java 21 compatibility while using JDK 25 via `-Dmaven.compiler.release=21`

Validation (Linux):

- `./commands/ms setup`

Notes:

- oc-bridge build emitted warnings (unused/dead code) but succeeded.

### assets/icons (done)

- Updated Open Control LVGL icon builder:
  - header filename + namespace configurable via `HEADER_FILENAME` and `NAMESPACE`
  - platform-specific tool overrides (`INKSCAPE_*`, `FONTFORGE_*`)
  - `bunx` preferred (pinned) runner for `lv_font_conv` with `npx` fallback
  - guided errors when tools are missing
- Updated midi-studio icon configs + wrappers:
  - fixed Windows-only tool paths so Linux/macOS use `inkscape`/`fontforge`
  - wrappers now call `open-control/ui-lvgl-cli-tools/icon/build.py`
- Added `ms icons <core|bitwig>`.

Validation (Linux):

- `./commands/ms icons core` fails with a guided FontForge error when FontForge is missing.

### docs/ms-cli (done)

- Added initial user documentation:
  - `docs/ms-cli/PREREQUISITES.md`
  - `docs/ms-cli/SETUP.md`
  - `docs/ms-cli/PORTS.md`
  - `docs/ms-cli/MIDI.md`
  - `docs/ms-cli/ASSETS.md`

### interactive + zsh completions

- Implemented interactive mode: `ms` without args shows a menu when stdin is a TTY.
- Non-interactive `ms` without args prints help (script-friendly).
- Added zsh completions: `commands/_ms_completions.zsh` and `ms completion zsh`.
- Updated `setup.sh` shell block to source zsh completions when `ZSH_VERSION` is set.

### bridge service parity (in progress)

- oc-bridge gaps addressed:
  - daemon mode now broadcasts logs to the same UDP channel used by the TUI (service parity with Windows)
  - monitoring now listens on the configured `log_broadcast_port` (instead of hard-coded default)
  - Windows service log broadcaster now uses `log_broadcast_port`

Validation (Linux):

- `cargo test` in `open-control/bridge`
- `oc-bridge --daemon` broadcasts logs to UDP:9999 (verified with a UDP receiver)

### ms bridge + shortcuts (in progress)

- Added `ms bridge` (pass-through) to run `oc-bridge`.
- Added `core-dev` and `bitwig-dev` wrappers (supports `bitwig-dev monitor`, and `--release` before subcommand).

Status: Step 11/12 completed on Linux.
