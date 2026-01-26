# SPDX-License-Identifier: MIT
"""System dependencies checker.

Validates system-level dependencies:
- Linux: SDL2, ALSA, libudev, pkg-config, C compiler
- macOS: SDL2 (via brew), C compiler
- Windows: SDL2 (bundled), C compiler
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ms.services.checkers.base import CheckResult
from ms.services.checkers.common import (
    CommandRunner,
    DefaultCommandRunner,
    Hints,
    first_line,
    get_platform_key,
)

if TYPE_CHECKING:
    from ms.platform.detection import LinuxDistro, Platform


# Declarative dependency definitions: (display_name, pkg_config_name, hint_key)
_LINUX_PKG_CONFIG_DEPS: list[tuple[str, str, str]] = [
    ("SDL2", "sdl2", "sdl2"),
    ("ALSA", "alsa", "alsa"),
    ("libudev", "libudev", "libudev"),
]

# C compiler candidates by platform
_C_COMPILERS_UNIX = ("cc", "gcc", "clang")
_C_COMPILERS_WINDOWS = ("cl", "gcc", "clang")


@dataclass(frozen=True, slots=True)
class SystemChecker:
    """Check system dependencies.

    Attributes:
        platform: Current platform
        distro: Linux distribution (if on Linux)
        tools_dir: Path to bundled tools directory
        hints: Installation hints
        runner: Command runner for checks
    """

    platform: "Platform"
    distro: "LinuxDistro | None" = None
    tools_dir: Path | None = None
    hints: Hints = field(default_factory=Hints.empty)
    runner: CommandRunner = field(default_factory=DefaultCommandRunner)

    def check_all(self) -> list[CheckResult]:
        """Run all system dependency checks."""
        from ms.platform.detection import Platform

        match self.platform:
            case Platform.LINUX:
                return self._check_linux()
            case Platform.MACOS:
                return self._check_macos()
            case Platform.WINDOWS:
                return self._check_windows()
            case _:
                return []

    def _check_linux(self) -> list[CheckResult]:
        """Check Linux system dependencies."""
        results: list[CheckResult] = []

        # pkg-config is required for library detection
        has_pkg_config = self._check_pkg_config(results)

        # Check libraries via pkg-config
        if has_pkg_config:
            for display_name, pkg_name, hint_key in _LINUX_PKG_CONFIG_DEPS:
                results.append(self._check_pkg_config_lib(display_name, pkg_name, hint_key))
        else:
            for display_name, _, _ in _LINUX_PKG_CONFIG_DEPS:
                results.append(
                    CheckResult.warning(display_name, "cannot check (pkg-config missing)")
                )

        # C compiler (independent of pkg-config)
        results.append(self._check_c_compiler(_C_COMPILERS_UNIX))

        return results

    def _check_macos(self) -> list[CheckResult]:
        """Check macOS system dependencies."""
        results: list[CheckResult] = []

        # Homebrew check
        if not shutil.which("brew"):
            results.append(
                CheckResult.error(
                    "brew", "missing (required for SDL2)", hint="Install from https://brew.sh"
                )
            )
            results.append(CheckResult.warning("SDL2", "cannot check (brew missing)"))
        else:
            results.append(CheckResult.success("brew", "ok"))
            results.append(self._check_brew_package("SDL2", "sdl2"))

        results.append(self._check_c_compiler(_C_COMPILERS_UNIX))
        return results

    def _check_windows(self) -> list[CheckResult]:
        """Check Windows system dependencies."""
        results: list[CheckResult] = []
        results.append(self._check_sdl2_bundled())
        results.append(self._check_c_compiler(_C_COMPILERS_WINDOWS))
        return results

    # -------------------------------------------------------------------------
    # Reusable check methods
    # -------------------------------------------------------------------------

    def _check_pkg_config(self, results: list[CheckResult]) -> bool:
        """Check if pkg-config is available. Appends result and returns availability."""
        if shutil.which("pkg-config"):
            results.append(CheckResult.success("pkg-config", "ok"))
            return True
        results.append(
            CheckResult.error("pkg-config", "missing", hint=self._get_hint("pkg-config"))
        )
        return False

    def _check_pkg_config_lib(self, display_name: str, pkg_name: str, hint_key: str) -> CheckResult:
        """Check a library via pkg-config."""
        result = self.runner.run(["pkg-config", "--exists", pkg_name])
        if result.returncode != 0:
            return CheckResult.error(display_name, "missing", hint=self._get_hint(hint_key))

        version_result = self.runner.run(["pkg-config", "--modversion", pkg_name])
        version = version_result.stdout.strip() if version_result.returncode == 0 else ""
        msg = f"ok ({version})" if version else "ok"
        return CheckResult.success(display_name, msg)

    def _check_brew_package(self, display_name: str, package: str) -> CheckResult:
        """Check a Homebrew package."""
        result = self.runner.run(["brew", "list", package])
        if result.returncode == 0:
            return CheckResult.success(display_name, "ok")
        return CheckResult.error(display_name, "missing", hint=self._get_hint(package))

    def _check_sdl2_bundled(self) -> CheckResult:
        """Check for bundled SDL2 on Windows."""
        if not self.tools_dir:
            return CheckResult.warning("SDL2", "cannot check (tools_dir not set)")

        sdl2_path = self.tools_dir / "sdl2"
        if (
            (sdl2_path / "lib").is_dir()
            or (sdl2_path / "include").is_dir()
            or (sdl2_path / "bin" / "SDL2.dll").is_file()
        ):
            return CheckResult.success("SDL2", "ok (bundled)")

        return CheckResult.warning("SDL2", "not found", hint="Run: uv run ms tools sync")

    def _check_c_compiler(self, candidates: tuple[str, ...]) -> CheckResult:
        """Check for a working C compiler from candidates list."""
        for compiler in candidates:
            path = shutil.which(compiler)
            if not path:
                continue

            # Try to get version info
            version_result = self.runner.run([compiler, "--version"])
            if version_result.returncode == 0:
                version = first_line(version_result.stdout + version_result.stderr)
                return CheckResult.success("C compiler", f"ok ({version})" if version else "ok")

            return CheckResult.success("C compiler", f"ok ({compiler})")

        return CheckResult.error(
            "C compiler",
            f"missing ({'/'.join(candidates)} not found)",
            hint=self._get_hint("cc"),
        )

    def _get_hint(self, dep_id: str) -> str | None:
        """Get installation hint for a system dependency."""
        platform_key = get_platform_key(self.platform, self.distro)
        return self.hints.get_system_hint(dep_id, platform_key)
