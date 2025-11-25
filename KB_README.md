# 🚀 Complete KB Builder: Ollama + FAISS

**Single script to build production-ready knowledge base - 100% FREE!**

## ✨ Features

✅ **FREE embeddings** (Ollama - runs locally)  
✅ **FAISS with normalization** (optimal for cosine similarity)  
✅ **Handles multiple pages** (sitemap or list)  
✅ **Production-ready** (error handling, retries, batching)  
✅ **All outputs saved separately** (scraped, chunks, embeddings, FAISS index)

---

## 📦 Install

```bash
# Python packages
pip install requests beautifulsoup4 faiss-cpu numpy ollama

# Ollama
# 1. Download: https://ollama.com/download
# 2. Install embedding model:
ollama pull nomic-embed-text
```

---

## ⚙️ Setup

Edit `build_complete_kb.py` - top of file:

```python
BASE_URL = "https://your-website.com"

PAGES_TO_SCRAPE = [
    f"{BASE_URL}/about",
    f"{BASE_URL}/products",
    f"{BASE_URL}/pricing",
    # Add your pages
]
```

---

## 🏃 Run

```bash
python build_complete_kb.py
```

**Output:**
```
data/
├── scraped_pages.json          # Raw scraped
├── kb_chunks.json              # Chunked content
├── kb_embeddings.json          # Normalized embeddings
├── faiss_normalized.index      # FAISS index (ready to use)
└── kb_metadata.json            # Statistics
```

---

## 📊 What You Get

| File | Contains | Use For |
|------|----------|---------|
| `scraped_pages.json` | Raw pages | Backup, re-chunking |
| `kb_chunks.json` | Chunks + metadata | Reading sources |
| `kb_embeddings.json` | Normalized vectors | Alternative search |
| `faiss_normalized.index` | FAISS index | **Fast search** ⭐ |
| `kb_metadata.json` | Build stats | Tracking |

---

## 🎯 Why This Setup?

### Ollama (FREE!)
- ✅ Runs locally
- ✅ No API costs
- ✅ `nomic-embed-text` - best free model for retrieval
- ✅ 768 dimensions (smaller, faster than OpenAI)

### FAISS with Normalization
- ✅ Vectors normalized for cosine similarity
- ✅ `IndexFlatIP` - optimal for normalized vectors
- ✅ Ready for production use
- ✅ Handles 100K+ chunks easily

---

## 💡 Using in Your Chatbot

```python
import faiss
import json
import numpy as np
import ollama

# Load FAISS index (one-time)
index = faiss.read_index('data/faiss_normalized.index')

# Load chunks
with open('data/kb_chunks.json', 'r') as f:
    chunks = json.load(f)

def search(query: str, top_k=3):
    # Get query embedding
    response = ollama.embeddings(
        model="nomic-embed-text",
        prompt=query
    )
    query_emb = np.array([response['embedding']]).astype('float32')
    
    # Normalize query (CRITICAL!)
    faiss.normalize_L2(query_emb)
    
    # Search FAISS
    scores, indices = index.search(query_emb, top_k)
    
    # Return results
    results = []
    for i, idx in enumerate(indices[0]):
        chunk = chunks[idx].copy()
        chunk['score'] = float(scores[0][i])
        results.append(chunk)
    
    return results

# Use it
results = search("What are your pricing plans?")
for r in results:
    print(f"Score: {r['score']:.3f}")
    print(f"Source: {r['page_title']}")
    print(f"Text: {r['chunk_text'][:100]}...")
    print()
```

---

## 🎓 Key Points

1. **Embeddings are normalized** - ready for cosine similarity
2. **FAISS uses IndexFlatIP** - optimized for normalized vectors
3. **Always normalize query** - critical for correct results
4. **FREE** - No OpenAI costs!
5. **Handles scale** - 100K+ chunks no problem

---

## 🔧 Advanced Options

### Use Sitemap
```python
USE_SITEMAP = True
SITEMAP_URL = "https://yoursite.com/sitemap.xml"
```

### Different Model
```python
EMBEDDING_MODEL = "mxbai-embed-large"  # More accurate, slower
# or
EMBEDDING_MODEL = "all-minilm"  # Faster, smaller
```

### Adjust Chunking
```python
CHUNK_SIZE = 1000      # Larger chunks
CHUNK_OVERLAP = 150    # More overlap
```

---

## 💰 Cost

**$0.00 - Completely FREE!**

Ollama runs locally, no API costs ever.

---

## 🎉 You're Ready!

Your knowledge base is production-ready and optimized for retrieval! 🚀
