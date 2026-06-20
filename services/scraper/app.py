"""
Lightweight Web Scraper Service (requests-html)
API Endpoint: POST /scrape-raw
Response: { "url": "...", "title": "...", "plaintext": "..." }
"""
import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from requests_html import HTMLSession
from bs4 import BeautifulSoup

app = FastAPI(title="Lightweight Scraper Service")

class ScrapeRequest(BaseModel):
    url: str
    max_length: int = 2000

def clean_text(text: str, max_length: int = 2000) -> str:
    """Clean and normalize text content"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = " ".join(lines)
    return cleaned[:max_length] if len(cleaned) > max_length else cleaned

async def scrape_url_async(url: str, max_length: int = 2000) -> dict:
    """Scrape a URL using requests-html (with JS rendering support)"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, scrape_url_sync, url, max_length)

def scrape_url_sync(url: str, max_length: int = 2000) -> dict:
    """Sync wrapper for scraping"""
    session = HTMLSession()
    try:
        response = session.get(url, timeout=30)
        response.html.render(timeout=20)  # Render JS
        
        soup = BeautifulSoup(response.html(html="<html>"), "html.parser")
        
        # Remove non-content tags
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        
        # Extract title
        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else None
        
        # Try to find main content
        main_tag = soup.find("main") or soup.find("article")
        if not main_tag:
            content_divs = soup.find_all("div", class_=lambda x: x and any(k in x.lower() for k in ["content", "article", "post", "text"]))
            main_tag = content_divs[0] if content_divs else soup.find("body")
        
        plaintext = None
        if main_tag:
            text = main_tag.get_text(separator="\n")
            plaintext = clean_text(text, max_length)
        
        session.close()
        return {
            "url": url,
            "title": title,
            "plaintext": plaintext
        }
    except Exception as e:
        session.close()
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/scrape-raw")
async def scrape_raw(request: ScrapeRequest):
    result = await scrape_url_async(request.url, request.max_length)
    return {
        "plaintext": result.get("plaintext"),
        "title": result.get("title"),
        "url": result.get("url")
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
