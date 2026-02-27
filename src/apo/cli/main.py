"""Apo CLI entry point."""

import click

from apo import __version__


@click.group()
@click.version_option(version=__version__, prog_name="apo")
def cli() -> None:
    """Apo — Turn conversations into contracts.

    Intent spec compiler for human-AI collaboration.
    """


from apo.cli.compile_cmd import compile_cmd
from apo.cli.check_cmd import check_cmd
from apo.cli.report_cmd import report_cmd
from apo.cli.init_cmd import init_cmd
from apo.cli.evolve_cmd import evolve_cmd

cli.add_command(compile_cmd)
cli.add_command(check_cmd)
cli.add_command(report_cmd)
cli.add_command(init_cmd)
cli.add_command(evolve_cmd)
