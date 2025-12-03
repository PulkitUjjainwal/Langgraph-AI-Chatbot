"""
LangGraph Sales Agent with RAG + Tool Calling - FastAPI Version

API Endpoints:
    POST /chat - Send a message and get response
    POST /chat/stream - Stream chatbot response
    POST /reset - Reset conversation for a session
    GET /history/{session_id} - Get conversation history
    GET /health - Health check

Request Format:
    {
        "message": "What is Export Genius?",
        "session_id": "user123",  # Unique identifier for conversation threading
        "dynamic_url": "https://example.com/data"  # Optional: Override dynamic URL
    }

Usage:
    uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --reload
"""

import json
import time
import uuid
from pathlib import Path
from typing import TypedDict, Annotated, Sequence, Dict, Any, Optional, List
import operator
import sys
from datetime import datetime

import numpy as np
import faiss
import ollama
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, tools_condition

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncio
from contextlib import asynccontextmanager

# Import Redis memory manager
from redis_memory import RedisMemoryManager, RedisCheckpointSaver

# Import optional dependencies
try:
    from web_scraper import WebScraper
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False

try:
    from export_genius_api import ExportGeniusAPIClient, fetch_company_data_from_url
    API_CLIENT_AVAILABLE = True
except ImportError:
    API_CLIENT_AVAILABLE = False


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Configuration for chatbot"""
    DATA_DIR = Path("data")
    CHUNKS_FILE = DATA_DIR / "kb_chunks.json"
    FAISS_INDEX_FILE = DATA_DIR / "faiss_normalized.index"

    EMBEDDING_MODEL = "nomic-embed-text"
    LLM_MODEL = "deepseek-v3.1:671b-cloud"

    TOP_K_RESULTS = 5
    MAX_CHUNK_CHARS = 800

    TEMPERATURE = 0.2
    TOP_P = 0.8
    TOP_K = 40
    NUM_PREDICT = 650
    NUM_CTX = 3400

    DYNAMIC_MAX_CHUNKS = 10
    ENABLE_PERFORMANCE_LOGGING = True

    # Redis Configuration
    REDIS_HOST = "localhost"
    REDIS_PORT = 6379
    REDIS_DB = 0
    REDIS_PASSWORD = None
    REDIS_TTL_DAYS = 7

    # Session management
    SESSION_TIMEOUT_MINUTES = 30
    MAX_SESSIONS = 1000


# ============================================================================
# PYDANTIC MODELS (Request/Response)
# ============================================================================

class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str = Field(..., description="User's message", min_length=1)
    session_id: str = Field(..., description="Unique session identifier for conversation threading")
    dynamic_url: Optional[str] = Field(None, description="Optional dynamic URL to fetch data from")
    ip_address: Optional[str] = Field(None, description="Optional IP address of the client")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "What is Export Genius?",
                "session_id": "user123",
                "dynamic_url": "https://www.exportgenius.in/company/example/abc123",
                "ip_address": "192.168.1.1"
            }
        }


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    response: str = Field(..., description="Bot's response")
    session_id: str = Field(..., description="Session identifier")
    processing_time: float = Field(..., description="Processing time in seconds")
    sources_used: List[str] = Field(default_factory=list, description="Sources used for response")
    
    class Config:
        json_schema_extra = {
            "example": {
                "response": "Export Genius is a global trade intelligence platform...",
                "session_id": "user123",
                "processing_time": 2.34,
                "sources_used": ["Knowledge Base", "Dynamic Content"]
            }
        }


class ResetRequest(BaseModel):
    """Request model for reset endpoint"""
    session_id: str = Field(..., description="Session identifier to reset")


class HistoryResponse(BaseModel):
    """Response model for history endpoint"""
    session_id: str
    messages: List[Dict[str, str]]
    total_messages: int


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str
    ollama_status: str
    kb_loaded: bool
    active_sessions: int
    uptime_seconds: float


# ============================================================================
# PERFORMANCE MONITORING
# ============================================================================

class PerformanceMonitor:
    """Monitor and log performance metrics"""

    def __init__(self):
        self.metrics: Dict[str, list] = {
            "retrieval_time": [],
            "generation_time": [],
            "total_time": []
        }

    def log_metric(self, metric_name: str, value: float):
        """Log a performance metric"""
        if metric_name not in self.metrics:
            self.metrics[metric_name] = []
        self.metrics[metric_name].append(value)

        # Keep only last 100 entries per metric
        if len(self.metrics[metric_name]) > 100:
            self.metrics[metric_name] = self.metrics[metric_name][-100:]

    def get_average(self, metric_name: str) -> float:
        """Get average for a metric"""
        values = self.metrics.get(metric_name, [])
        return sum(values) / len(values) if values else 0.0

    def print_summary(self):
        """Print performance summary"""
        print("\n[STATS] Performance Summary:")
        for metric_name, values in self.metrics.items():
            if values:
                avg = sum(values) / len(values)
                print(f"  {metric_name}: {avg:.2f}s (avg over {len(values)} calls)")


perf_monitor = PerformanceMonitor()


# ============================================================================
# REDIS MEMORY (Replaces file-based persistence)
# ============================================================================

# Global Redis manager (initialized at startup)
redis_manager: Optional[RedisMemoryManager] = None


# ============================================================================
# STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    """State for workflow"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_agent: str
    retrieved_context: str
    original_query: str
    use_cache: bool
    retrieved_chunks: list
    start_time: float


