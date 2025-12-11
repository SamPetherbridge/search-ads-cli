"""Impression Share CLI commands for search term analysis."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from asa_api_client import AppleSearchAdsClient

import typer
from asa_api_client.exceptions import AppleSearchAdsError
from asa_api_client.models import Selector
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


def _display_share_table(data: list[SearchTermShareData], limit: int = 100) -> None:
    """Display impression share data in a rich table."""
    table = Table(title="Impression Share Analysis", show_lines=False)

    table.add_column("App", style="magenta", no_wrap=True, max_width=25)
    table.add_column("Search Term", style="cyan", no_wrap=False, max_width=35)
    table.add_column("Country", style="dim", width=4)
    table.add_column("Share", justify="right", style="green", width=10)
    table.add_column("Rank", justify="center", width=4)
    table.add_column("Pop", justify="center", width=3)
    table.add_column("Date", style="dim", width=10)

    for row in data[:limit]:
        # Color share based on value
        share_style = "green"
        if row.high_share:
            if row.high_share < 0.3:
                share_style = "red"
            elif row.high_share < 0.5:
                share_style = "yellow"

        table.add_row(
            row.app_name[:25] if row.app_name else "",
            row.search_term[:35],
            row.country,
            f"[{share_style}]{row.share_range}[/{share_style}]",
            row.rank_display,
            row.popularity_display,
            row.date,
        )

    console.print(table)

    if len(data) > limit:
        print_info(f"Showing {limit} of {len(data)} results. Use --limit or --output to see all.")


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
    app: Annotated[
        str | None,
        typer.Option("--app", "-a", help="Filter by app name (partial match)"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Max rows to display (0 for all)"),
    ] = 100,
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
        asa impression-share analyze --app "Chippy" --limit 200
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

    # Aggregate by search term + app (keep latest)
    aggregated = _aggregate_by_search_term(data)
    data = list(aggregated.values())

    # Apply app filter
    if app:
        app_lower = app.lower()
        data = [d for d in data if d.app_name and app_lower in d.app_name.lower()]

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

    # Use limit=0 to show all, otherwise use specified limit
    display_limit = len(data) if limit == 0 else limit
    _display_share_table(data, limit=display_limit)

    # Summary
    low_share_count = sum(1 for d in data if d.high_share and d.high_share < 0.3)
    mid_share_count = sum(1 for d in data if d.high_share and 0.3 <= d.high_share < 0.5)
    high_share_count = sum(1 for d in data if d.high_share and d.high_share >= 0.5)

    console.print(f"\n[dim]Total unique search terms:[/dim] {len(data)}")
    console.print(f"  [dim]Low share (<30%):[/dim] {low_share_count} - [red]bid increase suggested[/red]")
    console.print(f"  [dim]Medium share (30-50%):[/dim] {mid_share_count} - [yellow]consider increase[/yellow]")
    console.print(f"  [dim]High share (50%+):[/dim] {high_share_count} - [green]performing well[/green]")


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
    """Show impression share summary by app and country.

    Provides a high-level overview of your impression share performance
    grouped by app, then by country/region.

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

    # Aggregate by app, then by country
    by_app: dict[str, dict[str, list[SearchTermShareData]]] = {}
    for item in data:
        app_name = item.app_name or "Unknown"
        if app_name not in by_app:
            by_app[app_name] = {}
        if item.country not in by_app[app_name]:
            by_app[app_name][item.country] = []
        by_app[app_name][item.country].append(item)

    table = Table(title=f"Impression Share Summary ({days} days)")
    table.add_column("App", style="magenta", no_wrap=True)
    table.add_column("Country", style="cyan")
    table.add_column("Search Terms", justify="right")
    table.add_column("Avg Share", justify="right")
    table.add_column("<30%", justify="right", style="red")
    table.add_column("30-50%", justify="right", style="yellow")
    table.add_column(">50%", justify="right", style="green")

    # Sort apps alphabetically
    total_terms = 0
    total_countries = set()

    for app_name in sorted(by_app.keys()):
        countries_data = by_app[app_name]

        # Calculate stats per country for this app
        country_rows = []
        for country, items in countries_data.items():
            unique_terms = len({i.search_term for i in items})
            avg_shares = [i.avg_share for i in items if i.avg_share > 0]
            avg_share = sum(avg_shares) / len(avg_shares) if avg_shares else 0

            low_count = sum(1 for i in items if i.high_share and i.high_share < 0.3)
            mid_count = sum(1 for i in items if i.high_share and 0.3 <= i.high_share < 0.5)
            high_count = sum(1 for i in items if i.high_share and i.high_share >= 0.5)

            country_rows.append((country, unique_terms, avg_share, low_count, mid_count, high_count))
            total_terms += unique_terms
            total_countries.add(country)

        # Sort by number of terms within each app
        country_rows.sort(key=lambda x: x[1], reverse=True)

        # Add rows with app name on first row only
        for i, (country, terms, avg, low, mid, high) in enumerate(country_rows):
            table.add_row(
                app_name[:25] if i == 0 else "",
                country,
                str(terms),
                f"{avg * 100:.0f}%",
                str(low),
                str(mid),
                str(high),
            )

        # Add separator between apps (if not last app)
        if app_name != sorted(by_app.keys())[-1]:
            table.add_row("", "", "", "", "", "", "", end_section=True)

    console.print(table)

    print_info(f"\nTotal: {total_terms} search terms across {len(by_app)} apps and {len(total_countries)} countries")


