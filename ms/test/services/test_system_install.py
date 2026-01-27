from __future__ import annotations

import subprocess
from pathlib import Path

from ms.output.console import MockConsole
from ms.services.checkers.base import CheckResult
from ms.services.system_install import SystemInstaller


class RecordingRunner:
    def __init__(self, returncode: int = 0):
        self.calls: list[list[str]] = []
        self._returncode = returncode

    def run(
        self, args: list[str], *, capture: bool = True, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        return subprocess.CompletedProcess(args, self._returncode, "", "")


def test_plan_parses_safe_installs_and_marks_manual() -> None:
    console = MockConsole()
    runner = RecordingRunner()
    installer = SystemInstaller(console=console, runner=runner, confirm=lambda _msg: True)

    results = [
        CheckResult.error("SDL2", "missing", hint="sudo apt install libsdl2-dev"),
        CheckResult.error("uv", "missing", hint="curl -LsSf https://astral.sh/uv/install.sh | sh"),
        CheckResult.error("gh auth", "not logged in", hint="Run: gh auth login"),
        CheckResult.warning("gh", "missing (optional)", hint="sudo apt install gh"),
    ]

    plan = installer.plan_installation(results)

    assert [s.argv for s in plan.steps] == [
        ["sudo", "apt", "install", "libsdl2-dev", "gh"],
    ]
    assert ("uv", "curl -LsSf https://astral.sh/uv/install.sh | sh") in plan.manual
    assert ("gh auth", "Run: gh auth login") in plan.manual


def test_plan_groups_packages_for_multi_package_installers() -> None:
    console = MockConsole()
    runner = RecordingRunner()
    installer = SystemInstaller(console=console, runner=runner, confirm=lambda _msg: True)

    results = [
        CheckResult.error("pkg-config", "missing", hint="sudo apt install pkg-config"),
        CheckResult.error("SDL2", "missing", hint="sudo apt install libsdl2-dev"),
        CheckResult.error("pkg-config", "missing", hint="sudo apt install pkg-config"),
    ]

    plan = installer.plan_installation(results)

    assert [s.argv for s in plan.steps] == [
        ["sudo", "apt", "install", "pkg-config", "libsdl2-dev"],
    ]


def test_plan_keeps_brew_variants_separate() -> None:
    console = MockConsole()
    runner = RecordingRunner()
    installer = SystemInstaller(console=console, runner=runner, confirm=lambda _msg: True)

    results = [
        CheckResult.error("inkscape", "missing", hint="brew install --cask inkscape"),
        CheckResult.error("pkg-config", "missing", hint="brew install pkg-config"),
    ]

    plan = installer.plan_installation(results)

    assert [s.argv for s in plan.steps] == [
        ["brew", "install", "--cask", "inkscape"],
        ["brew", "install", "pkg-config"],
    ]


def test_apply_dry_run_does_not_execute() -> None:
    console = MockConsole()
    runner = RecordingRunner()
    installer = SystemInstaller(console=console, runner=runner, confirm=lambda _msg: True)

    results = [CheckResult.error("SDL2", "missing", hint="sudo apt install libsdl2-dev")]
    plan = installer.plan_installation(results)

    ok = installer.apply(plan, dry_run=True, assume_yes=True)
    assert ok is True
    assert runner.calls == []


def test_apply_prompt_decline_skips_execution() -> None:
    console = MockConsole()
    runner = RecordingRunner()
    installer = SystemInstaller(console=console, runner=runner, confirm=lambda _msg: False)

    results = [CheckResult.error("SDL2", "missing", hint="sudo apt install libsdl2-dev")]
    plan = installer.plan_installation(results)

    ok = installer.apply(plan, dry_run=False, assume_yes=False)
    assert ok is False
    assert runner.calls == []
