"""Brand campaign CLI commands.

This module provides the `brand` command for creating brand protection campaigns.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any

import typer
from asa_api_client.exceptions import AppleSearchAdsError
from asa_api_client.models import (
    AdGroupCreate,
    CampaignCreate,
    CampaignStatus,
    CampaignSupplySource,
    KeywordCreate,
    KeywordMatchType,
    Money,
)
from rich.table import Table

from asa_api_cli.optimize import CampaignNameParts, wait_for_resource
from asa_api_cli.utils import (
    console,
    get_client,
    handle_api_error,
    print_error,
    print_info,
    print_result_panel,
    print_success,
    print_warning,
    spinner,
)

app = typer.Typer(
    name="brand",
    help="Create brand protection campaigns.",
)

# All 91 Apple Search Ads supported countries (as of December 2024)
# Organized by region for easier maintenance
ALL_COUNTRIES = {
    # Africa, Middle East, and India (19)
    "africa_middle_east_india": [
        "DZ",  # Algeria
        "AM",  # Armenia
        "BH",  # Bahrain
        "EG",  # Egypt
        "GH",  # Ghana
        "IN",  # India
        "IQ",  # Iraq
        "IL",  # Israel
        "JO",  # Jordan
        "KE",  # Kenya
        "KW",  # Kuwait
        "LB",  # Lebanon
        "MA",  # Morocco
        "OM",  # Oman
        "PK",  # Pakistan
        "QA",  # Qatar
        "SA",  # Saudi Arabia
        "ZA",  # South Africa
        "AE",  # United Arab Emirates
    ],
    # Asia Pacific (18)
    "asia_pacific": [
        "AU",  # Australia
        "KH",  # Cambodia
        "CN",  # China mainland (requires special documentation)
        "HK",  # Hong Kong
        "ID",  # Indonesia
        "JP",  # Japan
        "MO",  # Macau
        "MY",  # Malaysia
        "MN",  # Mongolia
        "NP",  # Nepal
        "NZ",  # New Zealand
        "PH",  # Philippines
        "SG",  # Singapore
        "KR",  # South Korea
        "LK",  # Sri Lanka
        "TW",  # Taiwan
        "TH",  # Thailand
        "VN",  # Vietnam
    ],
    # Europe (37)
    "europe": [
        "AL",  # Albania
        "AT",  # Austria
        "AZ",  # Azerbaijan
        "BE",  # Belgium
        "BG",  # Bulgaria
        "HR",  # Croatia
        "CY",  # Cyprus
        "CZ",  # Czech Republic
        "DK",  # Denmark
        "EE",  # Estonia
        "FI",  # Finland
        "FR",  # France
        "DE",  # Germany
        "GR",  # Greece
        "HU",  # Hungary
        "IS",  # Iceland
        "IE",  # Ireland
        "IT",  # Italy
        "KZ",  # Kazakhstan
        "KG",  # Kyrgyzstan
        "LV",  # Latvia
        "LU",  # Luxembourg
        "NL",  # Netherlands
        "NO",  # Norway
        "PL",  # Poland
        "PT",  # Portugal
        "RO",  # Romania
        "RU",  # Russia
        "SK",  # Slovakia
        "SI",  # Slovenia
        "ES",  # Spain
        "SE",  # Sweden
        "CH",  # Switzerland
        "TR",  # Türkiye
        "GB",  # UK
        "UA",  # Ukraine
        "UZ",  # Uzbekistan
    ],
    # Latin America and the Caribbean (15)
    "latin_america": [
        "AR",  # Argentina
        "BO",  # Bolivia
        "BR",  # Brazil
        "CL",  # Chile
        "CO",  # Colombia
        "CR",  # Costa Rica
        "DO",  # Dominican Republic
        "EC",  # Ecuador
        "SV",  # El Salvador
        "GT",  # Guatemala
        "HN",  # Honduras
        "MX",  # Mexico
        "PA",  # Panamá
        "PY",  # Paraguay
        "PE",  # Peru
    ],
    # North America (2)
    "north_america": [
        "CA",  # Canada
        "US",  # United States
    ],
}

# China requires special business documentation
CHINA_COUNTRIES = ["CN"]

# Preset groups
COUNTRY_PRESETS = {
    "english": ["US", "GB", "CA", "AU", "NZ", "IE"],
    "tier1": ["US", "GB", "CA", "AU"],
    "europe": ALL_COUNTRIES["europe"],
    "asia": [c for c in ALL_COUNTRIES["asia_pacific"] if c != "CN"],
    "latam": ALL_COUNTRIES["latin_america"],
}


def get_all_countries(include_china: bool = False) -> list[str]:
    """Get all supported countries.

    Args:
        include_china: Whether to include China (requires special documentation).

    Returns:
        List of country codes.
    """
    countries = []
    for region_countries in ALL_COUNTRIES.values():
        for code in region_countries:
            if code == "CN" and not include_china:
                continue
            countries.append(code)
    return countries


def get_country_count() -> int:
    """Get total number of supported countries (excluding China)."""
    return len(get_all_countries(include_china=False))


# Country code to name mapping for display
COUNTRY_NAMES = {
    "DZ": "Algeria",
    "AM": "Armenia",
    "BH": "Bahrain",
    "EG": "Egypt",
    "GH": "Ghana",
    "IN": "India",
    "IQ": "Iraq",
    "IL": "Israel",
    "JO": "Jordan",
    "KE": "Kenya",
    "KW": "Kuwait",
    "LB": "Lebanon",
    "MA": "Morocco",
    "OM": "Oman",
    "PK": "Pakistan",
    "QA": "Qatar",
    "SA": "Saudi Arabia",
    "ZA": "South Africa",
    "AE": "UAE",
    "AU": "Australia",
    "KH": "Cambodia",
    "CN": "China",
    "HK": "Hong Kong",
    "ID": "Indonesia",
    "JP": "Japan",
    "MO": "Macau",
    "MY": "Malaysia",
    "MN": "Mongolia",
    "NP": "Nepal",
    "NZ": "New Zealand",
    "PH": "Philippines",
    "SG": "Singapore",
    "KR": "South Korea",
    "LK": "Sri Lanka",
    "TW": "Taiwan",
    "TH": "Thailand",
    "VN": "Vietnam",
    "AL": "Albania",
    "AT": "Austria",
    "AZ": "Azerbaijan",
    "BE": "Belgium",
    "BG": "Bulgaria",
    "HR": "Croatia",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DK": "Denmark",
    "EE": "Estonia",
    "FI": "Finland",
    "FR": "France",
    "DE": "Germany",
    "GR": "Greece",
    "HU": "Hungary",
    "IS": "Iceland",
    "IE": "Ireland",
    "IT": "Italy",
    "KZ": "Kazakhstan",
    "KG": "Kyrgyzstan",
    "LV": "Latvia",
    "LU": "Luxembourg",
    "NL": "Netherlands",
    "NO": "Norway",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "RU": "Russia",
    "SK": "Slovakia",
    "SI": "Slovenia",
    "ES": "Spain",
    "SE": "Sweden",
    "CH": "Switzerland",
    "TR": "Türkiye",
    "GB": "UK",
    "UA": "Ukraine",
    "UZ": "Uzbekistan",
    "AR": "Argentina",
    "BO": "Bolivia",
    "BR": "Brazil",
    "CL": "Chile",
    "CO": "Colombia",
    "CR": "Costa Rica",
    "DO": "Dominican Republic",
    "EC": "Ecuador",
    "SV": "El Salvador",
    "GT": "Guatemala",
    "HN": "Honduras",
    "MX": "Mexico",
    "PA": "Panamá",
    "PY": "Paraguay",
    "PE": "Peru",
    "CA": "Canada",
    "US": "United States",
}


@dataclass
class BrandCampaignPlan:
    """Plan for creating a brand campaign."""

    app_name: str
    adam_id: int
    country: str
    name: str
    keywords: list[str]
    daily_budget: Decimal
    currency: str
    default_bid: Decimal


def _select_countries_interactive(include_china: bool = False) -> list[str]:
    """Interactive country selection.

    Returns:
        List of selected country codes.
    """
    from rich.rule import Rule

    console.print()
    console.print(Rule("Select Target Countries"))
    console.print()

    # Show presets
    table = Table(title="Country Presets", show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Preset")
    table.add_column("Countries")
    table.add_column("Count", justify="right")

    presets_list = [
        ("all", "All countries (excl. China)", get_country_count()),
        ("english", "English-speaking", len(COUNTRY_PRESETS["english"])),
        ("tier1", "Tier 1 (US, GB, CA, AU)", len(COUNTRY_PRESETS["tier1"])),
        ("europe", "Europe", len(COUNTRY_PRESETS["europe"])),
        ("asia", "Asia Pacific (excl. China)", len(COUNTRY_PRESETS["asia"])),
        ("latam", "Latin America", len(COUNTRY_PRESETS["latam"])),
    ]

    for i, (key, desc, count) in enumerate(presets_list, 1):
        table.add_row(str(i), key, desc, str(count))

    console.print(table)
    console.print()
    console.print("[dim]Or enter country codes separated by commas (e.g., US,GB,AU)[/dim]")
    console.print()

    selection = typer.prompt("Select preset (1-6) or enter country codes").strip()

    # Check if it's a preset number
    try:
        preset_idx = int(selection) - 1
        if 0 <= preset_idx < len(presets_list):
            preset_key = presets_list[preset_idx][0]
            if preset_key == "all":
                countries = get_all_countries(include_china=include_china)
            else:
                countries = COUNTRY_PRESETS[preset_key].copy()
            return countries
    except ValueError:
        pass

    # Check if it's a preset name
    selection_lower = selection.lower()
    if selection_lower == "all":
        return get_all_countries(include_china=include_china)
    if selection_lower in COUNTRY_PRESETS:
        return COUNTRY_PRESETS[selection_lower].copy()

    # Parse as comma-separated country codes
    countries = []
    all_valid = get_all_countries(include_china=True)

    for code in selection.upper().replace(" ", "").split(","):
        if not code:
            continue
        if code not in all_valid:
            print_warning(f"Unknown country code: {code}")
            continue
        if code in CHINA_COUNTRIES and not include_china:
            print_warning(
                f"Skipping {code} - China requires special business documentation. Use --include-china to include."
            )
            continue
        if code not in countries:
            countries.append(code)

    return countries


def _select_app_interactive(client: Any) -> tuple[int, str, str]:
    """Interactive app selection.

    Returns:
        Tuple of (adam_id, app_name, currency).
    """
    console.print()
    print_info("Select an app to create brand campaigns for:")

    with spinner("Loading campaigns..."):
        all_campaigns = client.campaigns.list()

    # Group by adam_id to show unique apps
    apps: dict[int, tuple[str, str]] = {}  # adam_id -> (app_name, currency)
    for camp in all_campaigns.data:
        if camp.adam_id and camp.adam_id not in apps:
            parsed = CampaignNameParts.parse(camp.name)
            name = parsed.app_name if parsed else camp.name.split(" - ")[0]
            currency = camp.daily_budget_amount.currency if camp.daily_budget_amount else "USD"
            apps[camp.adam_id] = (name, currency)

    if not apps:
        print_error("No apps", "No campaigns found to get app information from")
        raise typer.Exit(1)

    # Display apps
    table = Table(show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("App Name")
    table.add_column("Adam ID", style="dim")

    app_list = list(apps.items())
    for i, (aid, (name, _)) in enumerate(app_list, 1):
        table.add_row(str(i), name, str(aid))

    console.print(table)
    console.print()

    selection = typer.prompt("Select app number", default="1")
    try:
        idx = int(selection) - 1
        if 0 <= idx < len(app_list):
            adam_id, (app_name, currency) = app_list[idx]
            return adam_id, app_name, currency
        else:
            print_error("Invalid selection", f"Please enter 1-{len(app_list)}")
            raise typer.Exit(1)
    except ValueError:
        print_error("Invalid selection", "Please enter a number")
        raise typer.Exit(1)


def _get_brand_keywords_interactive(brand_name: str | None = None) -> list[str]:
    """Interactive brand keyword entry.

    Args:
        brand_name: Optional initial brand name.

    Returns:
        List of brand keywords.
    """
    console.print()

    if brand_name:
        keywords = [brand_name.lower()]
        print_info(f"Brand name: {brand_name}")
    else:
        brand = typer.prompt("Enter your brand name").strip()
        keywords = [brand.lower()]

    # Ask for variants
    console.print()
    console.print("[dim]Enter brand name variants (common misspellings, abbreviations)[/dim]")
    console.print("[dim]Press Enter with no input when done[/dim]")
    console.print()

    while True:
        variant = typer.prompt("Add variant (or press Enter to continue)", default="").strip()
        if not variant:
            break
        variant_lower = variant.lower()
        if variant_lower not in keywords:
            keywords.append(variant_lower)
            print_success(f"Added: {variant_lower}")
        else:
            print_warning(f"Already added: {variant_lower}")

    return keywords


def _get_budget_bid_interactive(
    ref_budget: Decimal | None = None,
    ref_bid: Decimal | None = None,
    ref_currency: str = "USD",
) -> tuple[Decimal, Decimal, str]:
    """Interactive budget and bid entry.

    Returns:
        Tuple of (budget, bid, currency).
    """
    console.print()

    # Budget
    default_budget = str(ref_budget) if ref_budget else "50.00"
    budget_input = typer.prompt(
        f"Daily budget per campaign ({ref_currency})",
        default=default_budget,
    )
    budget = Decimal(budget_input)

    # Bid
    default_bid = f"{ref_bid:.2f}" if ref_bid else "1.00"
    bid_input = typer.prompt(
        f"Default bid ({ref_currency})",
        default=default_bid,
    )
    bid = Decimal(bid_input)

    return budget, bid, ref_currency


@app.callback(invoke_without_command=True)
def create_brand_campaigns(
    ctx: typer.Context,
    brand_name: Annotated[
        str | None,
        typer.Argument(help="Brand name (optional, will prompt if not provided)"),
    ] = None,
    variants: Annotated[
        list[str] | None,
        typer.Option("--variant", "-v", help="Brand name variants"),
    ] = None,
    countries: Annotated[
        list[str] | None,
        typer.Option("--country", "-c", help="Target countries"),
    ] = None,
    reference_campaign: Annotated[
        int | None,
        typer.Option("--reference", "-r", help="Campaign ID to copy settings from"),
    ] = None,
    daily_budget: Annotated[
        float | None,
        typer.Option("--budget", "-b", help="Daily budget"),
    ] = None,
    default_bid: Annotated[
        float | None,
        typer.Option("--bid", help="Default bid amount"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview without creating"),
    ] = False,
    paused: Annotated[
        bool,
        typer.Option("--paused", "-p", help="Create in PAUSED status"),
    ] = False,
    include_china: Annotated[
        bool,
        typer.Option("--include-china", help="Include China (requires special docs)"),
    ] = False,
) -> None:
    """Create brand protection campaigns.

    Interactive mode (recommended):
        asa brand

    With arguments:
        asa brand "Chippy Tools" -v "Chippy Tool" -c US -c GB

    This creates single-keyword ad groups (SKAGs) for your brand name
    and variants, helping protect your brand from competitors.
    """
    # Skip if a subcommand was invoked
    if ctx.invoked_subcommand is not None:
        return
    from rich.rule import Rule

    client = get_client()

    try:
        with client:
            # Step 1: Get brand keywords
            if brand_name or variants:
                # Use provided arguments
                all_keywords = [brand_name.lower()] if brand_name else []
                if variants:
                    for v in variants:
                        kw = v.lower().strip()
                        if kw and kw not in all_keywords:
                            all_keywords.append(kw)
            else:
                # Interactive mode
                all_keywords = _get_brand_keywords_interactive()

            if not all_keywords:
                print_error("No keywords", "At least one brand keyword is required")
                raise typer.Exit(1)

            print_info(f"Brand keywords ({len(all_keywords)}): {', '.join(all_keywords)}")

            # Step 2: Get target countries
            if countries:
                target_countries = []
                all_valid = get_all_countries(include_china=True)
                for code in countries:
                    code_upper = code.upper()
                    if code_upper not in all_valid:
                        print_warning(f"Unknown country code: {code_upper}")
                        continue
                    if code_upper in CHINA_COUNTRIES and not include_china:
                        print_warning(f"Skipping {code_upper} - requires --include-china")
                        continue
                    target_countries.append(code_upper)
            else:
                target_countries = _select_countries_interactive(include_china)

            if not target_countries:
                print_error("No countries", "No valid target countries selected")
                raise typer.Exit(1)

            countries_preview = ", ".join(target_countries[:10])
            suffix = "..." if len(target_countries) > 10 else ""
            print_info(f"Target countries ({len(target_countries)}): {countries_preview}{suffix}")

            # Step 3: Get reference campaign or select app
            ref_budget: Decimal | None = None
            ref_bid: Decimal | None = None
            ref_currency = "USD"
            adam_id: int | None = None
            app_name: str | None = None

            if reference_campaign:
                with spinner("Loading reference campaign..."):
                    ref_camp = client.campaigns.get(reference_campaign)
                    adam_id = ref_camp.adam_id
                    parsed_name = CampaignNameParts.parse(ref_camp.name)
                    app_name = parsed_name.app_name if parsed_name else ref_camp.name.split(" - ")[0]

                    if ref_camp.daily_budget_amount:
                        ref_budget = Decimal(ref_camp.daily_budget_amount.amount)
                        ref_currency = ref_camp.daily_budget_amount.currency

                    # Get average bid from ad groups
                    ad_groups = client.campaigns(reference_campaign).ad_groups.list()
                    if ad_groups.data:
                        bids = [Decimal(ag.default_bid_amount.amount) for ag in ad_groups.data if ag.default_bid_amount]
                        if bids:
                            ref_bid = Decimal(sum(bids) / len(bids))

                print_info(f"Reference: {ref_camp.name}")
                if ref_budget:
                    bid_str = f"{ref_bid:.2f}" if ref_bid else "N/A"
                    print_info(f"  Budget: {ref_budget} {ref_currency}, Avg bid: {bid_str} {ref_currency}")
            else:
                adam_id, app_name, ref_currency = _select_app_interactive(client)

            if adam_id is None:
                print_error("No app selected", "Cannot continue without an app")
                return

            # Step 4: Get budget and bid
            if daily_budget is not None:
                final_budget = Decimal(str(daily_budget))
            elif ref_budget:
                final_budget = ref_budget
            else:
                final_budget = None

            if default_bid is not None:
                final_bid = Decimal(str(default_bid))
            elif ref_bid:
                final_bid = ref_bid
            else:
                final_bid = None

            # If not fully specified, prompt interactively
            if final_budget is None or final_bid is None:
                final_budget, final_bid, ref_currency = _get_budget_bid_interactive(
                    ref_budget=final_budget,
                    ref_bid=final_bid,
                    ref_currency=ref_currency,
                )

            # Step 5: Build campaign plans
            campaign_plans: list[BrandCampaignPlan] = []

            for country in target_countries:
                campaign_name = f"{app_name} - {country} - Brand - EM"
                campaign_plans.append(
                    BrandCampaignPlan(
                        app_name=app_name or all_keywords[0].title(),
                        adam_id=adam_id,
                        country=country,
                        name=campaign_name,
                        keywords=all_keywords,
                        daily_budget=final_budget,
                        currency=ref_currency,
                        default_bid=final_bid,
                    )
                )

            # Step 6: Display plan
            console.print()
            console.print(Rule("Brand Campaign Plan"))
            console.print()

            console.print(f"[bold]App:[/bold] {app_name} (Adam ID: {adam_id})")
            console.print(f"[bold]Keywords:[/bold] {', '.join(all_keywords)}")
            console.print(f"[bold]Daily Budget:[/bold] {final_budget} {ref_currency}")
            console.print(f"[bold]Default Bid:[/bold] {final_bid:.2f} {ref_currency}")
            console.print(f"[bold]Status:[/bold] {'PAUSED' if paused else 'ENABLED'}")
            console.print()

            # Show summary table for many countries, detailed for few
            if len(campaign_plans) > 10:
                console.print(f"[bold]Campaigns to create:[/bold] {len(campaign_plans)}")
                console.print(f"[bold]Ad groups per campaign:[/bold] {len(all_keywords)}")
                console.print(f"[bold]Total ad groups:[/bold] {len(campaign_plans) * len(all_keywords)}")
                console.print()

                # Group by region for display
                console.print("[dim]Countries by region:[/dim]")
                for region, codes in ALL_COUNTRIES.items():
                    region_countries = [c for c in target_countries if c in codes]
                    if region_countries:
                        region_name = region.replace("_", " ").title()
                        console.print(f"  {region_name}: {', '.join(region_countries)}")
            else:
                table = Table(title=f"Campaigns to Create ({len(campaign_plans)})")
                table.add_column("#", style="dim", width=4)
                table.add_column("Campaign Name")
                table.add_column("Country")
                table.add_column("Ad Groups")

                for i, plan in enumerate(campaign_plans, 1):
                    country_name = COUNTRY_NAMES.get(plan.country, plan.country)
                    table.add_row(str(i), plan.name, f"{plan.country} ({country_name})", str(len(plan.keywords)))

                console.print(table)

            console.print()

            if dry_run:
                print_info("Dry run - no campaigns created")
                return

            # Step 7: Confirm and create
            total_budget = final_budget * len(campaign_plans)
            console.print(f"[yellow]Total daily budget: {total_budget} {ref_currency}[/yellow]")
            console.print()

            if not typer.confirm(f"Create {len(campaign_plans)} brand campaign(s)?", default=True):
                print_info("Cancelled")
                return

            # Step 8: Create campaigns
            created_campaigns = 0
            created_ad_groups = 0
            created_keywords = 0

            for plan_idx, plan in enumerate(campaign_plans, 1):
                console.print()
                console.print(f"[dim][{plan_idx}/{len(campaign_plans)}][/dim] Creating {plan.name}...")

                with spinner("Creating campaign..."):
                    new_campaign = client.campaigns.create(
                        CampaignCreate(
                            name=plan.name,
                            adam_id=plan.adam_id,
                            countries_or_regions=[plan.country],
                            daily_budget_amount=Money(
                                amount=str(plan.daily_budget),
                                currency=plan.currency,
                            ),
                            supply_sources=[CampaignSupplySource.APPSTORE_SEARCH_RESULTS],
                            status=CampaignStatus.PAUSED if paused else CampaignStatus.ENABLED,
                        )
                    )

                print_success(f"Created campaign (ID: {new_campaign.id})")
                created_campaigns += 1

                # Wait for campaign to be available
                def get_campaign(cid: int = new_campaign.id) -> Any:
                    return client.campaigns.get(cid)

                wait_for_resource(get_campaign, max_attempts=10, delay=0.5)

                # Create ad groups for each keyword
                for keyword in plan.keywords:
                    ag_name = f"Exact - {keyword.title()}"[:200]

                    with spinner(f"  Creating: {ag_name}..."):
                        new_ag = client.campaigns(new_campaign.id).ad_groups.create(
                            AdGroupCreate(
                                name=ag_name,
                                default_bid_amount=Money(
                                    amount=str(plan.default_bid),
                                    currency=plan.currency,
                                ),
                                automated_keywords_opt_in=False,
                            )
                        )
                        created_ad_groups += 1

                    # Create keyword (must use bulk endpoint)
                    client.campaigns(new_campaign.id).ad_groups(new_ag.id).keywords.create_bulk(
                        [
                            KeywordCreate(
                                text=keyword,
                                match_type=KeywordMatchType.EXACT,
                                bid_amount=Money(
                                    amount=str(plan.default_bid),
                                    currency=plan.currency,
                                ),
                            )
                        ]
                    )
                    created_keywords += 1

                    print_success(f"  {ag_name} → '{keyword}'")

            # Summary
            console.print()
            print_result_panel(
                "Brand Campaigns Created",
                {
                    "Campaigns": str(created_campaigns),
                    "Ad Groups": str(created_ad_groups),
                    "Keywords": str(created_keywords),
                    "Status": "PAUSED" if paused else "ENABLED",
                },
            )

    except AppleSearchAdsError as e:
        handle_api_error(e)
        raise typer.Exit(1) from None
