from pathlib import Path

import pytest
from typer.testing import CliRunner

from ms.cli.commands.ux import ux_app


def test_hardware_help_and_explicit_device_options() -> None:
    runner = CliRunner()
    result = runner.invoke(ux_app, ["hardware", "--help"])
    assert result.exit_code == 0
    assert "reboot" in result.output
    result = runner.invoke(ux_app, ["hardware", "run", "input.ux"])
    assert result.exit_code != 0
    assert "--serial" in result.output


def test_invalid_script_fails_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.ux_hardware as command

    def unexpected(*_: object, **__: object) -> None:
        raise AssertionError("must validate before connecting")

    monkeypatch.setattr(command, "HardwareClient", unexpected)
    path = tmp_path / "bad.ux"
    path.write_text("0 encoder NAV 1\n", encoding="utf-8")
    result = CliRunner().invoke(
        ux_app,
        [
            "hardware",
            "run",
            str(path),
            "--serial",
            "18040250",
            "--control-port",
            "8001",
            "--output-root",
            str(tmp_path / "result"),
        ],
    )
    assert result.exit_code == 1
    assert "unsupported hardware" in result.output