# ============================================================================
# DYNAMIC CONTENT MANAGER
# ============================================================================

class DynamicContentManager:
    """Manages dynamic content fetching and embedding generation per session"""

    def __init__(self, redis_manager: RedisMemoryManager):
        self.redis = redis_manager
        self.content_cache: Dict[str, str] = {}
        self.max_cache_size = 50

    async def fetch_content(self, url: str, session_id: str = "") -> str:
        """
        Fetch content from URL with caching
        
        Priority:
        1. Check cache
        2. If company URL -> Use API
        3. If data file exists -> Load from file
        4. Fallback to web scraping
        """
        # Check cache first
        if url in self.content_cache:
            print(f"  [FAST] Using cached content for {url}")
            return self.content_cache[url]
        
        content = ""
        
        # Priority 1: Company API
        if API_CLIENT_AVAILABLE and ExportGeniusAPIClient.is_company_url(url):
            try:
                print(f"[COMPANY] Fetching company data from API: {url}")
                formatted_data = await fetch_company_data_from_url(url)
                if formatted_data:
                    content = "[Company Data from Export Genius API]\n\n" + formatted_data
                    print(f"  [OK] Company data fetched successfully")
            except Exception as e:
                print(f"  [WARN]  API error: {e}")
        
        # Priority 2: Local file
        if not content:
            data_file = Config.DATA_DIR / "dynamic_data.txt"
            if data_file.exists():
                try:
                    with open(data_file, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    if file_content:
                        content = "[Dynamic Content from File]\n\n" + file_content
                        print(f"  [OK] Loaded from file")
                except Exception as e:
                    print(f"  [WARN]  File error: {e}")
        
        # Priority 3: Web scraping
        if not content and SCRAPING_AVAILABLE:
            try:
                print(f"[WEB] Scraping URL: {url}")
                scraper = WebScraper(timeout=15, max_retries=2)
                result = scraper.scrape_url(url)
                
                if result['success']:
                    chunks = scraper.chunk_scraped_content(
                        result['content'],
                        chunk_size=1000,
                        overlap=100
                    )
                    selected_chunks = chunks[:Config.DYNAMIC_MAX_CHUNKS]
                    content = "[Dynamic Content from Website]\n\n" + "\n\n".join(selected_chunks)
                    print(f"  [OK] Scraped successfully")
            except Exception as e:
                print(f"  [WARN]  Scraping error: {e}")
        
        # Cache the content
        if content:
            self._add_to_cache(url, content)
        
        return content
    
    def _add_to_cache(self, key: str, value: str):
        """Add to cache with size limit"""
        if len(self.content_cache) >= self.max_cache_size:
            self.content_cache.pop(next(iter(self.content_cache)))
        self.content_cache[key] = value

    def _chunk_content(self, content: str, chunk_size: int = 800, overlap: int = 100) -> List[Dict[str, Any]]:
        """Chunk content into smaller pieces for embedding"""
        words = content.split()
        chunks = []

        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)

            chunks.append({
                'chunk_id': i // (chunk_size - overlap),
                'chunk_text': chunk_text,
                'word_count': len(chunk_words)
            })

        return chunks

    async def generate_and_store_embeddings(self, content: str, url: str, session_id: str):
        """
        Generate embeddings for dynamic content and store in Redis

        Args:
            content: Raw text content
            url: Source URL
            session_id: Session identifier
        """
        print(f"  [PROCESS] Generating embeddings for session: {session_id}")

        # 1. Chunk content
        chunks = self._chunk_content(content, chunk_size=800, overlap=100)

        if not chunks:
            print(f"  [WARN]  No chunks generated")
            return

        # 2. Generate embeddings
        embeddings_list = []
        for chunk in chunks:
            response = ollama.embeddings(
                model=Config.EMBEDDING_MODEL,
                prompt=chunk['chunk_text']
            )
            embeddings_list.append(response['embedding'])

        embeddings_array = np.array(embeddings_list).astype('float32')
        faiss.normalize_L2(embeddings_array)

        # 3. Store in Redis (with full content)
        self.redis.save_embeddings(
            session_id=session_id,
            dynamic_url=url,
            embeddings=embeddings_array,
            chunks=chunks,
            full_content=content
        )

        print(f"  [OK] Embeddings stored: {len(chunks)} chunks, {embeddings_array.shape}")

    async def get_embeddings_from_redis(self, url: str, session_id: str) -> Optional[tuple]:
        """Get embeddings from Redis cache"""
        return self.redis.get_embeddings(session_id, url)


