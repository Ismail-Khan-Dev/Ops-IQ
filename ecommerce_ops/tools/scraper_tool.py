import logging
from typing import Optional

from ecommerce_ops.connectors.competitor_scraper import scrape_competitor_price
from ecommerce_ops.tools.registry import Tool, ToolRegistry

logger = logging.getLogger("ecommerce_ops.tools.scraper_tool")


class ScraperTool(Tool):
    name = "scrape_competitor_price"
    description = "Scrape competitor price for a given SKU. Returns a float price or None."

    async def run(self, sku: str) -> Optional[float]:
        logger.info("ScraperTool scraping price for SKU: %s", sku)
        return await scrape_competitor_price(sku)


ToolRegistry.register(ScraperTool())
