"""Shared utilities for CLI commands."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

import typer
from asa_api_client import AppleSearchAdsClient
from asa_api_client.exceptions import AppleSearchAdsError, ConfigurationError
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# Custom theme for consistent styling
ASA_THEME = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red bold",
        "highlight": "magenta",
        "muted": "dim",
        "header": "bold cyan",
        "value": "white",
        "label": "blue",
    }
)

console = Console(theme=ASA_THEME)
error_console = Console(stderr=True, theme=ASA_THEME)

T = TypeVar("T")


def enum_value(v: Enum | str | bool) -> str:
    """Get the value from an enum, string, or bool.

    Since API models use `EnumType | str | bool` for forward compatibility,
    this helper safely extracts the string value.
    """
    if isinstance(v, Enum):
        return str(v.value)
    elif isinstance(v, bool):
        return "OPT_IN" if v else "OPT_OUT"
    return str(v)


class OutputFormat(str, Enum):
    """Output format options."""

    TABLE = "table"
    JSON = "json"
    CSV = "csv"


def get_client() -> AppleSearchAdsClient:
    """Get an authenticated client from environment variables.

    Returns:
        An authenticated AppleSearchAdsClient.

    Raises:
        typer.Exit: If configuration is invalid.
    """
    try:
        return AppleSearchAdsClient.from_env()
    except ConfigurationError as e:
        print_error("Configuration Error", e.message)
        error_console.print()
        print_info_panel(
            "Required Environment Variables",
            "• ASA_CLIENT_ID\n• ASA_TEAM_ID\n• ASA_KEY_ID\n• ASA_ORG_ID\n• ASA_PRIVATE_KEY_PATH (or ASA_PRIVATE_KEY)",
        )
        raise typer.Exit(1) from None


def handle_api_error(e: AppleSearchAdsError) -> None:
    """Handle and display an API error.

    Args:
        e: The exception to handle.
    """
    from asa_api_client.exceptions import ValidationError

    details_parts = []

    # Show request info if available (for debugging)
    if e.response_body and "_request" in e.response_body:
        details_parts.append(f"Request: {e.response_body['_request']}")

    if e.status_code:
        details_parts.append(f"Status code: {e.status_code}")

    # Show field errors for validation errors
    if isinstance(e, ValidationError) and e.field_errors:
        for field, errors in e.field_errors.items():
            for err in errors:
                details_parts.append(f"  {field}: {err}")

    # Show response body if available (for debugging)
    if e.response_body:
        import json

        # Remove internal _request field before displaying
        body_copy = {k: v for k, v in e.response_body.items() if not k.startswith("_")}
        body_str = json.dumps(body_copy, indent=2)
        if len(body_str) < 500:  # Only show if not too long
            details_parts.append(f"Response: {body_str}")

    details = "\n".join(details_parts) if details_parts else None
    print_error("API Error", e.message, details=details)


# ============================================================================
# Styled Output Functions
# ============================================================================


def print_success(message: str, details: str | None = None) -> None:
    """Print a success message with a checkmark.

    Args:
        message: The success message.
        details: Optional additional details.
    """
    text = Text()
    text.append("✓ ", style="success")
    text.append(message)
    if details:
        text.append(f"\n  {details}", style="muted")
    console.print(text)


def print_error(title: str, message: str, details: str | None = None) -> None:
    """Print an error message in a styled panel.

    Args:
        title: Error title.
        message: Error message.
        details: Optional additional details.
    """
    content = Text(message)
    if details:
        content.append(f"\n{details}", style="muted")

    panel = Panel(
        content,
        title=f"[error]✗ {title}[/error]",
        border_style="red",
        padding=(0, 1),
    )
    error_console.print(panel)


def print_warning(message: str) -> None:
    """Print a warning message.

    Args:
        message: The warning message.
    """
    text = Text()
    text.append("⚠ ", style="warning")
    text.append(message, style="warning")
    console.print(text)


def print_info(message: str) -> None:
    """Print an info message.

    Args:
        message: The info message.
    """
    text = Text()
    text.append("ℹ ", style="info")
    text.append(message)
    console.print(text)


def print_info_panel(title: str, content: str) -> None:
    """Print information in a styled panel.

    Args:
        title: Panel title.
        content: Panel content.
    """
    panel = Panel(
        content,
        title=f"[info]{title}[/info]",
        border_style="cyan",
        padding=(0, 1),
    )
    console.print(panel)


def print_result_panel(title: str, data: dict[str, Any]) -> None:
    """Print a result in a styled panel with key-value pairs.

    Args:
        title: Panel title.
        data: Dictionary of key-value pairs to display.
    """
    lines = []
    for key, value in data.items():
        lines.append(f"[label]{key}:[/label] [value]{value}[/value]")

    panel = Panel(
        "\n".join(lines),
        title=f"[success]{title}[/success]",
        border_style="green",
        padding=(0, 1),
    )
    console.print(panel)


# ============================================================================
# Table Output
# ============================================================================


def print_table(
    data: list[dict[str, Any]],
    columns: list[str],
    title: str | None = None,
    column_labels: dict[str, str] | None = None,
) -> None:
    """Print data as a rich table.

    Args:
        data: List of dictionaries to display.
        columns: Column names to include.
        title: Optional table title.
        column_labels: Optional mapping of column names to display labels.
    """
    table = Table(
        title=title,
        show_header=True,
        header_style="header",
        border_style="muted",
        row_styles=["", "dim"],
    )

    labels = column_labels or {}
    for col in columns:
        label = labels.get(col, col.replace("_", " ").title())
        table.add_column(label)

    for row in data:
        table.add_row(*[str(row.get(col, "")) for col in columns])

    console.print(table)


# ============================================================================
# JSON Output with Syntax Highlighting
# ============================================================================


def print_json(data: Any, title: str | None = None) -> None:
    """Print data as syntax-highlighted JSON.

    Args:
        data: Data to print as JSON.
        title: Optional title to display above the JSON.
    """
    if hasattr(data, "model_dump"):
        data = data.model_dump(by_alias=True, exclude_none=True)
    elif isinstance(data, list) and data and hasattr(data[0], "model_dump"):
        data = [item.model_dump(by_alias=True, exclude_none=True) for item in data]

    json_str = json.dumps(data, indent=2, default=str)

    syntax = Syntax(
        json_str,
        "json",
        theme="monokai",
        line_numbers=False,
        word_wrap=True,
    )

    if title:
        panel = Panel(syntax, title=f"[info]{title}[/info]", border_style="cyan")
        console.print(panel)
    else:
        console.print(syntax)


def print_csv(data: list[dict[str, Any]], columns: list[str]) -> None:
    """Print data as CSV.

    Args:
        data: List of dictionaries to print.
        columns: Column names to include.
    """
    import csv
    import sys

    writer = csv.DictWriter(sys.stdout, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data)


def output_data(
    data: list[dict[str, Any]],
    columns: list[str],
    format: OutputFormat,
    title: str | None = None,
    column_labels: dict[str, str] | None = None,
) -> None:
    """Output data in the specified format.

    Args:
        data: Data to output.
        columns: Column names for table/CSV output.
        format: Output format.
        title: Optional title for table output.
        column_labels: Optional mapping of column names to display labels.
    """
    if format == OutputFormat.JSON:
        print_json(data, title)
    elif format == OutputFormat.CSV:
        print_csv(data, columns)
    else:
        print_table(data, columns, title, column_labels)


# ============================================================================
# Progress Indicators
# ============================================================================


@contextmanager
def spinner(message: str) -> Iterator[None]:
    """Show a spinner while executing a block.

    Args:
        message: Message to display with the spinner.

    Yields:
        None

    Example:
        with spinner("Loading campaigns..."):
            campaigns = client.campaigns.list()
    """
    with console.status(f"[info]{message}[/info]", spinner="dots"):
        yield


def create_progress() -> Progress:
    """Create a progress bar for iteration.

    Returns:
        A configured Progress instance.

    Example:
        with create_progress() as progress:
            task = progress.add_task("Loading...", total=100)
            for item in items:
                progress.advance(task)
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def iterate_with_progress(
    items: Iterator[T],
    total: int | None = None,
    description: str = "Processing...",
) -> Iterator[T]:
    """Iterate over items with a progress bar.

    Args:
        items: Iterator to wrap.
        total: Total number of items (if known).
        description: Progress bar description.

    Yields:
        Items from the iterator.

    Example:
        for campaign in iterate_with_progress(client.campaigns.iter_all(), total=100):
            process(campaign)
    """
    with create_progress() as progress:
        task = progress.add_task(description, total=total)
        for item in items:
            yield item
            progress.advance(task)