@dataclass
class CorrelatedSearchTerm:
    """Search term with matched campaign/keyword data."""

    search_term: str
    country: str
    app_name: str
    low_share: float | None
    high_share: float | None
    rank: str | None
    search_popularity: int | None
    # Matched campaign/keyword data
    campaign_id: int | None = None
    campaign_name: str | None = None
    ad_group_id: int | None = None
    ad_group_name: str | None = None
    keyword_id: int | None = None
    keyword_text: str | None = None
    current_bid: Decimal | None = None
    currency: str | None = None

    @property
    def share_range(self) -> str:
        """Format impression share as range string."""
        if self.low_share is None and self.high_share is None:
            return "N/A"
        low = f"{int(self.low_share * 100)}" if self.low_share else "0"
        high = f"{int(self.high_share * 100)}" if self.high_share else "?"
        return f"{low}-{high}%"

    @property
    def avg_share(self) -> float:
        """Average of low and high share."""
        if self.low_share is None and self.high_share is None:
            return 0.0
        low = self.low_share or 0.0
        high = self.high_share or low
        return (low + high) / 2

    @property
    def is_matched(self) -> bool:
        """Whether this search term was matched to a keyword."""
        return self.keyword_id is not None


@dataclass
class KeywordInfo:
    """Cached keyword information for matching."""

    keyword_id: int
    keyword_text: str
    campaign_id: int
    campaign_name: str
    ad_group_id: int
    ad_group_name: str
    bid_amount: Decimal
    currency: str


def _build_keyword_index(
    client: "AppleSearchAdsClient",
    country: str,
) -> dict[str, list[KeywordInfo]]:
    """Build an index of keywords by text for a given country.

    Returns a dict mapping lowercase keyword text -> list of KeywordInfo
    (multiple campaigns may have the same keyword).
    """
    keyword_index: dict[str, list[KeywordInfo]] = {}

    # Get enabled campaigns for this country
    campaigns = list(client.campaigns.find(Selector().where("status", "==", "ENABLED")))

    for campaign in campaigns:
        # Check if campaign targets this country
        if country.upper() not in [c.upper() for c in campaign.countries_or_regions]:
            continue

        # Get ad groups for this campaign
        try:
            ad_groups = list(client.campaigns(campaign.id).ad_groups.find(Selector().where("status", "==", "ENABLED")))
        except AppleSearchAdsError:
            continue

        for ad_group in ad_groups:
            # Get keywords for this ad group
            try:
                keywords = list(client.campaigns(campaign.id).ad_groups(ad_group.id).keywords.list())
            except AppleSearchAdsError:
                continue

            for keyword in keywords:
                kw_text = keyword.text.lower()
                info = KeywordInfo(
                    keyword_id=keyword.id,
                    keyword_text=keyword.text,
                    campaign_id=campaign.id,
                    campaign_name=campaign.name,
                    ad_group_id=ad_group.id,
                    ad_group_name=ad_group.name,
                    bid_amount=Decimal(keyword.bid_amount.amount) if keyword.bid_amount else Decimal("0"),
                    currency=keyword.bid_amount.currency if keyword.bid_amount else "USD",
                )

                if kw_text not in keyword_index:
                    keyword_index[kw_text] = []
                keyword_index[kw_text].append(info)

    return keyword_index


