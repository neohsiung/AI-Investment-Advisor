import asyncio
import os
from typing import Dict, Any, Optional
from src.utils.logger import setup_logger

logger = setup_logger("Crawl4AIScraper")

class Crawl4AIScraper:
    """
    High-performance LLM-friendly web scraper leveraging Crawl4AI / Playwright.
    高效能 LLM 友善網頁爬蟲與 Markdown 轉譯模組。
    """
    def __init__(self, headless: bool = True, timeout: int = 30):
        self.headless = headless
        self.timeout = timeout

    async def scrape_markdown(self, url: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Scrapes a web page and returns clean LLM-ready Markdown and metadata.
        抓取網頁內容並轉譯為潔淨 Markdown。
        """
        logger.info(f"Scraping URL via Crawl4AI pipeline: {url}")
        
        # 1. Try importing native Crawl4AI library if available
        try:
            from crawl4ai import AsyncWebCrawler
            async with AsyncWebCrawler(verbose=False) as crawler:
                result = await crawler.arun(url=url)
                if result and result.markdown:
                    logger.info(f"Successfully scraped {len(result.markdown)} chars from {url}")
                    return {
                        "status": "success",
                        "url": url,
                        "markdown": result.markdown,
                        "title": getattr(result, "title", "Scraped Content"),
                        "extracted_at": getattr(result, "timestamp", None),
                    }
        except ImportError:
            logger.debug("crawl4ai package not directly installed, using fallback HTTP/Playwright fetcher")
        except Exception as e:
            logger.warning(f"AsyncWebCrawler failed for {url}: {e}, trying fallback")

        # 2. Fallback: Standard BeautifulSoup / Httpx Markdown Converter
        try:
            import httpx
            from bs4 import BeautifulSoup
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    # Remove scripts, styles, navs
                    for element in soup(["script", "style", "nav", "footer", "header", "iframe"]):
                        element.extract()
                    text = soup.get_text(separator="\n\n")
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    clean_markdown = "\n\n".join(lines)
                    title = soup.title.string if soup.title else "News Content"
                    return {
                        "status": "success",
                        "url": url,
                        "markdown": clean_markdown[:15000],
                        "title": str(title).strip(),
                    }
        except Exception as e:
            logger.error(f"Fallback scraper failed for {url}: {e}")

        return {
            "status": "error",
            "url": url,
            "error": "Failed to scrape markdown content",
            "markdown": ""
        }
