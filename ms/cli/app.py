from __future__ import annotations

import typer

from ms import __version__
from ms.cli.commands.bitwig import bitwig
from ms.cli.commands.bridge import bridge
from ms.cli.commands.check import check
from ms.cli.commands.clean import clean
from ms.cli.commands.core import core
from ms.cli.commands.setup import setup
from ms.cli.commands.status import status
from ms.cli.commands.sync import sync
from ms.cli.commands.tools import tools


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)


# Commands
app.command()(check)
app.command()(setup)
app.command()(sync)
app.command()(tools)
app.command()(status)
app.command()(clean)
app.command()(core)
app.command()(bitwig)
app.command()(bridge)


@app.callback()
def _main(  # pyright: ignore[reportUnusedFunction]
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit(code=0)


def main() -> None:
    app()
