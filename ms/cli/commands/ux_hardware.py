from __future__ import annotations

import json
import struct
from pathlib import Path

import typer

from ms.services.ux_hardware import HardwareClient, compile_script, run_repeated

hardware_app = typer.Typer(add_completion=False, no_args_is_help=True)


@hardware_app.command("run")
def run(
    script: Path = typer.Argument(..., help="Validated hardware subset of a .ux script."),
    serial: str = typer.Option(..., "--serial", help="Exact controller USB serial."),
    control_port: int = typer.Option(..., "--control-port", min=1, max=65535),
    output: Path = typer.Option(
        ..., "--output-root", help="New directory; existing output is never overwritten."
    ),
    duration_ms: int | None = typer.Option(None, "--duration-ms", min=1, max=120000),
    max_lateness_us: int = typer.Option(100000, "--max-lateness-us", min=0, max=1000000),
    repeat: int = typer.Option(
        1, "--repeat", min=1, max=100, help="Reboot the verified benchmark between trials."
    ),
    fresh: bool = typer.Option(
        False, "--fresh", help="Reboot verified benchmark firmware before the first trial."
    ),
) -> None:
    """Run once on already-flashed, RAM-only benchmark firmware; never builds or flashes."""
    try:
        compiled = compile_script(script, duration_ms=duration_ms)
        typer.echo(
            f"Validated {compiled.count} events; autonomous run {compiled.duration_us / 1e6:g}s."
        )
        typer.echo(
            "No polling during measurement. Ctrl+C requests cancellation; "
            "partial evidence is retained."
        )
        results = run_repeated(
            compiled,
            HardwareClient(control_port, serial),
            output,
            repeat=repeat,
            fresh=fresh,
            max_lateness_us=max_lateness_us,
        )
    except (OSError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Results: {output.resolve()}")
    if any(result.get("ok") is not True for result in results):
        typer.echo(json.dumps(results), err=True)
        raise typer.Exit(code=1)


@hardware_app.command("status")
def status(
    serial: str = typer.Option(..., "--serial"),
    control_port: int = typer.Option(..., "--control-port", min=1, max=65535),
) -> None:
    """Read bridge identity and benchmark capability/state (does not start a run)."""
    _control(serial, control_port, 0)


@hardware_app.command("cancel")
def cancel(
    run_id: int = typer.Argument(..., min=1, max=0xFFFFFFFF),
    serial: str = typer.Option(..., "--serial"),
    control_port: int = typer.Option(..., "--control-port", min=1, max=65535),
) -> None:
    """Cancel a matching RAM-only benchmark run; never resets normal firmware."""
    _control(serial, control_port, 5, struct.pack("<I", run_id))


@hardware_app.command("reboot")
def reboot(
    serial: str = typer.Option(..., "--serial"),
    control_port: int = typer.Option(..., "--control-port", min=1, max=65535),
) -> None:
    """Explicitly reboot benchmark firmware; unsaved benchmark results are lost."""
    _control(serial, control_port, 6)


def _control(serial: str, port: int, operation: int, body: bytes = b"") -> None:
    try:
        client = HardwareClient(port, serial)
        hello = client.hello()
        result = hello if operation == 0 else client.rpc(operation, body)
    except (OSError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(result, indent=2))
