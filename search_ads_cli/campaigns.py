"""Campaign CLI commands."""

from datetime import date, timedelta
from typing import Annotated, Any

import typer
from asa_api_client.exceptions import AppleSearchAdsError
from asa_api_client.models import CampaignStatus, CampaignUpdate, Money, Selector

from search_ads_cli.utils import (
    OutputFormat,
    confirm_action,
    enum_value,
    format_money,
    get_client,
    handle_api_error,
    output_data,
    print_json,
    print_result_panel,
    print_success,
    print_warning,
    spinner,
)

app = typer.Typer(help="Manage campaigns")

CAMPAIGN_COLUMNS = [
    "id",
    "name",
    "status",
    "serving_status",
    "daily_budget",
    "countries",
]

CAMPAIGN_COLUMNS_WITH_SPEND = [
    "id",
    "name",
    "status",
    "serving_status",
    "daily_budget",
    "spend_7d",
    "countries",
]

CAMPAIGN_COLUMN_LABELS = {
    "id": "ID",
    "serving_status": "Serving",
    "daily_budget": "Daily Budget",
    "spend_7d": "Spend (7d)",
}


def _colorize_status(status: str) -> str:
    """Add color to status values."""
    if status == "ENABLED":
        return "[green]ENABLED[/green]"
    elif status == "PAUSED":
        return "[yellow]PAUSED[/yellow]"
    return status


def _colorize_serving(serving: str) -> str:
    """Add color to serving status values."""
    if serving == "RUNNING":
        return "[green]RUNNING[/green]"
    elif serving == "NOT_RUNNING":
        return "[dim]NOT_RUNNING[/dim]"
    return serving


def campaign_to_dict(campaign: object, spend: str | None = None, colorize: bool = False) -> dict[str, Any]:
    """Convert campaign to display dictionary."""
    status = enum_value(campaign.status)  # type: ignore
    serving_status = enum_value(campaign.serving_status)  # type: ignore

    if colorize:
        status = _colorize_status(status)
        serving_status = _colorize_serving(serving_status)

    result = {
        "id": campaign.id,  # type: ignore
        "name": campaign.name,  # type: ignore
        "status": status,
        "serving_status": serving_status,
        "daily_budget": format_money(
            campaign.daily_budget_amount.amount if campaign.daily_budget_amount else None,  # type: ignore
            campaign.daily_budget_amount.currency if campaign.daily_budget_amount else None,  # type: ignore
        ),
        "countries": ", ".join(campaign.countries_or_regions[:3])  # type: ignore
        + ("..." if len(campaign.countries_or_regions) > 3 else ""),  # type: ignore
    }
    if spend is not None:
        result["spend_7d"] = spend
    return result


