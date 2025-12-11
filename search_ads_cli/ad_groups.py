"""Ad Group CLI commands."""

from typing import Annotated, Any

import typer
from asa_api_client.exceptions import AppleSearchAdsError
from asa_api_client.models import AdGroupStatus, AdGroupUpdate, Money, Selector

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

app = typer.Typer(help="Manage ad groups")

AD_GROUP_COLUMNS = [
    "id",
    "name",
    "status",
    "serving_status",
    "default_bid",
    "search_match",
]

AD_GROUP_COLUMN_LABELS = {
    "id": "ID",
    "serving_status": "Serving",
    "default_bid": "Default Bid",
    "search_match": "Search Match",
}


def ad_group_to_dict(ad_group: object) -> dict[str, Any]:
    """Convert ad group to display dictionary."""
    return {
        "id": ad_group.id,  # type: ignore
        "name": ad_group.name,  # type: ignore
        "status": enum_value(ad_group.status),  # type: ignore
        "serving_status": enum_value(ad_group.serving_status),  # type: ignore
        "default_bid": format_money(
            ad_group.default_bid_amount.amount,  # type: ignore
            ad_group.default_bid_amount.currency,  # type: ignore
        ),
        "search_match": enum_value(ad_group.automated_keywords_opt_in),  # type: ignore
    }


@app.command("list")
def list_ad_groups(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    status: Annotated[
        AdGroupStatus | None,
        typer.Option("--status", "-s", help="Filter by status"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of results"),
    ] = 100,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """List ad groups in a campaign.

    Examples:
        asa ad-groups list 123456789
        asa ad-groups list 123456789 --status ENABLED
        asa ad-groups list 123456789 --format json
    """
    client = get_client()

    try:
        with client:
            with spinner("Fetching ad groups..."):
                if status:
                    selector = Selector().where("status", "==", status.value).limit(limit)
                    ad_groups = client.campaigns(campaign_id).ad_groups.find(selector)
                else:
                    ad_groups = client.campaigns(campaign_id).ad_groups.list(limit=limit)

            if not ad_groups.data:
                print_warning("No ad groups found")
                return

            data = [ad_group_to_dict(ag) for ag in ad_groups]
            output_data(
                data,
                AD_GROUP_COLUMNS,
                format,
                title=f"Ad Groups ({ad_groups.total_results} total)",
                column_labels=AD_GROUP_COLUMN_LABELS,
            )

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("get")
def get_ad_group(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID")],
    format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.JSON,
) -> None:
    """Get details for a specific ad group.

    Examples:
        asa ad-groups get 123456789 987654321
        asa ad-groups get 123456789 987654321 --format table
    """
    client = get_client()

    try:
        with client:
            with spinner("Fetching ad group..."):
                ad_group = client.campaigns(campaign_id).ad_groups.get(ad_group_id)

            if format == OutputFormat.JSON:
                print_json(ad_group, title=f"Ad Group {ad_group_id}")
            else:
                data = [ad_group_to_dict(ad_group)]
                output_data(data, AD_GROUP_COLUMNS, format, column_labels=AD_GROUP_COLUMN_LABELS)

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("pause")
def pause_ad_group(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID to pause")],
) -> None:
    """Pause an ad group.

    Examples:
        asa ad-groups pause 123456789 987654321
    """
    client = get_client()

    try:
        with client:
            with spinner("Pausing ad group..."):
                ad_group = client.campaigns(campaign_id).ad_groups.update(
                    ad_group_id,
                    data=AdGroupUpdate(status=AdGroupStatus.PAUSED),
                )
            print_success(f"Ad group '{ad_group.name}' paused")

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("enable")
def enable_ad_group(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID to enable")],
) -> None:
    """Enable a paused ad group.

    Examples:
        asa ad-groups enable 123456789 987654321
    """
    client = get_client()

    try:
        with client:
            with spinner("Enabling ad group..."):
                ad_group = client.campaigns(campaign_id).ad_groups.update(
                    ad_group_id,
                    data=AdGroupUpdate(status=AdGroupStatus.ENABLED),
                )
            print_success(f"Ad group '{ad_group.name}' enabled")

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("set-bid")
def set_default_bid(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID")],
    bid: Annotated[float, typer.Argument(help="New default bid amount")],
    currency: Annotated[
        str,
        typer.Option("--currency", "-c", help="Currency code"),
    ] = "USD",
) -> None:
    """Set the default bid for an ad group.

    Examples:
        asa ad-groups set-bid 123456789 987654321 2.50
        asa ad-groups set-bid 123456789 987654321 2.50 --currency EUR
    """
    client = get_client()

    try:
        with client:
            with spinner("Updating default bid..."):
                ad_group = client.campaigns(campaign_id).ad_groups.update(
                    ad_group_id,
                    data=AdGroupUpdate(default_bid_amount=Money(amount=str(bid), currency=currency)),
                )

            print_result_panel(
                "Default Bid Updated",
                {
                    "Ad Group": ad_group.name,
                    "Default Bid": f"{ad_group.default_bid_amount.amount} {ad_group.default_bid_amount.currency}",
                },
            )

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("delete")
def delete_ad_group(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID to delete")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
) -> None:
    """Delete an ad group.

    WARNING: This action cannot be undone.

    Examples:
        asa ad-groups delete 123456789 987654321
        asa ad-groups delete 123456789 987654321 --force
    """
    client = get_client()

    try:
        with client:
            with spinner("Fetching ad group..."):
                ad_group = client.campaigns(campaign_id).ad_groups.get(ad_group_id)

            if not force:
                if not confirm_action(f"Are you sure you want to delete ad group '{ad_group.name}'?"):
                    print_warning("Cancelled")
                    raise typer.Exit(0)

            with spinner("Deleting ad group..."):
                client.campaigns(campaign_id).ad_groups.delete(ad_group_id)

            print_success(f"Ad group '{ad_group.name}' deleted")

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None
