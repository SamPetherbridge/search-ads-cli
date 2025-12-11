"""Report CLI commands."""

import csv
import json
from pathlib import Path
from typing import Annotated, Any

import typer
from asa_api_client.exceptions import AppleSearchAdsError
from asa_api_client.models import GranularityType
from rich.panel import Panel
from rich.table import Table

from search_ads_cli.utils import (
    console,
    format_number,
    format_percent,
    get_client,
    handle_api_error,
    parse_date,
    print_error,
    print_success,
    print_warning,
    spinner,
)

app = typer.Typer(help="Generate performance reports")


def format_report_money(spend: object | None) -> str:
    """Format money value for display."""
    if spend is None:
        return "-"
    return f"{spend.amount} {spend.currency}"  # type: ignore


def report_row_to_dict(row: object) -> dict[str, Any]:
    """Convert report row to display dictionary."""
    result: dict[str, Any] = {}

    # Metadata
    if row.metadata:  # type: ignore
        meta = row.metadata  # type: ignore
        if meta.campaign_name:
            result["campaign"] = meta.campaign_name
        if meta.ad_group_name:
            result["ad_group"] = meta.ad_group_name
        if meta.keyword:
            result["keyword"] = meta.keyword
        if meta.search_term_text:
            result["search_term"] = meta.search_term_text
        if meta.country_or_region:
            result["country"] = meta.country_or_region

    # Metrics
    if row.total:  # type: ignore
        total = row.total  # type: ignore
        result["impressions"] = total.impressions
        result["taps"] = total.taps
        result["installs"] = total.installs
        result["ttr"] = total.ttr
        result["conv_rate"] = total.conversion_rate
        result["spend"] = total.local_spend.amount if total.local_spend else None
        result["avg_cpt"] = total.avg_cpt.amount if total.avg_cpt else None
        result["avg_cpa"] = total.avg_cpa.amount if total.avg_cpa else None

    return result


def print_report_table(
    data: list[dict[str, Any]],
    columns: list[str],
    title: str,
) -> None:
    """Print report data as a styled table."""
    table = Table(
        title=title,
        show_header=True,
        header_style="header",
        border_style="muted",
        row_styles=["", "dim"],
    )

    # Column headers
    column_labels = {
        "campaign": "Campaign",
        "ad_group": "Ad Group",
        "keyword": "Keyword",
        "search_term": "Search Term",
        "country": "Country",
        "impressions": "Impressions",
        "taps": "Taps",
        "installs": "Installs",
        "ttr": "TTR",
        "conv_rate": "Conv Rate",
        "spend": "Spend",
        "avg_cpt": "Avg CPT",
        "avg_cpa": "Avg CPA",
    }

    for col in columns:
        table.add_column(column_labels.get(col, col))

    for row in data:
        values = []
        for col in columns:
            value = row.get(col)
            if col in ("ttr", "conv_rate"):
                values.append(format_percent(value))
            elif col in ("impressions", "taps", "installs"):
                values.append(format_number(value))
            elif col in ("spend", "avg_cpt", "avg_cpa"):
                values.append(str(value) if value else "-")
            else:
                values.append(str(value) if value else "-")
        table.add_row(*values)

    console.print(table)


def print_grand_totals(report: object) -> None:
    """Print grand totals in a styled panel."""
    if not report.grand_totals or not report.grand_totals.total:  # type: ignore
        return

    total = report.grand_totals.total  # type: ignore

    lines = []
    lines.append(f"[label]Impressions:[/label] [value]{format_number(total.impressions)}[/value]")
    lines.append(f"[label]Taps:[/label] [value]{format_number(total.taps)}[/value]")
    lines.append(f"[label]Installs:[/label] [value]{format_number(total.installs)}[/value]")

    if total.ttr is not None:
        lines.append(f"[label]TTR:[/label] [value]{format_percent(total.ttr)}[/value]")
    if total.conversion_rate is not None:
        lines.append(f"[label]Conv Rate:[/label] [value]{format_percent(total.conversion_rate)}[/value]")
    if total.local_spend:
        spend = total.local_spend
        lines.append(f"[label]Total Spend:[/label] [value]{spend.amount} {spend.currency}[/value]")

    panel = Panel(
        "\n".join(lines),
        title="[info]Grand Totals[/info]",
        border_style="cyan",
        padding=(0, 1),
    )
    console.print()
    console.print(panel)


