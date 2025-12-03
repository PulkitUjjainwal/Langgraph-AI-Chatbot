"""
Web Scraper Utility for Dynamic Content Extraction

Industry best practices:
- Proper error handling and logging
- Rate limiting and retry logic
- User-agent rotation
- Timeout configuration
- Content cleaning and normalization
"""

import re
import time
from typing import Optional, Dict, List
from urllib.parse import urlparse
import logging

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False
    print("⚠️  Warning: requests and beautifulsoup4 not installed. Install with:")
    print("   pip install requests beautifulsoup4")


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebScraper:
    """
    Production-ready web scraper with error handling and best practices

    Features:
    - Timeout configuration
    - User-agent rotation
    - Retry logic with exponential backoff
    - Content cleaning and normalization
    - Error handling and logging
    """

    def __init__(
        self,
        timeout: int = 10,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize web scraper

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (exponential backoff)
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # User agents for rotation (best practice to avoid blocking)
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        self.current_ua_index = 0

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with rotated user agent"""
        ua = self.user_agents[self.current_ua_index]
        self.current_ua_index = (self.current_ua_index + 1) % len(self.user_agents)

        return {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize extracted text

        Args:
            text: Raw text from webpage

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)

        # Keep more characters for data tables (numbers, symbols, etc.)
        # Only remove truly problematic characters
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', text)

        # Trim
        text = text.strip()

        return text

    def scrape_url(self, url: str) -> Dict[str, any]:
        """
        Scrape content from URL with retry logic and error handling

        Args:
            url: URL to scrape

        Returns:
            Dict with:
                - success: bool
                - content: str (cleaned text content)
                - title: str (page title)
                - error: str (error message if failed)
                - metadata: dict (additional info)
        """
        if not SCRAPING_AVAILABLE:
            return {
                'success': False,
                'content': '',
                'title': '',
                'error': 'Scraping libraries not installed (requests, beautifulsoup4)',
                'metadata': {}
            }

        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return {
                    'success': False,
                    'content': '',
                    'title': '',
                    'error': f'Invalid URL format: {url}',
                    'metadata': {}
                }
        except Exception as e:
            return {
                'success': False,
                'content': '',
                'title': '',
                'error': f'URL parsing error: {str(e)}',
                'metadata': {}
            }

        # Retry logic with exponential backoff
        last_error = None
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Scraping URL (attempt {attempt + 1}/{self.max_retries}): {url}")

                # Make request
                response = requests.get(
                    url,
                    headers=self._get_headers(),
                    timeout=self.timeout,
                    allow_redirects=True
                )

                # Check status
                response.raise_for_status()

                # Parse HTML
                soup = BeautifulSoup(response.content, 'html.parser')

                # Remove only script and style elements (KEEP nav, footer, header for data tables)
                for element in soup(['script', 'style']):
                    element.decompose()

                # Extract title
                title = soup.title.string if soup.title else "Untitled Page"
                title = self._clean_text(title)

                # Extract main content
                # Try to find main content area
                main_content = soup.find('main') or soup.find('article') or soup.find('body')

                if main_content:
                    # Extract text
                    text = main_content.get_text(separator=' ', strip=True)
                else:
                    text = soup.get_text(separator=' ', strip=True)

                # Clean text
                cleaned_text = self._clean_text(text)

                # Extract metadata
                metadata = {
                    'url': url,
                    'title': title,
                    'length': len(cleaned_text),
                    'status_code': response.status_code,
                    'content_type': response.headers.get('content-type', 'unknown'),
                    'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S')
                }

                logger.info(f"✓ Successfully scraped {url} ({len(cleaned_text)} chars)")

                return {
                    'success': True,
                    'content': cleaned_text,
                    'title': title,
                    'error': None,
                    'metadata': metadata
                }

            except requests.exceptions.Timeout:
                last_error = f"Timeout after {self.timeout}s"
                logger.warning(f"Timeout on attempt {attempt + 1}: {url}")

            except requests.exceptions.HTTPError as e:
                last_error = f"HTTP error: {e.response.status_code}"
                logger.warning(f"HTTP error on attempt {attempt + 1}: {url} - {e}")

            except requests.exceptions.ConnectionError:
                last_error = "Connection error"
                logger.warning(f"Connection error on attempt {attempt + 1}: {url}")

            except requests.exceptions.RequestException as e:
                last_error = f"Request error: {str(e)}"
                logger.warning(f"Request error on attempt {attempt + 1}: {url} - {e}")

            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                logger.error(f"Unexpected error on attempt {attempt + 1}: {url} - {e}")

            # Wait before retry (exponential backoff)
            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2 ** attempt)
                logger.info(f"Retrying in {delay}s...")
                time.sleep(delay)

        # All retries failed
        logger.error(f"✗ Failed to scrape {url} after {self.max_retries} attempts")
        return {
            'success': False,
            'content': '',
            'title': '',
            'error': last_error or 'Unknown error',
            'metadata': {'url': url, 'attempts': self.max_retries}
        }

    def scrape_multiple_urls(self, urls: List[str], delay_between: float = 1.0) -> List[Dict]:
        """
        Scrape multiple URLs with rate limiting

        Args:
            urls: List of URLs to scrape
            delay_between: Delay between requests (rate limiting)

        Returns:
            List of scraping results
        """
        results = []

        for i, url in enumerate(urls):
            result = self.scrape_url(url)
            results.append(result)

            # Rate limiting (except for last URL)
            if i < len(urls) - 1:
                time.sleep(delay_between)

        return results

    def chunk_scraped_content(
        self,
        content: str,
        chunk_size: int = 500,
        overlap: int = 50
    ) -> List[str]:
        """
        Chunk scraped content for RAG (similar to KB chunking)

        Args:
            content: Scraped text content
            chunk_size: Target size for each chunk
            overlap: Overlap between chunks

        Returns:
            List of text chunks
        """
        if not content:
            return []

        words = content.split()
        chunks = []

        i = 0
        while i < len(words):
            # Get chunk
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)
            chunks.append(chunk_text)

            # Move forward with overlap
            i += chunk_size - overlap

        return chunks


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def scrape_url_simple(url: str, timeout: int = 10) -> str:
    """
    Simple wrapper to scrape URL and return text content

    Args:
        url: URL to scrape
        timeout: Request timeout

    Returns:
        Scraped text content (empty string if failed)
    """
    scraper = WebScraper(timeout=timeout)
    result = scraper.scrape_url(url)

    if result['success']:
        return result['content']
    else:
        logger.error(f"Failed to scrape {url}: {result['error']}")
        return ""


def scrape_and_chunk(
    url: str,
    chunk_size: int = 500,
    overlap: int = 50,
    timeout: int = 10
) -> List[str]:
    """
    Scrape URL and return chunked content ready for RAG

    Args:
        url: URL to scrape
        chunk_size: Size of each chunk
        overlap: Overlap between chunks
        timeout: Request timeout

    Returns:
        List of text chunks
    """
    scraper = WebScraper(timeout=timeout)
    result = scraper.scrape_url(url)

    if result['success']:
        chunks = scraper.chunk_scraped_content(
            result['content'],
            chunk_size=chunk_size,
            overlap=overlap
        )
        logger.info(f"Created {len(chunks)} chunks from {url}")
        return chunks
    else:
        logger.error(f"Failed to scrape and chunk {url}: {result['error']}")
        return []


# ============================================================================
# TESTING
# ============================================================================

if __name__ == '__main__':
    # Test the scraper
    print("Testing Web Scraper...")
    print()

    # Example URL (replace with your actual URL)
    test_url = "https://example.com"

    scraper = WebScraper()
    result = scraper.scrape_url(test_url)

    if result['success']:
        print(f"✓ Successfully scraped: {result['title']}")
        print(f"  Content length: {len(result['content'])} chars")
        print(f"  Preview: {result['content'][:200]}...")
        print()

        # Test chunking
        chunks = scraper.chunk_scraped_content(result['content'])
        print(f"✓ Created {len(chunks)} chunks")
        print(f"  First chunk: {chunks[0][:100]}...")
    else:
        print(f"✗ Scraping failed: {result['error']}")
