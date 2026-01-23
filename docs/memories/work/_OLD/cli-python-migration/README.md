# CLI Python Migration: Unified Cross-Platform Build System

**Scope**: `ms` CLI + `setup.sh` bootstrap
**Status**: Phases 1-5 complete. Ready for Phase 6 (Linux/macOS testing)
**Created**: 2026-01-22
**Updated**: 2026-01-22

## Context

Windows testing revealed multiple issues with the current hybrid bash/Python architecture:
- `subprocess.run()` can't execute `.cmd` files without shell
- `os.execv()` fails with paths containing spaces
- Bash wrapper scripts in `tools/bin/` can't be executed by CMake
- `ms-legacy` (800 lines bash) has subtle Windows compatibility issues

## Objective

Migrate to a unified Python-based CLI that:
- Works identically on Linux, macOS, and Windows
- Has minimal bash (bootstrap only, ~50-80 lines)
- Is maintainable, testable, and debuggable
- Uses bundled tools directly (no bash wrappers)

## Reference Files

**DO NOT DELETE OR MODIFY WITHOUT READING:**

| File | Purpose | Lines |
|------|---------|-------|
| `setup.sh` | Current bootstrap script (to be simplified) | ~1000 |
| `commands/ms-legacy` | Legacy bash CLI (to be deprecated) | ~800 |
| `ms_cli/cli.py` | Current Python CLI | ~1400 |

## Architecture Decision

### D3: Minimal Bash Bootstrap + Full Python

```
setup.sh (~50-80 lines)              ms setup --bootstrap (Python)
────────────────────────────────     ──────────────────────────────
1. Check: git, curl                  1. Install bundled tools
2. Download uv (single binary)       2. Check system deps → guide user
3. uv python install 3.13            3. Clone repos (if --clone)
4. Exec: ms setup --bootstrap        4. Configure shell (PATH, etc.)
                                     5. Build bridge + extension
```

### Why D3?

| Criteria | D1 (Current bash) | D3 (Bootstrap + Python) |
|----------|-------------------|-------------------------|
| Bash lines | ~800 | ~50-80 |
| Logic duplication | Yes | No |
| Maintainability | Medium | High |
| Divergence risk | High | Low |
| Testability | Hard | Easy |
| Dependencies | git, curl, tar, unzip | git, curl |

## Dependencies Classification

### Bundled Tools (installed in `tools/`)

Downloaded automatically, no sudo needed:

| Tool | Platforms | Source |
|------|-----------|--------|
| uv | All | GitHub releases |
| python 3.13 | All | Via uv |
| cmake | All | GitHub releases |
| ninja | All | GitHub releases |
| zig | All | ziglang.org |
| bun | All | GitHub releases |
| jdk 25 | All | Adoptium API |
| maven | All | Apache mirror |
| emsdk | All | Git clone |
| platformio | All | Installer → `~/.platformio` |
| SDL2 | **Windows only** | GitHub releases (mingw) |

### System Dependencies (require package manager)

| Dependency | Linux | macOS | Windows |
|------------|-------|-------|---------|
| SDL2 | `libsdl2-dev` | `brew install sdl2` | Bundled |
| ALSA | `libasound2-dev` | N/A (CoreMIDI) | N/A (WinMM) |

### Prerequisites (must exist before setup)

| Tool | Linux | macOS | Windows |
|------|-------|-------|---------|
| git | `apt install git` | `xcode-select --install` | Git for Windows |
| curl | Usually bundled | Bundled | Git Bash |

Note: `gh` (GitHub CLI) is optional. If available, used for authenticated API access. Otherwise, falls back to public `curl` API.

## New Module Structure

```
ms_cli/
├── __init__.py              # Version
├── __main__.py              # Entry point
├── cli.py                   # Commands (simplified orchestration)
├── config.py                # Config TOML (exists)
│
├── platform.py              # (NEW) Platform detection
├── errors.py                # (NEW) Error messages with install hints
├── tools.py                 # (NEW) Tool resolution (direct .exe, not wrappers)
├── codebase.py              # (NEW) Codebase management
├── bridge.py                # (NEW) Bridge process management
│
└── build/                   # (NEW) Build logic
    ├── __init__.py
    ├── native.py            # SDL native (CMake + Ninja)
    ├── wasm.py              # WebAssembly (Emscripten)
    └── teensy.py            # Firmware (PlatformIO / oc-*)
```

## Key Design Decisions

### 1. Tool Resolution Strategy

**Problem**: `tools/bin/cmake` is a bash wrapper. CMake can't execute it on Windows.

**Solution**: `ToolResolver` class finds actual executables:

