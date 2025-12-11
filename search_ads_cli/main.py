"""Main CLI application."""

from typing import Annotated

import typer
from rich.console import Console

from search_ads_cli import ad_groups, auth, brand, campaigns, keywords, optimize, reports

app = typer.Typer(
    name="asa",
    help="Apple Search Ads API CLI - Manage campaigns, ad groups, keywords, and reports.",
    rich_markup_mode="rich",
)

console = Console()

# Register sub-commands
app.add_typer(auth.app, name="auth", help="Authentication commands")
app.add_typer(brand.app, name="brand", help="Create brand protection campaigns")
app.add_typer(campaigns.app, name="campaigns", help="Manage campaigns")
app.add_typer(ad_groups.app, name="ad-groups", help="Manage ad groups")
app.add_typer(keywords.app, name="keywords", help="Manage keywords")
app.add_typer(reports.app, name="reports", help="Generate reports")
app.add_typer(optimize.app, name="optimize", help="Optimization tools")


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        from asa_api_client import __version__ as api_version

        from search_ads_cli import __version__ as cli_version

        console.print(f"search-ads-cli {cli_version} (search-ads-api {api_version})")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Apple Search Ads API CLI.

    Manage your Apple Search Ads campaigns, ad groups, keywords,
    and generate performance reports from the command line.

    Set up authentication using environment variables:

        export ASA_CLIENT_ID="SEARCHADS.your-client-id"
        export ASA_TEAM_ID="YOUR_TEAM_ID"
        export ASA_KEY_ID="YOUR_KEY_ID"
        export ASA_ORG_ID="123456"
        export ASA_PRIVATE_KEY_PATH="/path/to/private-key.pem"

    Or test your credentials:

        asa auth test
    """
    if ctx.invoked_subcommand is None and not version:
        console.print(ctx.get_help())
        raise typer.Exit()


if __name__ == "__main__":
    app()
