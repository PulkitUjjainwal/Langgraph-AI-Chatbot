"""
KB Builder: Ollama + FAISS - WORKING VERSION
Fixed all Ollama API compatibility issues
"""
import json, os, time, hashlib
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import numpy as np
import faiss
import ollama

# ============================================================================
# CONFIGURATION
# ============================================================================
class Config:
    BASE_URL="https://www.exportgenius.in/"
    PAGES_TO_SCRAPE=[
        f"{BASE_URL}/company/global-trade-data.php",
        f"{BASE_URL}/about-us/product-and-services.php",
        f"{BASE_URL}/company/api.php",
        f"{BASE_URL}/export-import-trade-data/",
        f"{BASE_URL}/countries-covered.php",
        f"{BASE_URL}/search-live-data.php",
        f"{BASE_URL}/about-us/advantages-of-our-data-report.php",
        f"{BASE_URL}/plan-and-pricing.php",
        f"{BASE_URL}/company/about-us.php",
        f"{BASE_URL}/about-us/product-and-services.php",
        # f"{BASE_URL}/company/api.php"
        f"{BASE_URL}/countries-covered.php",
        f"{BASE_URL}/company/career.php",
        f"{BASE_URL}/about-us/why-choose-us.php",
        f"{BASE_URL}/company/clients.php",
        f"{BASE_URL}/blog/",
        f"{BASE_URL}/faq.php",
        f"{BASE_URL}/company/contact-us.php",
        f"{BASE_URL}"
        ]
    USE_SITEMAP = False
    SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
    DATA_DIR = Path("data")
    SCRAPED_FILE = DATA_DIR / "scraped_pages.json"
    CHUNKS_FILE = DATA_DIR / "kb_chunks.json"
    EMBEDDINGS_FILE = DATA_DIR / "kb_embeddings.json"
    FAISS_INDEX_FILE = DATA_DIR / "faiss_normalized.index"
    METADATA_FILE = DATA_DIR / "kb_metadata.json"
    CHUNK_SIZE = 800
    CHUNK_OVERLAP = 100
    MIN_CHUNK_SIZE = 100
    EMBEDDING_MODEL = "nomic-embed-text"
    BATCH_SIZE = 50
    DELAY_BETWEEN_BATCHES = 0.5
    MAX_RETRIES = 3
    
    @classmethod
    def ensure_directories(cls):
        cls.DATA_DIR.mkdir(exist_ok=True)

# ============================================================================
# SCRAPER
# ============================================================================
class WebsiteScraper:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    def scrape_urls(self, urls):
        documents = []
        print(f"📄 Scraping {len(urls)} pages...\n")
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] {url}")
            doc = self.scrape_page(url)
            if doc:
                documents.append(doc)
                print(f"  ✓ {doc['word_count']} words")
            else:
                print(f"  ✗ Skipped")
            time.sleep(0.5)
        return documents
    
    def scrape_sitemap(self, sitemap_url):
        print(f"📄 Fetching sitemap: {sitemap_url}")
        response = self.session.get(sitemap_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'xml')
        urls = [loc.text for loc in soup.find_all('loc')]
        print(f"✓ Found {len(urls)} URLs\n")
        return self.scrape_urls(urls)
    
    def scrape_page(self, url):
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            for element in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                element.decompose()
            
            title = ''
            if soup.find('h1'):
                title = soup.find('h1').get_text(strip=True)
            elif soup.find('title'):
                title = soup.find('title').get_text(strip=True)
            else:
                title = 'Untitled'
            
            content = ''
            for selector in ['article', 'main', '[role="main"]', '.content', 'body']:
                element = None
                if selector.startswith('['):
                    attr, value = selector[1:-1].split('=')
                    value = value.strip('"')
                    element = soup.find(attrs={attr: value})
                elif selector.startswith('.'):
                    element = soup.find(class_=selector[1:])
                else:
                    element = soup.find(selector)
                
                if element:
                    text = element.get_text(separator=' ', strip=True)
                    if len(text) > 100:
                        content = ' '.join(text.split())
                        break
            
            if not content or len(content) < 100:
                return None
            
            return {
                'id': hashlib.md5(url.encode()).hexdigest()[:16],
                'url': url,
                'title': title,
                'content': content,
                'word_count': len(content.split()),
                'scraped_at': datetime.now().isoformat()
            }
        except Exception as e:
            print(f"  Error: {e}")
            return None

