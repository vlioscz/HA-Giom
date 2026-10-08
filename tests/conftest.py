"""Shared fixtures."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let every test load the integration from custom_components/."""


@pytest.fixture
def status_3000() -> str:
    """status.xml as a GIOM 3000-series station serves it."""
    return (FIXTURES / "status_3000.xml").read_text(encoding="utf-8")


@pytest.fixture
def status_4000() -> str:
    """status.xml with the extra fields the 4000 series reports."""
    return (FIXTURES / "status_4000.xml").read_text(encoding="utf-8")


@pytest.fixture
def data_4000() -> str:
    """data.xml as a live IQWS-4000 serves it (4000 series only)."""
    return (FIXTURES / "data_4000.xml").read_text(encoding="utf-8")
