"""
Add Data Availability API data to Knowledge Base

Fetches country data availability from the MarketInside API and adds it to the KB
for fast retrieval when users ask about country coverage.

Usage:
    python scripts/add_data_availability.py
"""

import json
import requests
import sys
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# API Configuration
API_URL = "https://api-dp.marketinsidedata.com/api/v1/users/data-availability"
API_HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjMwNzk0OWNiLWZmODItNGVkOS1hNzZhLWMxOGRmOThiZDZkYyIsImlhdCI6MTcwNDU0OTU4MH0.sMR6ZZ52KNkiXG8V-Y6JxjkscCOOEDY7DPEFc5nMU88',
    'cache-control': 'no-cache',
    'content-type': 'application/json',
    'origin': 'https://www.marketinsidedata.com',
    'referer': 'https://www.marketinsidedata.com/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36'
}
API_PAYLOAD = {
    "data_type": "",
    "continent": "",
    "direction": "",
    "searchQuery": "",
    "pageNumber": 1,
    "pageSize": 100000  # Fetch all records
}


def fetch_data_availability() -> List[Dict[str, Any]]:
    """Fetch all data availability records from the API"""
    logger.info("Fetching data availability from API...")

    try:
        response = requests.post(
            API_URL,
            headers=API_HEADERS,
            json=API_PAYLOAD,
            timeout=60
        )
        response.raise_for_status()

        data = response.json()
        records = data.get('data', [])

        logger.info(f"Fetched {len(records)} records from API")
        return records

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        raise


def group_by_continent(records: List[Dict]) -> Dict[str, List[Dict]]:
    """Group records by continent"""
    grouped = defaultdict(list)

    for record in records:
        continent = record.get('continent', 'Unknown')
        grouped[continent].append(record)

    return dict(grouped)


def group_by_country(records: List[Dict]) -> Dict[str, List[Dict]]:
    """Group records by country"""
    grouped = defaultdict(list)

    for record in records:
        country = record.get('country', 'Unknown')
        grouped[country].append(record)

    return dict(grouped)


def create_continent_chunk(continent: str, countries_data: List[Dict]) -> str:
    """Create a chunk summarizing data availability for a continent"""

    # Group by country within this continent
    by_country = group_by_country(countries_data)
    country_names = sorted(by_country.keys())

    # Count data types
    detailed_count = sum(1 for r in countries_data if r.get('data_type') == 'Detailed')
    mirror_count = sum(1 for r in countries_data if r.get('data_type') == 'Mirror')

    # Count directions
    import_count = len([r for r in countries_data if r.get('direction') == 'Import'])
    export_count = len([r for r in countries_data if r.get('direction') == 'Export'])

    chunk = f"""[Data Availability - {continent}]
MarketInside provides trade data coverage for {len(country_names)} countries in {continent}.

Countries covered in {continent}: {', '.join(country_names)}

Data Summary for {continent}:
- Total country records: {len(countries_data)}
- Import data available: {import_count} records
- Export data available: {export_count} records
- Detailed data: {detailed_count} records
- Mirror data: {mirror_count} records

This data includes: Date, Importer/Exporter, Supplier/Buyer, HS Code, Product Description, Quantity, Unit, Value, Trade Partner Countries, Ports and more.
"""
    return chunk


def create_country_chunk(country: str, records: List[Dict]) -> str:
    """Create a detailed chunk for a specific country"""

    if not records:
        return ""

    continent = records[0].get('continent', 'Unknown')

    # Build details for each direction
    details = []
    for record in records:
        direction = record.get('direction', 'Unknown')
        data_type = record.get('data_type', 'Unknown')
        coverage = record.get('data_coverage', 'Unknown')
        period = record.get('period', 'Unknown')
        fields = record.get('data_fields', '')

        details.append(f"- {direction} ({data_type}): Period {period}, Coverage {coverage}")

    chunk = f"""[Data Availability - {country}]
{country} is located in {continent}. MarketInside provides the following trade data for {country}:

{chr(10).join(details)}

Data fields available: {records[0].get('data_fields', 'Date, HS Code, Product Description, Quantity, Unit, Value, Trade Partner Countries, Ports and more')}
"""
    return chunk