# ============================================================================
# Utility Functions
# ============================================================================


def parse_date(value: str) -> date:
    """Parse a date string in YYYY-MM-DD format.

    Args:
        value: Date string to parse.

    Returns:
        Parsed date object.

    Raises:
        typer.BadParameter: If the date format is invalid.
    """
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter(f"Invalid date format: '{value}'. Use YYYY-MM-DD format.") from None


def save_to_file(content: str, path: Path) -> None:
    """Save content to a file.

    Args:
        content: Content to save.
        path: File path.
    """
    path.write_text(content)
    print_success(f"Saved to {path}")


def format_number(value: int | float | None) -> str:
    """Format a number with thousands separators.

    Args:
        value: Number to format.

    Returns:
        Formatted string or "-" if None.
    """
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return f"{value:,}"


def format_money(amount: str | None, currency: str | None = None) -> str:
    """Format a monetary value.

    Args:
        amount: The amount string.
        currency: Optional currency code.

    Returns:
        Formatted money string.
    """
    if amount is None:
        return "-"
    if currency:
        return f"{amount} {currency}"
    return amount


def format_percent(value: float | None) -> str:
    """Format a value as a percentage.

    Args:
        value: Value between 0 and 1.

    Returns:
        Formatted percentage string.
    """
    if value is None:
        return "-"
    return f"{value:.2%}"


def confirm_action(message: str, default: bool = False) -> bool:
    """Ask for confirmation with styled prompt.

    Args:
        message: Confirmation message.
        default: Default value if user just presses Enter.

    Returns:
        True if confirmed, False otherwise.
    """
    return typer.confirm(message, default=default)
