"""CLI entry point for Groundskeeper."""

from __future__ import annotations

import click

from groundskeeper import __version__


@click.group()
@click.version_option(version=__version__, prog_name="groundskeeper")
def cli() -> None:
    """Groundskeeper — Cross-platform permission auditor for sovereign infrastructure."""


@cli.command()
@click.option("--platform", default=None, help="Scan a specific platform only.")
@click.option("--flagged", is_flag=True, help="Show only flagged grants.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format.",
)
@click.option("--quiet", is_flag=True, help="Suppress progress output.")
def scan(platform: str | None, flagged: bool, output_format: str, quiet: bool) -> None:
    """Scan platforms for permission grants."""
    click.echo("Scan command — full implementation in Phase 4.")


@cli.command()
@click.option("--output", "output_path", default=None, type=click.Path(), help="Write report to file.")
@click.option("--platform", default=None, help="Scope report to a specific platform.")
@click.option("--include-clean", is_flag=True, help="Include unflagged grants in report.")
def report(output_path: str | None, platform: str | None, include_clean: bool) -> None:
    """Generate an audit report."""
    click.echo("Report command — full implementation in Phase 4.")


@cli.group()
def config() -> None:
    """Manage Groundskeeper configuration."""


@config.command("init")
def config_init() -> None:
    """Create default configuration directory and files."""
    from pathlib import Path

    config_dir = Path.home() / ".groundskeeper"
    config_dir.mkdir(exist_ok=True)
    click.echo(f"Configuration directory: {config_dir}")


if __name__ == "__main__":
    cli()
