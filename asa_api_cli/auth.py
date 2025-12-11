"""Authentication CLI commands."""

from pathlib import Path
from typing import Annotated

import typer
from asa_api_client import AppleSearchAdsClient, Settings
from asa_api_client.exceptions import AppleSearchAdsError, ConfigurationError
from pydantic import ValidationError
from rich.table import Table

from asa_api_cli.utils import (
    console,
    print_error,
    print_info,
    print_result_panel,
    spinner,
)

app = typer.Typer(help="Authentication commands")


@app.command("test")
def test_auth(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", "-e", help="Path to .env file"),
    ] = Path(".env"),
) -> None:
    """Test authentication credentials.

    Loads configuration from environment variables and .env file,
    then attempts to authenticate with the Apple Search Ads API.

    Examples:
        asa auth test
        asa auth test --env-file .env.production
    """
    print_info("Testing Apple Search Ads API credentials...")
    console.print()

    # Try to load settings
    try:
        if env_file and env_file.exists():
            settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
            print_info(f"Loaded configuration from {env_file}")
        else:
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            if env_file:
                print_info("No .env file found, using environment variables only")
    except ValidationError as e:
        # Show what's missing
        table = Table(
            title="Configuration Status",
            show_header=True,
            header_style="header",
            border_style="muted",
        )
        table.add_column("Setting", style="label")
        table.add_column("Status")

        errors_by_field = {err["loc"][0]: err["msg"] for err in e.errors()}

        for field in ["client_id", "team_id", "key_id", "org_id", "private_key", "private_key_path"]:
            if field in errors_by_field:
                table.add_row(f"ASA_{field.upper()}", f"[error]{errors_by_field[field]}[/error]")
            else:
                table.add_row(f"ASA_{field.upper()}", "[success]OK[/success]")

        console.print(table)
        console.print()
        print_error("Configuration Error", "Missing or invalid settings")
        raise typer.Exit(1) from None

    # Display loaded configuration
    table = Table(
        title="Configuration",
        show_header=True,
        header_style="header",
        border_style="muted",
    )
    table.add_column("Setting", style="label")
    table.add_column("Value")

    # Mask client_id
    client_id_display = settings.client_id[:20] + "..." if len(settings.client_id) > 20 else settings.client_id
    table.add_row("ASA_CLIENT_ID", f"[success]{client_id_display}[/success]")
    table.add_row("ASA_TEAM_ID", f"[success]{settings.team_id}[/success]")
    table.add_row("ASA_KEY_ID", f"[success]{settings.key_id}[/success]")
    table.add_row("ASA_ORG_ID", f"[success]{settings.org_id}[/success]")

    if settings.private_key_path:
        table.add_row("ASA_PRIVATE_KEY_PATH", f"[success]{settings.private_key_path}[/success]")
    if settings.private_key:
        table.add_row("ASA_PRIVATE_KEY", "[success]<set>[/success]")

    console.print(table)
    console.print()

    # Try to authenticate
    print_info("Attempting to authenticate...")

    try:
        client = AppleSearchAdsClient.from_env(env_file=env_file)
    except ConfigurationError as e:
        print_error("Configuration Error", e.message)
        raise typer.Exit(1) from None

    try:
        # Try to list campaigns to verify authentication works
        with client:
            with spinner("Authenticating with Apple Search Ads API..."):
                campaigns = client.campaigns.list(limit=1)

            print_result_panel(
                "Authentication Successful",
                {
                    "Organization ID": str(client.org_id),
                    "Total Campaigns": str(campaigns.total_results),
                },
            )

    except AppleSearchAdsError as e:
        print_error("API Error", e.message, f"Status code: {e.status_code}" if e.status_code else None)
        raise typer.Exit(1) from None


@app.command("show")
def show_config(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", "-e", help="Path to .env file"),
    ] = Path(".env"),
) -> None:
    """Show current authentication configuration.

    Displays configuration loaded from environment variables and .env file.

    Examples:
        asa auth show
        asa auth show --env-file .env.production
    """
    # Try to load settings
    try:
        if env_file and env_file.exists():
            settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
            source = f"from {env_file}"
        else:
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            source = "from environment variables"

        table = Table(
            title=f"Current Configuration ({source})",
            show_header=True,
            header_style="header",
            border_style="muted",
        )
        table.add_column("Setting", style="label")
        table.add_column("Value")

        # Mask client_id partially
        client_id_display = settings.client_id[:20] + "..." if len(settings.client_id) > 20 else settings.client_id
        table.add_row("ASA_CLIENT_ID", client_id_display)
        table.add_row("ASA_TEAM_ID", settings.team_id)
        table.add_row("ASA_KEY_ID", settings.key_id)
        table.add_row("ASA_ORG_ID", str(settings.org_id))

        if settings.private_key_path:
            table.add_row("ASA_PRIVATE_KEY_PATH", str(settings.private_key_path))
        else:
            table.add_row("ASA_PRIVATE_KEY_PATH", "[muted]<not set>[/muted]")

        if settings.private_key:
            table.add_row("ASA_PRIVATE_KEY", "[success]<set>[/success]")
        else:
            table.add_row("ASA_PRIVATE_KEY", "[muted]<not set>[/muted]")

        console.print(table)

    except ValidationError as e:
        print_error("Configuration Error", "Could not load settings")
        for err in e.errors():
            field = err["loc"][0]
            msg = err["msg"]
            console.print(f"  [error]ASA_{str(field).upper()}:[/error] {msg}")
        raise typer.Exit(1) from None