# ============================================================================
# KNOWLEDGE BASE RETRIEVER
# ============================================================================

class KnowledgeBaseRetriever:
    """RAG system using FAISS and Ollama"""
    
    def __init__(self):
        print("[KB] Loading Knowledge Base...")
        
        if not Config.FAISS_INDEX_FILE.exists():
            raise FileNotFoundError(f"FAISS index not found: {Config.FAISS_INDEX_FILE}")
        
        self.index = faiss.read_index(str(Config.FAISS_INDEX_FILE))
        
        if not Config.CHUNKS_FILE.exists():
            raise FileNotFoundError(f"Chunks file not found: {Config.CHUNKS_FILE}")
        
        with open(Config.CHUNKS_FILE, 'r', encoding='utf-8') as f:
            self.chunks = json.load(f)
        
        self.embedding_cache = {}
        self.max_cache_size = 100
        
        print(f"  [OK] Loaded {len(self.chunks)} chunks")
    
    def retrieve(self, query: str, top_k: int = Config.TOP_K_RESULTS) -> list:
        """Retrieve relevant chunks"""
        start_time = time.time()
        
        cache_key = query.strip().lower()
        if cache_key in self.embedding_cache:
            query_embedding = self.embedding_cache[cache_key]
        else:
            response = ollama.embeddings(
                model=Config.EMBEDDING_MODEL,
                prompt=query
            )
            query_embedding = np.array([response['embedding']]).astype('float32')
            faiss.normalize_L2(query_embedding)
            self._add_to_embedding_cache(cache_key, query_embedding)
        
        scores, indices = self.index.search(query_embedding, top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            chunk = self.chunks[idx].copy()
            chunk['score'] = float(scores[0][i])
            results.append(chunk)
        
        if Config.ENABLE_PERFORMANCE_LOGGING:
            elapsed = time.time() - start_time
            perf_monitor.log_metric("retrieval_time", elapsed)
        
        return results
    
    def _add_to_embedding_cache(self, key: str, embedding: np.ndarray):
        """Add embedding to cache"""
        if len(self.embedding_cache) >= self.max_cache_size:
            self.embedding_cache.pop(next(iter(self.embedding_cache)))
        self.embedding_cache[key] = embedding
    
    def format_context(self, results: list) -> str:
        """Format retrieved chunks as context"""
        context_parts = []
        for i, result in enumerate(results, 1):
            chunk_text = result['chunk_text']
            if len(chunk_text) > Config.MAX_CHUNK_CHARS:
                chunk_text = chunk_text[:Config.MAX_CHUNK_CHARS] + "..."
            context_parts.append(
                f"[Source {i}: {result['page_title']}]\n{chunk_text}\n"
            )
        return "\n".join(context_parts)


# ============================================================================
# HYBRID RETRIEVER (KB + Dynamic Embeddings from Redis)
# ============================================================================

class HybridRetriever:
    """
    Hybrid retrieval combining:
    1. Static KB (FAISS index)
    2. Dynamic embeddings (from Redis)
    """

    def __init__(self, kb_retriever: KnowledgeBaseRetriever, redis_manager: RedisMemoryManager):
        self.kb_retriever = kb_retriever
        self.redis = redis_manager

    async def retrieve_dynamic(self, query: str, session_id: str, dynamic_url: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve from dynamic embeddings in Redis"""
        # Get embeddings from Redis
        cached = self.redis.get_embeddings(session_id, dynamic_url)

        if not cached:
            print(f"  [WARN]  No dynamic embeddings found in Redis for session: {session_id}")
            return []

        embeddings, chunks = cached

        # Create temporary FAISS index
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)

        # Generate query embedding
        response = ollama.embeddings(
            model=Config.EMBEDDING_MODEL,
            prompt=query
        )
        query_embedding = np.array([response['embedding']]).astype('float32')
        faiss.normalize_L2(query_embedding)

        # Search
        scores, indices = index.search(query_embedding, min(top_k, len(chunks)))

        # Build results
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(chunks):
                chunk = chunks[idx].copy()
                chunk['score'] = float(scores[0][i])
                chunk['source'] = 'dynamic'
                chunk['page_title'] = 'Company Data'
                results.append(chunk)

        return results

    async def hybrid_retrieve(
        self,
        query: str,
        session_id: str,
        dynamic_url: Optional[str] = None,
        kb_top_k: int = 3,
        dynamic_top_k: int = 3
    ) -> tuple[str, str]:
        """
        Hybrid retrieval from both KB and dynamic sources

        Returns:
            (kb_context, dynamic_context)
        """
        print(f"\n  [FIND] HYBRID RETRIEVAL:")

        # 1. KB Retrieval
        kb_results = self.kb_retriever.retrieve(query, top_k=kb_top_k)
        kb_context = self.kb_retriever.format_context(kb_results)
        print(f"     • KB: {len(kb_results)} chunks retrieved")

        # 2. Dynamic Retrieval (if URL provided)
        dynamic_context = ""
        if dynamic_url:
            dynamic_results = await self.retrieve_dynamic(query, session_id, dynamic_url, top_k=dynamic_top_k)

            if dynamic_results:
                # Format dynamic context
                dynamic_parts = []
                for i, result in enumerate(dynamic_results, 1):
                    chunk_text = result['chunk_text']
                    if len(chunk_text) > Config.MAX_CHUNK_CHARS:
                        chunk_text = chunk_text[:Config.MAX_CHUNK_CHARS] + "..."
                    dynamic_parts.append(f"[Dynamic Source {i}]\n{chunk_text}\n")

                dynamic_context = "\n".join(dynamic_parts)
                print(f"     • Dynamic: {len(dynamic_results)} chunks retrieved")
            else:
                print(f"     • Dynamic: No embeddings available")

        return kb_context, dynamic_context


# ============================================================================
# TOOLS DEFINITION
# ============================================================================

# Global dynamic content per session
session_dynamic_content: Dict[str, str] = {}


def fetch_dynamic_trade_data(query: str = "") -> str:
    """
    Fetch dynamic trade data.
    This function accesses session-specific dynamic content.
    """
    # Get current session's dynamic content
    # Note: This will be set before tool execution
    content = session_dynamic_content.get("current", "")
    
    if content:
        return f"Dynamic Trade Data:\n\n{content}"
    else:
        return "No dynamic trade data available."


all_tools = [fetch_dynamic_trade_data]


# ============================================================================
# QUERY CLASSIFICATION HELPERS
# ============================================================================

def classify_query_type(query: str) -> str:
    """
    Classify query type for smart context selection

    Returns: 'company', 'trade_data', or 'general'
    """
    query_lower = query.lower()

    # Company-specific queries
    company_keywords = [
        'what is', 'tell me about', 'who is', 'about',
        'company', 'profile', 'information about',
        'details of', 'describe', 'overview of'
    ]
    if any(kw in query_lower for kw in company_keywords):
        return 'company'

    # Trade data queries (numbers/statistics)
    trade_keywords = [
        'hs code', 'import', 'export', 'shipment', 'trade',
        'statistics', 'volume', 'value', 'quantity',
        'country', 'port', 'supplier', 'buyer', 'product',
        'how many', 'how much', 'list', 'show me'
    ]
    if any(kw in query_lower for kw in trade_keywords):
        return 'trade_data'

    # General queries
    return 'general'


def extract_numeric_focus(query: str) -> bool:
    """Check if query requires numeric precision"""
    numeric_indicators = [
        'how many', 'how much', 'count', 'number',
        'total', 'sum', 'average', 'statistics',
        'volume', 'value', 'quantity', 'amount',
        'list all', 'show all', 'list', 'enumerate'
    ]
    return any(indicator in query.lower() for indicator in numeric_indicators)


# ============================================================================
# WORKFLOW NODES
# ============================================================================

def create_retrieval_node(kb_retriever: KnowledgeBaseRetriever):
    """Create retrieval node"""

    def retrieval_node(state: AgentState) -> AgentState:
        """Retrieve relevant chunks from knowledge base"""
        messages = state["messages"]
        query = messages[-1].content if messages else ""

        print(f"\n[SEARCH] Retrieving from knowledge base...")

        results = kb_retriever.retrieve(query, top_k=Config.TOP_K_RESULTS)
        context = kb_retriever.format_context(results)

        print(f"  [OK] Retrieved {len(results)} chunks")

        return {
            "messages": [],
            "next_agent": "chatbot",
            "retrieved_context": context,
            "original_query": query,
            "use_cache": False,
            "retrieved_chunks": results,
            "start_time": state.get("start_time", time.time())
        }

    return retrieval_node


def create_chatbot_node():
    """Create chatbot node with SMART CONTEXT INJECTION"""

    llm = ChatOllama(
        model=Config.LLM_MODEL,
        temperature=Config.TEMPERATURE,
        top_p=Config.TOP_P,
        top_k=Config.TOP_K,
        num_predict=Config.NUM_PREDICT,
        num_ctx=Config.NUM_CTX,
    )

    llm_with_tools = llm.bind_tools(all_tools)

    def chatbot_node(state: AgentState) -> AgentState:
        """Generate response with smart context injection"""
        start_time = time.time()

        user_query = state.get("original_query", "")
        kb_context = state["retrieved_context"]
        messages = state.get("messages", [])

        print(f"\n[CHAT] Chatbot processing...")

        # Get dynamic content
        dynamic_content = session_dynamic_content.get("current", "")

        # Classify query type
        query_type = classify_query_type(user_query)
        needs_numeric_precision = extract_numeric_focus(user_query)

        print(f"  [FIND] Query type: {query_type.upper()}")
        if needs_numeric_precision:
            print(f"  [NUM] Numeric precision required")

        # SMART CONTEXT BUILDING
        print(f"\n  [STATS] CONTEXT MERGING DEBUG:")
        print(f"     • KB Context Available: {len(kb_context)} chars")
        print(f"     • Dynamic Content Available: {len(dynamic_content)} chars")
        print(f"     • Merging Strategy: {query_type.upper()}")

        if query_type == 'company':
            # Company queries → Prioritize dynamic content
            if dynamic_content:
                # Truncate to fit context window, prioritize dynamic
                max_dynamic = 2500
                max_kb = 800
                context = f"""=== COMPANY PROFILE (PRIMARY SOURCE) ===
{dynamic_content[:max_dynamic]}

=== ADDITIONAL REFERENCE ===
{kb_context[:max_kb]}"""
                print(f"  [OK] MERGED: Company profile (dynamic={len(dynamic_content[:max_dynamic])} chars, kb={len(kb_context[:max_kb])} chars)")
                print(f"     → Dynamic content ratio: {len(dynamic_content[:max_dynamic]) / (len(dynamic_content[:max_dynamic]) + len(kb_context[:max_kb])) * 100:.1f}%")
            else:
                context = kb_context
                print(f"  [DATA] Context: KB only (no dynamic data available)")

        elif query_type == 'trade_data':
            # Trade data queries → Hybrid approach
            if dynamic_content:
                max_each = 1500
                context = f"""=== KNOWLEDGE BASE ===
{kb_context[:max_each]}

=== TRADE DATA & STATISTICS ===
{dynamic_content[:max_each]}"""
                print(f"  [OK] MERGED: Hybrid approach (kb={len(kb_context[:max_each])} chars, dynamic={len(dynamic_content[:max_each])} chars)")
                print(f"     → Split ratio: 50% KB / 50% Dynamic")
            else:
                context = kb_context
                print(f"  [DATA] Context: KB only")

        else:
            # General queries → KB only
            context = kb_context
            print(f"  [DATA] Context: KB only (general query)")

        print(f"  [DATA] FINAL CONTEXT SIZE: {len(context)} chars (~{len(context)//4} tokens)")

        # Get conversation history
        conversation_history = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                conversation_history.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                conversation_history.append(f"Assistant: {msg.content}")

        history_text = "\n".join(conversation_history[-4:]) if conversation_history else ""

        # OPTIMIZED SYSTEM PROMPT FOR ACCURACY & SPEED
        if needs_numeric_precision:
            accuracy_instruction = """
[WARN] CRITICAL - NUMERIC ACCURACY:
- Quote exact numbers, values, and statistics from context
- Do NOT estimate, round, or approximate
- If specific data is unavailable, state clearly: "This information is not available"
- Format numbers clearly (e.g., 1,234,567 or 1.23M)
- Include units (USD, tons, pieces, etc.)"""
        else:
            accuracy_instruction = ""

        system_prompt = f"""You are Export Genius AI - an expert sales assistant for Export Genius, the world's leading trade data platform.

YOUR MISSION: Help users discover how Export Genius can transform their business with comprehensive import-export trade data.

{f"CONVERSATION HISTORY:\n{history_text}\n" if history_text else ""}CONTEXT:
{context}{accuracy_instruction}

RESPONSE GUIDELINES:
[CRITICAL] When asked about Export Genius, ALWAYS highlight our key strengths:
  - 190+ countries coverage with 6B+ shipment records
  - 10M+ company & employee contacts
  - Real-time trade data API integration
  - 62+ countries detailed customs data
  - Powerful market research and business intelligence tools

[OK] Be enthusiastic about Export Genius features and benefits
[OK] Use bullet points to showcase our capabilities
[OK] Prioritize "COMPANY PROFILE" or "TRADE DATA" sections when available
[OK] Quote exact data from context to prove our value
[OK] For trade data queries, demonstrate how Export Genius provides the answers
[ERROR] NEVER say "I don't have information about Export Genius" - you ARE Export Genius!
[ERROR] Do not be overly cautious - confidently present our services
[ERROR] Do not add excessive pleasantries

Answer queries with confidence, showcasing Export Genius as the solution."""

        system_message = SystemMessage(content=system_prompt)

        llm_messages = list(messages) if messages else []
        if not llm_messages or not isinstance(llm_messages[0], SystemMessage):
            llm_messages.insert(0, system_message)
        llm_messages.append(HumanMessage(content=user_query))

        print(f"  [AI] Sending merged context to LLM ({Config.LLM_MODEL})...")

        try:
            response = llm_with_tools.invoke(llm_messages)

            elapsed = time.time() - start_time
            if Config.ENABLE_PERFORMANCE_LOGGING:
                perf_monitor.log_metric("generation_time", elapsed)

            total_time = time.time() - state.get("start_time", start_time)
            if Config.ENABLE_PERFORMANCE_LOGGING:
                perf_monitor.log_metric("total_time", total_time)

            if hasattr(response, 'tool_calls') and response.tool_calls:
                print(f"  [TOOL]  Tool : {response.tool_calls[0]['name']}")
            else:
                print(f"  [OK] Direct response ({len(response.content)} chars)")

            print(f"  [FAST] Processing: {elapsed:.2f}s | Total: {total_time:.2f}s")

        except Exception as e:
            print(f"  [ERROR] Chatbot error: {e}")
            response = AIMessage(content="I apologize, but I encountered an error processing your request. Please try again.")

        return {
            "messages": [response],
            "next_agent": "END",
            "retrieved_context": kb_context,
            "original_query": user_query,
            "use_cache": False,
            "retrieved_chunks": state.get("retrieved_chunks", []),
            "start_time": state.get("start_time", time.time())
        }

    return chatbot_node


# ============================================================================
# CHATBOT MANAGER
# ============================================================================

class ChatbotManager:
    """Manages multiple chatbot sessions with Redis persistence"""

    def __init__(self, kb_retriever: KnowledgeBaseRetriever, redis_manager: RedisMemoryManager):
        self.kb_retriever = kb_retriever
        self.redis = redis_manager
        self.dynamic_content_manager = DynamicContentManager(redis_manager)
        self.hybrid_retriever = HybridRetriever(kb_retriever, redis_manager)
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.app = self._create_workflow()
        print("[OK] Chatbot Manager initialized (Redis-backed)")

    def _create_workflow(self):
        """Create LangGraph workflow with Redis checkpoint saver"""
        retrieval_node = create_retrieval_node(self.kb_retriever)
        chatbot_node = create_chatbot_node()
        tools_node = ToolNode(tools=all_tools)

        workflow = StateGraph(AgentState)
        workflow.add_node("retrieve", retrieval_node)
        workflow.add_node("chatbot", chatbot_node)
        workflow.add_node("tools", tools_node)

        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", "chatbot")
        workflow.add_conditional_edges(
            "chatbot",
            tools_condition,
            {"tools": "tools", END: END}
        )
        workflow.add_edge("tools", "chatbot")

        # Use Redis checkpoint saver
        memory = RedisCheckpointSaver(self.redis)

        return workflow.compile(checkpointer=memory)
    
    async def chat(self, message: str, session_id: str, dynamic_url: Optional[str] = None) -> tuple[str, float, List[str]]:
        """
        Process chat message with Redis-backed embeddings

        Returns:
            (response, processing_time, sources_used)
        """
        start_time = time.time()

        # Fetch dynamic content if URL provided
        dynamic_content = ""
        sources_used = ["Knowledge Base"]

        if dynamic_url:
            # Check if embeddings already exist in Redis
            cached_data = await self.dynamic_content_manager.get_embeddings_from_redis(dynamic_url, session_id)

            if cached_data:
                # Extract embeddings, chunks, and full content from cache
                embeddings, chunks, full_content = cached_data
                dynamic_content = full_content

                print(f"  [FAST] Using cached embeddings from Redis")
                print(f"  [CACHE HIT] Content loaded: {len(dynamic_content)} chars")
                sources_used.append("Dynamic Content (Redis)")
            else:
                # Fetch content and generate embeddings
                dynamic_content = await self.dynamic_content_manager.fetch_content(dynamic_url, session_id)

                if dynamic_content:
                    sources_used.append("Dynamic Content")

                    # Generate and store embeddings in Redis
                    await self.dynamic_content_manager.generate_and_store_embeddings(
                        content=dynamic_content,
                        url=dynamic_url,
                        session_id=session_id
                    )

        # Set session-specific dynamic content for tool access
        global session_dynamic_content
        session_dynamic_content["current"] = dynamic_content

        # Create config with thread ID
        thread_id = f"session_{session_id}"
        config = {"configurable": {"thread_id": thread_id}}

        # Store session metadata in Redis
        self.redis.update_session_meta(session_id, {
            "thread_id": thread_id,
            "dynamic_url": dynamic_url or "",
            "message_count": self.redis.get_session_meta(session_id).get("message_count", 0) + 1
        })

        # Invoke workflow with complete state
        try:
            result = self.app.invoke(
                {
                    "messages": [HumanMessage(content=message)],
                    "next_agent": "",
                    "retrieved_context": "",
                    "original_query": message,
                    "use_cache": False,
                    "retrieved_chunks": [],
                    "start_time": start_time,
                    "session_id": session_id,
                    "dynamic_url": dynamic_url or ""
                },
                config=config
            )
        except Exception as e:
            import traceback
            print(f"\n[ERROR] Workflow invocation failed:")
            print(traceback.format_exc())
            raise

        # Extract response
        response = ""
        if result["messages"]:
            response = result["messages"][-1].content
        else:
            response = "I'm sorry, I couldn't process that request."

        processing_time = time.time() - start_time

        # Update session info (both in-memory and Redis)
        self.sessions[session_id] = {
            "last_activity": datetime.now(),
            "thread_id": thread_id,
            "message_count": self.sessions.get(session_id, {}).get("message_count", 0) + 1
        }

        return response, processing_time, sources_used
    
    def reset_session(self, session_id: str):
        """Reset conversation for a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            print(f"[PROCESS] Session reset: {session_id}")
    
    def get_active_sessions(self) -> int:
        """Get count of active sessions"""
        return len(self.sessions)
    
    def cleanup_old_sessions(self):
        """Remove inactive sessions"""
        cutoff_time = datetime.now()
        expired_sessions = [
            sid for sid, info in self.sessions.items()
            if (cutoff_time - info["last_activity"]).total_seconds() > Config.SESSION_TIMEOUT_MINUTES * 60
        ]
        for sid in expired_sessions:
            del self.sessions[sid]
        if expired_sessions:
            print(f"[DELETE]  Cleaned up {len(expired_sessions)} expired sessions")


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

# Global variables
chatbot_manager: Optional[ChatbotManager] = None
app_start_time: float = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global chatbot_manager, app_start_time, redis_manager
    import sys

    sys.stderr.write("\n" + "=" * 70 + "\n")
    sys.stderr.write("FASTAPI CHATBOT STARTING (Redis-Backed)\n")
    sys.stderr.write("=" * 70 + "\n")
    sys.stderr.flush()

    app_start_time = time.time()

    try:
        # Initialize Redis connection
        sys.stderr.write("\nConnecting to Redis...\n")
        sys.stderr.flush()

        redis_manager = RedisMemoryManager(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            password=Config.REDIS_PASSWORD,
            ttl_days=Config.REDIS_TTL_DAYS
        )

        # Initialize KB retriever
        kb_retriever = KnowledgeBaseRetriever()

        # Initialize chatbot manager with Redis
        chatbot_manager = ChatbotManager(kb_retriever, redis_manager)

        # Print Redis stats
        stats = redis_manager.get_stats()
        sys.stderr.write(f"\nRedis Stats:\n")
        sys.stderr.write(f"   - Active conversations: {stats['conversations']}\n")
        sys.stderr.write(f"   - Cached embeddings: {stats['embeddings']}\n")
        sys.stderr.write(f"   - Active sessions: {stats['sessions']}\n")
        sys.stderr.write(f"   - Memory used: {stats['memory_used_mb']} MB\n")
        sys.stderr.write("\nFastAPI application ready!\n")
        sys.stderr.write("=" * 70 + "\n")
        sys.stderr.flush()

        yield

        # Shutdown
        print("\nShutting down...")
        if Config.ENABLE_PERFORMANCE_LOGGING:
            perf_monitor.print_summary()

        # Print final Redis stats
        final_stats = redis_manager.get_stats()
        print(f"\nFinal Redis Stats:")
        print(f"   - Total conversations: {final_stats['conversations']}")
        print(f"   - Total embeddings: {final_stats['embeddings']}")
        print(f"   - Memory peak: {final_stats['memory_peak_mb']} MB")

    except Exception as e:
        print(f"\nStartup error: {e}")
        import traceback
        traceback.print_exc()
        raise


app = FastAPI(
    title="Export Genius AI Chatbot API",
    description="LangGraph-powered chatbot with RAG and dynamic content fetching",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Send a message and get response

    - **message**: User's question
    - **session_id**: Unique session identifier for conversation threading
    - **dynamic_url**: Optional URL to fetch dynamic content from
    - **ip_address**: Optional IP address of the client
    """
    if not chatbot_manager:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")

    # Log IP address if provided
    if request.ip_address:
        print(f"\n[WEB] Request from IP: {request.ip_address}")

    try:
        response, processing_time, sources_used = await chatbot_manager.chat(
            message=request.message,
            session_id=request.session_id,
            dynamic_url=request.dynamic_url
        )

        # Schedule session cleanup in background
        background_tasks.add_task(chatbot_manager.cleanup_old_sessions)

        return ChatResponse(
            response=response,
            session_id=request.session_id,
            processing_time=processing_time,
            sources_used=sources_used
        )

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"\n[ERROR] Chat endpoint failed:")
        print(error_details)
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream chatbot response (Server-Sent Events)
    
    Note: Streaming implementation would require additional logic
    This is a placeholder for future implementation
    """
    raise HTTPException(status_code=501, detail="Streaming not yet implemented")


@app.post("/reset")
async def reset_session(request: ResetRequest):
    """Reset conversation history for a session"""
    if not chatbot_manager:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")
    
    chatbot_manager.reset_session(request.session_id)
    
    return JSONResponse(
        content={
            "status": "success",
            "message": f"Session {request.session_id} reset successfully"
        }
    )


@app.get("/history/{session_id}", response_model=HistoryResponse)
async def get_history(session_id: str, limit: int = 10):
    """Get conversation history for a session"""
    if not chatbot_manager:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")
    
    # Note: This would require implementing history retrieval from checkpointer
    # For now, return placeholder
    return HistoryResponse(
        session_id=session_id,
        messages=[],
        total_messages=0
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with Redis stats"""
    ollama_status = "healthy"
    try:
        ollama.list()
    except Exception:
        ollama_status = "unavailable"

    # Check Redis
    redis_status = "healthy"
    try:
        if redis_manager:
            redis_manager.client.ping()
    except Exception:
        redis_status = "unavailable"

    kb_loaded = chatbot_manager is not None and chatbot_manager.kb_retriever is not None
    active_sessions = chatbot_manager.get_active_sessions() if chatbot_manager else 0
    uptime = time.time() - app_start_time

    return HealthResponse(
        status="healthy" if kb_loaded and ollama_status == "healthy" and redis_status == "healthy" else "degraded",
        ollama_status=f"{ollama_status} | Redis: {redis_status}",
        kb_loaded=kb_loaded,
        active_sessions=active_sessions,
        uptime_seconds=uptime
    )


@app.get("/redis/stats")
async def redis_stats():
    """Get Redis cache statistics"""
    if not redis_manager:
        raise HTTPException(status_code=503, detail="Redis not initialized")

    stats = redis_manager.get_stats()

    return JSONResponse(
        content={
            "redis_stats": stats,
            "status": "healthy"
        }
    )


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Export Genius AI Chatbot API",
        "version": "1.0.0",
        "endpoints": {
            "POST /chat": "Send a message",
            "POST /reset": "Reset session",
            "GET /history/{session_id}": "Get conversation history",
            "GET /health": "Health check",
            "GET /docs": "Interactive API documentation"
        }
    }


# ============================================================================
# MAIN (for testing)
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("\n[START] Starting FastAPI server...")
    print("[KB] API docs will be available at: http://localhost:8000/docs")
    print()
    
    uvicorn.run(
        "fastapi_chatbot:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )