"""Impression Share CLI commands for search term analysis."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated

import typer
from asa_api_client.models.reports import GranularityType, ImpressionShareReport
from rich.table import Table

from asa_api_cli.utils import (
    console,
    get_client,
    handle_api_error,
    print_error,
    print_info,
    print_success,
    print_warning,
    spinner,
)

app = typer.Typer(help="Impression share analysis for search terms")


@dataclass
class SearchTermShareData:
    """Impression share data for a search term."""

    date: str
    app_name: str
    adam_id: str
    country: str
    search_term: str
    low_share: float | None
    high_share: float | None
    rank: str | None
    search_popularity: int | None

    @property
    def share_range(self) -> str:
        """Format impression share as range string."""
        if self.low_share is None and self.high_share is None:
            return "N/A"
        low = f"{int(self.low_share * 100)}" if self.low_share else "0"
        high = f"{int(self.high_share * 100)}" if self.high_share else "?"
        return f"{low}-{high}%"

    @property
    def rank_display(self) -> str:
        """Format rank for display - convert ONE, TWO etc to 1, 2."""
        if not self.rank:
            return "N/A"
        rank_map = {
            "ONE": "1",
            "TWO": "2",
            "THREE": "3",
            "FOUR": "4",
            "GREATER_THAN_FOUR": ">4",
        }
        return rank_map.get(self.rank, self.rank)

    @property
    def popularity_display(self) -> str:
        """Format popularity for display."""
        if self.search_popularity is None:
            return "N/A"
        return str(self.search_popularity)

    @property
    def avg_share(self) -> float:
        """Average of low and high share for sorting."""
        if self.low_share is None and self.high_share is None:
            return 0.0
        low = self.low_share or 0.0
        high = self.high_share or low
        return (low + high) / 2


def _parse_report_data(report: ImpressionShareReport) -> list[SearchTermShareData]:
    """Parse impression share report into structured data."""
    results: list[SearchTermShareData] = []

    for row in report.row:
        results.append(
            SearchTermShareData(
                date=row.date or "",
                app_name=row.app_name or "",
                adam_id=row.adam_id or "",
                country=row.country_or_region or "",
                search_term=row.search_term or "",
                low_share=row.low_impression_share,
                high_share=row.high_impression_share,
                rank=row.rank,
                search_popularity=row.search_popularity,
            )
        )

    return results


def _aggregate_by_search_term(
    data: list[SearchTermShareData],
) -> dict[str, SearchTermShareData]:
    """Aggregate data by search term, keeping latest entry."""
    aggregated: dict[str, SearchTermShareData] = {}

    for item in data:
        key = f"{item.search_term}|{item.country}"
        if key not in aggregated or item.date > aggregated[key].date:
            aggregated[key] = item

    return aggregated


def _display_share_table(data: list[SearchTermShareData]) -> None:
    """Display impression share data in a rich table."""
    table = Table(title="Impression Share Analysis", show_lines=False)

    table.add_column("Search Term", style="cyan", no_wrap=False, max_width=40)
    table.add_column("Country", style="dim", width=4)
    table.add_column("Share", justify="right", style="green", width=10)
    table.add_column("Rank", justify="center", width=4)
    table.add_column("Pop", justify="center", width=3)
    table.add_column("Date", style="dim", width=10)

    for row in data[:50]:  # Limit to 50 rows
        # Color share based on value
        share_style = "green"
        if row.high_share:
            if row.high_share < 0.3:
                share_style = "red"
            elif row.high_share < 0.5:
                share_style = "yellow"

        table.add_row(
            row.search_term[:40],
            row.country,
            f"[{share_style}]{row.share_range}[/{share_style}]",
            row.rank_display,
            row.popularity_display,
            row.date,
        )

    console.print(table)

    if len(data) > 50:
        print_info(f"Showing 50 of {len(data)} results. Use --output to export all.")


@app.command("analyze")
def analyze_impression_share(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to analyze (max 30)"),
    ] = 7,
    country: Annotated[
        str | None,
        typer.Option("--country", "-c", help="Filter by country code (e.g., US, AU)"),
    ] = None,
    min_share: Annotated[
        float | None,
        typer.Option(
            "--min-share",
            help="Only show search terms with share below this % (e.g., 30)",
        ),
    ] = None,
    search: Annotated[
        str | None,
        typer.Option("--search", "-s", help="Filter by search term (partial match)"),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Export to CSV file"),
    ] = None,
) -> None:
    """Analyze impression share for your search terms.

    Shows what percentage of impressions you're capturing for search terms
    where your ads appeared. Lower share indicates opportunity for bid increases.

    Examples:
        asa impression-share analyze --days 14
        asa impression-share analyze --country US --min-share 30
        asa impression-share analyze --search "calculator" --output report.csv
    """
    client = get_client()

    # Validate days - API limits to 30 days max
    if days > 30:
        print_warning("Maximum lookback is 30 days, using 30")
        days = 30

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    country_codes = [country.upper()] if country else None

    # Fetch impression share report
    with spinner("Creating impression share report..."):
        try:
            report = client.custom_reports.get_impression_share(
                start_date=start_date,
                end_date=end_date,
                granularity=GranularityType.DAILY,
                country_codes=country_codes,
                poll_interval=3.0,
                timeout=120.0,
            )
        except Exception as e:
            handle_api_error(e)
            return

    if not report.row:
        print_warning("No impression share data available for the selected period")
        return

    print_success(f"Retrieved {len(report.row)} records")

    # Parse data
    data = _parse_report_data(report)

    # Aggregate by search term (keep latest)
    aggregated = _aggregate_by_search_term(data)
    data = list(aggregated.values())

    # Apply search filter
    if search:
        search_lower = search.lower()
        data = [d for d in data if search_lower in d.search_term.lower()]

    # Apply min share filter (show only terms below this share)
    if min_share is not None:
        threshold = min_share / 100.0
        data = [d for d in data if d.high_share is not None and d.high_share < threshold]

    if not data:
        print_warning("No search terms match the specified filters")
        return

    # Sort by share (lowest first - most opportunity)
    data.sort(key=lambda x: x.avg_share)

    # Export to CSV if requested
    if output:
        try:
            import csv

            with open(output, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "search_term",
                        "country",
                        "low_share",
                        "high_share",
                        "rank",
                        "popularity",
                        "date",
                        "app_name",
                    ]
                )
                for row in data:
                    writer.writerow(
                        [
                            row.search_term,
                            row.country,
                            row.low_share,
                            row.high_share,
                            row.rank,
                            row.search_popularity,
                            row.date,
                            row.app_name,
                        ]
                    )
            print_success(f"Exported {len(data)} rows to {output}")
        except Exception as e:
            print_error("Export failed", str(e))

    _display_share_table(data)

    # Summary
    low_share_count = sum(1 for d in data if d.high_share and d.high_share < 0.3)
    mid_share_count = sum(
        1 for d in data if d.high_share and 0.3 <= d.high_share < 0.5
    )
    high_share_count = sum(1 for d in data if d.high_share and d.high_share >= 0.5)

    print_info(f"\nTotal unique search terms: {len(data)}")
    print_info(f"  Low share (<30%): {low_share_count} - [red]bid increase suggested[/red]")
    print_info(f"  Medium share (30-50%): {mid_share_count} - [yellow]consider increase[/yellow]")
    print_info(f"  High share (50%+): {high_share_count} - [green]performing well[/green]")


@app.command("report")
def generate_share_report(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to analyze (max 30)"),
    ] = 7,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Save to CSV file"),
    ] = None,
    country: Annotated[
        str | None,
        typer.Option("--country", "-c", help="Filter by country code"),
    ] = None,
) -> None:
    """Generate a detailed impression share report.

    Creates a comprehensive report with all search term data including
    daily breakdown. Use --output to export to CSV for further analysis.

    Examples:
        asa impression-share report --days 14 --output share_report.csv
    """
    client = get_client()

    # API limits to 30 days max
    if days > 30:
        print_warning("Maximum lookback is 30 days, using 30")
        days = 30

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    country_codes = [country.upper()] if country else None

    with spinner("Generating impression share report..."):
        try:
            report = client.custom_reports.get_impression_share(
                start_date=start_date,
                end_date=end_date,
                granularity=GranularityType.DAILY,
                country_codes=country_codes,
                poll_interval=3.0,
                timeout=120.0,
            )
        except Exception as e:
            handle_api_error(e)
            return

    if not report.row:
        print_warning("No data available")
        return

    print_success(f"Report generated with {len(report.row)} records")

    data = _parse_report_data(report)

    if output:
        try:
            import csv

            with open(output, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "date",
                        "search_term",
                        "country",
                        "low_share",
                        "high_share",
                        "rank",
                        "popularity",
                        "app_name",
                        "adam_id",
                    ]
                )
                for row in data:
                    writer.writerow(
                        [
                            row.date,
                            row.search_term,
                            row.country,
                            row.low_share,
                            row.high_share,
                            row.rank,
                            row.search_popularity,
                            row.app_name,
                            row.adam_id,
                        ]
                    )
            print_success(f"Exported {len(data)} rows to {output}")
        except Exception as e:
            print_error("Export failed", str(e))
    else:
        _display_share_table(data)


@app.command("summary")
def share_summary(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to analyze (max 30)"),
    ] = 7,
) -> None:
    """Show impression share summary by country.

    Provides a high-level overview of your impression share performance
    grouped by country/region.

    Examples:
        asa impression-share summary --days 14
    """
    client = get_client()

    if days > 30:
        print_warning("Maximum lookback is 30 days, using 30")
        days = 30

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    with spinner("Generating summary..."):
        try:
            report = client.custom_reports.get_impression_share(
                start_date=start_date,
                end_date=end_date,
                granularity=GranularityType.DAILY,
                poll_interval=3.0,
                timeout=120.0,
            )
        except Exception as e:
            handle_api_error(e)
            return

    if not report.row:
        print_warning("No data available")
        return

    data = _parse_report_data(report)

    # Aggregate by country
    by_country: dict[str, list[SearchTermShareData]] = {}
    for item in data:
        if item.country not in by_country:
            by_country[item.country] = []
        by_country[item.country].append(item)

    table = Table(title=f"Impression Share Summary ({days} days)")
    table.add_column("Country", style="cyan")
    table.add_column("Search Terms", justify="right")
    table.add_column("Avg Share", justify="right")
    table.add_column("<30%", justify="right", style="red")
    table.add_column("30-50%", justify="right", style="yellow")
    table.add_column(">50%", justify="right", style="green")

    # Calculate stats per country
    summary_rows = []
    for country, items in by_country.items():
        unique_terms = len({i.search_term for i in items})
        avg_shares = [i.avg_share for i in items if i.avg_share > 0]
        avg_share = sum(avg_shares) / len(avg_shares) if avg_shares else 0

        low_count = sum(1 for i in items if i.high_share and i.high_share < 0.3)
        mid_count = sum(1 for i in items if i.high_share and 0.3 <= i.high_share < 0.5)
        high_count = sum(1 for i in items if i.high_share and i.high_share >= 0.5)

        summary_rows.append(
            (country, unique_terms, avg_share, low_count, mid_count, high_count)
        )

    # Sort by number of terms
    summary_rows.sort(key=lambda x: x[1], reverse=True)

    for country, terms, avg, low, mid, high in summary_rows:
        table.add_row(
            country,
            str(terms),
            f"{avg * 100:.0f}%",
            str(low),
            str(mid),
            str(high),
        )

    console.print(table)

    total_terms = sum(r[1] for r in summary_rows)
    print_info(f"\nTotal: {total_terms} unique search terms across {len(by_country)} countries")
