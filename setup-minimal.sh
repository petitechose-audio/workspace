#!/usr/bin/env bash
# =============================================================================
# MIDI Studio - Minimal Bootstrap
# =============================================================================
# Installs uv + Python, then hands off to Python for the rest.
#
# Usage: ./setup-minimal.sh [options]
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
    
    # Detect architecture
    local arch
    case "$(uname -m)" in
        x86_64|amd64) arch="x64" ;;
        aarch64|arm64) arch="arm64" ;;
        *) log_error "Unsupported architecture: $(uname -m)"; exit 1 ;;
    esac
    
    # Get latest version from GitHub API
    local version
    version=$(curl -fsSL "https://api.github.com/repos/astral-sh/uv/releases/latest" | grep -oP '"tag_name":\s*"\K[^"]+')
    
    # Download appropriate binary
    local asset
    case "$OS-$arch" in
        linux-x64)   asset="uv-x86_64-unknown-linux-gnu.tar.gz" ;;
        linux-arm64) asset="uv-aarch64-unknown-linux-gnu.tar.gz" ;;
        macos-x64)   asset="uv-x86_64-apple-darwin.tar.gz" ;;
        macos-arm64) asset="uv-aarch64-apple-darwin.tar.gz" ;;
        windows-x64) asset="uv-x86_64-pc-windows-msvc.zip" ;;
        windows-arm64) asset="uv-aarch64-pc-windows-msvc.zip" ;;
        *) log_error "No uv build for $OS-$arch"; exit 1 ;;
    esac
    
    local url="https://github.com/astral-sh/uv/releases/download/${version}/${asset}"
    local tmp_file
    tmp_file=$(mktemp)
    
    log_info "Downloading uv $version..."
    curl -fsSL "$url" -o "$tmp_file"
    
    # Extract
    case "$asset" in
        *.zip)
            unzip -q "$tmp_file" -d "$uv_dir"
            ;;
        *.tar.gz)
            tar -xzf "$tmp_file" -C "$uv_dir" --strip-components=1
            ;;
    esac
    
    rm -f "$tmp_file"
    chmod +x "$uv_dir/uv" "$uv_dir/uvx" 2>/dev/null || true
    
    if [[ ! -x "$uv_bin" ]]; then
        log_error "Failed to install uv"
        exit 1
    fi
    
    log_ok "uv $version installed"
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
