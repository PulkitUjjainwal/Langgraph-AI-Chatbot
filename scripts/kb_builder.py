"""
Knowledge Base Builder for Market Inside Data
Scrapes website pages and creates KB chunks + FAISS index

This script follows the EXACT same pattern as your existing KB:
- Chunks format: kb_{site_id}_chunks.json
- FAISS index: faiss_{site_id}_normalized.index
- Embeddings: nomic-embed-text via Ollama

Usage:
    python scripts/kb_builder.py                    # Scrape all default pages & build index
    python scripts/kb_builder.py --url URL          # Add single URL to existing KB
    python scripts/kb_builder.py --rescrape URL     # Rescrape a URL (removes old chunks first)
    python scripts/kb_builder.py --rescrape-pricing # Rescrape pricing page with improved extraction
    python scripts/kb_builder.py --add-homepage     # Add homepage to existing KB
    python scripts/kb_builder.py --rebuild          # Rebuild entire KB from scratch
    python scripts/kb_builder.py --index-only       # Regenerate FAISS index from existing chunks
"""

import json
import re
import time
import argparse
import sys
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from urllib.parse import urlparse, urljoin
from dataclasses import dataclass, asdict
import logging
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS not installed. Install with: pip install faiss-cpu")

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not installed. Install with: pip install ollama")

try:
    from playwright.sync_api import sync_playwright, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Install with: pip install playwright && playwright install chromium")

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("BeautifulSoup not installed. Install with: pip install beautifulsoup4")


@dataclass
class KBChunk:
    """Knowledge Base chunk structure - matches existing format exactly"""
    chunk_id: int
    chunk_text: str
    page_title: str
    page_url: str
    heading_context: str
    word_count: int
    char_count: int


