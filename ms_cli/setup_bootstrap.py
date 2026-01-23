"""
Bootstrap tool installation for ms setup --bootstrap.

Downloads and installs workspace-managed tools:
- cmake, ninja, zig, bun
- jdk, maven
- emscripten SDK
- platformio
- SDL2 (Windows only)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request

from .platform import detect_platform, is_windows, detect_linux_distro


def log_info(msg: str) -> None:
    print(f"[INFO] {msg}")


def log_ok(msg: str) -> None:
    print(f"\033[32m[OK]\033[0m {msg}")


def log_warn(msg: str) -> None:
    print(f"\033[33m[WARN]\033[0m {msg}")


def log_error(msg: str) -> None:
    print(f"\033[31m[ERROR]\033[0m {msg}", file=sys.stderr)


# =============================================================================
# Download Utilities
# =============================================================================


def download_file(url: str, dest: Path) -> None:
    """Download a file from URL."""
    log_info(f"Downloading {url.split('/')[-1]}...")
    req = Request(url, headers={"User-Agent": "ms-cli/1.0"})
    with urlopen(req, timeout=120) as response:
        dest.write_bytes(response.read())


def extract_archive(archive: Path, dest: Path, strip_components: int = 1) -> None:
    """Extract tar.gz, tar.xz, or zip archive."""
    dest.mkdir(parents=True, exist_ok=True)

    if archive.suffix == ".zip" or archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            if strip_components == 0:
                zf.extractall(dest)
            else:
                # Strip leading directory components
                for member in zf.namelist():
                    parts = member.split("/")
                    if len(parts) > strip_components:
                        target = dest / "/".join(parts[strip_components:])
                        if member.endswith("/"):
                            target.mkdir(parents=True, exist_ok=True)
                        else:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(member) as src, open(target, "wb") as dst:
                                dst.write(src.read())
    else:
        # tar.gz or tar.xz
        mode = "r:gz" if ".gz" in archive.name else "r:xz"
        with tarfile.open(archive, mode) as tf:
            if strip_components == 0:
                tf.extractall(dest)
            else:
                for member in tf.getmembers():
                    parts = member.name.split("/")
                    if len(parts) > strip_components:
                        member.name = "/".join(parts[strip_components:])
                        tf.extract(member, dest)


def download_and_extract(url: str, dest: Path, strip_components: int = 1) -> None:
    """Download and extract an archive."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(url).suffix) as tmp:
        tmp_path = Path(tmp.name)

    try:
        download_file(url, tmp_path)
        extract_archive(tmp_path, dest, strip_components)
    finally:
        tmp_path.unlink(missing_ok=True)


