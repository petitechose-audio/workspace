# Manual Test Matrix

Run these commands from the workspace root.

## 1) Fresh bootstrap simulation

```bash
rm -rf tools .venv
./setup.sh
source ~/.bashrc   # or restart terminal
```

Expected:

- tools get installed under `tools/`
- `.venv` is created and python deps are synced
- `ms` is available

## 2) Doctor + verify

```bash
ms doctor
ms verify
```

Expected:

- `ms doctor` prints guided checks (tools + system deps)
- `ms verify` exits 0

## 3) Update (dry-run)

```bash
ms update --dry-run
```

Expected:

- prints planned actions
- does not modify the environment

## 4) Build setup

```bash
ms setup
ms verify
```

Expected:

- `oc-bridge` is built (cargo release)
- Bitwig host extension is built and deployed (if Bitwig Extensions dir exists)

## 5) Repos update (optional)

```bash
ms update --repos
```

Expected:

- clean repos are fast-forwarded
- dirty repos are skipped with a clear message

## 6) Assets (optional)

```bash
ms icons core
ms icons bitwig
```

Expected:

- if Inkscape/FontForge are missing: guided error
- if installed: generates TTF + header + LVGL binary fonts

## Platform notes

### Windows

- Use Git Bash (Git for Windows)
- Recommended: `winget install Git.Git GitHub.cli`

### macOS

- Ensure Homebrew is installed
- SDL2 is required: `brew install sdl2`
