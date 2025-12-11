"""Tests for the CLI application."""

from typer.testing import CliRunner

from asa_api_cli import app

runner = CliRunner()


def test_version() -> None:
    """Test --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "asa-api-cli" in result.stdout


def test_help() -> None:
    """Test --help flag."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "campaigns" in result.stdout
    assert "ad-groups" in result.stdout
    assert "keywords" in result.stdout
    assert "reports" in result.stdout


def test_campaigns_help() -> None:
    """Test campaigns subcommand help."""
    result = runner.invoke(app, ["campaigns", "--help"])
    assert result.exit_code == 0
    assert "list" in result.stdout


def test_auth_help() -> None:
    """Test auth subcommand help."""
    result = runner.invoke(app, ["auth", "--help"])
    assert result.exit_code == 0
    assert "show" in result.stdout
    assert "test" in result.stdout
