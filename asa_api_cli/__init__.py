"""Command-line interface for Apple Search Ads.

This module provides a CLI for interacting with the Apple Search Ads API.

Usage:
    asa --help
    asa campaigns list
    asa reports campaigns --start 2024-01-01 --end 2024-01-31
"""

from asa_api_cli.main import app

__all__ = ["app"]

__version__ = "0.1.0"
