from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.padding import Padding
from rich.rule import Rule
from rich.text import Text

from . import __version__
from .config import load_config

# New modular imports
from .platform import detect_platform as _detect_platform
from .codebase import resolve_codebase, list_codebases, CodebaseNotFoundError
from .tools import ToolResolver, ToolNotFoundError, run_tool
from .build.teensy import build_teensy, upload_teensy, monitor_teensy
from .build.native import build_native, run_native
from .build.wasm import build_wasm, serve_wasm


app = typer.Typer(add_completion=False, no_args_is_help=False)
console = Console()


class ExitCode:
    OK = 0
    USER_ERROR = 1
    ENV_ERROR = 2
    BUILD_ERROR = 3


def workspace_root() -> Path:
    env = os.environ.get("WORKSPACE_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p

    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        if (parent / "commands").is_dir() and (parent / "config.toml").exists():
            return parent

    # Fallback (expected to work when running from the workspace checkout)
    return Path(__file__).resolve().parents[1]


def run_subprocess(
    cmd: list[str],
    *,
    check: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        cwd=str(cwd) if cwd else None,
    )


def get_bin_root() -> Path:
    """Get bin output directory."""
    return workspace_root() / "bin"


def get_build_root() -> Path:
    """Get build directory."""
    return workspace_root() / ".build"


def get_tools() -> ToolResolver:
    """Get tool resolver for current workspace."""
    return ToolResolver(workspace_root())


def run_live(cmd: list[str], *, cwd: Path) -> int:
    """Run a command with live output."""
    proc = subprocess.run(cmd, cwd=str(cwd))
    return proc.returncode


def which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def detect_platform() -> str:
    """Detect platform (uses new platform module)."""
    return _detect_platform()


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _iter_child_repos(parent: Path) -> list[Path]:
    if not parent.is_dir():
        return []
    repos: list[Path] = []
    for child in parent.iterdir():
        if child.is_dir() and _is_git_repo(child):
            repos.append(child)
    repos.sort(key=lambda p: p.name)
    return repos


def _parse_git_porcelain(status: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (branch_line, entries).

    entries: list of (XY, path) where XY is the 2-char porcelain status.
    """

    lines = [ln.rstrip("\n") for ln in status.splitlines() if ln.strip()]
    if not lines:
        return ("", [])

    branch = lines[0]
    entries: list[tuple[str, str]] = []

    for ln in lines[1:]:
        if ln.startswith("?? "):
            entries.append(("??", ln[3:]))
            continue

        if len(ln) < 4:
            continue

        entries.append((ln[:2], ln[3:]))

    return (branch, entries)


def _parse_branch_line(branch_line: str) -> tuple[str, str | None]:
    s = branch_line.strip()
    if s.startswith("##"):
        s = s[2:].lstrip()
    s = s.split(" [", 1)[0].strip()
    if "..." in s:
        left, right = s.split("...", 1)
        return (left.strip(), right.strip())
    return (s, None)


def _pretty_xy(xy: str) -> str:
    # Make whitespace visible; " M" -> ".M", "M " -> "M."
    return xy.replace(" ", ".")


def _xy_style(xy: str) -> str:
    # Muted palette: dim + small semantic hint.
    if "?" in xy:
        return "dim magenta"
    if "D" in xy:
        return "dim red"
    if "A" in xy:
        return "dim green"
    if "R" in xy or "C" in xy:
        return "dim cyan"
    if "M" in xy:
        return "dim yellow"
    return "dim"


def _ahead_behind(branch_line: str) -> tuple[int, int]:
    ahead = 0
    behind = 0
    m = re.search(r"\[([^\]]+)\]", branch_line)
    if not m:
        return (0, 0)
    inside = m.group(1)
    ma = re.search(r"ahead\s+(\d+)", inside)
    mb = re.search(r"behind\s+(\d+)", inside)
    if ma:
        ahead = int(ma.group(1))
    if mb:
        behind = int(mb.group(1))
    return (ahead, behind)


def print_kv(key: str, value: str) -> None:
    console.print(f"[bold]{key}[/]: {value}")


def first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def check_cmd(
    name: str, version_args: list[str] | None = None, *, required: bool = True
) -> bool:
    path = which(name)
    if not path:
        style = "red" if required else "yellow"
        console.print(f"{name}: missing", style=style)
        return not required

    extra = ""
    if version_args:
        proc = run_subprocess([name, *version_args])
        if proc.returncode == 0:
            extra = first_line(proc.stdout + proc.stderr)

    msg = f"{name}: {extra}" if extra else f"{name}: ok"
    console.print(msg, style="green")
    return True


def check_tool(
    tools: ToolResolver,
    name: str,
    version_args: list[str] | None = None,
    *,
    required: bool = True,
) -> bool:
    """Check a tool using ToolResolver (handles bundled tools and .cmd files)."""
    try:
        resolver_method = getattr(tools, name, None)
        if resolver_method is None:
            raise ToolNotFoundError(name)
        path = resolver_method()
    except ToolNotFoundError:
        style = "red" if required else "yellow"
        console.print(f"{name}: missing", style=style)
        return not required

    extra = ""
    if version_args:
        proc = run_tool(path, version_args, capture=True)
        if proc.returncode == 0:
            extra = first_line(proc.stdout + proc.stderr)

    msg = f"{name}: {extra}" if extra else f"{name}: ok"
    console.print(msg, style="green")
    return True


def check_path(label: str, path: Path, *, required: bool = True) -> bool:
    if path.exists():
        console.print(f"{label}: ok ({path})", style="green")
        return True
    style = "red" if required else "yellow"
    console.print(f"{label}: missing ({path})", style=style)
    return not required


def list_git_repos(base: Path) -> list[Path]:
    if not base.is_dir():
        return []

    repos: list[Path] = []
    for child in base.iterdir():
        if not child.is_dir():
            continue
        if (child / ".git").is_dir():
            repos.append(child)
    return sorted(repos)


def git_is_clean(repo: Path) -> bool:
    proc = run_subprocess(["git", "-C", str(repo), "status", "--porcelain"])
    return proc.returncode == 0 and proc.stdout.strip() == ""


def git_has_upstream(repo: Path) -> bool:
    proc = run_subprocess(
        [
            "git",
            "-C",
            str(repo),
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]
    )
    return proc.returncode == 0


def git_pull_ff_only(repo: Path) -> subprocess.CompletedProcess[str]:
    return run_subprocess(["git", "-C", str(repo), "pull", "--ff-only"])


def reexec_ms(args: list[str]) -> None:
    os.execv(sys.executable, [sys.executable, "-m", "ms_cli", *args])


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        console.print(__version__)
        raise typer.Exit(code=ExitCode.OK)

    if ctx.invoked_subcommand is None:
        if not sys.stdin.isatty():
            # Non-interactive: show help for predictable scripting.
            console.print(ctx.get_help())
            raise typer.Exit(code=ExitCode.OK)

        # Interactive mode
        console.print("MIDI Studio CLI")
        console.print("")
        console.print("1) doctor")
        console.print("2) verify")
        console.print("3) setup")
        console.print("4) update (dry-run)")
        console.print("5) bridge (TUI)")
        console.print("6) run core")
        console.print("7) web core")
        console.print("8) run bitwig")
        console.print("9) web bitwig")
        console.print("0) quit")
        console.print("")

        choice = typer.prompt("Select", default="1")
        mapping: dict[str, list[str]] = {
            "1": ["doctor"],
            "2": ["verify"],
            "3": ["setup"],
            "4": ["update", "--dry-run"],
            "5": ["bridge"],
            "6": ["run", "core"],
            "7": ["web", "core"],
            "8": ["run", "bitwig"],
            "9": ["web", "bitwig"],
            "0": [],
        }

        args = mapping.get(choice)
        if args is None:
            console.print("invalid choice", style="red")
            raise typer.Exit(code=ExitCode.USER_ERROR)
        if not args:
            raise typer.Exit(code=ExitCode.OK)

        reexec_ms(args)


@app.command()
def doctor(
    json: bool = typer.Option(
        False, "--json", help="Output JSON (not implemented yet)."
    ),
) -> None:
    """Diagnose environment and suggest fixes."""

    if json:
        console.print("error: --json not implemented yet", style="red")
        raise typer.Exit(code=ExitCode.USER_ERROR)

    root = workspace_root()
    platform_id = detect_platform()

    print_kv("workspace", str(root))
    print_kv("platform", f"{platform_id} ({platform.platform()})")

    pyver = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    print_kv("python", f"{pyver} ({sys.executable})")

    failed = False

    console.print("\n[bold]Workspace[/]")
    if not (root / "open-control").is_dir():
        console.print("open-control: missing (run ./setup.sh)", style="red")
        failed = True
    else:
        console.print("open-control: ok", style="green")

    if not (root / "midi-studio").is_dir():
        console.print("midi-studio: missing (run ./setup.sh)", style="red")
        failed = True
    else:
        console.print("midi-studio: ok", style="green")

    cfg = None
    cfg_path = root / "config.toml"
    if cfg_path.exists():
        try:
            cfg = load_config(cfg_path)
            console.print("config.toml: ok", style="green")
        except Exception as e:  # noqa: BLE001
            console.print(f"config.toml: invalid ({e})", style="red")
            failed = True
    else:
        console.print("config.toml: missing", style="yellow")

    console.print("\n[bold]Tools[/]")
    tools = get_tools()

    # System tools (always in PATH)
    failed |= not check_cmd("git", ["--version"])
    failed |= not check_cmd("gh", ["--version"])
    failed |= not check_cmd("uv", ["--version"])

    # Bundled tools (in tools/ OR PATH, handles .cmd on Windows)
    failed |= not check_tool(tools, "cmake", ["--version"])
    failed |= not check_tool(tools, "ninja", ["--version"])
    failed |= not check_tool(tools, "zig", ["version"])
    check_tool(tools, "bun", ["--version"], required=False)
    failed |= not check_tool(tools, "java", ["-version"])
    failed |= not check_tool(tools, "mvn", ["-version"])
    failed |= not check_tool(tools, "pio", ["--version"])

    if which("cargo") is None:
        console.print(
            "cargo: missing (install rustup: https://rustup.rs)", style="yellow"
        )
    else:
        check_cmd("cargo", ["--version"], required=False)

    if which("gh") is not None:
        auth = run_subprocess(["gh", "auth", "status"])
        if auth.returncode != 0:
            console.print("gh auth: not logged in (run: gh auth login)", style="yellow")

    # Python deps sync state (read-only)
    if which("uv") is not None:
        sync = run_subprocess(["uv", "sync", "--check"], cwd=root)
        if sync.returncode == 0:
            console.print("python deps: synced (.venv)", style="green")
        else:
            console.print(
                "python deps: not synced (run: uv sync --frozen)", style="yellow"
            )

    console.print("\n[bold]Project[/]")
    tools_dir_rel = "tools"
    if cfg is not None:
        tools_dir_rel = str(cfg.raw.get("paths", {}).get("tools", "tools"))
    tools_dir = root / tools_dir_rel

    emsdk_dir = tools_dir / "emsdk"
    if (emsdk_dir / "emsdk.py").exists():
        console.print("emsdk: ok", style="green")
    else:
        console.print("emsdk: missing (run ./setup.sh)", style="red")
        failed = True

    bridge_dir_rel = "open-control/bridge"
    if cfg is not None:
        bridge_dir_rel = str(cfg.raw.get("paths", {}).get("bridge", bridge_dir_rel))
    bridge_dir = root / bridge_dir_rel
    bridge_bin = bridge_dir / "target" / "release" / "oc-bridge"
    if platform_id == "windows":
        bridge_bin = bridge_bin.with_suffix(".exe")
    if bridge_bin.exists():
        console.print("oc-bridge: built", style="green")
    else:
        console.print(
            "oc-bridge: not built (will be built by ms setup)", style="yellow"
        )

    ext_dir_rel = "midi-studio/plugin-bitwig/host"
    if cfg is not None:
        ext_dir_rel = str(cfg.raw.get("paths", {}).get("extension", ext_dir_rel))
    ext_dir = root / ext_dir_rel
    if (ext_dir / "pom.xml").exists():
        console.print("bitwig host: ok", style="green")
    else:
        console.print("bitwig host: missing (check clones)", style="red")
        failed = True

    # Bitwig Extensions directory (deploy target)
    bitwig_dir = None
    if cfg is not None:
        bitwig_dir = cfg.raw.get("bitwig", {}).get(platform_id)

    candidates: list[Path] = []
    if bitwig_dir:
        candidates.append(Path(str(bitwig_dir)).expanduser())
    else:
        home = Path.home()
        if platform_id == "linux":
            candidates.extend(
                [
                    home / "Bitwig Studio" / "Extensions",
                    home / ".BitwigStudio" / "Extensions",
                ]
            )
        elif platform_id in {"macos", "windows"}:
            candidates.append(home / "Documents" / "Bitwig Studio" / "Extensions")

    resolved = next((p for p in candidates if p.exists()), None)
    if resolved is not None:
        console.print(f"bitwig extensions: {resolved}", style="green")
    elif candidates:
        console.print(
            f"bitwig extensions: not found (expected: {candidates[0]})", style="yellow"
        )

    console.print("\n[bold]Runtime (optional)[/]")
    if platform_id == "linux":
        if which("lsmod") is not None:
            lsmod = run_subprocess(["lsmod"])
            if "snd_virmidi" in lsmod.stdout:
                console.print("virmidi: loaded", style="green")
            else:
                console.print(
                    "virmidi: not loaded (see docs/ms-cli/MIDI.md or run sudo modprobe snd-virmidi)",
                    style="yellow",
                )

        # Serial permissions (upload + bridge)
        groups_ok = False
        if which("id") is not None:
            id_groups = run_subprocess(["id", "-nG"])
            if id_groups.returncode == 0:
                groups = set(id_groups.stdout.split())
                groups_ok = bool(groups.intersection({"dialout", "uucp"}))

        udev_candidates = [
            Path("/etc/udev/rules.d/49-oc-bridge.rules"),
            Path("/etc/udev/rules.d/00-teensy.rules"),
            Path("/etc/udev/rules.d/99-platformio-udev.rules"),
        ]
        udev_ok = any(p.exists() for p in udev_candidates)

        if groups_ok or udev_ok:
            console.print("serial permissions: ok", style="green")
        else:
            console.print("serial permissions: missing", style="yellow")
            console.print("recommended: ms bridge install", style="yellow")
            console.print(
                "Teensy udev: curl -fsSL https://www.pjrc.com/teensy/00-teensy.rules | sudo tee /etc/udev/rules.d/00-teensy.rules >/dev/null",
                style="yellow",
            )
            console.print(
                "PlatformIO udev: curl -fsSL https://raw.githubusercontent.com/platformio/platformio-core/develop/scripts/99-platformio-udev.rules | sudo tee /etc/udev/rules.d/99-platformio-udev.rules >/dev/null",
                style="yellow",
            )
            console.print(
                "then: sudo udevadm control --reload-rules && sudo udevadm trigger (re-login may be required)",
                style="yellow",
            )
    elif platform_id == "windows":
        console.print("MIDI: install loopMIDI for virtual ports", style="yellow")
    elif platform_id == "macos":
        console.print("MIDI: enable IAC Driver (Audio MIDI Setup)", style="yellow")

    console.print("\n[bold]Assets (optional)[/]")
    if which("inkscape") is None:
        console.print(
            "inkscape: missing (https://inkscape.org/release/1.4.3/platforms/)",
            style="yellow",
        )
    else:
        check_cmd("inkscape", ["--version"], required=False)
    if which("fontforge") is None:
        console.print(
            "fontforge: missing (https://fontforge.org/en-US/downloads/)",
            style="yellow",
        )
    else:
        check_cmd("fontforge", ["--version"], required=False)

    console.print("\n[bold]System deps[/]")
    if platform_id == "linux":
        if which("pkg-config") is None:
            console.print("pkg-config: missing", style="red")
            failed = True
        else:
            sdl2 = run_subprocess(["pkg-config", "--exists", "sdl2"])
            alsa = run_subprocess(["pkg-config", "--exists", "alsa"])
            if sdl2.returncode == 0:
                console.print("SDL2: ok", style="green")
            else:
                console.print(
                    "SDL2: missing (install libsdl2-dev / SDL2-devel)", style="red"
                )
                failed = True
            if alsa.returncode == 0:
                console.print("ALSA: ok", style="green")
            else:
                console.print(
                    "ALSA: missing (install libasound2-dev / alsa-lib-devel)",
                    style="red",
                )
                failed = True
    elif platform_id == "macos":
        if which("brew") is None:
            console.print("brew: missing (required for SDL2)", style="red")
            failed = True
        else:
            sdl2 = run_subprocess(["brew", "list", "sdl2"])
            if sdl2.returncode == 0:
                console.print("SDL2: ok", style="green")
            else:
                console.print("SDL2: missing (run: brew install sdl2)", style="red")
                failed = True
    else:
        console.print("System checks: not implemented for this OS", style="yellow")

    console.print("")
    if failed:
        console.print("doctor: issues found", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    console.print("doctor: ok", style="green")


@app.command()
def verify(
    full: bool = typer.Option(False, "--full", help="Run slower full verification."),
) -> None:
    """Run smoke tests for the installation."""

    root = workspace_root()
    platform_id = detect_platform()

    failed = False

    console.print("[bold]Tools[/]")
    failed |= not check_cmd("uv", ["--version"])
    failed |= not check_cmd("cmake", ["--version"])
    failed |= not check_cmd("ninja", ["--version"])
    failed |= not check_cmd("zig", ["version"])
    check_cmd("bun", ["--version"], required=False)
    failed |= not check_cmd("java", ["-version"])
    failed |= not check_cmd("mvn", ["-version"])
    failed |= not check_cmd("pio", ["--version"])

    console.print(
        "python: "
        + f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    console.print("\n[bold]Project[/]")
    cfg_path = root / "config.toml"
    if cfg_path.exists():
        try:
            cfg = load_config(cfg_path)
            console.print("config.toml: ok", style="green")
        except Exception as e:  # noqa: BLE001
            console.print(f"config.toml: invalid ({e})", style="red")
            failed = True
            cfg = None
    else:
        console.print("config.toml: missing", style="red")
        failed = True
        cfg = None

    # Python deps sync state
    if which("uv") is not None:
        sync = run_subprocess(["uv", "sync", "--check"], cwd=root)
        if sync.returncode == 0:
            console.print("python deps: ok", style="green")
        else:
            console.print("python deps: not synced", style="red")
            failed = True

    tools_dir_rel = "tools"
    if cfg is not None:
        tools_dir_rel = str(cfg.raw.get("paths", {}).get("tools", "tools"))
    tools_dir = root / tools_dir_rel

    emsdk_dir = tools_dir / "emsdk"
    failed |= not check_path("emsdk", emsdk_dir / "emsdk.py")

    bridge_dir_rel = "open-control/bridge"
    if cfg is not None:
        bridge_dir_rel = str(cfg.raw.get("paths", {}).get("bridge", bridge_dir_rel))
    bridge_dir = root / bridge_dir_rel
    bridge_bin = bridge_dir / "target" / "release" / "oc-bridge"
    if platform_id == "windows":
        bridge_bin = bridge_bin.with_suffix(".exe")
    check_path("oc-bridge", bridge_bin, required=False)

    console.print("\n[bold]PlatformIO[/]")
    pio_devices = run_subprocess(["pio", "device", "list"])
    if pio_devices.returncode != 0:
        console.print("pio device list: failed", style="red")
        failed = True
    else:
        console.print("pio device list: ok", style="green")

    if platform_id == "linux":
        groups_ok = False
        if which("id") is not None:
            id_groups = run_subprocess(["id", "-nG"])
            if id_groups.returncode == 0:
                groups = set(id_groups.stdout.split())
                groups_ok = bool(groups.intersection({"dialout", "uucp"}))

        udev_candidates = [
            Path("/etc/udev/rules.d/49-oc-bridge.rules"),
            Path("/etc/udev/rules.d/00-teensy.rules"),
            Path("/etc/udev/rules.d/99-platformio-udev.rules"),
        ]
        udev_ok = any(p.exists() for p in udev_candidates)

        if groups_ok or udev_ok:
            console.print("serial permissions: ok", style="green")
        else:
            console.print("serial permissions: missing", style="yellow")
            console.print("recommended: ms bridge install", style="yellow")
            console.print(
                "Teensy udev: curl -fsSL https://www.pjrc.com/teensy/00-teensy.rules | sudo tee /etc/udev/rules.d/00-teensy.rules >/dev/null",
                style="yellow",
            )
            console.print(
                "PlatformIO udev: curl -fsSL https://raw.githubusercontent.com/platformio/platformio-core/develop/scripts/99-platformio-udev.rules | sudo tee /etc/udev/rules.d/99-platformio-udev.rules >/dev/null",
                style="yellow",
            )
            console.print(
                "then: sudo udevadm control --reload-rules && sudo udevadm trigger (re-login may be required)",
                style="yellow",
            )

    if full:
        console.print("\n[bold]Full[/]")
        console.print("verify --full: not implemented yet", style="yellow")

    raise typer.Exit(code=ExitCode.OK if not failed else ExitCode.ENV_ERROR)


def _print_changes(*, include_clean: bool) -> int:
    root = workspace_root()

    repos: list[Path] = []
    if _is_git_repo(root):
        repos.append(root)
    repos.extend(_iter_child_repos(root / "midi-studio"))
    repos.extend(_iter_child_repos(root / "open-control"))

    if not repos:
        console.print("no git repos found", style="yellow")
        return 0

    console.print(
        Text("XY: X=index, Y=worktree ('.' = clean)", style="dim"), markup=False
    )
    console.print("")

    shown = 0
    dirty = 0
    diverged = 0

    for repo in repos:
        proc = run_subprocess(
            ["git", "status", "--porcelain=v1", "-b"],
            cwd=repo,
        )
        if proc.returncode != 0:
            continue

        branch, entries = _parse_git_porcelain(proc.stdout)
        local_branch, upstream = _parse_branch_line(branch) if branch else ("", None)
        ahead, behind = _ahead_behind(branch)

        has_worktree = bool(entries)
        has_divergence = bool(ahead or behind or (local_branch and upstream is None))

        if not include_clean and not (has_worktree or has_divergence):
            continue

        shown += 1
        if has_worktree:
            dirty += 1
        if has_divergence:
            diverged += 1

        console.print(
            Rule(str(repo.resolve()), characters="-", style="grey50"),
            markup=False,
        )

        # Repo summary
        branch_parts: list[str] = []
        if local_branch:
            branch_parts.append(f"branch: {local_branch}")
        if upstream:
            branch_parts.append(f"upstream: {upstream}")
        else:
            branch_parts.append("upstream: none")
        if ahead or behind:
            branch_parts.append(f"divergence: +{ahead}/-{behind}")
        console.print(
            Padding(Text(" | ".join(branch_parts), style="dim"), (0, 0, 0, 2)),
            markup=False,
        )

        staged_count = sum(1 for xy, _ in entries if xy != "??" and xy[0] != " ")
        unstaged_count = sum(1 for xy, _ in entries if xy != "??" and xy[1] != " ")
        untracked_count = sum(1 for xy, _ in entries if xy == "??")

        if has_worktree:
            console.print(
                Padding(
                    Text(
                        f"worktree: {staged_count} staged, {unstaged_count} unstaged, {untracked_count} untracked",
                        style="dim",
                    ),
                    (0, 0, 0, 2),
                ),
                markup=False,
            )
        else:
            console.print(Padding(Text("worktree: clean", style="dim"), (0, 0, 0, 2)))

        tracked = [(xy, p) for xy, p in entries if xy != "??"]
        untracked = [p for xy, p in entries if xy == "??"]

        if tracked:
            console.print(
                Padding(
                    Text(f"tracked ({len(tracked)}):", style="bold grey70"),
                    (1, 0, 0, 2),
                ),
                markup=False,
            )
            for xy, path in tracked:
                code = _pretty_xy(xy)
                code_style = _xy_style(xy)

                # Keep rename entries readable (avoid awkward wrapping)
                if " -> " in path:
                    old, new = path.split(" -> ", 1)

                    line1 = Text()
                    line1.append(code, style=code_style)
                    line1.append("  ")
                    line1.append(old)
                    console.print(
                        Padding(line1, (0, 0, 0, 4)), overflow="fold", markup=False
                    )

                    line2 = Text(new, style="dim")
                    console.print(
                        Padding(line2, (0, 0, 0, 8)), overflow="fold", markup=False
                    )
                    continue

                line = Text()
                line.append(code, style=code_style)
                line.append("  ")
                line.append(path)
                console.print(
                    Padding(line, (0, 0, 0, 4)), overflow="fold", markup=False
                )

        if untracked:
            console.print(
                Padding(
                    Text(f"untracked ({len(untracked)}):", style="bold grey70"),
                    (1, 0, 0, 2),
                ),
                markup=False,
            )
            for path in untracked:
                line = Text()
                line.append("??", style=_xy_style("??"))
                line.append("  ")
                line.append(path)
                console.print(
                    Padding(line, (0, 0, 0, 4)), overflow="fold", markup=False
                )

        console.print("")

    console.print(
        Text(
            f"repos: {shown} shown ({dirty} dirty, {diverged} diverged) / {len(repos)} total",
            style="dim",
        ),
        markup=False,
    )
    return 0


@app.command(name="changes")
def changes_cmd(
    all: bool = typer.Option(False, "--all", help="Include clean repos (no changes)."),
) -> None:
    """List git changes across workspace repos."""

    raise typer.Exit(code=_print_changes(include_clean=all))


@app.command(name="status")
def status_cmd(
    all: bool = typer.Option(False, "--all", help="Include clean repos (no changes)."),
) -> None:
    """Alias for changes."""

    raise typer.Exit(code=_print_changes(include_clean=all))


@app.command()
def icons(
    codebase: str = typer.Argument(..., help="Codebase: core|bitwig"),
) -> None:
    """Generate LVGL icon fonts (requires Inkscape + FontForge)."""

    root = workspace_root()
    builder = root / "open-control" / "ui-lvgl-cli-tools" / "icon" / "build.py"
    if not builder.exists():
        console.print(f"builder not found: {builder}", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    if codebase == "core":
        project = root / "midi-studio" / "core"
    elif codebase == "bitwig":
        project = root / "midi-studio" / "plugin-bitwig"
    else:
        console.print("usage: ms icons <core|bitwig>", style="red")
        raise typer.Exit(code=ExitCode.USER_ERROR)

    if not (project / "platformio.ini").exists():
        console.print(f"platformio.ini not found: {project}", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    code = run_live([sys.executable, str(builder)], cwd=project)
    if code != 0:
        raise typer.Exit(code=ExitCode.BUILD_ERROR)


@app.command(name="run")
def run_cmd(
    codebase: str = typer.Argument(..., help="Codebase: core, bitwig, ..."),
) -> None:
    """Build and run native desktop simulator."""
    root = workspace_root()

    try:
        cb = resolve_codebase(codebase, root)
        tools = get_tools()
    except CodebaseNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.USER_ERROR)
    except ToolNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    console.print(f"[bold]Running {codebase} (native)[/]")
    code = run_native(
        cb,
        tools=tools,
        workspace=root,
        bin_root=get_bin_root(),
        build_root=get_build_root(),
    )

    if code != 0:
        raise typer.Exit(code=ExitCode.BUILD_ERROR)


@app.command()
def web(
    codebase: str = typer.Argument(..., help="Codebase: core, bitwig, ..."),
    port: int = typer.Option(8080, "--port", "-p", help="HTTP server port"),
    no_watch: bool = typer.Option(False, "--no-watch", help="Disable watch mode"),
) -> None:
    """Build and serve WASM simulator."""
    root = workspace_root()

    try:
        cb = resolve_codebase(codebase, root)
        tools = get_tools()
    except CodebaseNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.USER_ERROR)
    except ToolNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    console.print(f"[bold]Building {codebase} (wasm)[/]")
    code = serve_wasm(
        cb,
        tools=tools,
        workspace=root,
        bin_root=get_bin_root(),
        build_root=get_build_root(),
        port=port,
        watch=not no_watch,
    )

    if code != 0:
        raise typer.Exit(code=ExitCode.BUILD_ERROR)


@app.command()
def build(
    codebase: str = typer.Argument(..., help="Codebase: core, bitwig, ..."),
    target: str = typer.Argument("", help="Target: native, wasm (default: teensy)"),
    release: bool = typer.Option(False, "--release", help="Use release environment"),
    raw: bool = typer.Option(False, "--raw", help="Use raw pio (skip oc-build)"),
) -> None:
    """Build targets (teensy, native, or wasm)."""
    root = workspace_root()
    env = "release" if release else "dev"

    try:
        cb = resolve_codebase(codebase, root)
        tools = get_tools()
    except CodebaseNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.USER_ERROR)
    except ToolNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    if target == "native":
        console.print(f"[bold]Building {codebase} (native)[/]")
        code = build_native(
            cb,
            tools=tools,
            workspace=root,
            bin_root=get_bin_root(),
            build_root=get_build_root(),
        )
    elif target == "wasm":
        console.print(f"[bold]Building {codebase} (wasm)[/]")
        code = build_wasm(
            cb,
            tools=tools,
            workspace=root,
            bin_root=get_bin_root(),
            build_root=get_build_root(),
        )
    else:
        # Default: teensy
        console.print(f"[bold]Building {codebase} (teensy {env})[/]")
        code = build_teensy(
            cb,
            env,
            tools=tools,
            bin_root=get_bin_root(),
            raw=raw,
        )

    if code != 0:
        raise typer.Exit(code=ExitCode.BUILD_ERROR)

    console.print("Build complete", style="green")


@app.command()
def upload(
    codebase: str = typer.Argument(..., help="Codebase: core, bitwig, ..."),
    release: bool = typer.Option(False, "--release", help="Use release environment"),
    raw: bool = typer.Option(False, "--raw", help="Use raw pio (skip oc-upload)"),
) -> None:
    """Build and upload teensy firmware."""
    root = workspace_root()
    env = "release" if release else "dev"

    try:
        cb = resolve_codebase(codebase, root)
        tools = get_tools()
    except CodebaseNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.USER_ERROR)
    except ToolNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    console.print(f"[bold]Uploading {codebase} (teensy {env})[/]")
    code = upload_teensy(
        cb,
        env,
        tools=tools,
        bin_root=get_bin_root(),
        raw=raw,
    )

    if code != 0:
        raise typer.Exit(code=ExitCode.BUILD_ERROR)

    console.print("Upload complete", style="green")


@app.command()
def monitor(
    codebase: str = typer.Argument(..., help="Codebase: core, bitwig, ..."),
    release: bool = typer.Option(False, "--release", help="Use release environment"),
    raw: bool = typer.Option(False, "--raw", help="Use raw pio (skip oc-monitor)"),
) -> None:
    """Monitor serial output."""
    root = workspace_root()
    env = "release" if release else "dev"

    try:
        cb = resolve_codebase(codebase, root)
        tools = get_tools()
    except CodebaseNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.USER_ERROR)
    except ToolNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    console.print(f"[bold]Monitoring {codebase} (teensy {env})[/]")
    code = monitor_teensy(
        cb,
        env,
        tools=tools,
        raw=raw,
    )

    if code != 0:
        raise typer.Exit(code=ExitCode.BUILD_ERROR)


@app.command()
def clean(
    codebase: str = typer.Argument("", help="Codebase to clean (all if empty)"),
) -> None:
    """Clean build artifacts."""
    root = workspace_root()
    bin_root = get_bin_root()
    build_root = get_build_root()
    midi_studio = root / "midi-studio"

    if not codebase:
        # Clean all
        console.print("Cleaning all builds...")

        if build_root.exists():
            shutil.rmtree(build_root)

        if bin_root.exists():
            for cb_dir in bin_root.iterdir():
                if not cb_dir.is_dir():
                    continue
                # Don't clean bridge
                if cb_dir.name == "bridge":
                    continue
                for subdir in ["native", "wasm", "teensy"]:
                    target = cb_dir / subdir
                    if target.exists():
                        shutil.rmtree(target)

        # Clean PlatformIO builds
        for pio_build in midi_studio.glob("*/.pio/build"):
            shutil.rmtree(pio_build)
    else:
        # Clean specific codebase
        try:
            cb = resolve_codebase(codebase, root)
        except CodebaseNotFoundError as e:
            console.print(f"error: {e}", style="red")
            raise typer.Exit(code=ExitCode.USER_ERROR)

        console.print(f"Cleaning {codebase}...")

        cb_build = build_root / codebase
        if cb_build.exists():
            shutil.rmtree(cb_build)

        cb_bin = bin_root / codebase
        for subdir in ["native", "wasm", "teensy"]:
            target = cb_bin / subdir
            if target.exists():
                shutil.rmtree(target)

        pio_build = cb.path / ".pio" / "build"
        if pio_build.exists():
            shutil.rmtree(pio_build)

    console.print("Clean complete", style="green")


@app.command(name="list")
def list_cmd() -> None:
    """List available codebases."""
    root = workspace_root()
    codebases = list_codebases(root)

    console.print("[bold]Available codebases:[/]")
    for cb in codebases:
        console.print(f"  {cb}")


@app.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
def bridge(ctx: typer.Context) -> None:
    """Run oc-bridge (TUI by default)."""

    root = workspace_root()
    cfg = load_config(root / "config.toml")

    bridge_dir_rel = str(cfg.raw.get("paths", {}).get("bridge", "open-control/bridge"))
    bridge_dir = root / bridge_dir_rel

    exe_name = "oc-bridge.exe" if detect_platform() == "windows" else "oc-bridge"

    # Prefer workspace-installed binary (stable path for services).
    exe = root / "bin" / "bridge" / exe_name
    if not exe.exists():
        exe = bridge_dir / "target" / "release" / exe_name

    if not exe.exists():
        console.print(f"error: oc-bridge not found: {exe}", style="red")
        console.print("hint: run ms setup", style="yellow")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    os.execv(str(exe), [str(exe), *ctx.args])


@app.command()
def core(
    release: bool = typer.Option(False, "--release", help="Use release environment"),
    raw: bool = typer.Option(False, "--raw", help="Use raw pio (skip oc-upload)"),
) -> None:
    """Quick upload for core (teensy)."""
    root = workspace_root()
    env = "release" if release else "dev"

    try:
        cb = resolve_codebase("core", root)
        tools = get_tools()
    except CodebaseNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.USER_ERROR)
    except ToolNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    console.print(f"[bold]Uploading core (teensy {env})[/]")
    code = upload_teensy(
        cb,
        env,
        tools=tools,
        bin_root=get_bin_root(),
        raw=raw,
    )

    if code != 0:
        raise typer.Exit(code=ExitCode.BUILD_ERROR)

    console.print("Upload complete", style="green")


@app.command()
def bitwig(
    release: bool = typer.Option(False, "--release", help="Use release environment"),
    raw: bool = typer.Option(False, "--raw", help="Use raw pio (skip oc-upload)"),
) -> None:
    """Quick upload for bitwig (teensy)."""
    root = workspace_root()
    env = "release" if release else "dev"

    try:
        cb = resolve_codebase("bitwig", root)
        tools = get_tools()
    except CodebaseNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.USER_ERROR)
    except ToolNotFoundError as e:
        console.print(f"error: {e}", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    console.print(f"[bold]Uploading bitwig (teensy {env})[/]")
    code = upload_teensy(
        cb,
        env,
        tools=tools,
        bin_root=get_bin_root(),
        raw=raw,
    )

    if code != 0:
        raise typer.Exit(code=ExitCode.BUILD_ERROR)

    console.print("Upload complete", style="green")


@app.command()
def setup(
    bootstrap: bool = typer.Option(
        False, "--bootstrap", help="Full bootstrap (install tools)"
    ),
    skip_system_check: bool = typer.Option(
        False, "--skip-system-check", help="Skip system deps check"
    ),
) -> None:
    """Project setup (build bridge + extension, or --bootstrap for full install)."""

    root = workspace_root()

    if bootstrap:
        from .setup_bootstrap import run_bootstrap

        code = run_bootstrap(root, skip_system_check=skip_system_check)
        raise typer.Exit(code=code)
    platform_id = detect_platform()
    cfg = load_config(root / "config.toml")

    failed = False

    console.print("[bold]Bridge[/]")
    bridge_dir_rel = str(cfg.raw.get("paths", {}).get("bridge", "open-control/bridge"))
    bridge_dir = root / bridge_dir_rel
    if not bridge_dir.is_dir():
        console.print(f"bridge dir missing: {bridge_dir}", style="red")
        failed = True
    elif which("cargo") is None:
        console.print("cargo: missing (install rustup: https://rustup.rs)", style="red")
        failed = True
    else:
        code = run_live(["cargo", "build", "--release"], cwd=bridge_dir)
        if code != 0:
            console.print("bridge build failed", style="red")
            raise typer.Exit(code=ExitCode.BUILD_ERROR)

        bridge_bin = bridge_dir / "target" / "release" / "oc-bridge"
        if platform_id == "windows":
            bridge_bin = bridge_bin.with_suffix(".exe")
        if not bridge_bin.exists():
            console.print(f"bridge binary missing: {bridge_bin}", style="red")
            failed = True
        else:
            # Install into workspace/bin/bridge (stable runtime location)
            bin_bridge_dir = root / "bin" / "bridge"
            bin_bridge_dir.mkdir(parents=True, exist_ok=True)
            dst_bridge_bin = bin_bridge_dir / bridge_bin.name
            shutil.copy2(bridge_bin, dst_bridge_bin)
            try:
                dst_bridge_bin.chmod(0o755)
            except Exception:
                pass

            src_config_dir = bridge_dir / "config"
            if src_config_dir.is_dir():
                shutil.copytree(
                    src_config_dir,
                    bin_bridge_dir / "config",
                    dirs_exist_ok=True,
                )

            console.print(f"oc-bridge: {dst_bridge_bin}", style="green")

    console.print("\n[bold]Bitwig Host[/]")
    host_dir_rel = str(
        cfg.raw.get("paths", {}).get("extension", "midi-studio/plugin-bitwig/host")
    )
    host_dir = root / host_dir_rel
    if not (host_dir / "pom.xml").exists():
        console.print(f"host dir missing: {host_dir}", style="red")
        failed = True
    else:
        # Find mvn using ToolResolver
        tools = get_tools()
        try:
            mvn_path = tools.mvn()
        except ToolNotFoundError:
            console.print("mvn: missing", style="red")
            failed = True
            mvn_path = None

        if mvn_path:
            bitwig_dir = cfg.raw.get("bitwig", {}).get(platform_id)
            candidates: list[Path] = []
            if bitwig_dir:
                candidates.append(Path(str(bitwig_dir)).expanduser())
            else:
                home = Path.home()
                if platform_id == "linux":
                    candidates.extend(
                        [
                            home / "Bitwig Studio" / "Extensions",
                            home / ".BitwigStudio" / "Extensions",
                        ]
                    )
                elif platform_id in {"macos", "windows"}:
                    candidates.append(
                        home / "Documents" / "Bitwig Studio" / "Extensions"
                    )

            install_dir = next((p for p in candidates if p.exists()), None)
            if install_dir is None and candidates:
                install_dir = candidates[0]

            if install_dir is None:
                console.print("bitwig extensions dir not found", style="red")
                failed = True
            else:
                install_dir.mkdir(parents=True, exist_ok=True)

                # JDK 25 is installed, but compile in Java 21 compatibility.
                # Also set JAVA_HOME to bundled JDK
                java_home = tools.tools_dir / "jdk"
                env = os.environ.copy()
                env["JAVA_HOME"] = str(java_home)

                from .tools import run_tool

                result = run_tool(
                    mvn_path,
                    [
                        "package",
                        "-Dmaven.compiler.release=21",
                        f"-Dbitwig.extensions.dir={install_dir}",
                    ],
                    cwd=host_dir,
                    env=env,
                )
                if result.returncode != 0:
                    console.print("maven build failed", style="red")
                    raise typer.Exit(code=ExitCode.BUILD_ERROR)

                deployed = install_dir / "midi_studio.bwextension"
                if not deployed.exists():
                    console.print(f"extension not found: {deployed}", style="red")
                    failed = True
                else:
                    console.print(f"extension: {deployed}", style="green")

                    # Keep a copy in workspace/bin/bitwig for convenience.
                    bin_bitwig_dir = root / "bin" / "bitwig"
                    bin_bitwig_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(deployed, bin_bitwig_dir / deployed.name)
                    except Exception:
                        pass

    console.print("")
    if failed:
        console.print("setup: failed", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    console.print("setup: ok", style="green")


@app.command()
def update(
    repos: bool = typer.Option(False, "--repos", help="Update git repos (ff-only)."),
    tools: bool = typer.Option(
        False, "--tools", help="Upgrade workspace-managed tools."
    ),
    python: bool = typer.Option(
        False, "--python", help="Upgrade Python deps (uv.lock + sync)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show actions without executing."
    ),
) -> None:
    """Upgrade tools/deps/repos (explicit)."""

    if not (repos or tools or python):
        repos = True
        tools = True
        python = True

    root = workspace_root()
    failed = False

    console.print(f"workspace: {root}")

    if dry_run:
        console.print("mode: dry-run", style="yellow")

    # ---------------------------------------------------------------------
    # Python deps (uv.lock)
    # ---------------------------------------------------------------------
    if python:
        console.print("\n[bold]Python[/]")
        if which("uv") is None:
            console.print("uv: missing", style="red")
            failed = True
        elif dry_run:
            console.print("would run: uv lock --upgrade", style="yellow")
            console.print("would run: uv sync --frozen", style="yellow")
        else:
            lock = run_subprocess(["uv", "lock", "--upgrade"], cwd=root)
            if lock.returncode != 0:
                console.print("uv lock: failed", style="red")
                console.print(first_line(lock.stderr), style="red")
                failed = True
            sync = run_subprocess(["uv", "sync", "--frozen"], cwd=root)
            if sync.returncode != 0:
                console.print("uv sync: failed", style="red")
                console.print(first_line(sync.stderr), style="red")
                failed = True
            else:
                console.print("python deps: updated", style="green")

    # ---------------------------------------------------------------------
    # Repos
    # ---------------------------------------------------------------------
    if repos:
        console.print("\n[bold]Repos[/]")
        bases = [root / "open-control", root / "midi-studio"]
        all_repos: list[Path] = []
        for base in bases:
            all_repos.extend(list_git_repos(base))

        if not all_repos:
            console.print("no repos found (run ./setup.sh)", style="red")
            failed = True
        else:
            updated = 0
            skipped = 0
            for repo in all_repos:
                if not git_is_clean(repo):
                    console.print(f"skip (dirty): {repo}", style="yellow")
                    skipped += 1
                    continue
                if not git_has_upstream(repo):
                    console.print(f"skip (no upstream): {repo}", style="yellow")
                    skipped += 1
                    continue

                if dry_run:
                    console.print(f"would pull: {repo}", style="yellow")
                    continue

                pull = git_pull_ff_only(repo)
                if pull.returncode != 0:
                    console.print(f"pull failed: {repo}", style="red")
                    console.print(first_line(pull.stderr), style="red")
                    failed = True
                else:
                    console.print(f"pulled: {repo}", style="green")
                    updated += 1

            console.print(f"repos: updated={updated} skipped={skipped}")

    # ---------------------------------------------------------------------
    # Tools
    # ---------------------------------------------------------------------
    if tools:
        console.print("\n[bold]Tools[/]")

        tools_dir = root / "tools"
        if not tools_dir.is_dir():
            console.print("tools/: missing (run ./setup.sh)", style="red")
            failed = True
        else:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_dir = tools_dir / ".old" / ts

            refresh_paths: list[Path] = [
                tools_dir / "cmake",
                tools_dir / "ninja",
                tools_dir / "zig",
                tools_dir / "bun",
                tools_dir / "jdk",
                tools_dir / "maven",
                tools_dir / "uv",
            ]

            if detect_platform() == "windows":
                refresh_paths.append(tools_dir / "windows" / "SDL2")

            existing = [p for p in refresh_paths if p.exists()]
            if dry_run:
                for p in existing:
                    console.print(f"would refresh: {p}", style="yellow")
                console.print(
                    "would run: ./setup.sh --skip-repos --skip-shell", style="yellow"
                )
            else:
                backup_dir.mkdir(parents=True, exist_ok=True)
                for p in existing:
                    dest = backup_dir / p.name
                    console.print(f"refresh: {p} -> {dest}", style="cyan")
                    shutil.move(str(p), str(dest))

                setup_script = root / "setup.sh"
                setup = run_subprocess(
                    [str(setup_script), "--skip-repos", "--skip-shell"], cwd=root
                )
                if setup.returncode != 0:
                    console.print("setup.sh: failed", style="red")
                    console.print(first_line(setup.stderr), style="red")
                    failed = True
                else:
                    console.print("tools: refreshed", style="green")

                # PlatformIO upgrade
                if which("pio") is not None:
                    _ = run_subprocess(["pio", "upgrade"])  # best-effort

                # Rust toolchain upgrade
                if which("rustup") is not None:
                    _ = run_subprocess(["rustup", "update", "stable"])  # best-effort

                # emsdk upgrade (best-effort)
                emsdk_dir = tools_dir / "emsdk"
                if (emsdk_dir / "emsdk.py").exists():
                    _ = run_subprocess(
                        ["git", "-C", str(emsdk_dir), "pull"]
                    )  # best-effort
                    _ = run_subprocess(
                        [
                            sys.executable,
                            str(emsdk_dir / "emsdk.py"),
                            "install",
                            "latest",
                        ],
                        cwd=emsdk_dir,
                    )
                    _ = run_subprocess(
                        [
                            sys.executable,
                            str(emsdk_dir / "emsdk.py"),
                            "activate",
                            "latest",
                        ],
                        cwd=emsdk_dir,
                    )

    console.print("")
    if failed:
        console.print("update: failed", style="red")
        raise typer.Exit(code=ExitCode.ENV_ERROR)

    console.print("update: ok", style="green")


@app.command()
def completion(shell: str = typer.Argument("bash", help="Shell: bash|zsh")) -> None:
    """Print shell completion script."""

    root = workspace_root()
    if shell == "bash":
        path = root / "commands" / "_ms_completions.bash"
        if not path.exists():
            console.print("error: commands/_ms_completions.bash not found", style="red")
            raise typer.Exit(code=ExitCode.ENV_ERROR)
        sys.stdout.write(path.read_text(encoding="utf-8"))
        raise typer.Exit(code=ExitCode.OK)

    if shell == "zsh":
        path = root / "commands" / "_ms_completions.zsh"
        if not path.exists():
            console.print("error: commands/_ms_completions.zsh not found", style="red")
            raise typer.Exit(code=ExitCode.ENV_ERROR)
        sys.stdout.write(path.read_text(encoding="utf-8"))
        raise typer.Exit(code=ExitCode.OK)

    console.print("completion: unsupported shell", style="yellow")
    raise typer.Exit(code=ExitCode.USER_ERROR)


@app.command(name="r")
def alias_run(
    codebase: str = typer.Argument(..., help="Codebase: core, bitwig, ..."),
) -> None:
    """Alias for run."""
    run_cmd(codebase)


@app.command(name="w")
def alias_web(
    codebase: str = typer.Argument(..., help="Codebase: core, bitwig, ..."),
    port: int = typer.Option(8080, "--port", "-p", help="HTTP server port"),
    no_watch: bool = typer.Option(False, "--no-watch", help="Disable watch mode"),
) -> None:
    """Alias for web."""
    web(codebase, port, no_watch)


@app.command(name="b")
def alias_build(
    codebase: str = typer.Argument(..., help="Codebase: core, bitwig, ..."),
    target: str = typer.Argument("", help="Target: native, wasm (default: teensy)"),
    release: bool = typer.Option(False, "--release", help="Use release environment"),
    raw: bool = typer.Option(False, "--raw", help="Use raw pio (skip oc-build)"),
) -> None:
    """Alias for build."""
    build(codebase, target, release, raw)
