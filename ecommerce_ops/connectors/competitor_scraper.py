"""
Competitor Price Scraper
Production-grade competitor pricing connector.
Supports:
1. Redis/in-memory price caching (6h TTL) to avoid duplicate requests.
2. Managed SERP API integration (SerpApi / ValueSERP) when configured.
3. Resilient Playwright browser pool fallback when direct HTTP encounters CAPTCHA/bot blocks.
"""

import asyncio
import logging
import os
import re
from typing import Optional

import httpx

from ecommerce_ops.infra.browser_pool import browser_pool

logger = logging.getLogger("ecommerce_ops.connectors.scraper")

SCRAPE_TIMEOUT_SECONDS = 15
PRICE_CACHE_TTL_SECONDS = 21600  # 6 hours
GOOGLE_SHOPPING_URL = "https://www.google.com/search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


async def scrape_competitor_price(sku: str) -> Optional[float]:
    """Scrape competitor price for a given SKU with caching and fallback layers."""
    if not sku:
        return None

    clean_sku = str(sku).strip().upper()

    # 1. Cache lookup
    try:
        from ecommerce_ops.memory.cache import cache

        cached_val = await cache.get(f"competitor_price:{clean_sku}")
        if cached_val is not None:
            logger.debug("Competitor price cache hit for %s: $%s", clean_sku, cached_val)
            return float(cached_val)
    except Exception as e:
        logger.debug("Price cache lookup skipped: %s", e)

    # 2. Scrape with timeout
    try:
        price = await asyncio.wait_for(_fetch_price_pipeline(clean_sku), timeout=SCRAPE_TIMEOUT_SECONDS)
        if price is not None and price > 0:
            try:
                from ecommerce_ops.memory.cache import cache

                await cache.set(f"competitor_price:{clean_sku}", price, ttl=PRICE_CACHE_TTL_SECONDS)
            except Exception:
                pass
        return price
    except TimeoutError:
        logger.warning("Timeout scraping competitor for SKU: %s", clean_sku)
        return None
    except Exception as e:
        logger.error("Error scraping competitor price for %s: %s", clean_sku, e)
        return None


async def _fetch_price_pipeline(sku: str) -> Optional[float]:
    """Pipeline: SerpApi -> HTTP Direct -> Browser Pool fallback."""
    serp_api_key = os.getenv("SERPAPI_API_KEY") or os.getenv("SERP_API_KEY")

    # Path A: Managed SERP API
    if serp_api_key:
        price = await _fetch_via_serpapi(sku, serp_api_key)
        if price is not None:
            return price

    # Path B: Direct HTTP GET
    price = await _fetch_via_http(sku)
    if price is not None:
        return price

    # Path C: Headless Browser Pool Fallback
    return await _fetch_via_browser(sku)


async def _fetch_via_serpapi(sku: str, api_key: str) -> Optional[float]:
    """Fetch structured shopping results via SerpApi."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_shopping",
                    "q": f"{sku} buy",
                    "api_key": api_key,
                    "num": 5,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("shopping_results", [])
                prices = []
                for item in results:
                    p = item.get("extracted_price")
                    if p and isinstance(p, (int, float)) and p > 0:
                        prices.append(float(p))
                if prices:
                    median_price = sorted(prices)[len(prices) // 2]
                    logger.info("SerpApi found price for %s: $%.2f", sku, median_price)
                    return round(median_price, 2)
    except Exception as e:
        logger.warning("SerpApi lookup failed for %s: %s", sku, e)
    return None


async def _fetch_via_http(sku: str) -> Optional[float]:
    """Fetch price from Google Shopping search results via HTTP client."""
    query = f"{sku} buy price"
    params = {"q": query, "tbm": "shop"}
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=8.0) as client:
            resp = await client.get(GOOGLE_SHOPPING_URL, params=params, headers=headers)
            if resp.status_code == 200:
                # Check for CAPTCHA
                if "sorry/index" in str(resp.url) or "recaptcha" in resp.text.lower():
                    logger.warning("Google HTTP scraping triggered CAPTCHA for SKU: %s", sku)
                    return None

                prices = _extract_prices(resp.text)
                if prices:
                    median_price = sorted(prices)[len(prices) // 2]
                    logger.info("Scraped competitor price via HTTP for %s: $%.2f", sku, median_price)
                    return round(median_price, 2)
    except Exception as e:
        logger.debug("HTTP price fetch exception for %s: %s", sku, e)
    return None


async def _fetch_via_browser(sku: str) -> Optional[float]:
    """Fallback: fetch price via shared browser pool session."""
    try:
        session = await browser_pool.get_context()
        try:
            query = f"{sku} buy price"
            url = f"{GOOGLE_SHOPPING_URL}?q={query}&tbm=shop"
            await session.page.goto(url, timeout=10000, wait_until="domcontentloaded")
            content = await session.page.content()
            prices = _extract_prices(content)
            if prices:
                median_price = sorted(prices)[len(prices) // 2]
                logger.info("BrowserPool scraped price for %s: $%.2f", sku, median_price)
                return round(median_price, 2)
        finally:
            await session.close()
    except Exception as e:
        logger.debug("BrowserPool scraping skipped for %s: %s", sku, e)
    return None


def _extract_prices(html: str) -> list[float]:
    """Extract price values from Google Shopping HTML."""
    price_pattern = re.compile(r"\$(\d{1,5}(?:\.\d{2})?)")
    matches = price_pattern.findall(html)

    prices = []
    for match in matches:
        try:
            price = float(match)
            if 0.01 < price < 100_000:
                prices.append(price)
        except ValueError:
            continue
    return prices