class MarketInsideKBBuilder:
    """
    Builds Knowledge Base for Market Inside Data website

    Creates:
    - kb_marketinside_chunks.json (same format as existing)
    - faiss_marketinside_normalized.index (FAISS index with normalized embeddings)
    """

    # Default pages to scrape (includes homepage)
    DEFAULT_PAGES = [
        # Homepage (was missing)
        "https://www.marketinsidedata.com",

        # Core pages
        "https://www.marketinsidedata.com/en/about-us",
        "https://www.marketinsidedata.com/en/api",
        "https://www.marketinsidedata.com/en/data-license",
        "https://www.marketinsidedata.com/en/plan-and-pricing",
        "https://www.marketinsidedata.com/en/platform",
        "https://www.marketinsidedata.com/en/search-data",
        "https://www.marketinsidedata.com/en/case-studies",
        "https://www.marketinsidedata.com/en/terms-and-conditions",

        # Industry Solutions
        "https://www.marketinsidedata.com/en/solutions/industry/logistics",
        "https://www.marketinsidedata.com/en/solutions/industry/banking-finance",
        "https://www.marketinsidedata.com/en/solutions/industry/manufacturing",
        "https://www.marketinsidedata.com/en/solutions/industry/healthcare",
        "https://www.marketinsidedata.com/en/solutions/industry/consulting",
        "https://www.marketinsidedata.com/en/solutions/industry/universities",
        "https://www.marketinsidedata.com/en/solutions/industry/agri-food",
        "https://www.marketinsidedata.com/en/solutions/industry/government",
        "https://www.marketinsidedata.com/en/solutions/industry/research",

        # Use Cases
        "https://www.marketinsidedata.com/en/solutions/usecase/buyer-supplier-discovery",
        "https://www.marketinsidedata.com/en/solutions/usecase/competitor-benchmarking",
        "https://www.marketinsidedata.com/en/solutions/usecase/market-entry-insights",
        "https://www.marketinsidedata.com/en/solutions/usecase/market-intelligence",
        "https://www.marketinsidedata.com/en/solutions/usecase/research-analytics",
        "https://www.marketinsidedata.com/en/solutions/usecase/trade-compliance",
    ]

    def __init__(
        self,
        site_id: str = "marketinside",
        data_dir: str = "data",
        embedding_model: str = "nomic-embed-text",
        ollama_base_url: str = "http://localhost:11434"
    ):
        self.site_id = site_id
        self.data_dir = Path(data_dir)
        self.embedding_model = embedding_model
        self.ollama_base_url = ollama_base_url

        # File paths (matching existing pattern)
        self.chunks_file = self.data_dir / f"kb_{site_id}_chunks.json"
        self.faiss_file = self.data_dir / f"faiss_{site_id}_normalized.index"

        self.chunks: List[KBChunk] = []
        self.chunk_id_counter = 0

        # Ollama client for embeddings
        self.ollama_client = None
        if OLLAMA_AVAILABLE:
            self.ollama_client = ollama.Client(host=ollama_base_url)

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove special characters but keep essential punctuation
        text = re.sub(r'[^\w\s\.\,\!\?\-\:\;\'\"\%\$\@\#\&\(\)\[\]\{\}\/\+\=]', ' ', text)

        # Remove multiple spaces
        text = re.sub(r' +', ' ', text)

        return text.strip()

    def _extract_headings(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Extract headings with their following content"""
        headings_content = []

        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
            heading_text = self._clean_text(heading.get_text())
            if not heading_text or len(heading_text) < 3:
                continue

            # Get content following this heading until next heading
            content_parts = []
            for sibling in heading.find_next_siblings():
                if sibling.name in ['h1', 'h2', 'h3', 'h4']:
                    break
                text = self._clean_text(sibling.get_text())
                if text:
                    content_parts.append(text)

            if content_parts:
                headings_content.append((heading_text, ' '.join(content_parts)))

        return headings_content

    def _extract_card_sections(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """
        Extract content from card-based layouts (like pricing page regions).
        Looks for parent containers that hold both heading and content together.
        """
        card_content = []

        # Find all headings and look at their parent containers
        for heading in soup.find_all(['h2', 'h3', 'h4']):
            heading_text = self._clean_text(heading.get_text())
            if not heading_text or len(heading_text) < 3:
                continue

            # Find the nearest parent container (div, section, article)
            parent = heading.find_parent(['div', 'section', 'article'])
            if not parent:
                continue

            # Get all text content from this parent container
            parent_text = self._clean_text(parent.get_text())

            # Remove the heading text from the content to avoid duplication
            content = parent_text.replace(heading_text, '', 1).strip()

            if content and len(content) > 20:
                card_content.append((heading_text, content))

        return card_content

    def _extract_pricing_regions(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """
        Special extraction for pricing page region cards.
        Each region (America, Global, Africa, Europe, Asia Pacific) is in its own card.
        """
        regions = []
        region_names = ['America', 'Global', 'Africa', 'Europe', 'Asia Pacific']

        for heading in soup.find_all(['h2', 'h3', 'h4']):
            heading_text = self._clean_text(heading.get_text())

            # Check if this is a region heading
            if heading_text not in region_names:
                continue

            # Find the card container - go up to find a meaningful parent
            card = None
            for parent in heading.parents:
                if parent.name in ['div', 'section', 'article']:
                    # Check if this parent contains enough content (countries list)
                    parent_text = parent.get_text()
                    # Region cards typically have country lists and feature bullets
                    if len(parent_text) > 100 and ('Countries' in parent_text or 'Data' in parent_text):
                        card = parent
                        break

            if card:
                # Extract all text from this card
                card_text = self._clean_text(card.get_text())

                # The content should include the country list and features
                if card_text and len(card_text) > 50:
                    regions.append((heading_text, card_text))
                    logger.info(f"  Extracted region '{heading_text}': {len(card_text)} chars")

        return regions

    def _chunk_text(self, text: str, max_chunk_size: int = 8000, overlap: int = 200) -> List[str]:
        """Split text into chunks with overlap"""
        if len(text) <= max_chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + max_chunk_size

            # Try to break at sentence boundary
            if end < len(text):
                search_start = max(end - 500, start)
                last_period = text.rfind('. ', search_start, end)
                if last_period > search_start:
                    end = last_period + 1

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - overlap if end < len(text) else len(text)

        return chunks

    def scrape_page(self, url: str, page: Page) -> Optional[Dict]:
        """Scrape a single page using Playwright"""
        logger.info(f"Scraping: {url}")

        try:
            # Navigate to page
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(2)  # Wait for dynamic content

            # Get page title
            title = page.title() or "Market Inside Data"

            # Get page content
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')

            # Remove unwanted elements
            for element in soup.find_all(['script', 'style', 'nav', 'footer', 'iframe', 'noscript']):
                element.decompose()

            # Extract main content
            main_content = soup.find('main') or soup.find('body')

            if not main_content:
                logger.warning(f"No main content found for {url}")
                return None

            # Get full text
            full_text = self._clean_text(main_content.get_text())

            # Use special extraction for pricing page (has card-based regions)
            if 'plan-and-pricing' in url:
                logger.info("  Using pricing page extraction for region cards...")
                headings_content = self._extract_pricing_regions(main_content)
                # Also try card sections as fallback
                if len(headings_content) < 3:
                    headings_content.extend(self._extract_card_sections(main_content))
            else:
                # Standard heading extraction for other pages
                headings_content = self._extract_headings(main_content)

            return {
                'url': url,
                'title': title,
                'full_text': full_text,
                'headings_content': headings_content
            }

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    def create_chunks_from_page(self, page_data: Dict) -> List[KBChunk]:
        """Create KB chunks from scraped page data"""
        if not page_data:
            return []

        chunks = []
        url = page_data['url']
        title = page_data['title']
        full_text = page_data['full_text']
        headings_content = page_data['headings_content']

        # Create chunk for full page content
        text_chunks = self._chunk_text(full_text)
        for text in text_chunks:
            chunk = KBChunk(
                chunk_id=self.chunk_id_counter,
                chunk_text=text,
                page_title=title,
                page_url=url,
                heading_context="",
                word_count=len(text.split()),
                char_count=len(text)
            )
            chunks.append(chunk)
            self.chunk_id_counter += 1

        # Create chunks for each heading section
        for heading, content in headings_content:
            if len(content) < 50:
                continue

            chunk_text = f"[{heading}] {content}"
            text_chunks = self._chunk_text(chunk_text)

            for text in text_chunks:
                chunk = KBChunk(
                    chunk_id=self.chunk_id_counter,
                    chunk_text=text,
                    page_title=title,
                    page_url=url,
                    heading_context=heading,
                    word_count=len(text.split()),
                    char_count=len(text)
                )
                chunks.append(chunk)
                self.chunk_id_counter += 1

        return chunks

    def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding using Ollama (same as your existing setup)"""
        if not self.ollama_client:
            raise RuntimeError("Ollama client not available")

        try:
            response = self.ollama_client.embeddings(
                model=self.embedding_model,
                prompt=text
            )
            return np.array(response['embedding']).astype('float32')
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    def build_faiss_index(self, chunks: List[KBChunk]) -> faiss.Index:
        """
        Build FAISS index from chunks

        Uses the same approach as your existing setup:
        - nomic-embed-text embeddings via Ollama
        - L2 normalization for cosine similarity
        - IndexFlatIP (inner product after normalization = cosine similarity)
        """
        if not FAISS_AVAILABLE:
            raise RuntimeError("FAISS not available")

        if not self.ollama_client:
            raise RuntimeError("Ollama client not available")

        logger.info(f"Generating embeddings for {len(chunks)} chunks...")

        embeddings = []
        for i, chunk in enumerate(chunks):
            if i % 10 == 0:
                logger.info(f"  Processing chunk {i+1}/{len(chunks)}...")

            # Generate embedding
            embedding = self.generate_embedding(chunk.chunk_text[:2000])  # Truncate very long chunks
            embeddings.append(embedding)

            # Rate limiting to avoid overloading Ollama
            if i % 50 == 0 and i > 0:
                time.sleep(0.5)

        # Stack embeddings into matrix
        embeddings_matrix = np.vstack(embeddings).astype('float32')

        # Normalize for cosine similarity (same as your existing setup)
        faiss.normalize_L2(embeddings_matrix)

        # Create index (IndexFlatIP = inner product, which equals cosine after normalization)
        dimension = embeddings_matrix.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings_matrix)

        logger.info(f"Created FAISS index with {index.ntotal} vectors (dimension: {dimension})")
        return index

    def save_chunks(self):
        """Save chunks to JSON file"""
        self.data_dir.mkdir(parents=True, exist_ok=True)

        data = [asdict(chunk) for chunk in self.chunks]

        with open(self.chunks_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(self.chunks)} chunks to {self.chunks_file}")

    def save_faiss_index(self, index: faiss.Index):
        """Save FAISS index to file"""
        faiss.write_index(index, str(self.faiss_file))
        logger.info(f"Saved FAISS index to {self.faiss_file}")

    def load_existing_chunks(self) -> bool:
        """Load existing chunks if available"""
        if self.chunks_file.exists():
            logger.info(f"Loading chunks from: {self.chunks_file}")
            with open(self.chunks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Debug: Check first chunk keys
                if data:
                    logger.info(f"First chunk keys: {list(data[0].keys())}")

                # Filter out any unexpected fields
                clean_data = []
                for chunk in data:
                    clean_chunk = {k: v for k, v in chunk.items() if k in [
                        'chunk_id', 'chunk_text', 'page_title', 'page_url',
                        'heading_context', 'word_count', 'char_count'
                    ]}
                    clean_data.append(clean_chunk)

                self.chunks = [KBChunk(**chunk) for chunk in clean_data]
                self.chunk_id_counter = max(c.chunk_id for c in self.chunks) + 1 if self.chunks else 0
                logger.info(f"Loaded {len(self.chunks)} existing chunks")
                return True
        return False

    def build_kb(self, urls: List[str] = None, append: bool = False):
        """Build knowledge base from list of URLs"""
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not available. Install with: pip install playwright && playwright install chromium")
            return

        urls = urls or self.DEFAULT_PAGES

        # Load existing chunks if appending
        if append and self.chunks_file.exists():
            self.load_existing_chunks()
            existing_urls = {c.page_url for c in self.chunks}
            urls = [u for u in urls if u not in existing_urls]
            logger.info(f"{len(urls)} new URLs to scrape.")

        if not urls:
            logger.info("No new URLs to scrape.")
            return

        # Scrape pages
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = context.new_page()

            for url in urls:
                page_data = self.scrape_page(url, page)
                if page_data:
                    new_chunks = self.create_chunks_from_page(page_data)
                    self.chunks.extend(new_chunks)
                    logger.info(f"  Created {len(new_chunks)} chunks from {url}")

                time.sleep(1)  # Rate limiting

            browser.close()

        # Save chunks
        self.save_chunks()

        # Build and save FAISS index
        if FAISS_AVAILABLE and OLLAMA_AVAILABLE:
            logger.info("Building FAISS index...")
            index = self.build_faiss_index(self.chunks)
            self.save_faiss_index(index)
        else:
            logger.warning("Skipping FAISS index (missing dependencies)")

        # Print summary
        self._print_summary()

    def rebuild_index_only(self):
        """Rebuild FAISS index from existing chunks (without re-scraping)"""
        if not self.load_existing_chunks():
            logger.error(f"No existing chunks found at {self.chunks_file}")
            return

        if not FAISS_AVAILABLE or not OLLAMA_AVAILABLE:
            logger.error("FAISS or Ollama not available")
            return

        logger.info("Rebuilding FAISS index from existing chunks...")
        index = self.build_faiss_index(self.chunks)
        self.save_faiss_index(index)
        self._print_summary()

    def add_single_url(self, url: str):
        """Add a single URL to the existing KB"""
        self.build_kb(urls=[url], append=True)

    def rescrape_url(self, url: str):
        """
        Rescrape a specific URL - removes old chunks and re-scrapes.
        Useful for updating pages that have changed or were scraped incorrectly.
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not available")
            return

        # Load existing chunks
        if not self.load_existing_chunks():
            logger.warning("No existing chunks found, will create new KB")
            self.chunks = []

        # Remove existing chunks for this URL
        old_count = len(self.chunks)
        self.chunks = [c for c in self.chunks if c.page_url != url]
        removed = old_count - len(self.chunks)
        if removed > 0:
            logger.info(f"Removed {removed} existing chunks for {url}")

        # Rescrape the URL
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = context.new_page()

            page_data = self.scrape_page(url, page)
            if page_data:
                new_chunks = self.create_chunks_from_page(page_data)
                self.chunks.extend(new_chunks)
                logger.info(f"Created {len(new_chunks)} new chunks from {url}")

            browser.close()

        # Reassign chunk IDs to be sequential
        for i, chunk in enumerate(self.chunks):
            chunk.chunk_id = i
        self.chunk_id_counter = len(self.chunks)

        # Save chunks
        self.save_chunks()

        # Rebuild FAISS index
        if FAISS_AVAILABLE and OLLAMA_AVAILABLE:
            logger.info("Rebuilding FAISS index...")
            index = self.build_faiss_index(self.chunks)
            self.save_faiss_index(index)

        self._print_summary()

    def _print_summary(self):
        """Print KB summary"""
        unique_urls = set(c.page_url for c in self.chunks)
        logger.info("=" * 60)
        logger.info("KB BUILD COMPLETE")
        logger.info(f"  Total pages: {len(unique_urls)}")
        logger.info(f"  Total chunks: {len(self.chunks)}")
        logger.info(f"  Chunks file: {self.chunks_file}")
        logger.info(f"  FAISS index: {self.faiss_file}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Build Knowledge Base for Market Inside Data')
    parser.add_argument('--url', type=str, help='Single URL to scrape and add')
    parser.add_argument('--rescrape', type=str, help='Rescrape a specific URL (removes old chunks first)')
    parser.add_argument('--rescrape-pricing', action='store_true', help='Rescrape the pricing page with improved extraction')
    parser.add_argument('--add-homepage', action='store_true', help='Add homepage to existing KB')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild entire KB from scratch')
    parser.add_argument('--index-only', action='store_true', help='Regenerate FAISS index from existing chunks')
    parser.add_argument('--site-id', type=str, default='marketinside', help='Site ID (default: marketinside)')
    parser.add_argument('--data-dir', type=str, default='data', help='Data directory (default: data)')

    args = parser.parse_args()

    builder = MarketInsideKBBuilder(
        site_id=args.site_id,
        data_dir=args.data_dir
    )

    if args.rescrape:
        logger.info(f"Rescraping URL: {args.rescrape}")
        builder.rescrape_url(args.rescrape)
    elif args.rescrape_pricing:
        logger.info("Rescraping pricing page with improved region extraction...")
        builder.rescrape_url("https://www.marketinsidedata.com/en/plan-and-pricing")
    elif args.url:
        logger.info(f"Adding single URL: {args.url}")
        builder.add_single_url(args.url)
    elif args.add_homepage:
        logger.info("Adding homepage...")
        builder.add_single_url("https://www.marketinsidedata.com/en")
    elif args.index_only:
        logger.info("Regenerating FAISS index only...")
        builder.rebuild_index_only()
    elif args.rebuild:
        logger.info("Rebuilding entire KB...")
        builder.build_kb(append=False)
    else:
        logger.info("Building KB (appending to existing)...")
        builder.build_kb(append=True)


if __name__ == "__main__":
    main()
