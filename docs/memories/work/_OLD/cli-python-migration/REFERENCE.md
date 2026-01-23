# Reference Files

**Parent**: [README.md](./README.md)

This document lists all files that will be modified or deprecated during the migration.

## Files to Preserve (Reference)

These files contain working logic that should be referenced during migration:

### `setup.sh`

**Location**: `setup.sh` (workspace root)
**Status**: To be simplified to ~50-80 lines

Key functions to migrate to Python:
- `setup_cmake()` → `ms_cli/build/tools.py`
- `setup_ninja()` → `ms_cli/build/tools.py`
- `setup_zig()` → `ms_cli/build/tools.py`
- `setup_bun()` → `ms_cli/build/tools.py`
- `setup_jdk()` → `ms_cli/build/tools.py`
- `setup_maven()` → `ms_cli/build/tools.py`
- `setup_sdl2_windows()` → `ms_cli/build/tools.py`
- `setup_emscripten()` → `ms_cli/build/tools.py`
- `setup_platformio()` → `ms_cli/build/tools.py`
- `check_system_deps()` → `ms_cli/errors.py`
- `configure_shell()` → `ms_cli/cli.py` (setup command)

### `commands/ms-legacy`

**Location**: `commands/ms-legacy`
**Status**: To be deprecated as `commands/ms-legacy.deprecated`

Key functions to migrate:
- `cmd_native_build()` → `ms_cli/build/native.py`
- `cmd_native_run()` → `ms_cli/build/native.py`
- `cmd_wasm_build()` → `ms_cli/build/wasm.py`
- `cmd_wasm_serve()` → `ms_cli/build/wasm.py`
- `cmd_teensy_build()` → `ms_cli/build/teensy.py`
- `cmd_teensy_upload()` → `ms_cli/build/teensy.py`
- `cmd_teensy_monitor()` → `ms_cli/build/teensy.py`
- `start_bridge()` → `ms_cli/bridge.py`
- `cleanup_bridge()` → `ms_cli/bridge.py`
- `resolve_codebase()` → `ms_cli/codebase.py`
- `list_codebases()` → `ms_cli/codebase.py`
- `check_native_deps()` → `ms_cli/errors.py`

### `ms_cli/cli.py`

**Location**: `ms_cli/cli.py`
**Status**: To be modified (remove legacy delegation, add new commands)

Functions to remove:
- `_wrap_windows_cmd()` (temporary workaround)
- `_resolve_windows_bash()` (temporary workaround)
- `_delegate_to_legacy()` (delegation)
- All commands that call `_delegate_to_legacy()`

Functions to keep:
- `workspace_root()`
- `detect_platform()` (move to platform.py)
- `which()` (move to tools.py)
- `run_live()` (replace with tools.run_tool)
- `run_subprocess()` (replace with tools.run_tool)
- `setup()` (enhance with --bootstrap)
- `update()` (keep as-is)
- `doctor()` (keep as-is)
- `verify()` (keep as-is)

## Files to Create

| File | Purpose | Size |
|------|---------|------|
| `ms_cli/platform.py` | Platform detection | ~50 lines |
| `ms_cli/errors.py` | Error messages | ~150 lines |
| `ms_cli/tools.py` | Tool resolution | ~250 lines |
| `ms_cli/codebase.py` | Codebase management | ~80 lines |
| `ms_cli/bridge.py` | Bridge process | ~150 lines |
| `ms_cli/build/__init__.py` | Exports | ~15 lines |
| `ms_cli/build/teensy.py` | Teensy builds | ~150 lines |
| `ms_cli/build/native.py` | Native builds | ~180 lines |
| `ms_cli/build/wasm.py` | WASM builds | ~180 lines |

## Files to Deprecate

After migration is complete and tested:

| File | New Name |
|------|----------|
| `commands/ms-legacy` | `commands/ms-legacy.deprecated` |
| `setup.sh` | Keep (simplified) |

## Migration Checklist

### Phase 1: Create New Modules
- [x] `ms_cli/platform.py`
- [x] `ms_cli/errors.py`
- [x] `ms_cli/tools.py`
- [x] `ms_cli/codebase.py`
- [x] `ms_cli/bridge.py`

### Phase 2: Create Build Modules
- [x] `ms_cli/build/__init__.py`
- [x] `ms_cli/build/teensy.py`
- [x] `ms_cli/build/native.py`
- [x] `ms_cli/build/wasm.py`

### Phase 3: Update CLI Commands
- [x] `ms build` (native Python)
- [x] `ms run` (native Python)
- [x] `ms web` (native Python)
- [x] `ms upload` (native Python)
- [x] `ms monitor` (native Python)
- [x] `ms core` (native Python)
- [x] `ms bitwig` (native Python)
- [x] `ms clean` (native Python)
- [x] `ms list` (native Python)

### Phase 4: Bootstrap Migration
- [x] Simplify `setup.sh` to ~50-80 lines (setup-minimal.sh created)
- [x] Implement `ms setup --bootstrap`
- [x] Test full bootstrap flow

### Phase 5: Cleanup
- [x] Remove `_delegate_to_legacy()`
- [x] Remove `_wrap_windows_cmd()`
- [x] Remove `_resolve_windows_bash()`
- [x] Rename `commands/ms-legacy` → `.deprecated`

### Phase 6: Test Matrix
- [ ] Linux: all commands
- [ ] macOS: all commands
- [ ] Windows: all commands
