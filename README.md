# Export Genius Trade Data Chatbot - Complete Technical Documentation

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [System Components](#system-components)
3. [Complete Request Flow](#complete-request-flow)
4. [Code-Level Breakdown](#code-level-breakdown)
5. [Redis Integration](#redis-integration)
6. [FIFO Cache Mechanism](#fifo-cache-mechanism)
7. [API Reference](#api-reference)
8. [Setup & Installation](#setup--installation)

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Server                            │
│                     (fastapi_chatbot.py)                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ChatbotManager                              │
│              (Orchestrates entire conversation)                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
         ┌──────────┐  ┌──────────┐  ┌──────────┐
         │ Retrieval│  │ Chatbot  │  │  Tools   │
         │   Node   │  │   Node   │  │   Node   │
         └──────────┘  └──────────┘  └──────────┘
                │             │             │
                ▼             ▼             ▼
         ┌──────────────────────────────────────┐
         │      HybridRetriever                 │
         │  (Static KB + Dynamic Embeddings)    │
         └──────────────────────────────────────┘
                │                    │
                ▼                    ▼
         ┌──────────┐          ┌──────────┐
         │  FAISS   │          │  Redis   │
         │  Index   │          │  Cache   │
         │(Static KB│          │(Dynamic  │
         │379 chunks│          │URLs w/   │
         │         )│          │FIFO)     │
         └──────────┘          └──────────┘
```

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Web Framework** | FastAPI | REST API server |
| **LLM** | Ollama (deepseek-v3.1:671b) | Language model for chat |
| **Embeddings** | Ollama (nomic-embed-text) | Text to vector conversion |
| **Vector DB (Static)** | FAISS | Static knowledge base search |
| **Cache & Memory** | Redis | Dynamic embeddings + conversation history |
| **Graph Framework** | LangGraph | Multi-node conversation flow |
| **Web Scraping** | BeautifulSoup4 | Dynamic content extraction |

---

## System Components

### 1. Configuration (`Config` class)

**File**: `fastapi_chatbot.py:67-98`

**Purpose**: Central configuration for all system parameters

```python
class Config:
    # Data Files
    DATA_DIR = Path("data")
    CHUNKS_FILE = DATA_DIR / "kb_chunks.json"
    FAISS_INDEX_FILE = DATA_DIR / "faiss_normalized.index"

    # Models
    EMBEDDING_MODEL = "nomic-embed-text"          # For text → vectors
    LLM_MODEL = "deepseek-v3.1:671b-cloud"        # For chat responses

    # Retrieval Parameters
    TOP_K_RESULTS = 5                             # How many chunks to retrieve
    MAX_CHUNK_CHARS = 800                         # Max size of each chunk

    # LLM Generation Parameters
    TEMPERATURE = 0.2                             # Randomness (0 = deterministic)
    TOP_P = 0.8                                   # Nucleus sampling threshold
    TOP_K = 40                                    # Top-k sampling
    NUM_PREDICT = 650                             # Max tokens to generate
    NUM_CTX = 3400                                # Context window size

    # Redis Configuration
    REDIS_HOST = "localhost"
    REDIS_PORT = 6379
    REDIS_DB = 0
    REDIS_TTL_DAYS = 7                            # How long to keep sessions
```

**Key Parameters Explained**:
- `TOP_K_RESULTS = 5`: Retrieves top 5 most relevant chunks from knowledge base
- `TEMPERATURE = 0.2`: Low temperature = more focused, factual responses
- `NUM_CTX = 3400`: Large context window to fit conversation history + retrieved chunks
- `REDIS_TTL_DAYS = 7`: Sessions expire after 7 days of inactivity

---

### 2. API Models (Pydantic)

**File**: `fastapi_chatbot.py:105-160`

#### ChatRequest
```python
class ChatRequest(BaseModel):
    message: str                              # User's question
    session_id: str                           # Unique session identifier
    dynamic_url: Optional[str] = None         # Optional: URL to scrape
    ip_address: Optional[str] = None          # Optional: User IP (for logging)
```

#### ChatResponse
```python
class ChatResponse(BaseModel):
    response: str                             # Chatbot's answer
    session_id: str                           # Session ID (for tracking)
    processing_time: float                    # Time taken (seconds)
    sources_used: List[str]                   # Which sources were used
    metadata: Dict[str, Any]                  # Additional info
```

---

### 3. PerformanceMonitor

**File**: `fastapi_chatbot.py:166-212`

**Purpose**: Track and log performance metrics

```python
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {}                     # {metric_name: [values]}

    def log_metric(self, metric_name: str, value: float):
        """Record a performance metric"""
        if metric_name not in self.metrics:
            self.metrics[metric_name] = []
        self.metrics[metric_name].append(value)
```

**Usage Example**:
```python
monitor = PerformanceMonitor()
monitor.log_metric("retrieval_time", 0.234)
monitor.log_metric("llm_inference_time", 5.678)
monitor.print_summary()  # Print averages
```

---

### 4. AgentState (TypedDict)

**File**: `fastapi_chatbot.py:215-227`

**Purpose**: State object passed between LangGraph nodes

```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]  # Conversation messages
    next_agent: str                                           # Which node to go to next
    retrieved_context: str                                    # Context from retrieval
    original_query: str                                       # User's original question
    use_cache: bool                                           # Use cached response?
    retrieved_chunks: List[Dict[str, Any]]                    # Raw chunks retrieved
    start_time: float                                         # Request start timestamp
    session_id: str                                           # Session identifier
    dynamic_url: str                                          # Dynamic URL (if any)
```

**Why TypedDict?**
- Provides type hints for state object
- LangGraph passes this state through all nodes
- Each node can read/modify state before passing to next node

---

### 5. DynamicContentManager

**File**: `fastapi_chatbot.py:230-374`

**Purpose**: Fetch, process, and cache dynamic URL content

#### Key Methods:

##### `fetch_and_embed(session_id, url)`
**Line**: 235-302

**Flow**:
```
1. Hash URL → Generate 16-char hash
2. Check Redis cache → If exists, return cached embeddings
3. If not cached:
   a. Fetch content from URL (web scraper / API)
   b. Clean and chunk content (800 chars per chunk, 100 char overlap)
   c. Generate embeddings using Ollama (nomic-embed-text)
   d. Normalize embeddings (L2 normalization)
   e. Save to Redis with FIFO management
4. Return (embeddings_array, chunks)
```

**Code Breakdown**:
```python
def fetch_and_embed(self, session_id: str, url: str) -> tuple[np.ndarray, List[Dict]]:
    # Step 1: Generate URL hash for caching
    url_hash = hashlib.md5(url.encode()).hexdigest()[:16]

    # Step 2: Check Redis cache
    cached_data = self.redis.get_embeddings(session_id, url)
    if cached_data:
        return cached_data  # Cache HIT - return immediately

    # Step 3a: Fetch content from URL
    content = self._fetch_content(url)  # Web scraper or API

    # Step 3b: Chunk content into smaller pieces
    chunks = self._chunk_content(content, chunk_size=800, overlap=100)

    # Step 3c: Generate embeddings for each chunk
    embeddings = []
    for chunk in chunks:
        response = ollama.embeddings(
            model=Config.EMBEDDING_MODEL,
            prompt=chunk["chunk_text"]
        )
        embeddings.append(response["embedding"])

    embeddings_array = np.array(embeddings, dtype='float32')

    # Step 3d: Normalize embeddings (required for FAISS)
    faiss.normalize_L2(embeddings_array)

    # Step 3e: Save to Redis with FIFO management
    self.redis.save_embeddings(
        session_id=session_id,
        dynamic_url=url,
        embeddings=embeddings_array,
        chunks=chunks
    )  # ← This triggers FIFO if session has 10+ URLs

    return embeddings_array, chunks
```

##### `_chunk_content(content, chunk_size=800, overlap=100)`
**Line**: 310-325

**Purpose**: Split large text into overlapping chunks

**Why Overlapping?**
- Prevents context loss at chunk boundaries
- Example: "Export Genius provides | trade data for 100+ countries"
  - Without overlap: Context split awkwardly
  - With overlap: Both chunks contain full sentence

**Algorithm**:
```python
chunks = []
start = 0
while start < len(content):
    end = start + chunk_size
    chunk_text = content[start:end]

    chunks.append({
        "chunk_text": chunk_text,
        "chunk_id": len(chunks),
        "start_pos": start,
        "end_pos": end
    })

    start += (chunk_size - overlap)  # Move forward, keeping overlap
```

---

### 6. KnowledgeBaseRetriever

**File**: `fastapi_chatbot.py:376-449`

**Purpose**: Retrieve relevant chunks from static FAISS knowledge base

#### Initialization (Line 379-397):
```python
def __init__(self):
    # Load FAISS index (pre-built from kb_chunks.json)
    self.index = faiss.read_index(str(Config.FAISS_INDEX_FILE))

    # Load chunk metadata
    with open(Config.CHUNKS_FILE, 'r', encoding='utf-8') as f:
        self.chunks = json.load(f)

    print(f"[OK] Knowledge Base loaded: {len(self.chunks)} chunks")
```

**FAISS Index Structure**:
- Type: IndexFlatIP (Inner Product similarity)
- Dimension: 768 (nomic-embed-text embedding size)
- Contains: 379 pre-computed embeddings from static knowledge base

#### `retrieve(query, top_k=5)` (Line 398-427):

**Flow**:
```
1. Generate query embedding using Ollama
2. Normalize query embedding (L2 normalization)
3. Search FAISS index for top_k nearest neighbors
4. Return matching chunks with scores
```

**Code**:
```python
def retrieve(self, query: str, top_k: int = 5) -> list:
    # Step 1: Generate query embedding
    response = ollama.embeddings(
        model=Config.EMBEDDING_MODEL,
        prompt=query
    )
    query_embedding = np.array([response["embedding"]], dtype='float32')

    # Step 2: Normalize (required for cosine similarity via inner product)
    faiss.normalize_L2(query_embedding)

    # Step 3: Search FAISS index
    scores, indices = self.index.search(query_embedding, top_k)

    # Step 4: Retrieve matching chunks
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < len(self.chunks):
            chunk = self.chunks[idx].copy()
            chunk["score"] = float(score)
            results.append(chunk)

    return results
```

**Similarity Score**: Higher = more relevant (range: 0.0 to 1.0)

---

### 7. HybridRetriever

**File**: `fastapi_chatbot.py:451-548`

**Purpose**: Combine static KB + dynamic URL embeddings for comprehensive retrieval

#### Architecture:
```
┌─────────────────────────────────────────┐
│         HybridRetriever                 │
│                                         │
│  ┌─────────────┐    ┌────────────────┐ │
│  │   Static    │    │    Dynamic     │ │
│  │   FAISS     │    │    Redis       │ │
│  │   KB        │    │   Embeddings   │ │
│  │ (379 chunks)│    │ (Session URLs) │ │
│  └─────────────┘    └────────────────┘ │
│         │                   │           │
│         └────────┬──────────┘           │
│                  ▼                      │
│          ┌──────────────┐               │
│          │ Merge &      │               │
│          │ Deduplicate  │               │
│          └──────────────┘               │
└─────────────────────────────────────────┘
```

#### `retrieve(query, session_id, dynamic_url, top_k=5)` (Line 473-520):

**Flow**:
```
1. Always retrieve from static KB (FAISS)
2. If dynamic_url provided:
   a. Fetch and embed dynamic content
   b. Search dynamic embeddings
   c. Merge with static results
3. Deduplicate and sort by relevance
4. Return top_k chunks
```

**Code with Explanation**:
```python
def retrieve(self, query: str, session_id: str, dynamic_url: str = "", top_k: int = 5):
    all_results = []

    # Part 1: Static KB Retrieval (ALWAYS)
    print(f"[RETRIEVAL] Static KB search for: '{query}'")
    kb_results = self.kb_retriever.retrieve(query, top_k=top_k)

    for result in kb_results:
        result["source_type"] = "static_kb"  # Tag source
        all_results.append(result)

    print(f"[RETRIEVAL] Static KB: {len(kb_results)} chunks (scores: {[r['score']:.3f for r in kb_results]})")

    # Part 2: Dynamic URL Retrieval (CONDITIONAL)
    if dynamic_url:
        print(f"[RETRIEVAL] Dynamic URL search: {dynamic_url}")

        # 2a. Fetch and embed dynamic content
        embeddings, chunks = self.dynamic_manager.fetch_and_embed(session_id, dynamic_url)

        # 2b. Search dynamic embeddings
        query_response = ollama.embeddings(model=Config.EMBEDDING_MODEL, prompt=query)
        query_embedding = np.array([query_response["embedding"]], dtype='float32')
        faiss.normalize_L2(query_embedding)

        # Create temporary FAISS index for dynamic embeddings
        dynamic_index = faiss.IndexFlatIP(embeddings.shape[1])
        dynamic_index.add(embeddings)

        # Search dynamic index
        scores, indices = dynamic_index.search(query_embedding, top_k)

        # Add dynamic results
        for score, idx in zip(scores[0], indices[0]):
            if idx < len(chunks):
                chunk = chunks[idx].copy()
                chunk["score"] = float(score)
                chunk["source_type"] = "dynamic_url"
                chunk["dynamic_url"] = dynamic_url
                all_results.append(chunk)

        print(f"[RETRIEVAL] Dynamic URL: {len(indices[0])} chunks")

    # Part 3: Merge, deduplicate, and sort
    all_results.sort(key=lambda x: x["score"], reverse=True)  # Highest score first

    # Deduplicate by chunk_text
    seen_texts = set()
    unique_results = []
    for result in all_results:
        text = result.get("chunk_text", "")
        if text not in seen_texts:
            seen_texts.add(text)
            unique_results.append(result)

    return unique_results[:top_k]  # Return top_k after deduplication
```

**Key Features**:
1. **Always includes static KB**: Ensures baseline knowledge
2. **Dynamic content is additive**: Augments static knowledge
3. **Score-based ranking**: Most relevant chunks bubble to top
4. **Deduplication**: Prevents duplicate content in context

---

### 8. LangGraph Nodes

#### Retrieval Node (Line 619-645)

**Purpose**: Fetch relevant context based on query type

```python
def retrieval_node(state: AgentState) -> AgentState:
    query = state["original_query"]
    session_id = state["session_id"]
    dynamic_url = state["dynamic_url"]

    # Determine if static KB is needed
    query_type = classify_query_type(query)
    needs_kb = query_type in ["general_trade_info", "feature_inquiry", "mixed"]

    # Retrieve chunks
    if needs_kb or dynamic_url:
        chunks = hybrid_retriever.retrieve(
            query=query,
            session_id=session_id,
            dynamic_url=dynamic_url,
            top_k=Config.TOP_K_RESULTS
        )
        context = "\n".join([c["chunk_text"] for c in chunks])
        state["retrieved_context"] = context
        state["retrieved_chunks"] = chunks

    return state
```

**Query Type Classification** (Line 573-603):
- `greeting`: "Hi", "Hello" → No retrieval needed
- `general_trade_info`: "What is Export Genius?" → Static KB only
- `company_specific`: "Tell me about Tesla" → Dynamic URL if provided
- `feature_inquiry`: "How do I use API?" → Static KB
- `data_request`: "Show me India exports" → Both static + dynamic
- `mixed`: Questions combining multiple types

#### Chatbot Node (Line 661-811)

**Purpose**: Generate response using LLM

**Flow**:
```
1. Build system prompt with retrieved context
2. Send conversation history + context to LLM
3. LLM generates response
4. Update conversation history
5. Save checkpoint to Redis
```

**System Prompt Structure**:
```python
system_prompt = f"""You are a specialized Export Genius trade data assistant.

CONTEXT FROM KNOWLEDGE BASE:
{retrieved_context}

INSTRUCTIONS:
1. Answer based on the provided context
2. If context doesn't contain answer, say so
3. Be concise and factual
4. Cite sources when possible

USER QUERY: {original_query}
"""
```

**LLM Invocation**:
```python
llm = ChatOllama(
    model=Config.LLM_MODEL,
    temperature=Config.TEMPERATURE,
    num_ctx=Config.NUM_CTX,
    num_predict=Config.NUM_PREDICT,
    top_p=Config.TOP_P,
    top_k=Config.TOP_K
)

# Generate response
messages = [SystemMessage(content=system_prompt)] + state["messages"]
response = llm.invoke(messages)

# Update state
state["messages"].append(AIMessage(content=response.content))
return state
```

---

### 9. ChatbotManager

**File**: `fastapi_chatbot.py:813-938`

**Purpose**: Orchestrate entire conversation flow

#### Workflow Creation (Line 825-937):

**LangGraph Workflow**:
```
┌─────────┐
│  START  │
└────┬────┘
     │
     ▼
┌─────────────┐
│  Retrieval  │  ← Fetch context
│    Node     │
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  Chatbot    │  ← Generate response
│    Node     │
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  Tools      │  ← Call tools if needed
│   Node      │  (Optional)
└─────┬───────┘
      │
      ▼
┌─────────┐
│   END   │
└─────────┘
```

**Code**:
```python
def _create_workflow(self):
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("chatbot", chatbot_node)
    workflow.add_node("tools", ToolNode(tools=[fetch_dynamic_trade_data]))

    # Define flow
    workflow.add_edge(START, "retrieval")       # Start → Retrieval
    workflow.add_edge("retrieval", "chatbot")   # Retrieval → Chatbot

    # Conditional: If tools needed, go to tools node, else END
    workflow.add_conditional_edges(
        "chatbot",
        tools_condition,  # Checks if LLM requested tool calls
        {
            "tools": "tools",
            END: END
        }
    )

    workflow.add_edge("tools", "chatbot")  # Tools → Chatbot (for follow-up)

    # Compile with Redis checkpoint saver
    return workflow.compile(checkpointer=self.checkpointer)
```

#### `chat()` Method (Line 848-938):

**Complete Request Processing**:
```python
async def chat(self, message: str, session_id: str, dynamic_url: str = ""):
    start_time = time.time()

    # Step 1: Create thread ID (for LangGraph)
    thread_id = f"session_{session_id}"
    config = {"configurable": {"thread_id": thread_id}}

    # Step 2: Prepare state
    initial_state = {
        "messages": [HumanMessage(content=message)],
        "next_agent": "",
        "retrieved_context": "",
        "original_query": message,
        "use_cache": False,
        "retrieved_chunks": [],
        "start_time": start_time,
        "session_id": session_id,
        "dynamic_url": dynamic_url or ""
    }

    # Step 3: Invoke LangGraph workflow
    result = self.app.invoke(initial_state, config=config)

    # Step 4: Extract response
    response_content = result["messages"][-1].content

    # Step 5: Determine sources used
    sources_used = []
    if result.get("retrieved_chunks"):
        for chunk in result["retrieved_chunks"]:
            source_type = chunk.get("source_type", "unknown")
            if source_type == "static_kb":
                sources_used.append("Static Knowledge Base")
            elif source_type == "dynamic_url":
                sources_used.append(f"Dynamic URL: {chunk.get('dynamic_url', 'unknown')}")

    # Step 6: Calculate processing time
    processing_time = time.time() - start_time

    # Step 7: Update session metadata in Redis
    self.redis.update_session_meta(session_id, {
        "last_query": message,
        "last_response_time": processing_time,
        "total_queries": self.redis.get_session_meta(session_id).get("total_queries", 0) + 1
    })

    return response_content, processing_time, list(set(sources_used))
```

---

## Complete Request Flow

### End-to-End Example: "What is Export Genius?"

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. API REQUEST                                                   │
└──────────────────────────────────────────────────────────────────┘
POST /chat
{
  "message": "What is Export Genius?",
  "session_id": "user_123",
  "dynamic_url": null
}
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ 2. FastAPI Endpoint (/chat)                                      │
│    - Validate request                                            │
│    - Extract message, session_id                                 │
│    - Call chatbot_manager.chat()                                 │
└──────────────────────────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ 3. ChatbotManager.chat()                                         │
│    - Create thread_id = "session_user_123"                       │
│    - Prepare initial state                                       │
│    - Invoke LangGraph workflow                                   │
└──────────────────────────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ 4. LangGraph: Retrieval Node                                     │
│    - Classify query type: "general_trade_info"                   │
│    - Call HybridRetriever.retrieve()                             │
└──────────────────────────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ 5. HybridRetriever.retrieve()                                    │
│    A. Static KB Retrieval:                                       │
│       - Generate query embedding                                 │
│       - Search FAISS index (379 chunks)                          │
│       - Return top 5 chunks                                      │
│    B. Dynamic URL: (None in this case)                           │
│       - Skip                                                     │
│    C. Merge and return results                                   │
└──────────────────────────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ 6. Retrieval Node Returns                                        │
│    state["retrieved_context"] = """                              │
│    Export Genius is a comprehensive trade intelligence platform  │
│    that provides global import-export data covering 100+         │
│    countries...                                                  │
│    """                                                           │
│    state["retrieved_chunks"] = [chunk1, chunk2, chunk3, ...]    │
└──────────────────────────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ 7. LangGraph: Chatbot Node                                       │
│    - Build system prompt with context                            │
│    - Send to LLM (deepseek-v3.1:671b)                           │
│    - Wait for response (~5-7 seconds)                            │
└──────────────────────────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ 8. LLM Generates Response                                        │
│    "Export Genius is a comprehensive trade intelligence          │
│     platform that provides detailed import-export data for       │
│     over 100 countries. It offers real-time shipment tracking,   │
│     company profiles, and market analytics..."                   │
└──────────────────────────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ 9. Chatbot Node Returns                                          │
│    - Update state["messages"] with AI response                   │
│    - Save checkpoint to Redis                                    │
│    - Return state                                                │
└──────────────────────────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ 10. ChatbotManager.chat() Completes                              │
│     - Extract response from result["messages"][-1]               │
│     - Calculate processing time                                  │
│     - Determine sources_used: ["Static Knowledge Base"]          │
│     - Update session metadata in Redis                           │
│     - Return (response, processing_time, sources_used)           │
└──────────────────────────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ 11. FastAPI Endpoint Returns                                     │
│     ChatResponse(                                                │
│         response="Export Genius is a comprehensive...",          │
│         session_id="user_123",                                   │
│         processing_time=5.234,                                   │
│         sources_used=["Static Knowledge Base"],                  │
│         metadata={...}                                           │
│     )                                                            │
└──────────────────────────────────────────────────────────────────┘
```

### Timings Breakdown

| Stage | Time (seconds) | Percentage |
|-------|---------------|-----------|
| Request validation | 0.001 | 0.02% |
| Query classification | 0.010 | 0.15% |
| Embedding generation | 0.500 | 7.50% |
| FAISS search | 0.050 | 0.75% |
| Context formatting | 0.020 | 0.30% |
| **LLM inference** | **5.500** | **82.28%** |
| Response formatting | 0.030 | 0.45% |
| Redis save | 0.100 | 1.50% |
| Overhead | 0.473 | 7.05% |
| **Total** | **6.684** | **100%** |

**Bottleneck**: LLM inference (deepseek-v3.1:671b) takes 82% of time.

---

## Redis Integration

### RedisMemoryManager

**File**: `redis_memory.py`

**Purpose**: Manage all Redis operations for sessions, embeddings, and conversation history

### Storage Structure

```
Redis Key Hierarchy:
├── Conversations
│   ├── conv:{thread_id}:history         → Conversation messages (JSON)
│   └── conv:{thread_id}:checkpoint      → LangGraph checkpoint (pickle)
│
├── Embeddings (per session + URL)
│   ├── embed:{session_id}:{url_hash}           → Embeddings array (pickle)
│   ├── embed:{session_id}:{url_hash}:chunks    → Text chunks (JSON)
│   └── embed:{session_id}:{url_hash}:meta      → Metadata (JSON)
│
├── Session Tracking (FIFO)
│   ├── session:{session_id}:urls        → URL tracking list (FIFO, max 10)
│   └── session:{session_id}:meta        → Session metadata (JSON)
│
└── All keys have TTL (default: 7 days)
```

### Key Methods

#### `save_embeddings()` (redis_memory.py:126-208)
**Purpose**: Save embeddings with automatic FIFO management

**Full Implementation**:
```python
def save_embeddings(
    self,
    session_id: str,
    dynamic_url: str,
    embeddings: np.ndarray,
    chunks: List[Dict[str, Any]],
    max_urls: int = 10
):
    """
    Save embeddings to Redis with FIFO cache management.

    When session reaches max_urls capacity:
    1. Identifies oldest URL
    2. Deletes all keys for oldest URL
    3. Removes from tracking list
    4. Adds new URL
    """

    # Generate URL hash (16 chars from MD5)
    url_hash = hashlib.md5(dynamic_url.encode()).hexdigest()[:16]

    # Get current URL tracking list
    list_key = f"session:{session_id}:urls"
    current_urls = [u.decode() for u in self.client.lrange(list_key, 0, -1)]

    # ========================================
    # FIFO CLEANUP LOGIC
    # ========================================
    if len(current_urls) >= max_urls and url_hash not in current_urls:
        # Session at capacity and adding NEW URL
        url_to_remove = current_urls[0]  # Oldest (first in list)

        print(f"  [FIFO] Session at capacity ({max_urls} URLs), removing oldest: {url_to_remove}")

        # Delete all Redis keys for old URL
        keys_to_delete = [
            f"embed:{session_id}:{url_to_remove}",
            f"embed:{session_id}:{url_to_remove}:chunks",
            f"embed:{session_id}:{url_to_remove}:meta"
        ]
        deleted_count = self.client.delete(*keys_to_delete)
        print(f"  [CLEANUP] Deleted {deleted_count} Redis keys")

    # ========================================
    # SAVE NEW EMBEDDINGS
    # ========================================

    # Save embeddings (binary pickle)
    embed_key = f"embed:{session_id}:{url_hash}"
    self.client.setex(
        embed_key,
        self.ttl_seconds,
        pickle.dumps(embeddings)
    )

    # Save chunks (JSON)
    chunks_key = f"embed:{session_id}:{url_hash}:chunks"
    self.client.setex(
        chunks_key,
        self.ttl_seconds,
        json.dumps(chunks)
    )

    # Save metadata (JSON)
    meta_key = f"embed:{session_id}:{url_hash}:meta"
    metadata = {
        "url": dynamic_url,
        "url_hash": url_hash,
        "embedding_shape": embeddings.shape,
        "chunk_count": len(chunks),
        "created_at": datetime.now().isoformat()
    }
    self.client.setex(
        meta_key,
        self.ttl_seconds,
        json.dumps(metadata)
    )

    # ========================================
    # UPDATE URL TRACKING LIST
    # ========================================
    if url_hash not in current_urls:
        # Add to right (newest)
        self.client.rpush(list_key, url_hash)

        # Trim to keep only last max_urls
        self.client.ltrim(list_key, -max_urls, -1)

        # Set TTL on tracking list
        self.client.expire(list_key, self.ttl_seconds)

    print(f"  [CACHE] Embeddings saved: {session_id}/{url_hash}")
    print(f"          Shape: {embeddings.shape}, Chunks: {len(chunks)}")
```

#### `get_embeddings()` (redis_memory.py:210-236)
**Purpose**: Retrieve cached embeddings from Redis

```python
def get_embeddings(self, session_id: str, dynamic_url: str):
    url_hash = hashlib.md5(dynamic_url.encode()).hexdigest()[:16]

    embed_key = f"embed:{session_id}:{url_hash}"
    chunks_key = f"embed:{session_id}:{url_hash}:chunks"

    embed_data = self.client.get(embed_key)
    chunks_data = self.client.get(chunks_key)

    if embed_data and chunks_data:
        embeddings = pickle.loads(embed_data)  # Deserialize numpy array
        chunks = json.loads(chunks_data)       # Deserialize JSON

        print(f"  [CACHE HIT] Loaded: {session_id}/{url_hash}")
        return embeddings, chunks

    return None  # Cache MISS
```

---

## FIFO Cache Mechanism

### How FIFO Works

**Scenario**: User queries 12 different company URLs in one session

```
Request 1-10: Normal operation
┌─────────────────────────────────────────────┐
│ session:user_123:urls                       │
│ [url1, url2, url3, ..., url10]             │
│ Count: 10/10 (AT CAPACITY)                  │
└─────────────────────────────────────────────┘

Request 11: FIFO triggers
┌─────────────────────────────────────────────┐
│ 1. Detect capacity reached (10/10)          │
│ 2. Identify oldest URL: url1                │
│ 3. Delete Redis keys:                       │
│    - embed:user_123:url1                    │
│    - embed:user_123:url1:chunks             │
│    - embed:user_123:url1:meta               │
│ 4. Remove url1 from tracking list           │
│ 5. Add url11 to tracking list               │
│ 6. Save url11 embeddings                    │
└─────────────────────────────────────────────┘

Result:
┌─────────────────────────────────────────────┐
│ session:user_123:urls                       │
│ [url2, url3, ..., url10, url11]            │
│ Count: 10/10 (STILL AT CAPACITY)            │
└─────────────────────────────────────────────┘
```

### Benefits of FIFO

1. **Bounded Memory**: Each session limited to 10 URLs × ~7MB = 70MB max
2. **Automatic Cleanup**: No manual intervention needed
3. **Session Isolation**: Each user has separate cache
4. **Conversation Preserved**: Chat history unaffected by FIFO

### FIFO vs No FIFO

| Metric | Without FIFO | With FIFO (max 10) |
|--------|--------------|-------------------|
| User queries 50 companies | 50 URLs × 7MB = 350MB | 10 URLs × 7MB = 70MB |
| 10 concurrent users | 3.5 GB | 700 MB |
| Memory growth | Unbounded | Bounded |

---

## API Reference

### Endpoints

#### 1. POST /chat
**Purpose**: Send message and get response

**Request**:
```json
{
  "message": "What is Export Genius?",
  "session_id": "user_123",
  "dynamic_url": "https://example.com/company",  // Optional
  "ip_address": "192.168.1.1"                    // Optional
}
```

**Response**:
```json
{
  "response": "Export Genius is a comprehensive trade intelligence platform...",
  "session_id": "user_123",
  "processing_time": 5.234,
  "sources_used": ["Static Knowledge Base"],
  "metadata": {
    "query_type": "general_trade_info",
    "chunks_used": 5,
    "model": "deepseek-v3.1:671b-cloud"
  }
}
```

#### 2. POST /reset
**Purpose**: Clear conversation history for a session

**Request**:
```json
{
  "session_id": "user_123"
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Session reset successfully",
  "session_id": "user_123"
}
```

#### 3. GET /history/{session_id}
**Purpose**: Get conversation history

**Response**:
```json
{
  "session_id": "user_123",
  "messages": [
    {"role": "user", "content": "What is Export Genius?"},
    {"role": "assistant", "content": "Export Genius is..."}
  ],
  "message_count": 2
}
```

#### 4. GET /health
**Purpose**: Check system health

**Response**:
```json
{
  "status": "healthy",
  "kb_chunks": 379,
  "redis_connected": true,
  "active_sessions": 5,
  "model": "deepseek-v3.1:671b-cloud"
}
```

#### 5. GET /redis/stats
**Purpose**: Get Redis statistics

**Response**:
```json
{
  "redis_stats": {
    "conversations": 10,
    "embeddings": 30,
    "sessions": 5,
    "url_tracking_lists": 5,
    "memory_used_mb": 1.23,
    "memory_peak_mb": 1.50
  },
  "status": "healthy"
}
```

---

## Setup & Installation

### Prerequisites
- Python 3.10+
- Redis server (running on localhost:6379)
- Ollama with models:
  - `deepseek-v3.1:671b-cloud`
  - `nomic-embed-text`

### Installation Steps

```bash
# 1. Clone repository
cd "C:\MI Ticket\MI Chat Bot\Scrapper Function"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Verify Redis is running
redis-cli ping  # Should return "PONG"

# 4. Verify Ollama models
ollama list
# Should show:
#   deepseek-v3.1:671b-cloud
#   nomic-embed-text

# 5. Ensure knowledge base files exist
ls data/
#   kb_chunks.json
#   faiss_normalized.index

# 6. Start server
python -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --reload
```

### Testing

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is Export Genius?","session_id":"test_user"}'

# Test with dynamic URL
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Tell me about this company","session_id":"test_user","dynamic_url":"https://example.com/company-123"}'

# Test FIFO cache
python test_fifo_cache.py

# Benchmark performance
python benchmark_performance.py
```

---

## Configuration & Tuning

### Performance Tuning

See `PERFORMANCE_OPTIMIZATION_GUIDE.md` for detailed optimization strategies:
- Switch to faster LLM model (10x speedup)
- Reduce context window (20-30% speedup)
- Implement response caching (instant for repeats)

### FIFO Cache Configuration

**Change max URLs per session**:

Edit `redis_memory.py:132`:
```python
def save_embeddings(..., max_urls: int = 15):  # Change from 10 to 15
```

Or pass custom value:
```python
redis_manager.save_embeddings(
    session_id="user_123",
    dynamic_url="https://...",
    embeddings=embeddings,
    chunks=chunks,
    max_urls=20  # Custom limit for this call
)
```

### Redis TTL

**Change session expiration time**:

Edit `fastapi_chatbot.py:93`:
```python
REDIS_TTL_DAYS = 14  # Sessions expire after 14 days instead of 7
```

---

## Troubleshooting

### Common Issues

#### 1. Redis Connection Failed
```
[ERROR] Redis connection failed: Connection refused
```

**Solution**:
```bash
# Start Redis
redis-server

# Or check if already running
redis-cli ping
```

#### 2. Ollama Model Not Found
```
[ERROR] Model 'deepseek-v3.1:671b-cloud' not found
```

**Solution**:
```bash
# Pull model
ollama pull deepseek-v3.1:671b-cloud
ollama pull nomic-embed-text
```

#### 3. Slow Response Times
```
Average response time: 15+ seconds
```

**Solution**: See `PERFORMANCE_OPTIMIZATION_GUIDE.md` for optimization strategies.

#### 4. FIFO Not Working
```
Session has more than 10 URLs cached
```

**Solution**:
```bash
# Test FIFO mechanism
python test_fifo_cache.py

# Check implementation
python -c "from redis_memory import RedisMemoryManager; rm = RedisMemoryManager(); print(rm.get_session_url_count('your_session_id'))"
```

---

## Architecture Decisions

### Why LangGraph?
- **State management**: Handles conversation state automatically
- **Checkpointing**: Persist conversation to Redis
- **Multi-node workflows**: Separate retrieval, generation, tools
- **Conditional routing**: Dynamic flow based on query type

### Why FAISS for Static KB?
- **Speed**: Millisecond search on 379 chunks
- **Efficiency**: Pre-computed embeddings (no re-embedding)
- **Accuracy**: Cosine similarity via normalized inner product

### Why Redis for Dynamic Embeddings?
- **Fast**: In-memory cache, sub-millisecond reads
- **Persistent**: Data survives restarts (with RDB/AOF)
- **TTL**: Automatic expiration after 7 days
- **FIFO**: Bounded memory with automatic cleanup

### Why Hybrid Retrieval?
- **Static KB**: Baseline knowledge (company info, features)
- **Dynamic URLs**: Real-time data (specific companies, live data)
- **Best of both**: Comprehensive answers combining static + dynamic

---

## Monitoring & Analytics

### Performance Metrics

```python
from redis_memory import RedisMemoryManager

redis = RedisMemoryManager()

# Global stats
stats = redis.get_stats()
print(f"Total embeddings: {stats['embeddings']}")
print(f"Active sessions: {stats['sessions']}")
print(f"Memory used: {stats['memory_used_mb']} MB")

# Per-session stats
session_stats = redis.get_session_detailed_stats("user_123")
print(f"URLs tracked: {session_stats['tracked_urls']}")
print(f"Embedding keys: {session_stats['embedding_keys_count']}")
```

### Query Logs

All queries logged to console:
```
[START] Chat request from user_123
[RETRIEVAL] Static KB search for: 'What is Export Genius?'
[RETRIEVAL] Static KB: 5 chunks (scores: [0.876, 0.834, ...])
[CONTEXT] Building prompt with 5 chunks
[LLM] Generating response...
[OK] Response generated in 5.23s
[CACHE] Session metadata updated
```

---

## Future Enhancements

### Planned Features
1. **Streaming responses**: SSE for real-time output
2. **Response caching**: Semantic cache for similar queries
3. **Global embedding cache**: Share embeddings across users
4. **LRU cache**: Replace FIFO with Least Recently Used
5. **Cloud deployment**: Docker + Kubernetes

### Optimization Opportunities
1. Switch to cloud LLM (GPT-4o-mini, Claude Haiku) for 10x speedup
2. Implement query embedding cache
3. Add CDN for static content
4. Parallel retrieval for multiple sources

---

## Additional Documentation

- **FIFO Cache Details**: See `FIFO_CACHE_IMPLEMENTATION.md`
- **Redis Integration**: See `REDIS_INTEGRATION_GUIDE.md`
- **Performance Optimization**: See `PERFORMANCE_OPTIMIZATION_GUIDE.md`
- **Quick Start**: See `QUICK_START.md`
- **Architecture**: See `ARCHITECTURE.md`

---

## Contributing

**Code Standards**:
- Type hints for all functions
- Comprehensive docstrings
- Print statements for debugging
- Error handling for all external calls

**Testing**:
- Unit tests for all components
- Integration tests for API endpoints
- Performance benchmarks

---

## License

Proprietary - Export Genius Internal Use Only

---

**Last Updated**: 2025-12-03
**Version**: 1.0.0
**Chatbot Version**: Redis-Integrated with FIFO Cache