def save_report(
    data: list[dict[str, Any]],
    output: Path,
    columns: list[str],
) -> None:
    """Save report to file."""
    suffix = output.suffix.lower()

    if suffix == ".json":
        output.write_text(json.dumps(data, indent=2, default=str))
    elif suffix == ".csv":
        with output.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)
    else:
        print_error("Unsupported Format", f"File format '{suffix}' is not supported", "Supported formats: .json, .csv")
        raise typer.Exit(1)

    print_success(f"Report saved to {output}")


@app.command("campaigns")
def campaign_report(
    start: Annotated[
        str,
        typer.Option("--start", "-s", help="Start date (YYYY-MM-DD)"),
    ],
    end: Annotated[
        str,
        typer.Option("--end", "-e", help="End date (YYYY-MM-DD)"),
    ],
    campaign_ids: Annotated[
        list[int] | None,
        typer.Option("--campaign", "-c", help="Filter by campaign ID(s)"),
    ] = None,
    granularity: Annotated[
        GranularityType,
        typer.Option("--granularity", "-g", help="Time granularity"),
    ] = GranularityType.DAILY,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Save to file (JSON or CSV)"),
    ] = None,
) -> None:
    """Generate a campaign performance report.

    Examples:
        asa reports campaigns --start 2024-01-01 --end 2024-01-31
        asa reports campaigns -s 2024-01-01 -e 2024-01-31 --campaign 123
        asa reports campaigns -s 2024-01-01 -e 2024-01-31 -o report.csv
        asa reports campaigns -s 2024-01-01 -e 2024-01-31 --granularity MONTHLY
    """
    start_date = parse_date(start)
    end_date = parse_date(end)

    client = get_client()

    try:
        with client:
            with spinner("Generating campaign report..."):
                report = client.reports.campaigns(
                    start_date=start_date,
                    end_date=end_date,
                    campaign_ids=campaign_ids,
                    granularity=granularity,
                )

            if not report.row:
                print_warning("No data found for the specified period")
                return

            data = [report_row_to_dict(row) for row in report.row]
            columns = ["campaign", "impressions", "taps", "installs", "ttr", "conv_rate", "spend"]

            if output:
                save_report(data, output, columns)
            else:
                print_report_table(
                    data,
                    columns,
                    f"Campaign Report ({start} to {end})",
                )
                print_grand_totals(report)

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("ad-groups")
def ad_group_report(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    start: Annotated[
        str,
        typer.Option("--start", "-s", help="Start date (YYYY-MM-DD)"),
    ],
    end: Annotated[
        str,
        typer.Option("--end", "-e", help="End date (YYYY-MM-DD)"),
    ],
    granularity: Annotated[
        GranularityType,
        typer.Option("--granularity", "-g", help="Time granularity"),
    ] = GranularityType.DAILY,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Save to file (JSON or CSV)"),
    ] = None,
) -> None:
    """Generate an ad group performance report.

    Examples:
        asa reports ad-groups 123 --start 2024-01-01 --end 2024-01-31
        asa reports ad-groups 123 -s 2024-01-01 -e 2024-01-31 -o report.csv
    """
    start_date = parse_date(start)
    end_date = parse_date(end)

    client = get_client()

    try:
        with client:
            with spinner("Generating ad group report..."):
                report = client.reports.ad_groups(
                    campaign_id=campaign_id,
                    start_date=start_date,
                    end_date=end_date,
                    granularity=granularity,
                )

            if not report.row:
                print_warning("No data found for the specified period")
                return

            data = [report_row_to_dict(row) for row in report.row]
            columns = ["ad_group", "impressions", "taps", "installs", "ttr", "conv_rate", "spend"]

            if output:
                save_report(data, output, columns)
            else:
                print_report_table(
                    data,
                    columns,
                    f"Ad Group Report ({start} to {end})",
                )
                print_grand_totals(report)

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("keywords")
def keyword_report(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    start: Annotated[
        str,
        typer.Option("--start", "-s", help="Start date (YYYY-MM-DD)"),
    ],
    end: Annotated[
        str,
        typer.Option("--end", "-e", help="End date (YYYY-MM-DD)"),
    ],
    ad_group_ids: Annotated[
        list[int] | None,
        typer.Option("--ad-group", "-a", help="Filter by ad group ID(s)"),
    ] = None,
    granularity: Annotated[
        GranularityType,
        typer.Option("--granularity", "-g", help="Time granularity"),
    ] = GranularityType.DAILY,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Save to file (JSON or CSV)"),
    ] = None,
) -> None:
    """Generate a keyword performance report.

    Examples:
        asa reports keywords 123 --start 2024-01-01 --end 2024-01-31
        asa reports keywords 123 -s 2024-01-01 -e 2024-01-31 --ad-group 456
        asa reports keywords 123 -s 2024-01-01 -e 2024-01-31 -o keywords.csv
    """
    start_date = parse_date(start)
    end_date = parse_date(end)

    client = get_client()

    try:
        with client:
            with spinner("Generating keyword report..."):
                report = client.reports.keywords(
                    campaign_id=campaign_id,
                    start_date=start_date,
                    end_date=end_date,
                    ad_group_ids=ad_group_ids,
                    granularity=granularity,
                )

            if not report.row:
                print_warning("No data found for the specified period")
                return

            data = [report_row_to_dict(row) for row in report.row]
            columns = ["keyword", "impressions", "taps", "installs", "ttr", "conv_rate", "spend", "avg_cpt"]

            if output:
                save_report(data, output, columns)
            else:
                print_report_table(
                    data,
                    columns,
                    f"Keyword Report ({start} to {end})",
                )
                print_grand_totals(report)

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None