# ============================================================================
# CHUNKER
# ============================================================================
class TextChunker:
    def __init__(self, chunk_size=Config.CHUNK_SIZE, overlap=Config.CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def chunk_documents(self, documents):
        all_chunks = []
        print("✂️  Chunking documents...\n")
        for doc_idx, doc in enumerate(documents, 1):
            content = doc.get('content', '')
            if len(content) < Config.MIN_CHUNK_SIZE:
                continue
            chunks = self._chunk_text(content)
            print(f"  {doc_idx}. {len(chunks)} chunks - {doc['title'][:60]}")
            for idx, text in enumerate(chunks):
                all_chunks.append({
                    'chunk_id': f"{doc['id']}_chunk_{idx}",
                    'chunk_index': idx,
                    'total_chunks': len(chunks),
                    'chunk_text': text,
                    'char_count': len(text),
                    'word_count': len(text.split()),
                    'source_url': doc['url'],
                    'page_title': doc['title'],
                    'page_id': doc['id'],
                    'scraped_at': doc['scraped_at'],
                    'chunked_at': datetime.now().isoformat()
                })
        return all_chunks
    
    def _chunk_text(self, text):
        sentences = self._split_sentences(text)
        chunks = []
        current = []
        current_len = 0
        for sent in sentences:
            if current_len + len(sent) > self.chunk_size and current:
                chunks.append(' '.join(current))
                overlap_sents = []
                overlap_len = 0
                for s in reversed(current):
                    if overlap_len + len(s) <= self.overlap:
                        overlap_sents.insert(0, s)
                        overlap_len += len(s)
                    else:
                        break
                current = overlap_sents + [sent]
                current_len = sum(len(s) for s in current)
            else:
                current.append(sent)
                current_len += len(sent)
        if current and len(' '.join(current)) >= Config.MIN_CHUNK_SIZE:
            chunks.append(' '.join(current))
        return chunks
    
    def _split_sentences(self, text):
        text = text.replace('\n\n', '. ').replace('\n', ' ')
        for delim in ['. ', '! ', '? ']:
            text = text.replace(delim, delim + '||SPLIT||')
        return [s.strip() for s in text.split('||SPLIT||') if s.strip() and len(s) > 10]

# ============================================================================
# EMBEDDING GENERATOR - FIXED
# ============================================================================
class OllamaEmbeddingGenerator:
    def __init__(self, model=Config.EMBEDDING_MODEL):
        self.model = model
        self.total_chunks = 0
        
        # Test connection
        try:
            ollama.list()
            print(f"✓ Ollama connected")
        except Exception as e:
            raise Exception(
                f"Ollama not running:\n"
                f"  1. Download: https://ollama.com/download\n"
                f"  2. Run: ollama pull {model}\n"
                f"  Error: {e}"
            )
        
        # Check if model exists - PROPERLY FIXED
        try:
            response = ollama.list()
            
            # Extract model names - handle all formats
            model_names = []
            if isinstance(response, dict):
                if 'models' in response:
                    for m in response['models']:
                        if isinstance(m, dict):
                            name = m.get('name', m.get('model', ''))
                            if name:
                                model_names.append(name)
                        elif isinstance(m, str):
                            model_names.append(m)
            elif isinstance(response, list):
                for m in response:
                    if isinstance(m, dict):
                        name = m.get('name', m.get('model', ''))
                        if name:
                            model_names.append(name)
                    elif isinstance(m, str):
                        model_names.append(m)
            
            # Check if our model is in the list
            model_found = any(self.model in str(name) for name in model_names)
            
            if not model_found:
                print(f"⚠️  Model {self.model} not found. Pulling...")
                ollama.pull(self.model)
                print(f"✓ Downloaded {self.model}")
        except Exception as e:
            print(f"⚠️  Could not verify model (will try anyway): {e}")
    
    def create_embeddings(self, texts):
        all_embeddings = []
        total_batches = (len(texts) + Config.BATCH_SIZE - 1) // Config.BATCH_SIZE
        print(f"🧠 Generating embeddings with {self.model}...\n")
        
        for batch_num, i in enumerate(range(0, len(texts), Config.BATCH_SIZE), 1):
            batch = texts[i:i + Config.BATCH_SIZE]
            print(f"  Batch {batch_num}/{total_batches} ({len(batch)} chunks)...", end='')
            
            for attempt in range(Config.MAX_RETRIES):
                try:
                    batch_embeddings = []
                    for text in batch:
                        response = ollama.embeddings(model=self.model, prompt=text)
                        batch_embeddings.append(response['embedding'])
                    
                    all_embeddings.extend(batch_embeddings)
                    self.total_chunks += len(batch)
                    print(" ✓")
                    break
                except Exception as e:
                    if attempt == Config.MAX_RETRIES - 1:
                        raise
                    print(f" ⚠️  Retry {attempt + 1}")
                    time.sleep(2 * (attempt + 1))
            
            if i + Config.BATCH_SIZE < len(texts):
                time.sleep(Config.DELAY_BETWEEN_BATCHES)
        
        return np.array(all_embeddings, dtype=np.float32)

# ============================================================================
# FAISS BUILDER
# ============================================================================
class FAISSIndexBuilder:
    @staticmethod
    def build_normalized_index(embeddings):
        print("🔧 Building FAISS index (normalized)...")
        embeddings = embeddings.astype(np.float32)
        dimension = embeddings.shape[1]
        num_vectors = embeddings.shape[0]
        faiss.normalize_L2(embeddings)
        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings)
        print(f"  ✓ Index: {num_vectors} vectors, {dimension} dims")
        print(f"  ✓ Normalized for optimal retrieval")
        return index, embeddings

