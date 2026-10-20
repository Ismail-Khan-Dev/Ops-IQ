import asyncio
import logging
from typing import Optional

from playwright.async_api import Browser, Playwright, async_playwright

logger = logging.getLogger("ecommerce_ops.infra.browser_pool")


class BrowserPool:
    def __init__(self, max_contexts: int = 3, headless: bool = True):
        self._max_contexts = max_contexts
        self._headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._ref_count = 0
        self._closed = False

    async def start(self):
        if self._browser is not None:
            self._ref_count += 1
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._semaphore = asyncio.Semaphore(self._max_contexts)
        self._ref_count = 1
        self._closed = False
        logger.info(
            "BrowserPool started (max_contexts=%d, headless=%s)",
            self._max_contexts,
            self._headless,
        )

    async def get_context(self):
        if self._browser is None:
            await self.start()
        await self._semaphore.acquire()
        try:
            context = await self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()
        except Exception:
            self._semaphore.release()
            raise
        return BrowserPageSession(context, page, self._semaphore)

    async def stop(self):
        self._ref_count -= 1
        if self._ref_count > 0 or self._closed:
            return
        self._closed = True
        try:
            if self._browser:
                await self._browser.close()
        except Exception as e:
            logger.warning("Error closing browser: %s", e)
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning("Error stopping playwright: %s", e)
        self._browser = None
        self._playwright = None
        self._semaphore = None
        logger.info("BrowserPool stopped")


class BrowserPageSession:
    def __init__(self, context, page, semaphore: asyncio.Semaphore):
        self.context = context
        self.page = page
        self._semaphore = semaphore

    async def close(self):
        try:
            await self.context.close()
        finally:
            self._semaphore.release()


browser_pool = BrowserPool(max_contexts=3, headless=True)