def get_github_latest_release(repo: str) -> str:
    """Get latest release version from GitHub."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = Request(url, headers={"User-Agent": "ms-cli/1.0"})
    with urlopen(req, timeout=30) as response:
        data = json.loads(response.read())
        return data["tag_name"].lstrip("v")


def fetch_json(url: str) -> dict:
    """Fetch JSON from URL."""
    req = Request(url, headers={"User-Agent": "ms-cli/1.0"})
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read())


# =============================================================================
# Architecture Detection
# =============================================================================


def get_arch() -> str:
    """Get architecture: x64 or arm64."""
    import platform as _platform

    machine = _platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    return machine


# =============================================================================
# Tool Installation Functions
# =============================================================================


def setup_cmake(tools_dir: Path) -> bool:
    """Install CMake."""
    cmake_dir = tools_dir / "cmake"
    cmake_bin = cmake_dir / "bin" / ("cmake.exe" if is_windows() else "cmake")

    if cmake_bin.exists():
        log_ok("cmake (already installed)")
        return True

    version = get_github_latest_release("Kitware/CMake")
    log_info(f"Installing cmake {version}...")

    platform = detect_platform()
    arch = get_arch()

    if platform == "linux":
        asset = (
            f"cmake-{version}-linux-{'x86_64' if arch == 'x64' else 'aarch64'}.tar.gz"
        )
    elif platform == "macos":
        asset = f"cmake-{version}-macos-universal.tar.gz"
    elif platform == "windows":
        asset = f"cmake-{version}-windows-x86_64.zip"
    else:
        log_error(f"Unsupported platform: {platform}")
        return False

    url = f"https://github.com/Kitware/CMake/releases/download/v{version}/{asset}"
    download_and_extract(url, cmake_dir)

    # macOS: extract from CMake.app bundle
    if platform == "macos" and (cmake_dir / "CMake.app").exists():
        for item in (cmake_dir / "CMake.app" / "Contents").iterdir():
            shutil.move(str(item), str(cmake_dir / item.name))
        shutil.rmtree(cmake_dir / "CMake.app")

    log_ok(f"cmake {version}")
    return True


def setup_ninja(tools_dir: Path) -> bool:
    """Install Ninja."""
    ninja_dir = tools_dir / "ninja"
    ninja_bin = ninja_dir / ("ninja.exe" if is_windows() else "ninja")

    if ninja_bin.exists():
        log_ok("ninja (already installed)")
        return True

    version = get_github_latest_release("ninja-build/ninja")
    log_info(f"Installing ninja {version}...")

    platform = detect_platform()
    arch = get_arch()

    if platform == "linux":
        asset = f"ninja-linux{'-aarch64' if arch == 'arm64' else ''}.zip"
    elif platform == "macos":
        asset = "ninja-mac.zip"
    elif platform == "windows":
        asset = "ninja-win.zip"
    else:
        log_error(f"Unsupported platform: {platform}")
        return False

    url = f"https://github.com/ninja-build/ninja/releases/download/v{version}/{asset}"
    download_and_extract(url, ninja_dir, strip_components=0)

    if not is_windows():
        ninja_bin.chmod(0o755)

    log_ok(f"ninja {version}")
    return True


def setup_zig(tools_dir: Path, python: Path) -> bool:
    """Install Zig."""
    zig_dir = tools_dir / "zig"
    zig_bin = zig_dir / ("zig.exe" if is_windows() else "zig")

    if zig_bin.exists():
        # Check for dev version
        result = subprocess.run(
            [str(zig_bin), "version"], capture_output=True, text=True
        )
        if result.returncode == 0:
            ver = result.stdout.strip()
            if "-dev" not in ver:
                log_ok(f"zig {ver} (already installed)")
                return True
            log_warn(f"zig {ver} (dev build) - reinstalling stable")
            shutil.rmtree(zig_dir)

    log_info("Installing zig (latest stable)...")

    platform = detect_platform()
    arch = get_arch()

    zig_platform_map = {
        ("linux", "x64"): "x86_64-linux",
        ("linux", "arm64"): "aarch64-linux",
        ("macos", "x64"): "x86_64-macos",
        ("macos", "arm64"): "aarch64-macos",
        ("windows", "x64"): "x86_64-windows",
        ("windows", "arm64"): "aarch64-windows",
    }

    zig_platform = zig_platform_map.get((platform, arch))
    if not zig_platform:
        log_error(f"Unsupported platform: {platform}-{arch}")
        return False

    # Get latest stable version from ziglang.org
    data = fetch_json("https://ziglang.org/download/index.json")
    stable_versions = [k for k in data.keys() if re.fullmatch(r"\d+\.\d+\.\d+", k)]
    stable_versions.sort(key=lambda s: tuple(map(int, s.split("."))))

    if not stable_versions:
        log_error("No stable Zig versions found")
        return False

    version = stable_versions[-1]
    url = data[version][zig_platform]["tarball"]

    download_and_extract(url, zig_dir)
    _create_zig_wrappers(tools_dir)
    log_ok(f"zig {version}")
    return True


def _create_zig_wrappers(tools_dir: Path) -> None:
    """Create zig-cc/zig-cxx wrappers for CMake compatibility.

    Zig requires 'zig cc' subcommand but CMake calls the compiler directly.
    These wrappers translate the invocation.
    """
    bin_dir = tools_dir / "bin"
    bin_dir.mkdir(exist_ok=True)

    zig_path = tools_dir / "zig" / ("zig.exe" if is_windows() else "zig")

    if is_windows():
        (bin_dir / "zig-cc.cmd").write_text(f'@echo off\n"{zig_path}" cc %*\n')
        (bin_dir / "zig-cxx.cmd").write_text(f'@echo off\n"{zig_path}" c++ %*\n')
    else:
        cc = bin_dir / "zig-cc"
        cc.write_text(f'#!/bin/bash\nexec "{zig_path}" cc "$@"\n')
        cc.chmod(0o755)

        cxx = bin_dir / "zig-cxx"
        cxx.write_text(f'#!/bin/bash\nexec "{zig_path}" c++ "$@"\n')
        cxx.chmod(0o755)


def setup_bun(tools_dir: Path) -> bool:
    """Install Bun."""
    bun_dir = tools_dir / "bun"
    bun_bin = bun_dir / ("bun.exe" if is_windows() else "bun")

    if bun_bin.exists():
        log_ok("bun (already installed)")
        return True

    # Get latest version from GitHub
    url = "https://api.github.com/repos/oven-sh/bun/releases/latest"
    data = fetch_json(url)
    tag = data["tag_name"]

    log_info(f"Installing bun {tag}...")

    platform = detect_platform()
    arch = get_arch()

    asset_map = {
        ("linux", "x64"): "bun-linux-x64.zip",
        ("linux", "arm64"): "bun-linux-aarch64.zip",
        ("macos", "x64"): "bun-darwin-x64.zip",
        ("macos", "arm64"): "bun-darwin-aarch64.zip",
        ("windows", "x64"): "bun-windows-x64.zip",
    }

    asset = asset_map.get((platform, arch))
    if not asset:
        log_error(f"No bun build for {platform}-{arch}")
        return False

    download_url = f"https://github.com/oven-sh/bun/releases/download/{tag}/{asset}"
    download_and_extract(download_url, bun_dir, strip_components=0)

    if not is_windows():
        bun_bin.chmod(0o755)

    log_ok(f"bun {tag}")
    return True


def setup_jdk(tools_dir: Path) -> bool:
    """Install Temurin JDK 25."""
    jdk_dir = tools_dir / "jdk"

    # Check existing
    java_bin = jdk_dir / "bin" / ("java.exe" if is_windows() else "java")
    if not java_bin.exists() and detect_platform() == "macos":
        java_bin = jdk_dir / "Contents" / "Home" / "bin" / "java"

    if java_bin.exists():
        log_ok("jdk (already installed)")
        return True

    log_info("Installing Temurin JDK 25...")

    platform = detect_platform()
    arch = get_arch()

    adoptium_os = {"linux": "linux", "macos": "mac", "windows": "windows"}.get(platform)
    adoptium_arch = {"x64": "x64", "arm64": "aarch64"}.get(arch)

    if not adoptium_os or not adoptium_arch:
        log_error(f"Unsupported platform: {platform}-{arch}")
        return False

    api_url = f"https://api.adoptium.net/v3/assets/latest/25/hotspot?architecture={adoptium_arch}&image_type=jdk&os={adoptium_os}"
    data = fetch_json(api_url)

    if not data:
        log_error("Could not fetch JDK info from Adoptium")
        return False

    download_url = data[0]["binary"]["package"]["link"]
    download_and_extract(download_url, jdk_dir)

    log_ok("jdk 25")
    return True


def setup_maven(tools_dir: Path) -> bool:
    """Install Maven."""
    maven_dir = tools_dir / "maven"
    mvn_bin = maven_dir / "bin" / ("mvn.cmd" if is_windows() else "mvn")

    if mvn_bin.exists():
        log_ok("maven (already installed)")
        return True

    log_info("Resolving latest Maven 3.9.x...")

    # Get Maven metadata
    req = Request(
        "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/maven-metadata.xml",
        headers={"User-Agent": "ms-cli/1.0"},
    )
    with urlopen(req, timeout=30) as response:
        meta = response.read().decode()

    # Find latest 3.9.x
    versions = re.findall(r"<version>(3\.9\.\d+)</version>", meta)
    if not versions:
        log_error("Could not find Maven 3.9.x version")
        return False

    version = sorted(versions, key=lambda v: tuple(map(int, v.split("."))))[-1]
    log_info(f"Installing Maven {version}...")

    url = f"https://dlcdn.apache.org/maven/maven-3/{version}/binaries/apache-maven-{version}-bin.tar.gz"
    fallback_url = f"https://archive.apache.org/dist/maven/maven-3/{version}/binaries/apache-maven-{version}-bin.tar.gz"

    try:
        download_and_extract(url, maven_dir)
    except Exception:
        download_and_extract(fallback_url, maven_dir)

    log_ok(f"maven {version}")
    return True


def setup_sdl2_windows(tools_dir: Path) -> bool:
    """Install SDL2 for Windows (bundled)."""
    if not is_windows():
        return True

    sdl_dir = tools_dir / "windows" / "SDL2"

    if (sdl_dir / "lib" / "libSDL2.dll.a").exists():
        log_ok("SDL2 (already installed)")
        return True

    log_info("Installing SDL2 for Windows...")

    # Get latest SDL2 version (not SDL3)
    url = "https://api.github.com/repos/libsdl-org/SDL/releases"
    data = fetch_json(url)

    version = None
    for release in data:
        tag = release["tag_name"]
        if tag.startswith("release-2"):
            version = tag.replace("release-", "")
            break

    if not version:
        log_error("Could not find SDL2 release")
        return False

    download_url = f"https://github.com/libsdl-org/SDL/releases/download/release-{version}/SDL2-devel-{version}-mingw.tar.gz"

    sdl_dir.mkdir(parents=True, exist_ok=True)
    download_and_extract(download_url, sdl_dir)

    # Move x86_64-w64-mingw32 contents to root
    mingw_dir = sdl_dir / f"SDL2-{version}" / "x86_64-w64-mingw32"
    if mingw_dir.exists():
        for item in mingw_dir.iterdir():
            shutil.move(str(item), str(sdl_dir / item.name))
        shutil.rmtree(sdl_dir / f"SDL2-{version}")

    log_ok(f"SDL2 {version}")
    return True


def setup_emscripten(tools_dir: Path, python: Path) -> bool:
    """Install Emscripten SDK."""
    emsdk_dir = tools_dir / "emsdk"
    emcc = (
        emsdk_dir / "upstream" / "emscripten" / ("emcc.bat" if is_windows() else "emcc")
    )

    if emcc.exists():
        log_ok("emscripten (already installed)")
        return True

    log_info("Installing Emscripten SDK (this may take a while)...")

    if not emsdk_dir.exists():
        subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "https://github.com/emscripten-core/emsdk.git",
                str(emsdk_dir),
            ],
            check=True,
        )

    emsdk_py = emsdk_dir / "emsdk.py"
    subprocess.run(
        [str(python), str(emsdk_py), "install", "latest"], cwd=emsdk_dir, check=True
    )
    subprocess.run(
        [str(python), str(emsdk_py), "activate", "latest"], cwd=emsdk_dir, check=True
    )

    log_ok("emscripten (latest)")
    return True


def setup_platformio(tools_dir: Path, python: Path) -> bool:
    """Install PlatformIO."""
    home = Path.home()
    pio_bin = (
        home
        / ".platformio"
        / "penv"
        / ("Scripts" if is_windows() else "bin")
        / ("pio.exe" if is_windows() else "pio")
    )

    if pio_bin.exists():
        log_ok("platformio (already installed)")
        return True

    log_info("Installing PlatformIO...")

    # Download installer
    with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tmp:
        tmp_path = Path(tmp.name)

    try:
        download_file(
            "https://raw.githubusercontent.com/platformio/platformio-core-installer/master/get-platformio.py",
            tmp_path,
        )
        subprocess.run([str(python), str(tmp_path)], check=True)
    finally:
        tmp_path.unlink(missing_ok=True)

    log_ok("platformio")
    return True


# =============================================================================
# System Dependencies Check
# =============================================================================


def check_system_deps() -> list[str]:
    """Check system dependencies (SDL2, ALSA). Returns list of missing deps."""
    missing = []
    platform = detect_platform()

    if platform == "linux":
        # Check pkg-config
        if shutil.which("pkg-config") is None:
            return ["pkg-config"]

        # SDL2
        result = subprocess.run(["pkg-config", "--exists", "sdl2"], capture_output=True)
        if result.returncode != 0:
            missing.append("SDL2")

        # ALSA
        result = subprocess.run(["pkg-config", "--exists", "alsa"], capture_output=True)
        if result.returncode != 0:
            missing.append("ALSA")

    elif platform == "macos":
        # Check brew and SDL2
        result = subprocess.run(["brew", "list", "sdl2"], capture_output=True)
        if result.returncode != 0:
            missing.append("SDL2")

    # Windows: SDL2 is bundled, no system deps needed

    return missing


def print_install_instructions(missing: list[str]) -> None:
    """Print install instructions for missing system deps."""
    platform = detect_platform()
    distro = detect_linux_distro()

    print()
    log_error(f"Missing system dependencies: {', '.join(missing)}")
    print()
    print("Install with your package manager:")

    if platform == "linux":
        if distro == "fedora":
            print("  sudo dnf install SDL2-devel alsa-lib-devel")
        elif distro == "debian":
            print("  sudo apt install libsdl2-dev libasound2-dev")
        elif distro == "arch":
            print("  sudo pacman -S sdl2 alsa-lib")
        else:
            print("  # Install SDL2 and ALSA dev packages for your distro")
    elif platform == "macos":
        print("  brew install sdl2")

    print()
    print("Then re-run: ms setup --bootstrap")


# =============================================================================
# Main Bootstrap Function
# =============================================================================


def run_bootstrap(
    workspace: Path,
    *,
    skip_system_check: bool = False,
    skip_clone: bool = False,
) -> int:
    """
    Run full bootstrap installation.

    Returns:
        Exit code (0 = success)
    """
    tools_dir = workspace / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    # Find Python in venv
    venv_python = (
        workspace
        / ".venv"
        / ("Scripts" if is_windows() else "bin")
        / ("python.exe" if is_windows() else "python")
    )
    if not venv_python.exists():
        venv_python = Path(sys.executable)

    print()
    print("==========================================")
    print(" MIDI Studio - Bootstrap")
    print("==========================================")
    print()

    # 1. Check system dependencies
    if not skip_system_check:
        log_info("Checking system dependencies...")
        missing = check_system_deps()
        if missing:
            print_install_instructions(missing)
            print("Press Enter when done (or Ctrl+C to cancel)...")
            try:
                input()
            except KeyboardInterrupt:
                print()
                return 1

            # Verify again
            missing = check_system_deps()
            if missing:
                log_error("Dependencies still missing")
                return 1

        log_ok("System dependencies OK")

    print()
    log_info("=== Installing build tools ===")

    # 2. Install tools
    success = True
    success &= setup_cmake(tools_dir)
    success &= setup_ninja(tools_dir)
    success &= setup_zig(tools_dir, venv_python)
    success &= setup_bun(tools_dir)
    success &= setup_jdk(tools_dir)
    success &= setup_maven(tools_dir)
    success &= setup_sdl2_windows(tools_dir)
    success &= setup_emscripten(tools_dir, venv_python)
    success &= setup_platformio(tools_dir, venv_python)

    if not success:
        log_error("Some tools failed to install")
        return 1

    print()
    log_ok("All tools installed")

    # 3. Build bridge and extension (reuse existing setup command logic)
    print()
    log_info("=== Building project components ===")
    print("Run: ms setup  (to build bridge + extension)")

    print()
    print("==========================================")
    log_ok("Bootstrap complete!")
    print()
    print("Next steps:")
    print("  1. Restart terminal (or: source ~/.bashrc)")
    print("  2. Run: ms setup  (build bridge + extension)")
    print("  3. Run: ms doctor (verify installation)")
    print("==========================================")

    return 0
