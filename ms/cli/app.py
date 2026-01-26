from __future__ import annotations

import typer

from ms import __version__
from ms.cli.commands.build import build, run, web
from ms.cli.commands.bitwig import bitwig_app
from ms.cli.commands.bridge import bridge_app
from ms.cli.commands.check import check
from ms.cli.commands.repos import repos_app
from ms.cli.commands.setup import setup
from ms.cli.commands.tools import tools_app


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)


# Commands
app.command()(check)
app.command()(setup)
app.command()(build)
app.command(name="run")(run)
app.command()(web)
app.add_typer(repos_app, name="repos")
app.add_typer(tools_app, name="tools")
app.add_typer(bridge_app, name="bridge")
app.add_typer(bitwig_app, name="bitwig")


@app.callback()
def _main(  # pyright: ignore[reportUnusedFunction]
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit(code=0)


def main() -> None:
    app()