@app.command("correlate")
def correlate_impression_share(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to analyze (max 30)"),
    ] = 7,
    country: Annotated[
        str | None,
        typer.Option("--country", "-c", help="Filter by country code (required for correlation)"),
    ] = None,
    min_share: Annotated[
        float | None,
        typer.Option(
            "--min-share",
            help="Only show search terms with share below this % (e.g., 30)",
        ),
    ] = None,
    unmatched_only: Annotated[
        bool,
        typer.Option("--unmatched", "-u", help="Only show search terms not matched to keywords"),
    ] = False,
    matched_only: Annotated[
        bool,
        typer.Option("--matched", "-m", help="Only show search terms matched to keywords"),
    ] = False,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Max rows to display (0 for all)"),
    ] = 50,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Export to CSV file"),
    ] = None,
) -> None:
    """Correlate impression share data with your campaigns and keywords.

    Matches search terms from impression share reports to your actual
    campaign keywords, showing current bid amounts. Useful for identifying
    which keywords need bid adjustments.

    For SKAG campaigns with single-market targeting, this provides accurate
    campaign-level attribution for impression share data.

    Examples:
        asa impression-share correlate --country US
        asa impression-share correlate --country AU --min-share 30
        asa impression-share correlate --country US --unmatched  # New keyword opportunities
        asa impression-share correlate --country US --matched --min-share 40  # Bid increase candidates
    """
    if not country:
        print_error("Error", "Country is required for correlation. Use --country/-c")
        raise typer.Exit(1)

    country = country.upper()
    client = get_client()

    if days > 30:
        print_warning("Maximum lookback is 30 days, using 30")
        days = 30

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    try:
        with client:
            # Step 1: Get impression share data
            with spinner("Fetching impression share data..."):
                report = client.custom_reports.get_impression_share(
                    start_date=start_date,
                    end_date=end_date,
                    granularity=GranularityType.DAILY,
                    country_codes=[country],
                    poll_interval=3.0,
                    timeout=120.0,
                )

            if not report.row:
                print_warning(f"No impression share data available for {country}")
                return

            print_success(f"Retrieved {len(report.row)} impression share records")

            # Step 2: Build keyword index for this country
            with spinner(f"Building keyword index for {country}..."):
                keyword_index = _build_keyword_index(client, country)

            total_kw = sum(len(v) for v in keyword_index.values())
            print_info(f"Indexed {total_kw} keywords from {len(keyword_index)} unique terms")

            # Step 3: Correlate data
            share_data = _parse_report_data(report)
            aggregated = _aggregate_by_search_term(share_data)

            correlated: list[CorrelatedSearchTerm] = []
            for item in aggregated.values():
                if item.country.upper() != country:
                    continue

                search_term_lower = item.search_term.lower()
                matched_keywords = keyword_index.get(search_term_lower, [])

                if matched_keywords:
                    # Use first match (could be multiple campaigns with same keyword)
                    # TODO: Could show all matches or pick based on criteria
                    match = matched_keywords[0]
                    correlated.append(
                        CorrelatedSearchTerm(
                            search_term=item.search_term,
                            country=item.country,
                            app_name=item.app_name,
                            low_share=item.low_share,
                            high_share=item.high_share,
                            rank=item.rank,
                            search_popularity=item.search_popularity,
                            campaign_id=match.campaign_id,
                            campaign_name=match.campaign_name,
                            ad_group_id=match.ad_group_id,
                            ad_group_name=match.ad_group_name,
                            keyword_id=match.keyword_id,
                            keyword_text=match.keyword_text,
                            current_bid=match.bid_amount,
                            currency=match.currency,
                        )
                    )
                else:
                    # Unmatched search term
                    correlated.append(
                        CorrelatedSearchTerm(
                            search_term=item.search_term,
                            country=item.country,
                            app_name=item.app_name,
                            low_share=item.low_share,
                            high_share=item.high_share,
                            rank=item.rank,
                            search_popularity=item.search_popularity,
                        )
                    )

            # Apply filters
            if min_share is not None:
                threshold = min_share / 100.0
                correlated = [c for c in correlated if c.high_share is not None and c.high_share < threshold]

            if unmatched_only:
                correlated = [c for c in correlated if not c.is_matched]
            elif matched_only:
                correlated = [c for c in correlated if c.is_matched]

            if not correlated:
                print_warning("No search terms match the specified filters")
                return

            # Sort by share (lowest first)
            correlated.sort(key=lambda x: x.avg_share)

            # Stats
            matched_count = sum(1 for c in correlated if c.is_matched)
            unmatched_count = len(correlated) - matched_count

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
                                "app_name",
                                "low_share",
                                "high_share",
                                "rank",
                                "popularity",
                                "campaign_name",
                                "ad_group_name",
                                "keyword_text",
                                "current_bid",
                                "currency",
                            ]
                        )
                        for row in correlated:
                            writer.writerow(
                                [
                                    row.search_term,
                                    row.country,
                                    row.app_name,
                                    row.low_share,
                                    row.high_share,
                                    row.rank,
                                    row.search_popularity,
                                    row.campaign_name or "",
                                    row.ad_group_name or "",
                                    row.keyword_text or "",
                                    row.current_bid or "",
                                    row.currency or "",
                                ]
                            )
                    print_success(f"Exported {len(correlated)} rows to {output}")
                except Exception as e:
                    print_error("Export failed", str(e))

            # Display table
            display_limit = len(correlated) if limit == 0 else limit

            table = Table(title=f"Impression Share Correlation - {country}")
            table.add_column("Search Term", style="cyan", max_width=30)
            table.add_column("Share", justify="right", width=8)
            table.add_column("Campaign", style="magenta", max_width=25)
            table.add_column("Keyword", style="dim", max_width=20)
            table.add_column("Bid", justify="right", width=10)
            table.add_column("Pop", justify="center", width=3)

            for row in correlated[:display_limit]:
                share_style = "green"
                if row.high_share:
                    if row.high_share < 0.3:
                        share_style = "red"
                    elif row.high_share < 0.5:
                        share_style = "yellow"

                bid_display = f"{row.current_bid:.2f} {row.currency}" if row.current_bid else "[dim]—[/dim]"
                campaign_display = row.campaign_name[:25] if row.campaign_name else "[dim]Not matched[/dim]"
                keyword_display = row.keyword_text[:20] if row.keyword_text else ""

                table.add_row(
                    row.search_term[:30],
                    f"[{share_style}]{row.share_range}[/{share_style}]",
                    campaign_display,
                    keyword_display,
                    bid_display,
                    str(row.search_popularity) if row.search_popularity else "—",
                )

            console.print(table)

            if len(correlated) > display_limit:
                print_info(f"Showing {display_limit} of {len(correlated)} results. Use --limit 0 to see all.")

            # Summary
            console.print(f"\n[dim]Total search terms:[/dim] {len(correlated)}")
            console.print(f"  [green]Matched to keywords:[/green] {matched_count}")
            console.print(f"  [yellow]Unmatched (opportunities):[/yellow] {unmatched_count}")

            low_share_matched = sum(1 for c in correlated if c.is_matched and c.high_share and c.high_share < 0.3)
            if low_share_matched > 0:
                console.print(
                    f"\n[red]⚠ {low_share_matched} matched keywords have <30% share - consider bid increases[/red]"
                )

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None
