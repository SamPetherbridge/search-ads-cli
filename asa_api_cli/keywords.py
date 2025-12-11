"""Keyword CLI commands."""

from typing import Annotated, Any

import typer
from asa_api_client.exceptions import AppleSearchAdsError
from asa_api_client.models import (
    KeywordCreate,
    KeywordMatchType,
    KeywordStatus,
    KeywordUpdate,
    Money,
    NegativeKeywordCreate,
    Selector,
)

from asa_api_cli.utils import (
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

app = typer.Typer(help="Manage keywords")

KEYWORD_COLUMNS = [
    "id",
    "text",
    "match_type",
    "status",
    "bid",
]

KEYWORD_COLUMN_LABELS = {
    "id": "ID",
    "match_type": "Match Type",
}


def keyword_to_dict(keyword: object) -> dict[str, Any]:
    """Convert keyword to display dictionary."""
    return {
        "id": keyword.id,  # type: ignore
        "text": keyword.text,  # type: ignore
        "match_type": enum_value(keyword.match_type),  # type: ignore
        "status": enum_value(keyword.status),  # type: ignore
        "bid": format_money(
            keyword.bid_amount.amount if keyword.bid_amount else None,  # type: ignore
            keyword.bid_amount.currency if keyword.bid_amount else None,  # type: ignore
        ),
    }


@app.command("list")
def list_keywords(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID")],
    status: Annotated[
        KeywordStatus | None,
        typer.Option("--status", "-s", help="Filter by status"),
    ] = None,
    match_type: Annotated[
        KeywordMatchType | None,
        typer.Option("--match-type", "-m", help="Filter by match type"),
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
    """List targeting keywords in an ad group.

    Examples:
        asa keywords list 123 456
        asa keywords list 123 456 --status ACTIVE
        asa keywords list 123 456 --match-type EXACT
        asa keywords list 123 456 --format json
    """
    client = get_client()

    try:
        with client:
            with spinner("Fetching keywords..."):
                selector = Selector().limit(limit)

                if status:
                    selector = selector.where("status", "==", status.value)
                if match_type:
                    selector = selector.where("matchType", "==", match_type.value)

                if selector.conditions:
                    keywords = client.campaigns(campaign_id).ad_groups(ad_group_id).keywords.find(selector)
                else:
                    keywords = client.campaigns(campaign_id).ad_groups(ad_group_id).keywords.list(limit=limit)

            if not keywords.data:
                print_warning("No keywords found")
                return

            data = [keyword_to_dict(k) for k in keywords]
            output_data(
                data,
                KEYWORD_COLUMNS,
                format,
                title=f"Keywords ({keywords.total_results} total)",
                column_labels=KEYWORD_COLUMN_LABELS,
            )

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("get")
def get_keyword(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID")],
    keyword_id: Annotated[int, typer.Argument(help="Keyword ID")],
    format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.JSON,
) -> None:
    """Get details for a specific keyword.

    Examples:
        asa keywords get 123 456 789
    """
    client = get_client()

    try:
        with client:
            with spinner("Fetching keyword..."):
                keyword = client.campaigns(campaign_id).ad_groups(ad_group_id).keywords.get(keyword_id)

            if format == OutputFormat.JSON:
                print_json(keyword, title=f"Keyword {keyword_id}")
            else:
                data = [keyword_to_dict(keyword)]
                output_data(data, KEYWORD_COLUMNS, format, column_labels=KEYWORD_COLUMN_LABELS)

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("add")
def add_keyword(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID")],
    text: Annotated[str, typer.Argument(help="Keyword text")],
    match_type: Annotated[
        KeywordMatchType,
        typer.Option("--match-type", "-m", help="Match type"),
    ] = KeywordMatchType.EXACT,
    bid: Annotated[
        float | None,
        typer.Option("--bid", "-b", help="Bid amount (uses ad group default if not specified)"),
    ] = None,
    currency: Annotated[
        str,
        typer.Option("--currency", "-c", help="Currency code"),
    ] = "USD",
) -> None:
    """Add a targeting keyword.

    Examples:
        asa keywords add 123 456 "productivity app"
        asa keywords add 123 456 "todo list" --match-type BROAD
        asa keywords add 123 456 "task manager" --bid 2.50
    """
    client = get_client()

    try:
        with client:
            create_data = KeywordCreate(
                text=text,
                match_type=match_type,
            )
            if bid is not None:
                create_data.bid_amount = Money(amount=str(bid), currency=currency)

            with spinner("Adding keyword..."):
                keyword = client.campaigns(campaign_id).ad_groups(ad_group_id).keywords.create(create_data)

            print_result_panel(
                "Keyword Added",
                {
                    "ID": str(keyword.id),
                    "Text": keyword.text,
                    "Match Type": keyword.match_type.value,
                },
            )

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("pause")
def pause_keyword(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID")],
    keyword_id: Annotated[int, typer.Argument(help="Keyword ID to pause")],
) -> None:
    """Pause a keyword.

    Examples:
        asa keywords pause 123 456 789
    """
    client = get_client()

    try:
        with client:
            with spinner("Pausing keyword..."):
                keyword = (
                    client.campaigns(campaign_id)
                    .ad_groups(ad_group_id)
                    .keywords.update(keyword_id, data=KeywordUpdate(status=KeywordStatus.PAUSED))
                )
            print_success(f"Keyword '{keyword.text}' paused")

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("enable")
def enable_keyword(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID")],
    keyword_id: Annotated[int, typer.Argument(help="Keyword ID to enable")],
) -> None:
    """Enable a paused keyword.

    Examples:
        asa keywords enable 123 456 789
    """
    client = get_client()

    try:
        with client:
            with spinner("Enabling keyword..."):
                keyword = (
                    client.campaigns(campaign_id)
                    .ad_groups(ad_group_id)
                    .keywords.update(keyword_id, data=KeywordUpdate(status=KeywordStatus.ACTIVE))
                )
            print_success(f"Keyword '{keyword.text}' enabled")

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("set-bid")
def set_keyword_bid(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID")],
    keyword_id: Annotated[int, typer.Argument(help="Keyword ID")],
    bid: Annotated[float, typer.Argument(help="New bid amount")],
    currency: Annotated[
        str,
        typer.Option("--currency", "-c", help="Currency code"),
    ] = "USD",
) -> None:
    """Set the bid for a keyword.

    Examples:
        asa keywords set-bid 123 456 789 3.00
        asa keywords set-bid 123 456 789 2.50 --currency EUR
    """
    client = get_client()

    try:
        with client:
            with spinner("Updating keyword bid..."):
                keyword = (
                    client.campaigns(campaign_id)
                    .ad_groups(ad_group_id)
                    .keywords.update(
                        keyword_id,
                        data=KeywordUpdate(bid_amount=Money(amount=str(bid), currency=currency)),
                    )
                )

            print_result_panel(
                "Keyword Bid Updated",
                {
                    "Keyword": keyword.text,
                    "Bid": f"{keyword.bid_amount.amount} {keyword.bid_amount.currency}",
                },
            )

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("delete")
def delete_keyword(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[int, typer.Argument(help="Ad Group ID")],
    keyword_id: Annotated[int, typer.Argument(help="Keyword ID to delete")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
) -> None:
    """Delete a keyword.

    Examples:
        asa keywords delete 123 456 789
        asa keywords delete 123 456 789 --force
    """
    client = get_client()

    try:
        with client:
            with spinner("Fetching keyword..."):
                keyword = client.campaigns(campaign_id).ad_groups(ad_group_id).keywords.get(keyword_id)

            if not force:
                if not confirm_action(f"Are you sure you want to delete keyword '{keyword.text}'?"):
                    print_warning("Cancelled")
                    raise typer.Exit(0)

            with spinner("Deleting keyword..."):
                client.campaigns(campaign_id).ad_groups(ad_group_id).keywords.delete(keyword_id)

            print_success(f"Keyword '{keyword.text}' deleted")

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


# Negative keywords subcommand
negatives_app = typer.Typer(help="Manage negative keywords")
app.add_typer(negatives_app, name="negatives")

NEGATIVE_KEYWORD_COLUMNS = ["id", "text", "match_type", "status"]
NEGATIVE_KEYWORD_COLUMN_LABELS = {
    "id": "ID",
    "match_type": "Match Type",
}


@negatives_app.command("list")
def list_negatives(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    ad_group_id: Annotated[
        int | None,
        typer.Option("--ad-group", "-a", help="Ad Group ID (for ad group level negatives)"),
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
    """List negative keywords.

    Examples:
        asa keywords negatives list 123                 # Campaign level
        asa keywords negatives list 123 --ad-group 456  # Ad group level
    """
    client = get_client()

    try:
        with client:
            level = "Ad Group" if ad_group_id else "Campaign"

            with spinner(f"Fetching {level.lower()} negative keywords..."):
                if ad_group_id:
                    negatives = client.campaigns(campaign_id).ad_groups(ad_group_id).negative_keywords.list(limit=limit)
                else:
                    negatives = client.campaigns(campaign_id).negative_keywords.list(limit=limit)

            if not negatives.data:
                print_warning(f"No {level.lower()} negative keywords found")
                return

            data = [
                {
                    "id": n.id,
                    "text": n.text,
                    "match_type": n.match_type.value,
                    "status": n.status.value,
                }
                for n in negatives
            ]
            output_data(
                data,
                NEGATIVE_KEYWORD_COLUMNS,
                format,
                title=f"{level} Negative Keywords ({negatives.total_results} total)",
                column_labels=NEGATIVE_KEYWORD_COLUMN_LABELS,
            )

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@negatives_app.command("add")
def add_negative(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    text: Annotated[str, typer.Argument(help="Keyword text to exclude")],
    ad_group_id: Annotated[
        int | None,
        typer.Option("--ad-group", "-a", help="Ad Group ID (for ad group level negative)"),
    ] = None,
    match_type: Annotated[
        KeywordMatchType,
        typer.Option("--match-type", "-m", help="Match type"),
    ] = KeywordMatchType.EXACT,
) -> None:
    """Add a negative keyword.

    Examples:
        asa keywords negatives add 123 "free"                    # Campaign level
        asa keywords negatives add 123 "cheap" --ad-group 456    # Ad group level
        asa keywords negatives add 123 "competitor" --match-type BROAD
    """
    client = get_client()

    try:
        with client:
            create_data = NegativeKeywordCreate(
                text=text,
                match_type=match_type,
            )

            level = "ad group" if ad_group_id else "campaign"

            with spinner(f"Adding negative keyword at {level} level..."):
                if ad_group_id:
                    negative = (
                        client.campaigns(campaign_id).ad_groups(ad_group_id).negative_keywords.create(create_data)
                    )
                else:
                    negative = client.campaigns(campaign_id).negative_keywords.create(create_data)

            print_result_panel(
                "Negative Keyword Added",
                {
                    "Level": level.title(),
                    "Text": negative.text,
                    "Match Type": negative.match_type.value,
                },
            )

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@negatives_app.command("delete")
def delete_negative(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    keyword_id: Annotated[int, typer.Argument(help="Negative keyword ID to delete")],
    ad_group_id: Annotated[
        int | None,
        typer.Option("--ad-group", "-a", help="Ad Group ID (for ad group level negative)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
) -> None:
    """Delete a negative keyword.

    Examples:
        asa keywords negatives delete 123 789                  # Campaign level
        asa keywords negatives delete 123 789 --ad-group 456   # Ad group level
    """
    client = get_client()

    try:
        with client:
            if not force:
                if not confirm_action("Are you sure you want to delete this negative keyword?"):
                    print_warning("Cancelled")
                    raise typer.Exit(0)

            level = "ad group" if ad_group_id else "campaign"

            with spinner(f"Deleting {level} negative keyword..."):
                if ad_group_id:
                    client.campaigns(campaign_id).ad_groups(ad_group_id).negative_keywords.delete(keyword_id)
                else:
                    client.campaigns(campaign_id).negative_keywords.delete(keyword_id)

            print_success("Negative keyword deleted")

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None
