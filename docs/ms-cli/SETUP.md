# Setup

## 1. Bootstrap (safe)

From the workspace root:

```bash
./setup.sh
source ~/.bashrc   # or restart terminal
```

Shell completions:

```bash
ms completion bash   # print script
ms completion zsh
```

Contract:

- `setup.sh` installs missing tools only (no upgrades, no git pulls, no builds)

## 2. Diagnose

```bash
ms doctor
ms verify
```

## 3. Build project artifacts

```bash
ms setup
```

## Bridge

```bash
ms bridge          # oc-bridge TUI (monitors service if running)
ms bridge install  # install service
ms bridge uninstall
```

## Shortcuts

If `commands/` is in your PATH (via `./setup.sh`), you also get:

```bash
bitwig-dev           # upload bitwig (default)
bitwig-dev monitor   # monitor bitwig
bitwig-dev --release # upload bitwig release

core-dev
core-dev monitor
```

This builds:

- `open-control/bridge` (Rust) -> `oc-bridge`
- Bitwig host extension (Maven) and deploys it to your Bitwig Extensions folder

## 4. Update (explicit)

```bash
ms update
```

Useful flags:

- `ms update --dry-run`
- `ms update --python`
- `ms update --tools`
- `ms update --repos`
