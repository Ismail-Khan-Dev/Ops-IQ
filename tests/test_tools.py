"""Tests for Competitor Scraper and Tool Registry."""

from unittest.mock import AsyncMock, patch

import pytest

from ecommerce_ops.connectors.competitor_scraper import _extract_prices, scrape_competitor_price
from ecommerce_ops.tools.registry import Tool, ToolRegistry


@pytest.fixture(autouse=True)
def _ensure_scraper_registered():
    from ecommerce_ops.tools.scraper_tool import ScraperTool
    ToolRegistry.register(ScraperTool())


# ── Price Extraction Tests ────────────────────────────────


def test_extract_prices_basic():
    html = '<span>$29.99</span><span>$34.50</span>'
    prices = _extract_prices(html)
    assert 29.99 in prices
    assert 34.50 in prices


def test_extract_prices_no_prices():
    html = '<span>No prices here</span>'
    prices = _extract_prices(html)
    assert len(prices) == 0


def test_extract_prices_filters_extremes():
    html = '<span>$0.00</span><span>$999999.99</span><span>$25.00</span>'
    prices = _extract_prices(html)
    assert 25.00 in prices
    assert 0.00 not in prices
    assert 999999.99 not in prices


def test_extract_prices_various_formats():
    html = '$10 $19.99 $199 $1,234.56'
    prices = _extract_prices(html)
    assert 10.0 in prices
    assert 19.99 in prices
    assert 199.0 in prices


def test_extract_prices_empty_string():
    assert _extract_prices("") == []


# ── Scraper Async Tests ───────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_competitor_price_timeout():
    with patch("ecommerce_ops.connectors.competitor_scraper._fetch_price", new_callable=AsyncMock) as mock:
        mock.side_effect = TimeoutError()
        result = await scrape_competitor_price("SKU-1")
        assert result is None


@pytest.mark.asyncio
async def test_scrape_competitor_price_success():
    with patch("ecommerce_ops.connectors.competitor_scraper._fetch_price", new_callable=AsyncMock) as mock:
        mock.return_value = 29.99
        result = await scrape_competitor_price("SKU-1")
        assert result == 29.99


@pytest.mark.asyncio
async def test_scrape_competitor_price_no_results():
    with patch("ecommerce_ops.connectors.competitor_scraper._fetch_price", new_callable=AsyncMock) as mock:
        mock.return_value = None
        result = await scrape_competitor_price("SKU-1")
        assert result is None


# ── Tool Registry Tests ───────────────────────────────────


class DummyTool(Tool):
    name = "dummy_tool"
    description = "A dummy tool for testing"

    async def run(self, **kwargs) -> str:
        return "dummy_result"


def test_tool_registry_register():
    tool = DummyTool()
    ToolRegistry.register(tool)
    assert ToolRegistry.get("dummy_tool") is not None


def test_tool_registry_get_unknown():
    result = ToolRegistry.get("nonexistent_tool_xyz")
    assert result is None


def test_tool_registry_list_tools():
    tools = ToolRegistry.list_tools()
    assert isinstance(tools, list)
    assert any(t["name"] == "scrape_competitor_price" for t in tools)


@pytest.mark.asyncio
async def test_tool_registry_run_tool():
    result = await ToolRegistry.run_tool("scrape_competitor_price", sku="TEST-SKU")
    assert result is None or isinstance(result, float)


@pytest.mark.asyncio
async def test_tool_registry_run_unknown_tool():
    with pytest.raises(ValueError, match="Unknown tool"):
        await ToolRegistry.run_tool("nonexistent_tool_xyz")
