"""Core app command - hardware and simulator builds."""

from __future__ import annotations

from enum import Enum, auto

import typer

from ms.cli.commands._helpers import exit_on_error, exit_with_code
from ms.cli.context import build_context
from ms.core.app import resolve
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.output.console import Style
from ms.services.build import BuildService
from ms.services.hardware import HardwareService


class Mode(Enum):
    """Build mode for core app."""

    SIM_NATIVE = auto()  # native simulator
    SIM_WEB = auto()  # wasm simulator
    HW_BUILD = auto()  # build only
    HW_UPLOAD = auto()  # build + upload
    HW_FULL = auto()  # build + upload + monitor (default)


def _resolve_mode(build: bool, upload: bool, native: bool, web: bool) -> Mode:
    """Determine build mode from CLI flags (first match wins)."""
    if native:
        return Mode.SIM_NATIVE
    if web:
        return Mode.SIM_WEB
    if build:
        return Mode.HW_BUILD
    if upload:
        return Mode.HW_UPLOAD
    return Mode.HW_FULL


def core(
    build: bool = typer.Option(False, "--build", help="HW: build only"),
    upload: bool = typer.Option(False, "--upload", help="HW: build + upload"),
    native: bool = typer.Option(False, "--native", help="Sim: build + run"),
    web: bool = typer.Option(False, "--web", help="Sim: build + serve"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying"),
) -> None:
    """Build/run core app.

    Modes (mutually exclusive, first match wins):
      --native  Simulator: native build + run
      --web     Simulator: WASM build + serve
      --build   Hardware: build only
      --upload  Hardware: build + upload
      (default) Hardware: build + upload + monitor
    """
    ctx = build_context()

    # Resolve app
    result = resolve("core", ctx.workspace.root)
    match result:
        case Err(e):
            ctx.console.error(e.message)
            if e.available:
                ctx.console.print(f"Available: {', '.join(e.available)}", Style.DIM)
            raise typer.Exit(code=int(ErrorCode.USER_ERROR))
        case Ok(app):
            pass

    mode = _resolve_mode(build, upload, native, web)

    # Simulator modes
    if mode in (Mode.SIM_NATIVE, Mode.SIM_WEB):
        build_svc = BuildService(
            workspace=ctx.workspace,
            platform=ctx.platform,
            config=ctx.config,
            console=ctx.console,
        )
        if mode == Mode.SIM_NATIVE:
            exit_with_code(build_svc.run_native(app_name="core"))
        else:
            exit_with_code(build_svc.serve_wasm(app_name="core"))

    # Hardware modes
    hw = HardwareService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )

    match mode:
        case Mode.HW_BUILD:
            exit_on_error(hw.build(app, dry_run=dry_run), ctx)

        case Mode.HW_UPLOAD:
            exit_on_error(hw.upload(app, dry_run=dry_run), ctx)

        case Mode.HW_FULL:
            exit_with_code(hw.monitor(app))
