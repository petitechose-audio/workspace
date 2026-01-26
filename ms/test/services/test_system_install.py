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
        ["sudo", "apt", "install", "libsdl2-dev"],
        ["sudo", "apt", "install", "gh"],
    ]
    assert ("uv", "curl -LsSf https://astral.sh/uv/install.sh | sh") in plan.manual
    assert ("gh auth", "Run: gh auth login") in plan.manual


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
