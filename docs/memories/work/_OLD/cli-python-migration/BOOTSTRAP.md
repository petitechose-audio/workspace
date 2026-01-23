# Bootstrap Specification

**Parent**: [README.md](./README.md)

## Overview

The bootstrap process has two parts:
1. **`setup.sh`** (~50-80 lines bash): Minimal bootstrap to get Python running
2. **`ms setup --bootstrap`** (Python): Full environment setup

## Current setup.sh Reference

**Location**: `setup.sh` (workspace root)
**Lines**: ~1000
**Status**: To be simplified

The current script does everything. We will extract only the minimal bootstrap.

## New setup.sh Specification

```bash
#!/usr/bin/env bash
# =============================================================================
# MIDI Studio - Minimal Bootstrap
# =============================================================================
# Installs uv + Python, then hands off to Python for the rest.
#
# Usage: ./setup.sh [options]
#
# Options are passed through to: ms setup --bootstrap [options]
#
# Prerequisites:
#   - git (for cloning repos)
#   - curl (for downloading uv)
# =============================================================================

set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$WORKSPACE/tools"

# -----------------------------------------------------------------------------
# Colors
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

log_info()  { echo -e "[INFO] $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# -----------------------------------------------------------------------------
# OS Detection
# -----------------------------------------------------------------------------
detect_os() {
    case "$(uname -s)" in
        Linux*)  echo "linux" ;;
        Darwin*) echo "macos" ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *) echo "unknown" ;;
    esac
}

OS="$(detect_os)"

# -----------------------------------------------------------------------------
# Prerequisites Check
# -----------------------------------------------------------------------------
check_prerequisites() {
    local missing=()
    
    command -v git &>/dev/null || missing+=("git")
    command -v curl &>/dev/null || missing+=("curl")
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing prerequisites: ${missing[*]}"
        echo ""
        echo "Install first:"
        case "$OS" in
            linux)   echo "  sudo apt install git curl  # or equivalent" ;;
            macos)   echo "  xcode-select --install" ;;
            windows) echo "  Install Git for Windows: https://git-scm.com/" ;;
        esac
        exit 1
    fi
    
    log_ok "Prerequisites OK (git, curl)"
}

# -----------------------------------------------------------------------------
# Install uv (Python package manager)
# -----------------------------------------------------------------------------
install_uv() {
    local uv_dir="$TOOLS_DIR/uv"
    local uv_bin="$uv_dir/uv"
    [[ "$OS" == "windows" ]] && uv_bin="$uv_dir/uv.exe"
    
    if [[ -x "$uv_bin" ]]; then
        log_ok "uv already installed"
        return 0
    fi
    
    log_info "Installing uv..."
    mkdir -p "$uv_dir"
    
    # Use uv's official installer
    curl -fsSL https://astral.sh/uv/install.sh | \
        CARGO_HOME="$uv_dir" sh -s -- --no-modify-path -q
    
    if [[ ! -x "$uv_bin" ]]; then
        log_error "Failed to install uv"
        exit 1
    fi
    
    log_ok "uv installed"
}

# -----------------------------------------------------------------------------
# Install Python via uv
# -----------------------------------------------------------------------------
install_python() {
    local uv_bin="$TOOLS_DIR/uv/uv"
    [[ "$OS" == "windows" ]] && uv_bin="$TOOLS_DIR/uv/uv.exe"
    
    local python_dir="$TOOLS_DIR/python"
    
    log_info "Installing Python 3.13 via uv..."
    UV_PYTHON_INSTALL_DIR="$python_dir" "$uv_bin" python install 3.13 --quiet
    
    log_ok "Python 3.13 installed"
}

# -----------------------------------------------------------------------------
# Create/sync virtualenv
# -----------------------------------------------------------------------------
setup_venv() {
    local uv_bin="$TOOLS_DIR/uv/uv"
    [[ "$OS" == "windows" ]] && uv_bin="$TOOLS_DIR/uv/uv.exe"
    
    local python_dir="$TOOLS_DIR/python"
    local venv_dir="$WORKSPACE/.venv"
    
    if [[ ! -d "$venv_dir" ]]; then
        log_info "Creating virtualenv..."
        UV_PYTHON_INSTALL_DIR="$python_dir" "$uv_bin" venv \
            --python 3.13 "$venv_dir" --quiet
    fi
    
    if [[ -f "$WORKSPACE/pyproject.toml" ]]; then
        log_info "Syncing Python dependencies..."
        UV_PYTHON_INSTALL_DIR="$python_dir" "$uv_bin" sync --frozen --quiet
    fi
    
    log_ok "Python environment ready"
}

# -----------------------------------------------------------------------------
# Find Python in venv
# -----------------------------------------------------------------------------
find_python() {
    local venv_dir="$WORKSPACE/.venv"
    
    if [[ "$OS" == "windows" ]]; then
        echo "$venv_dir/Scripts/python.exe"
    else
        echo "$venv_dir/bin/python"
    fi
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    echo ""
    echo "=========================================="
    echo " MIDI Studio - Bootstrap"
    echo "=========================================="
    echo ""
    
    check_prerequisites
    install_uv
    install_python
    setup_venv
    
    local python
    python="$(find_python)"
    
    if [[ ! -x "$python" ]]; then
        log_error "Python not found at: $python"
        exit 1
    fi
    
    echo ""
    log_ok "Bootstrap complete, handing off to Python..."
    echo ""
    
    # Hand off to Python for the rest
    exec "$python" -m ms_cli setup --bootstrap "$@"
}

main "$@"
```