# ============================================================================
# MAIN BUILDER
# ============================================================================
class KnowledgeBaseBuilder:
    def __init__(self):
        Config.ensure_directories()
        self.start_time = None
        self.end_time = None
    
    def build(self):
        self.start_time = datetime.now()
        print("=" * 70)
        print("🚀 KB BUILDER: Ollama + FAISS")
        print("=" * 70)
        print()
        
        # Scrape
        print("📂 Step 1: Scraping...\n")
        scraper = WebsiteScraper(Config.BASE_URL)
        if Config.USE_SITEMAP:
            documents = scraper.scrape_sitemap(Config.SITEMAP_URL)
        else:
            documents = scraper.scrape_urls(Config.PAGES_TO_SCRAPE)
        
        if not documents:
            raise Exception("No documents scraped!")
        
        print(f"\n✓ Scraped {len(documents)} pages\n")
        with open(Config.SCRAPED_FILE, 'w', encoding='utf-8') as f:
            json.dump(documents, f, indent=2, ensure_ascii=False)
        print(f"💾 {Config.SCRAPED_FILE}\n")
        
        # Chunk
        chunker = TextChunker()
        chunks = chunker.chunk_documents(documents)
        if not chunks:
            raise Exception("No chunks created!")
        
        print(f"\n✓ Created {len(chunks)} chunks\n")
        with open(Config.CHUNKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)
        print(f"💾 {Config.CHUNKS_FILE}\n")
        
        # Embed
        embedder = OllamaEmbeddingGenerator()
        texts = [c['chunk_text'] for c in chunks]
        embeddings = embedder.create_embeddings(texts)
        print(f"\n✓ Generated {len(embeddings)} embeddings")
        print(f"✓ Dimensions: {embeddings.shape[1]}\n")
        
        # FAISS
        index, normalized_embeddings = FAISSIndexBuilder.build_normalized_index(embeddings)
        faiss.write_index(index, str(Config.FAISS_INDEX_FILE))
        print(f"💾 {Config.FAISS_INDEX_FILE}\n")
        
        # Save embeddings
        embeddings_data = {
            'model': Config.EMBEDDING_MODEL,
            'dimensions': int(embeddings.shape[1]),
            'count': len(embeddings),
            'normalized': True,
            'embeddings': normalized_embeddings.tolist()
        }
        with open(Config.EMBEDDINGS_FILE, 'w') as f:
            json.dump(embeddings_data, f, indent=2)
        print(f"💾 {Config.EMBEDDINGS_FILE}\n")
        
        # Metadata
        self.end_time = datetime.now()
        metadata = self._gen_metadata(documents, chunks, embeddings)
        with open(Config.METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"💾 {Config.METADATA_FILE}\n")
        
        # Summary
        print("=" * 70)
        print("✅ BUILD COMPLETE!")
        print("=" * 70)
        print()
        print(f"📊 Pages: {metadata['total_documents']}")
        print(f"📦 Chunks: {metadata['total_chunks']}")
        print(f"📝 Words: {metadata['total_words']:,}")
        print(f"🧠 Embeddings: {metadata['embedding_count']} (normalized)")
        print(f"🔧 FAISS: Ready for cosine similarity")
        print(f"💵 Cost: $0.00 (FREE!)")
        print(f"⏱️  Time: {metadata['build_time']}")
        print()
        return metadata
    
    def _gen_metadata(self, docs, chunks, embeddings):
        duration = (self.end_time - self.start_time).total_seconds()
        return {
            'build_timestamp': self.end_time.isoformat(),
            'build_time': f"{duration:.2f}s",
            'total_documents': len(docs),
            'total_chunks': len(chunks),
            'total_words': sum(c['word_count'] for c in chunks),
            'embedding_count': len(chunks),
            'embedding_dimensions': int(embeddings.shape[1]),
            'cost': 0.0,
            'config': {
                'embedding_model': Config.EMBEDDING_MODEL,
                'embeddings_normalized': True,
                'faiss_index_type': 'IndexFlatIP',
                'chunk_size': Config.CHUNK_SIZE
            },
            'output_files': {
                'scraped': str(Config.SCRAPED_FILE),
                'chunks': str(Config.CHUNKS_FILE),
                'embeddings': str(Config.EMBEDDINGS_FILE),
                'faiss_index': str(Config.FAISS_INDEX_FILE),
                'metadata': str(Config.METADATA_FILE)
            }
        }

# ============================================================================
# MAIN
# ============================================================================
def main():
    import sys
    print()
    
    if Config.BASE_URL == "https://your-website.com":
        print("⚠️  Edit Configuration section!\n")
        sys.exit(1)
    
    try:
        ollama.list()
    except Exception:
        print("❌ Ollama not running!\n")
        print("Setup:")
        print("  1. Download: https://ollama.com/download")
        print("  2. Run: ollama pull nomic-embed-text\n")
        sys.exit(1)
    
    try:
        builder = KnowledgeBaseBuilder()
        builder.build()
        print("🎉 Knowledge base ready!\n")
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()