@app.command("search-terms")
def search_term_report(
    campaign_id: Annotated[int, typer.Argument(help="Campaign ID")],
    start: Annotated[
        str,
        typer.Option("--start", "-s", help="Start date (YYYY-MM-DD)"),
    ],
    end: Annotated[
        str,
        typer.Option("--end", "-e", help="End date (YYYY-MM-DD)"),
    ],
    ad_group_id: Annotated[
        int | None,
        typer.Option("--ad-group", "-a", help="Filter by ad group ID"),
    ] = None,
    granularity: Annotated[
        GranularityType,
        typer.Option("--granularity", "-g", help="Time granularity"),
    ] = GranularityType.DAILY,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Save to file (JSON or CSV)"),
    ] = None,
) -> None:
    """Generate a search term performance report.

    Shows actual search queries that triggered your ads.

    Examples:
        asa reports search-terms 123 --start 2024-01-01 --end 2024-01-31
        asa reports search-terms 123 -s 2024-01-01 -e 2024-01-31 -o terms.csv
    """
    start_date = parse_date(start)
    end_date = parse_date(end)

    client = get_client()

    try:
        with client:
            with spinner("Generating search term report..."):
                report = client.reports.search_terms(
                    campaign_id=campaign_id,
                    start_date=start_date,
                    end_date=end_date,
                    ad_group_id=ad_group_id,
                    granularity=granularity,
                )

            if not report.row:
                print_warning("No data found for the specified period")
                return

            data = [report_row_to_dict(row) for row in report.row]
            columns = ["search_term", "impressions", "taps", "installs", "ttr", "conv_rate", "spend"]

            if output:
                save_report(data, output, columns)
            else:
                print_report_table(
                    data,
                    columns,
                    f"Search Term Report ({start} to {end})",
                )
                print_grand_totals(report)

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None