@app.command("list")
def list_campaigns(
    status: Annotated[
        CampaignStatus | None,
        typer.Option("--status", "-s", help="Filter by status (ENABLED or PAUSED)"),
    ] = None,
    all_campaigns: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show all campaigns including paused (default: enabled only)"),
    ] = False,
    with_spend: Annotated[
        bool,
        typer.Option("--with-spend", "-w", help="Include 7-day spend (slower - requires report API)"),
    ] = False,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of results"),
    ] = 100,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """List campaigns.

    By default, shows only ENABLED campaigns. Use --all to see paused campaigns too.

    Examples:
        asa campaigns list                    # Show enabled campaigns
        asa campaigns list --all              # Show all campaigns
        asa campaigns list --status PAUSED    # Show only paused campaigns
        asa campaigns list --with-spend       # Include 7-day spend data
        asa campaigns list --format json
    """
    client = get_client()

    try:
        with client:
            # Determine which status to filter by
            filter_status = status
            if filter_status is None and not all_campaigns:
                filter_status = CampaignStatus.ENABLED

            with spinner("Fetching campaigns..."):
                if filter_status:
                    selector = Selector().where("status", "==", filter_status.value).limit(limit)
                    campaigns = client.campaigns.find(selector)
                else:
                    campaigns = client.campaigns.list(limit=limit)

            if not campaigns.data:
                print_warning("No campaigns found")
                return

            # Get spend data if requested
            spend_by_campaign: dict[int, str] = {}
            if with_spend:
                with spinner("Fetching 7-day spend data..."):
                    end = date.today()
                    start = end - timedelta(days=7)
                    report = client.reports.campaigns(start, end)

                    for row in report.row or []:
                        if row.metadata and row.metadata.campaign_id and row.total:
                            spend = row.total.local_spend
                            if spend:
                                spend_by_campaign[row.metadata.campaign_id] = f"{spend.amount} {spend.currency}"

            # Use colors for table output
            use_colors = format == OutputFormat.TABLE

            data = [
                campaign_to_dict(
                    c,
                    spend=spend_by_campaign.get(c.id),
                    colorize=use_colors,
                )
                for c in campaigns
            ]

            # Choose columns based on whether spend is included
            columns = CAMPAIGN_COLUMNS_WITH_SPEND if with_spend else CAMPAIGN_COLUMNS

            # Build title
            status_label = filter_status.value if filter_status else "all"
            title = f"Campaigns ({campaigns.total_results} {status_label})"

            output_data(
                data,
                columns,
                format,
                title=title,
                column_labels=CAMPAIGN_COLUMN_LABELS,
            )

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("get")
def get_campaign(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.JSON,
) -> None:
    """Get details for a specific campaign.

    Examples:
        asa campaigns get 123456789
        asa campaigns get 123456789 --format table
    """
    client = get_client()

    try:
        with client:
            with spinner("Fetching campaign..."):
                campaign = client.campaigns.get(campaign_id)

            if format == OutputFormat.JSON:
                print_json(campaign, title=f"Campaign {campaign_id}")
            else:
                data = [campaign_to_dict(campaign)]
                output_data(data, CAMPAIGN_COLUMNS, format, column_labels=CAMPAIGN_COLUMN_LABELS)

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("pause")
def pause_campaign(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID to pause")],
) -> None:
    """Pause a campaign.

    Examples:
        asa campaigns pause 123456789
    """
    client = get_client()

    try:
        with client:
            with spinner("Pausing campaign..."):
                campaign = client.campaigns.update(
                    campaign_id,
                    data=CampaignUpdate(status=CampaignStatus.PAUSED),
                )
            print_success(f"Campaign '{campaign.name}' paused")

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("enable")
def enable_campaign(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID to enable")],
) -> None:
    """Enable a paused campaign.

    Examples:
        asa campaigns enable 123456789
    """
    client = get_client()

    try:
        with client:
            with spinner("Enabling campaign..."):
                campaign = client.campaigns.update(
                    campaign_id,
                    data=CampaignUpdate(status=CampaignStatus.ENABLED),
                )
            print_success(f"Campaign '{campaign.name}' enabled")

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("set-budget")
def set_budget(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    daily_budget: Annotated[
        float | None,
        typer.Option("--daily", "-d", help="Daily budget amount"),
    ] = None,
    total_budget: Annotated[
        float | None,
        typer.Option("--total", "-t", help="Total budget amount"),
    ] = None,
    currency: Annotated[
        str,
        typer.Option("--currency", "-c", help="Currency code"),
    ] = "USD",
) -> None:
    """Update campaign budget.

    Examples:
        asa campaigns set-budget 123456789 --daily 100
        asa campaigns set-budget 123456789 --daily 100 --total 10000
        asa campaigns set-budget 123456789 --daily 100 --currency EUR
    """
    if daily_budget is None and total_budget is None:
        print_warning("Specify at least --daily or --total budget")
        raise typer.Exit(1)

    client = get_client()

    try:
        with client:
            update = CampaignUpdate()
            if daily_budget is not None:
                update.daily_budget_amount = Money(amount=str(daily_budget), currency=currency)
            if total_budget is not None:
                update.budget_amount = Money(amount=str(total_budget), currency=currency)

            with spinner("Updating budget..."):
                campaign = client.campaigns.update(campaign_id, data=update)

            result_data = {"Campaign": campaign.name}
            if campaign.daily_budget_amount:
                amt = campaign.daily_budget_amount
                result_data["Daily Budget"] = f"{amt.amount} {amt.currency}"
            if campaign.budget_amount:
                amt = campaign.budget_amount
                result_data["Total Budget"] = f"{amt.amount} {amt.currency}"

            print_result_panel("Budget Updated", result_data)

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("delete")
def delete_campaign(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID to delete")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
) -> None:
    """Delete a campaign.

    WARNING: This action cannot be undone.

    Examples:
        asa campaigns delete 123456789
        asa campaigns delete 123456789 --force
    """
    client = get_client()

    try:
        with client:
            # Get campaign name for confirmation
            with spinner("Fetching campaign..."):
                campaign = client.campaigns.get(campaign_id)

            if not force:
                if not confirm_action(f"Are you sure you want to delete campaign '{campaign.name}'?"):
                    print_warning("Cancelled")
                    raise typer.Exit(0)

            with spinner("Deleting campaign..."):
                client.campaigns.delete(campaign_id)

            print_success(f"Campaign '{campaign.name}' deleted")

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None
