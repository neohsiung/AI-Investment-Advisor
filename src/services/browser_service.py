import requests
from bs4 import BeautifulSoup
from src.utils.logger import setup_logger

class BrowserService:
    def __init__(self):
        self.logger = setup_logger("BrowserService")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def fetch_page_content(self, url):
        """
        Fetches main text content from a URL.
        """
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove scripts and styles
            for script in soup(["script", "style"]):
                script.decompose()
                
            text = soup.get_text(separator='\n')
            
            # Simple cleaning
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return clean_text[:5000] # Limit to 5000 chars to avoid token overflow
            
        except Exception as e:
            self.logger.error(f"Error scraping {url}: {e}")
            return f"Error fetching content: {e}"

    def google_search(self, query):
        """
        Performs a simple Google Search (Custom Search JSON API would be better, but this is a stub).
        REAL IMPLEMENTATION requires Google Custom Search API Key.
        For now, this is a placeholder that might fail if scraped directly.
        Alternative: DuckDuckGo HTML or use Serper.dev in future.
        """
        self.logger.warning("Google Search is not fully implemented (requires API). Returning mock results.")
        return [
            {"title": "Mock Result 1", "link": "http://example.com/1", "snippet": "Mock snippet for " + query},
            {"title": "Mock Result 2", "link": "http://example.com/2", "snippet": "Another snippet"}
        ]
