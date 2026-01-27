# Phase 1: Deshellize

**Scope**: ms (hardware + platform utilities) + repo hygiene
**Status**: started
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- `ms` does not depend on bash/Git Bash for any workflow.
- Hardware workflows keep the oc-* UX, but oc-* is implemented in Python (no bash).
- No `shell=True` in our subprocess usage.
- Legacy entrypoints removed.

## Planned commits (atomic)

1. `chore(cli): remove legacy shell entrypoints`
   - Delete `setup-minimal.sh`
   - Delete `commands/`

2. `feat(oc-cli): port oc-* scripts to python`
   - Add `oc-build`, `oc-upload`, `oc-monitor` as Python entrypoints runnable via `uv run`
   - Preserve the compact oc-* output summary (spinner + build summary)

3. `refactor(hardware): call python oc-* from ms`
   - Update `ms/services/hardware.py` to run `python -m ms.oc_cli.oc_*` (no bash)
   - Add `--env` passthrough for hardware modes (`ms build|upload|monitor <app> ...`)

4. `test(hardware): add command construction tests`
   - Tests that do not call real PlatformIO

5. `test(pytest): skip network tests by default`
   - Ensure `pytest` runs are stable by default (network is opt-in)

6. `fix(platform): remove shell=True usage`
   - Fix `ms/platform/clipboard.py`

## Work log

- 2026-01-27:
  - Commit `182c8d7`: removed legacy shell entrypoints (`setup-minimal.sh`, `commands/*`) and replaced prior docs.
  - Verified: `uv run ms --help`, `uv run ms check`, `uv run pytest ms/test -q`.

- 2026-01-27:
  - Ported oc-* (build/upload/monitor) to Python and exposed as `uv run oc-build|oc-upload|oc-monitor`.
  - Updated `ms` hardware workflows to run the Python oc-* modules (no bash).
  - Added `--env` passthrough for hardware modes (`ms build|upload|monitor <app> ...`).
  - Removed `shell=True` from clipboard implementation.
  - Made network tests opt-in by default (pytest marker).
  - Verified: `uv run oc-build --help`, `uv run ms check`, `uv run pytest ms/test -q`.

## Decisions

- Expose oc-* as Python console scripts via `pyproject.toml` so they can be run as `uv run oc-build ...`.

## Plan deviations

- 2026-01-27: Instead of deleting oc-* and calling PlatformIO directly from `ms/services/hardware.py`, we keep the oc-* UX but re-implement oc-* in Python so it can be executed via `uv run` and from `ms` without bash.

## Verification (minimum)

Run after each commit:

```bash
uv run pytest ms/test -q
uv run ms --help
uv run ms check
```

Opt-in network tests:

```bash
uv run pytest -m network
```

After commit 2 (hardware deshellized):

```bash
uv run ms build core --target teensy --dry-run
uv run ms build bitwig --target teensy --dry-run
```

## Sources

- `ms/services/hardware.py`
- `open-control/cli-tools/bin/oc-build`
- `open-control/cli-tools/lib/common.sh`
- `ms/oc_cli/common.py`
- `ms/oc_cli/oc_build.py`
- `ms/oc_cli/oc_upload.py`
- `ms/oc_cli/oc_monitor.py`
- `pyproject.toml`
- `ms/platform/clipboard.py`
- `setup-minimal.sh`
- `commands/`