## ms setup --bootstrap Specification

When called with `--bootstrap`, `ms setup` performs:

1. **Check system dependencies** (SDL2, ALSA on Linux)
   - If missing: show install commands, wait for user

2. **Install bundled tools** (cmake, ninja, jdk, maven, emsdk, pio, etc.)
   - Download from official sources
   - Install to `tools/`

3. **Clone repos** (if `--clone` flag or first run)
   - Clone `open-control/*` repos
   - Clone `midi-studio/*` repos

4. **Configure shell** (PATH, JAVA_HOME, etc.)
   - Detect shell config file
   - Add configuration block
   - Suggest `source` or restart

5. **Build project components**
   - Bridge (cargo build)
   - Bitwig extension (maven)

6. **Verify installation**
   - Check all tools accessible
   - Print summary

## Flow Diagram

```
User runs: ./setup.sh
              │
              ▼
┌─────────────────────────────┐
│  setup.sh (Bash)            │
│  ~50-80 lines               │
├─────────────────────────────┤
│  1. Check: git, curl        │
│  2. Install uv              │
│  3. Install Python 3.13     │
│  4. Create .venv + sync     │
│  5. exec: ms setup --bootstrap
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  ms setup --bootstrap       │
│  (Python)                   │
├─────────────────────────────┤
│  1. Check system deps       │
│     → Show install cmds     │
│     → Wait for Enter        │
│                             │
│  2. Install bundled tools   │
│     → cmake, ninja, zig     │
│     → bun, jdk, maven       │
│     → emsdk, platformio     │
│     → SDL2 (Windows)        │
│                             │
│  3. Clone repos (optional)  │
│     → open-control/*        │
│     → midi-studio/*         │
│                             │
│  4. Configure shell         │
│     → Add to .bashrc/.zshrc │
│     → Suggest source        │
│                             │
│  5. Build components        │
│     → Bridge (cargo)        │
│     → Bitwig ext (maven)    │
│                             │
│  6. Verify & summary        │
└─────────────────────────────┘
```

## Subsequent Runs

After first install, user runs `ms setup` directly:

```
User runs: ms setup
              │
              ▼
┌─────────────────────────────┐
│  ms setup (no --bootstrap)  │
├─────────────────────────────┤
│  1. Check PATH is correct   │
│     → Suggest source if not │
│                             │
│  2. Build bridge            │
│                             │
│  3. Build Bitwig extension  │
│                             │
│  4. Summary                 │
└─────────────────────────────┘
```

## Interactive System Dependencies Flow

When system dependencies are missing:

```
$ ms setup --bootstrap

Checking system dependencies...

Missing: SDL2, ALSA

These are system packages that require sudo to install.
Please open a new terminal and run:

  sudo apt install libsdl2-dev libasound2-dev

Press Enter when done (or Ctrl+C to cancel)...
[User presses Enter]

Verifying... OK

Continuing with setup...
```
