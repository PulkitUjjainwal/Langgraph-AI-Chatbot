"""
Simple API Data Integration for Existing KB
Adds Market Inside API data to your existing knowledge base
Compatible with LangGraph chatbot setup
"""

import json
import hashlib
import requests
import numpy as np
import faiss
import ollama
from pathlib import Path
from datetime import datetime
from typing import List, Dict

# ============================================================================
# CONFIGURATION
# ============================================================================
DATA_DIR = Path("data")
API_URL = "https://api-dp.marketinsidedata.com/api/v1/users/data-availability"
API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjMwNzk0OWNiLWZmODItNGVkOS1hNzZhLWMxOGRmOThiZDZkYyIsImlhdCI6MTcwNDU0OTU4MH0.sMR6ZZ52KNkiXG8V-Y6JxjkscCOOEDY7DPEFc5nMU88"

EMBEDDING_MODEL = "nomic-embed-text"  # Same as your existing KB
CHUNK_SIZE = 800  # Match your existing configuration
CHUNK_OVERLAP = 100

# ============================================================================
# STEP 1: FETCH API DATA
# ============================================================================
def fetch_api_data():
    """Fetch data from Market Inside API"""
    print("📡 Fetching API data...")
    
    headers = {
        'accept': 'application/json, text/plain, */*',
        'authorization': f'Bearer {API_TOKEN}',
        'content-type': 'application/json',
        'origin': 'https://www.marketinsidedata.com',
        'referer': 'https://www.marketinsidedata.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    payload = {
        "data_type": "",
        "continent": "",
        "direction": "",
        "searchQuery": "",
        "pageNumber": 1,
        "pageSize": 1000000
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Save raw API response for reference
        with open(DATA_DIR / "api_raw_response.json", 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✓ Fetched {len(data.get('data', []))} entries")
        return data
    
    except Exception as e:
        print(f"❌ Failed to fetch API data: {e}")
        return None

# ============================================================================
# STEP 2: CONVERT API DATA TO DOCUMENTS
# ============================================================================
def create_documents_from_api(api_data):
    """Convert API data to document format matching existing KB structure"""
    print("📄 Creating documents from API data...")
    
    documents = []
    
    if not api_data or 'data' not in api_data:
        return documents
    
    # Group by country for better organization
    country_data = {}
    for entry in api_data['data']:
        country = entry.get('country', 'Unknown')
        if country not in country_data:
            country_data[country] = {'import': [], 'export': []}
        
        direction = entry.get('direction', '').lower()
        if direction in ['import', 'export']:
            country_data[country][direction].append(entry)
    
    # Create comprehensive documents for each country
    for country, data in country_data.items():
        # Main country document
        content_parts = [
            f"Trade Data Availability for {country}",
            f"",
            f"Market Inside provides comprehensive trade data for {country}.",
            f"Located in {data['import'][0].get('continent', 'Unknown') if data['import'] else data['export'][0].get('continent', 'Unknown') if data['export'] else 'Unknown'} continent.",
            ""
        ]
        
        # Add import information
        if data['import']:
            for entry in data['import']:
                content_parts.extend([
                    f"IMPORT DATA AVAILABLE:",
                    f"Data Type: {entry.get('data_type', 'N/A')}",
                    f"Coverage: {entry.get('data_coverage', 'N/A')} of all import activities",
                    f"Period Available: {entry.get('period', 'N/A')}",
                    f"Data Fields Available: {entry.get('data_fields', 'N/A')}",
                    f"",
                    f"Import data includes detailed information about importers, suppliers, HS codes, product descriptions,",
                    f"quantities, values, trade partner countries, ports, and comprehensive trade analytics.",
                    ""
                ])
        
        # Add export information
        if data['export']:
            for entry in data['export']:
                content_parts.extend([
                    f"EXPORT DATA AVAILABLE:",
                    f"Data Type: {entry.get('data_type', 'N/A')}",
                    f"Coverage: {entry.get('data_coverage', 'N/A')} of all export activities",
                    f"Period Available: {entry.get('period', 'N/A')}",
                    f"Data Fields Available: {entry.get('data_fields', 'N/A')}",
                    f"",
                    f"Export data includes detailed information about exporters, buyers, HS codes, product descriptions,",
                    f"quantities, values, trade partner countries, ports, and comprehensive trade analytics.",
                    ""
                ])
        
        content = ' '.join(content_parts)
        
        # Create document matching existing KB structure
        doc_id = hashlib.md5(f"api_{country}".encode()).hexdigest()[:16]
        documents.append({
            'id': doc_id,
            'url': f"https://www.marketinsidedata.com/data/{country.lower().replace(' ', '-')}",
            'title': f"{country} Trade Data - Market Inside",
            'content': content,
            'word_count': len(content.split()),
            'scraped_at': datetime.now().isoformat()
        })
    
    print(f"✓ Created {len(documents)} documents")
    return documents

# ============================================================================
# STEP 3: CHUNK DOCUMENTS
# ============================================================================
def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into chunks with overlap"""
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        if len(chunk) > 100:  # Minimum chunk size
            chunks.append(chunk)
    
    return chunks

def create_chunks_from_documents(documents):
    """Create chunks from documents matching existing KB structure"""
    print("✂️ Creating chunks...")
    
    all_chunks = []
    
    for doc in documents:
        text_chunks = chunk_text(doc['content'])
        
        for idx, text_content in enumerate(text_chunks):  # Changed variable name to avoid conflict
            chunk = {
                'chunk_id': f"{doc['id']}_chunk_{idx}",
                'chunk_index': idx,
                'total_chunks': len(text_chunks),
                'chunk_text': text_content,  # Using the renamed variable
                'char_count': len(text_content),
                'word_count': len(text_content.split()),
                'source_url': doc['url'],
                'page_title': doc['title'],
                'page_id': doc['id'],
                'scraped_at': doc['scraped_at'],
                'chunked_at': datetime.now().isoformat()
            }
            all_chunks.append(chunk)
    
    print(f"✓ Created {len(all_chunks)} chunks")
    return all_chunks

# ============================================================================
# STEP 4: GENERATE EMBEDDINGS
# ============================================================================
def generate_embeddings(chunks):
    """Generate embeddings for new chunks"""
    print("🧠 Generating embeddings...")
    
    embeddings = []
    texts = [chunk['chunk_text'] for chunk in chunks]
    
    for i, text in enumerate(texts):
        if i % 10 == 0:
            print(f"  Processing {i+1}/{len(texts)}...")
        
        try:
            response = ollama.embeddings(model=EMBEDDING_MODEL, prompt=text)
            embeddings.append(response['embedding'])
        except Exception as e:
            print(f"  ⚠️ Error on chunk {i}: {e}")
            # Use zero vector as fallback
            embeddings.append([0.0] * 768)  # Assuming 768 dimensions
    
    embeddings_array = np.array(embeddings, dtype=np.float32)
    
    # Normalize embeddings (important for cosine similarity)
    faiss.normalize_L2(embeddings_array)
    
    print(f"✓ Generated {len(embeddings)} embeddings")
    return embeddings_array

# ============================================================================
# STEP 5: MERGE WITH EXISTING KB
# ============================================================================
def backup_existing_files():
    """Create backups of existing KB files"""
    print("💾 Creating backups...")
    
    import shutil
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = DATA_DIR / f"backup_{timestamp}"
    backup_dir.mkdir(exist_ok=True)
    
    files_to_backup = [
        "kb_chunks.json",
        "kb_embeddings.json",
        "faiss_normalized.index",
        "kb_metadata.json"
    ]
    
    for filename in files_to_backup:
        src = DATA_DIR / filename
        if src.exists():
            dst = backup_dir / filename
            shutil.copy2(src, dst)
    
    print(f"  ✓ Backups saved to {backup_dir}")
    return backup_dir

def merge_with_existing_kb(new_chunks, new_embeddings):
    """Merge new API data with existing KB"""
    print("🔗 Merging with existing KB...")
    
    # Load existing chunks
    with open(DATA_DIR / "kb_chunks.json", 'r', encoding='utf-8') as f:
        existing_chunks = json.load(f)
    print(f"  Existing chunks: {len(existing_chunks)}")
    
    # Load existing embeddings
    with open(DATA_DIR / "kb_embeddings.json", 'r') as f:
        embeddings_data = json.load(f)
        existing_embeddings = np.array(embeddings_data['embeddings'], dtype=np.float32)
    print(f"  Existing embeddings: {len(existing_embeddings)}")
    
    # Load existing FAISS index
    index = faiss.read_index(str(DATA_DIR / "faiss_normalized.index"))
    print(f"  Existing index vectors: {index.ntotal}")
    
    # Merge chunks
    all_chunks = existing_chunks + new_chunks
    with open(DATA_DIR / "kb_chunks.json", 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)
    
    # Merge embeddings
    all_embeddings = np.vstack([existing_embeddings, new_embeddings])
    
    # Add new embeddings to FAISS index
    index.add(new_embeddings)
    faiss.write_index(index, str(DATA_DIR / "faiss_normalized.index"))
    
    # Save merged embeddings
    embeddings_data = {
        'model': EMBEDDING_MODEL,
        'dimensions': int(all_embeddings.shape[1]),
        'count': len(all_embeddings),
        'normalized': True,
        'embeddings': all_embeddings.tolist()
    }
    with open(DATA_DIR / "kb_embeddings.json", 'w') as f:
        json.dump(embeddings_data, f, indent=2)
    
    print(f"✓ Merged successfully:")
    print(f"  Total chunks: {len(all_chunks)}")
    print(f"  Total embeddings: {len(all_embeddings)}")
    print(f"  FAISS vectors: {index.ntotal}")
    
    return len(all_chunks), len(all_embeddings)

def update_metadata(api_chunks_count, total_chunks, total_embeddings):
    """Update KB metadata"""
    print("📊 Updating metadata...")
    
    # Load existing metadata
    metadata_file = DATA_DIR / "kb_metadata.json"
    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
    else:
        metadata = {}
    
    # Add API integration info
    metadata['last_api_update'] = datetime.now().isoformat()
    metadata['api_chunks_added'] = api_chunks_count
    metadata['total_chunks'] = total_chunks
    metadata['total_embeddings'] = total_embeddings
    
    # Track API updates
    if 'api_updates' not in metadata:
        metadata['api_updates'] = []
    
    metadata['api_updates'].append({
        'timestamp': datetime.now().isoformat(),
        'chunks_added': api_chunks_count,
        'total_chunks_after': total_chunks
    })
    
    # Save updated metadata
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print("✓ Metadata updated")

# ============================================================================
# MAIN INTEGRATION FUNCTION
# ============================================================================
def integrate_api_data():
    """Main function to integrate API data into existing KB"""
    print("=" * 70)
    print("🚀 INTEGRATING API DATA INTO EXISTING KB")
    print("=" * 70)
    print()
    
    try:
        # Check if KB exists
        if not (DATA_DIR / "kb_chunks.json").exists():
            print("❌ No existing KB found! Please build your KB first.")
            return False
        
        # Create backup
        backup_dir = backup_existing_files()
        
        # Step 1: Fetch API data
        api_data = fetch_api_data()
        if not api_data:
            print("❌ Failed to fetch API data")
            return False
        
        # Step 2: Create documents
        documents = create_documents_from_api(api_data)
        if not documents:
            print("❌ No documents created from API data")
            return False
        
        # Save documents for reference
        with open(DATA_DIR / "api_documents.json", 'w') as f:
            json.dump(documents, f, indent=2, ensure_ascii=False)
        
        # Step 3: Create chunks
        chunks = create_chunks_from_documents(documents)
        
        # Save API chunks separately for reference
        with open(DATA_DIR / "api_chunks.json", 'w') as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)
        
        # Step 4: Generate embeddings
        embeddings = generate_embeddings(chunks)
        
        # Step 5: Merge with existing KB
        total_chunks, total_embeddings = merge_with_existing_kb(chunks, embeddings)
        
        # Step 6: Update metadata
        update_metadata(len(chunks), total_chunks, total_embeddings)
        
        print()
        print("=" * 70)
        print("✅ API DATA INTEGRATION COMPLETE!")
        print("=" * 70)
        print(f"📊 Added {len(chunks)} new chunks from API data")
        print(f"💾 Backup saved to: {backup_dir}")
        print(f"🎯 Your LangGraph chatbot can now access the API data!")
        print()
        
        return True
        
    except Exception as e:
        print(f"\n❌ Integration failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Offer to restore from backup
        print("\n⚠️ Would you like to restore from backup? (y/n): ", end="")
        if input().lower() == 'y':
            restore_from_backup(backup_dir)
        
        return False

def restore_from_backup(backup_dir):
    """Restore KB from backup"""
    import shutil
    
    print("🔄 Restoring from backup...")
    
    files = ["kb_chunks.json", "kb_embeddings.json", "faiss_normalized.index", "kb_metadata.json"]
    
    for filename in files:
        src = backup_dir / filename
        dst = DATA_DIR / filename
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  ✓ Restored {filename}")
    
    print("✓ Restoration complete")

# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    import sys
    
    print()
    
    # Check if Ollama is running
    try:
        ollama.list()
        print("✓ Ollama is running\n")
    except Exception:
        print("❌ Ollama is not running!")
        print("Please start Ollama and ensure 'nomic-embed-text' model is available")
        print("Run: ollama pull nomic-embed-text")
        sys.exit(1)
    
    # Check if data directory exists
    if not DATA_DIR.exists():
        print(f"❌ Data directory '{DATA_DIR}' not found!")
        sys.exit(1)
    
    # Run integration
    success = integrate_api_data()
    
    if success:
        print("🎉 You can now use your LangGraph chatbot with the enhanced KB!")
        print("   The API data has been seamlessly integrated.")
    else:
        print("😔 Integration failed. Please check the errors above.")
        sys.exit(1)