```python
class ToolResolver:
    def cmake(self) -> Path:
        # Try bundled first: tools/cmake/bin/cmake.exe
        # Fall back to system PATH
        return self._resolve("cmake", [
            self.tools_dir / "cmake" / "bin" / self._exe("cmake"),
        ])
```

### 2. CMake Invocation

**Problem**: CMake can't find Ninja via bash wrapper.

**Solution**: Pass `-DCMAKE_MAKE_PROGRAM` explicitly:

```python
cmake_args = [
    "-G", "Ninja",
    f"-DCMAKE_MAKE_PROGRAM={tools.ninja()}",  # Direct path
    ...
]
```

### 3. PlatformIO / oc-* Scripts

**Decision**: Use `oc-build`, `oc-upload`, `oc-monitor` when available (nice output). Fall back to raw `pio` with `--raw` flag.

```bash
ms build core           # Uses oc-build (if available)
ms build core --raw     # Uses raw pio
```

### 4. Error Messages

Platform-specific install hints:

```python
INSTALL_HINTS = {
    "cmake": InstallHint(
        fedora="sudo dnf install cmake",
        debian="sudo apt install cmake",
        arch="sudo pacman -S cmake",
        macos="brew install cmake",
        windows="choco install cmake",
    ),
    ...
}
```

## Implementation Order

### Phase 1: New Modules (no breaking changes)

| Step | File | Description |
|------|------|-------------|
| 1.1 | `ms_cli/platform.py` | Platform detection |
| 1.2 | `ms_cli/errors.py` | Error messages with hints |
| 1.3 | `ms_cli/tools.py` | Tool resolution |
| 1.4 | `ms_cli/codebase.py` | Codebase management |
| 1.5 | `ms_cli/bridge.py` | Bridge process management |

### Phase 2: Build Modules (no breaking changes)

| Step | File | Description |
|------|------|-------------|
| 2.1 | `ms_cli/build/__init__.py` | Exports |
| 2.2 | `ms_cli/build/teensy.py` | Teensy builds |
| 2.3 | `ms_cli/build/native.py` | Native SDL builds |
| 2.4 | `ms_cli/build/wasm.py` | WASM builds |

### Phase 3: Command Migration

| Step | Command | Test |
|------|---------|------|
| 3.1 | `ms build core` | Teensy build |
| 3.2 | `ms build core native` | Native build |
| 3.3 | `ms build core wasm` | WASM build |
| 3.4 | `ms upload core` | Teensy upload |
| 3.5 | `ms core` | Shortcut |
| 3.6 | Repeat for bitwig | All targets |
| 3.7 | `ms run core` | Native + bridge |
| 3.8 | `ms web core` | WASM + serve |
| 3.9 | `ms monitor core` | Serial monitor |
| 3.10 | `ms clean` | Clean builds |
| 3.11 | `ms list` | List codebases |

### Phase 4: Bootstrap Migration

| Step | Action |
|------|--------|
| 4.1 | Create minimal `setup.sh` (~50-80 lines) |
| 4.2 | Implement `ms setup --bootstrap` |
| 4.3 | Test full bootstrap flow |

### Phase 5: Cleanup

| Step | Action |
|------|--------|
| 5.1 | Rename `commands/ms-legacy` → `commands/ms-legacy.deprecated` |
| 5.2 | Remove `_delegate_to_legacy()` from cli.py |
| 5.3 | Remove temporary Windows workarounds |
| 5.4 | Archive old `setup.sh` as `setup.sh.deprecated` |

## Testing Matrix

| Command | Linux | macOS | Windows |
|---------|-------|-------|---------|
| `ms build core` (teensy) | ☐ | ☐ | ☐ |
| `ms build core native` | ☐ | ☐ | ☐ |
| `ms build core wasm` | ☐ | ☐ | ☐ |
| `ms run core` | ☐ | ☐ | ☐ |
| `ms web core` | ☐ | ☐ | ☐ |
| `ms build bitwig` | ☐ | ☐ | ☐ |
| `ms run bitwig` | ☐ | ☐ | ☐ |
| `ms setup` | ☐ | ☐ | ☐ |
| `ms setup --bootstrap` | ☐ | ☐ | ☐ |

## Rollback Plan

If issues arise:
1. `commands/ms-legacy.deprecated` can be renamed back
2. `setup.sh.deprecated` can be restored
3. `_delegate_to_legacy()` can be re-enabled

## Notes

- Bridge ports are hardcoded in C++ source files (extracted via regex)
- SDL2 is system dependency on Linux/macOS, bundled on Windows
- PlatformIO installs to `~/.platformio` (not in workspace)
- Emscripten tools are Python scripts (call via `sys.executable`)
