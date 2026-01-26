# SPDX-License-Identifier: MIT
"""Install a small, safe subset of host dependencies.

This is intentionally conservative:
- It never executes arbitrary shell snippets from hints.
- It only auto-executes a small allowlist of well-known installers.

Hints that don't match the safe allowlist are returned as manual steps.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Callable

from ms.output.console import ConsoleProtocol, Style
from ms.services.checkers.base import CheckResult
from ms.services.checkers.common import CommandRunner, DefaultCommandRunner

__all__ = ["InstallPlan", "InstallStep", "SystemInstaller"]


@dataclass(frozen=True, slots=True)
class InstallStep:
    name: str
    argv: list[str]

    @property
    def display(self) -> str:
        return shlex.join(self.argv)


@dataclass(frozen=True, slots=True)
class InstallPlan:
    steps: list[InstallStep]
    manual: list[tuple[str, str]]

    @property
    def is_empty(self) -> bool:
        return not self.steps and not self.manual


_MANUAL_PREFIXES = (
    "Run:",
    "N/A",
    "Install ",
    "Enable ",
    "Download ",
    "http://",
    "https://",
)

_SHELL_META = {
    "|",
    "||",
    "&&",
    ";",
    ">",
    ">>",
    "<",
    "2>",
    "&>",
}

_SAFE_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("sudo", "apt", "install"),
    ("sudo", "dnf", "install"),
    ("sudo", "pacman", "-S"),
    ("brew", "install"),
    ("winget", "install"),
)

_SAFE_EXACT: tuple[tuple[str, ...], ...] = (("xcode-select", "--install"),)


def _is_manual_hint(hint: str) -> bool:
    stripped = hint.strip()
    return stripped.startswith(_MANUAL_PREFIXES)


def _parse_safe_install_argv(hint: str) -> list[str] | None:
    """Parse a safe, non-shell install command from a hint string."""
    if _is_manual_hint(hint):
        return None

    try:
        argv = shlex.split(hint, posix=True)
    except ValueError:
        return None

    if not argv:
        return None

    if any(tok in _SHELL_META for tok in argv):
        return None

    for prefix in _SAFE_PREFIXES:
        if tuple(argv[: len(prefix)]) == prefix and len(argv) > len(prefix):
            return argv

    for exact in _SAFE_EXACT:
        if tuple(argv) == exact:
            return argv

    return None


class SystemInstaller:
    """Build and execute a safe installation plan from check results."""

    def __init__(
        self,
        *,
        console: ConsoleProtocol,
        runner: CommandRunner | None = None,
        confirm: Callable[[str], bool] | None = None,
    ) -> None:
        self._console = console
        self._runner = runner or DefaultCommandRunner()
        self._confirm = confirm

    def plan_installation(self, results: list[CheckResult]) -> InstallPlan:
        steps: list[InstallStep] = []
        manual: list[tuple[str, str]] = []

        for r in results:
            hint = (r.hint or "").strip()
            if not hint:
                continue
            argv = _parse_safe_install_argv(hint)
            if argv is None:
                manual.append((r.name, hint))
            else:
                steps.append(InstallStep(name=r.name, argv=argv))

        return InstallPlan(steps=steps, manual=manual)

    def apply(self, plan: InstallPlan, *, dry_run: bool, assume_yes: bool) -> bool:
        if plan.is_empty:
            return True

        success = True

        if plan.steps:
            self._console.header("Install")
            for step in plan.steps:
                self._console.print(f"  {step.display}", Style.DIM)
            self._console.newline()

            if dry_run:
                self._console.print("Dry-run: not executing install commands", Style.DIM)
            elif assume_yes:
                for step in plan.steps:
                    self._console.print(f"Running: {step.display}", Style.DIM)
                    result = self._runner.run(step.argv, capture=False)
                    if result.returncode != 0:
                        self._console.error(f"Install failed: {step.name}")
                        success = False
                        break
                    self._console.success(f"Installed: {step.name}")
            elif self._confirm is None:
                self._console.error("Cannot prompt for confirmation (no prompt available)")
                success = False
            elif not self._confirm("Run the install commands above?"):
                self._console.warning("Skipped install commands")
                success = False
            else:
                for step in plan.steps:
                    self._console.print(f"Running: {step.display}", Style.DIM)
                    result = self._runner.run(step.argv, capture=False)
                    if result.returncode != 0:
                        self._console.error(f"Install failed: {step.name}")
                        success = False
                        break
                    self._console.success(f"Installed: {step.name}")

        if plan.manual:
            self._console.header("Manual steps")
            for name, hint in plan.manual:
                self._console.print(f"  {name}: {hint}", Style.WARNING)

        return success