def create_kb_chunks(records: List[Dict]) -> List[Dict]:
    """Create KB chunks from data availability records"""
    chunks = []

    # Group by continent
    by_continent = group_by_continent(records)
    logger.info(f"Found {len(by_continent)} continents: {list(by_continent.keys())}")

    # Create continent summary chunks
    for continent, continent_records in by_continent.items():
        chunk_text = create_continent_chunk(continent, continent_records)
        chunks.append({
            'chunk_text': chunk_text,
            'page_title': f'Data Availability - {continent}',
            'page_url': 'https://www.marketinsidedata.com/en/search-data',
            'heading_context': f'Data Availability - {continent}',
            'source': 'data-availability-api'
        })

    # Create individual country chunks
    by_country = group_by_country(records)
    logger.info(f"Found {len(by_country)} countries")

    for country, country_records in by_country.items():
        chunk_text = create_country_chunk(country, country_records)
        if chunk_text:
            chunks.append({
                'chunk_text': chunk_text,
                'page_title': f'Data Availability - {country}',
                'page_url': 'https://www.marketinsidedata.com/en/search-data',
                'heading_context': f'Data Availability - {country}',
                'source': 'data-availability-api'
            })

    # Create a master summary chunk
    total_countries = len(by_country)
    continents = list(by_continent.keys())

    master_chunk = f"""[MarketInside Data Availability Summary]
MarketInside provides comprehensive trade data coverage across {len(continents)} continents and {total_countries} countries worldwide.

Continents covered: {', '.join(sorted(continents))}

Total countries with data: {total_countries}

Data types available:
- Detailed Data: Complete shipment-level records with full buyer/supplier information
- Mirror Data: Trade statistics derived from partner country reports

Each country's data includes: Date, Importer/Exporter names, Supplier/Buyer names, HS Code, Product Description, Quantity, Unit, Value (USD), Trade Partner Countries, Ports, and more.

For specific country availability, ask about any country (e.g., "What data do you have for Kenya?" or "Show me India's data coverage").
"""

    chunks.insert(0, {
        'chunk_text': master_chunk,
        'page_title': 'MarketInside Data Availability Summary',
        'page_url': 'https://www.marketinsidedata.com/en/search-data',
        'heading_context': 'Data Availability Summary',
        'source': 'data-availability-api'
    })

    return chunks


def load_existing_chunks(chunks_file: Path) -> List[Dict]:
    """Load existing KB chunks"""
    if chunks_file.exists():
        with open(chunks_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def remove_old_api_chunks(chunks: List[Dict]) -> List[Dict]:
    """Remove existing data-availability API chunks to avoid duplicates"""
    # Remove chunks that were added from the API previously
    filtered = [
        c for c in chunks
        if c.get('source') != 'data-availability-api'
        and 'Data Availability -' not in c.get('heading_context', '')
    ]
    removed = len(chunks) - len(filtered)
    if removed > 0:
        logger.info(f"Removed {removed} existing data-availability chunks")
    return filtered


def save_chunks(chunks: List[Dict], chunks_file: Path):
    """Save chunks to JSON file"""
    # Reassign chunk IDs
    for i, chunk in enumerate(chunks):
        chunk['chunk_id'] = i
        chunk['word_count'] = len(chunk['chunk_text'].split())
        chunk['char_count'] = len(chunk['chunk_text'])

    with open(chunks_file, 'w', encoding='utf-8') as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(chunks)} chunks to {chunks_file}")


def rebuild_faiss_index(chunks: List[Dict], faiss_file: Path, ollama_url: str = "http://localhost:11434"):
    """Rebuild FAISS index from chunks"""
    try:
        import faiss
        import numpy as np
        import ollama
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.error("Install with: pip install faiss-cpu ollama")
        return

    logger.info(f"Generating embeddings for {len(chunks)} chunks...")

    client = ollama.Client(host=ollama_url)
    embeddings = []

    for i, chunk in enumerate(chunks):
        if i % 20 == 0:
            logger.info(f"  Processing chunk {i+1}/{len(chunks)}...")

        try:
            response = client.embeddings(
                model="nomic-embed-text",
                prompt=chunk['chunk_text'][:2000]  # Truncate very long chunks
            )
            embeddings.append(np.array(response['embedding']).astype('float32'))
        except Exception as e:
            logger.error(f"Embedding failed for chunk {i}: {e}")
            # Use zero vector as fallback
            embeddings.append(np.zeros(768, dtype='float32'))

    # Stack embeddings
    embeddings_matrix = np.vstack(embeddings).astype('float32')

    # Normalize for cosine similarity
    faiss.normalize_L2(embeddings_matrix)

    # Create index
    dimension = embeddings_matrix.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings_matrix)

    # Save index
    faiss.write_index(index, str(faiss_file))
    logger.info(f"Saved FAISS index with {index.ntotal} vectors to {faiss_file}")


def main():
    # Paths
    data_dir = Path(__file__).parent.parent / "data"
    chunks_file = data_dir / "kb_marketinside_chunks.json"
    faiss_file = data_dir / "faiss_marketinside_normalized.index"

    # Fetch API data
    records = fetch_data_availability()

    if not records:
        logger.error("No records fetched from API")
        return

    # Create KB chunks from API data
    new_chunks = create_kb_chunks(records)
    logger.info(f"Created {len(new_chunks)} new chunks from API data")

    # Load existing chunks
    existing_chunks = load_existing_chunks(chunks_file)
    logger.info(f"Loaded {len(existing_chunks)} existing chunks")

    # Remove old API chunks to avoid duplicates
    existing_chunks = remove_old_api_chunks(existing_chunks)

    # Merge chunks
    all_chunks = existing_chunks + new_chunks
    logger.info(f"Total chunks after merge: {len(all_chunks)}")

    # Save chunks
    save_chunks(all_chunks, chunks_file)

    # Rebuild FAISS index
    rebuild_faiss_index(all_chunks, faiss_file)

    # Print summary
    logger.info("=" * 60)
    logger.info("DATA AVAILABILITY IMPORT COMPLETE")
    logger.info(f"  API records fetched: {len(records)}")
    logger.info(f"  New chunks created: {len(new_chunks)}")
    logger.info(f"  Total KB chunks: {len(all_chunks)}")
    logger.info(f"  Chunks file: {chunks_file}")
    logger.info(f"  FAISS index: {faiss_file}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
