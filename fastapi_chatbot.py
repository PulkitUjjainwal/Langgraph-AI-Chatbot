"""
LangGraph Sales Agent with RAG + Tool Calling - FastAPI Version

API Endpoints (All under /api prefix):
    POST /api/chat - Send a message and get response
    POST /api/chat/stream - Stream chatbot response
    POST /api/init - Initialize session with dynamic URL
    POST /api/reset - Reset conversation for a session
    GET /api/history/{session_id} - Get conversation history
    GET /api/health - Health check
    GET /api/redis/stats - Redis statistics

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
import re
import os
from pathlib import Path
from typing import TypedDict, Annotated, Sequence, Dict, Any, Optional, List
import operator
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

import numpy as np
import faiss
import ollama
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, tools_condition

from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncio
from contextlib import asynccontextmanager

# Import Redis memory manager
from redis_memory import RedisMemoryManager, RedisCheckpointSaver

# Import hostility detection
from hostility_detector import HostilityDetector, HostilityConfig

print("[DEBUG] All imports completed successfully!")

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

    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v3.1:671b-cloud")

    TOP_K_RESULTS = 5
    MAX_CHUNK_CHARS = 800

    TEMPERATURE = 0.2
    TOP_P = 0.8
    TOP_K = 40
    NUM_PREDICT = 650
    NUM_CTX = 3400

    DYNAMIC_MAX_CHUNKS = 10
    ENABLE_PERFORMANCE_LOGGING = True

    # Ollama Configuration
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", None)

    # Redis Configuration
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    REDIS_TTL_DAYS = int(os.getenv("REDIS_TTL_DAYS", "7"))

    # Session management
    SESSION_TIMEOUT_MINUTES = 30
    MAX_SESSIONS = 1000


# ============================================================================
# OLLAMA CLIENT HELPER - Lazy wrapper to avoid blocking on import
# ============================================================================

class LazyOllamaClient:
    """Wrapper that creates Ollama client only when methods are called"""

    def __init__(self):
        self._local_client = None  # For embeddings
        self._cloud_client = None  # For LLM calls

    def _get_local_client(self):
        """Lazy initialize the local Ollama client (for embeddings)"""
        if self._local_client is None:
            self._local_client = ollama.Client(host="http://localhost:11434")
        return self._local_client

    def _get_cloud_client(self):
        """Lazy initialize the cloud Ollama client (for LLM)"""
        if self._cloud_client is None:
            if Config.OLLAMA_API_KEY:
                self._cloud_client = ollama.Client(
                    host=Config.OLLAMA_BASE_URL,
                    headers={'Authorization': f'Bearer {Config.OLLAMA_API_KEY}'}
                )
            else:
                # Fallback to local if no API key
                self._cloud_client = ollama.Client(host="http://localhost:11434")
        return self._cloud_client

    def embeddings(self, **kwargs):
        """Forward embeddings call to LOCAL client (uses /api/embed for compatibility)"""
        # Convert prompt parameter to input for embed() API
        if 'prompt' in kwargs:
            kwargs['input'] = kwargs.pop('prompt')

        # Call local embed() API
        response = self._get_local_client().embed(**kwargs)

        # Convert embeddings array to single embedding for backward compatibility
        if 'embeddings' in response and len(response['embeddings']) > 0:
            response['embedding'] = response['embeddings'][0]

        return response

    def list(self):
        """Forward list call to local client"""
        return self._get_local_client().list()

    def pull(self, model_name):
        """Forward pull call to local client"""
        return self._get_local_client().pull(model_name)

def get_ollama_client():
    """Get the lazy Ollama client wrapper"""
    return _lazy_ollama_client

def get_ollama_cloud_client():
    """Get the cloud Ollama client for LLM calls"""
    return _lazy_ollama_client._get_cloud_client()

# Create single instance
_lazy_ollama_client = LazyOllamaClient()


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


class InitRequest(BaseModel):
    """Request model for init endpoint"""
    session_id: str = Field(..., description="Unique session identifier")
    dynamic_url: Optional[str] = Field(None, description="Optional dynamic URL to pre-cache")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user_123",
                "dynamic_url": "https://www.exportgenius.in/company/petron-corporation"
            }
        }


class InitResponse(BaseModel):
    """Response model for init endpoint"""
    status: str = Field(..., description="Status: success, partial_success, or error")
    suggested_questions: List[str] = Field(..., description="5 suggested questions for the user")
    cache_status: Dict[str, Any] = Field(..., description="Cache information")
    processing_time: float = Field(..., description="Processing time in seconds")
    dynamic_url_processed: bool = Field(..., description="Whether dynamic URL was processed")
    error: Optional[str] = Field(None, description="Error message if any")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "suggested_questions": [
                    "What products does Petron Corporation import?",
                    "Show me Petron's top trading partners",
                    "What is Petron's trade volume trend?",
                    "Tell me about Petron's recent shipments",
                    "How can Export Genius help analyze this company?"
                ],
                "cache_status": {
                    "cache_hit": False,
                    "cached_at": "2025-12-03T12:00:00Z"
                },
                "processing_time": 15.2,
                "dynamic_url_processed": True
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
    session_id: str  # For guardrail node
    dynamic_url: str  # For context


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
        Generate embeddings for dynamic content and store in Redis (OPTIMIZED with parallel processing)

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

        # 2. Generate embeddings in PARALLEL (3-5x faster!)
        print(f"  [OPTIMIZE] Processing {len(chunks)} chunks in parallel...")

        async def embed_chunk(chunk_text):
            """Helper to embed a single chunk asynchronously"""
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: get_ollama_client().embeddings(
                    model=Config.EMBEDDING_MODEL,
                    prompt=chunk_text
                )['embedding']
            )

        # Process all chunks concurrently
        embeddings_tasks = [embed_chunk(chunk['chunk_text']) for chunk in chunks]
        embeddings_list = await asyncio.gather(*embeddings_tasks)

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

        print(f"  [OK] Embeddings stored: {len(chunks)} chunks, {embeddings_array.shape} (parallel processing)")

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
            response = get_ollama_client().embeddings(
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

    def get_chunks(self, count: int = 10) -> list:
        """Get sample chunks from knowledge base for question generation"""
        return self.chunks[:count] if self.chunks else []

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
        response = get_ollama_client().embeddings(
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

def create_guardrail_node(hostility_detector):
    """
    Create guardrail node for profanity/hostility detection

    This node runs AFTER retrieval, BEFORE chatbot
    - Fast rule-based check (2-8ms)
    - Intent-based response (question vs abuse vs dismissal)
    - Never blocks users (forgiving approach)
    - Tracks for monitoring
    """

    def guardrail_node(state: AgentState) -> AgentState:
        """
        Guardrail: Check for hostility and handle appropriately

        Flow:
        1. Clean message → Pass through to chatbot
        2. Question with profanity → Pass through (let chatbot answer)
        3. Pure abuse → Return brief response, skip LLM
        4. Dismissal → Return graceful exit, skip LLM
        """
        messages = state.get("messages", [])
        if not messages:
            return state

        user_message = messages[-1].content if messages else ""

        # Get session info from state
        session_id = state.get("session_id", "unknown")

        # Check for hostility (2-8ms, no LLM call)
        should_handle, intent, suggested_response = hostility_detector.check_message(
            message=user_message,
            session_id=session_id,
            ip_address=None
        )

        print(f"  [GUARDRAIL] Intent: {intent} | Handle: {should_handle}")

        # Decision logic based on intent
        if not should_handle or intent == "clean":
            # Clean message - pass through to chatbot normally
            return state

        if intent == "question":
            # Has question despite profanity
            # Option 1: Suggested response is None → Just answer the question
            # Option 2: Suggested response exists → Prepend acknowledgment
            if suggested_response:
                # Add subtle acknowledgment to state (chatbot will see this context)
                print(f"  [GUARDRAIL] Question with profanity - adding context")
                # Let chatbot handle, but it will be aware of frustration
            return state

        if intent == "dismissal":
            # User wants to exit → Return graceful response, skip LLM
            print(f"  [GUARDRAIL] Dismissal detected - returning graceful exit")
            response = AIMessage(content=suggested_response)
            return {
                "messages": state["messages"] + [response],
                "next_agent": "END",
                "retrieved_context": state.get("retrieved_context", ""),
                "original_query": state.get("original_query", ""),
                "use_cache": False,
                "retrieved_chunks": state.get("retrieved_chunks", []),
                "start_time": state.get("start_time", time.time())
            }

        if intent == "abuse":
            # Pure abuse, no question → Return brief response, skip LLM (saves time!)
            print(f"  [GUARDRAIL] Pure abuse detected - returning brief response (skip LLM)")
            response = AIMessage(content=suggested_response)
            return {
                "messages": state["messages"] + [response],
                "next_agent": "END",
                "retrieved_context": state.get("retrieved_context", ""),
                "original_query": state.get("original_query", ""),
                "use_cache": False,
                "retrieved_chunks": state.get("retrieved_chunks", []),
                "start_time": state.get("start_time", time.time())
            }

        # Default: pass through
        return state

    return guardrail_node


def create_retrieval_node(kb_retriever: KnowledgeBaseRetriever):
    """Create retrieval node"""

    def retrieval_node(state: AgentState) -> AgentState:
        """Retrieve relevant chunks from knowledge base"""
        messages = state["messages"]
        query = messages[-1].content if messages else ""

        print(f"\n[SEARCH] Retrieving from knowledge base...")

        # Increase top_k for data type queries to ensure we get country-specific chunks
        query_lower = query.lower()
        is_data_type_query = any(term in query_lower for term in ['data type', 'data available', 'what data', 'which data'])

        top_k = Config.TOP_K_RESULTS * 2 if is_data_type_query else Config.TOP_K_RESULTS

        results = kb_retriever.retrieve(query, top_k=top_k)
        context = kb_retriever.format_context(results)

        if is_data_type_query:
            print(f"  [OK] Retrieved {len(results)} chunks (expanded for data type query)")
        else:
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


# ============================================================================
# SMART BOT ENHANCEMENTS - Week 2
# ============================================================================

def detect_greeting(query: str) -> dict:
    """
    Detect if query is a greeting and return appropriate response
    Returns: {"is_greeting": bool, "response": str or None}
    """
    query_lower = query.lower().strip()

    # Greeting patterns
    greetings = ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening', 'greetings']

    # Check if query is a simple greeting (not part of longer question)
    if query_lower in greetings or (any(query_lower.startswith(g) for g in greetings) and len(query.split()) <= 3):
        # Context-aware greeting responses
        responses = [
            "Hello! I'm Alex from Export Genius. I help businesses find buyers, suppliers, and market opportunities using trade data from 190+ countries. What are you looking to achieve today?",
            "Hi there! Welcome to Export Genius. I can help you discover new markets, find active importers, or track competitor activity. What would you like to explore?",
            "Good to meet you! I'm here to help you leverage global trade data for your business growth. Are you looking to find buyers, research markets, or something else?"
        ]

        # Pick response based on variation
        import random
        response = random.choice(responses)

        return {"is_greeting": True, "response": response}

    return {"is_greeting": False, "response": None}


def detect_industry(query: str, context: str = "") -> dict:
    """
    Detect industry mentioned in query and return specific context
    Returns: {"industry": str or None, "context_hint": str, "examples": str}
    """
    query_lower = query.lower()
    combined_text = (query_lower + " " + context.lower())

    # Industry detection patterns
    industries = {
        'textile': {
            'keywords': ['textile', 'fabric', 'garment', 'clothing', 'apparel', 'cotton', 'yarn'],
            'context': 'textile and apparel trade',
            'examples': 'cotton fabric importers, garment manufacturers, yarn buyers'
        },
        'electronics': {
            'keywords': ['electronics', 'electronic', 'smartphone', 'mobile', 'computer', 'chip', 'semiconductor'],
            'context': 'electronics and technology trade',
            'examples': 'smartphone importers, electronics distributors, tech component buyers'
        },
        'food': {
            'keywords': ['food', 'agriculture', 'grain', 'fruit', 'vegetable', 'meat', 'dairy'],
            'context': 'food and agriculture trade',
            'examples': 'food importers, agricultural buyers, organic food distributors'
        },
        'machinery': {
            'keywords': ['machinery', 'equipment', 'machine', 'industrial', 'manufacturing'],
            'context': 'industrial machinery and equipment trade',
            'examples': 'machinery importers, equipment buyers, industrial suppliers'
        },
        'chemicals': {
            'keywords': ['chemical', 'pharmaceutical', 'drug', 'medicine', 'cosmetic'],
            'context': 'chemicals and pharmaceuticals trade',
            'examples': 'chemical importers, pharmaceutical buyers, cosmetic distributors'
        },
        'automotive': {
            'keywords': ['automotive', 'auto', 'car', 'vehicle', 'automobile', 'parts'],
            'context': 'automotive and auto parts trade',
            'examples': 'auto parts importers, vehicle buyers, automotive distributors'
        }
    }

    # Detect industry
    for industry, data in industries.items():
        if any(keyword in combined_text for keyword in data['keywords']):
            return {
                "industry": industry,
                "context_hint": f"Focus on {data['context']}",
                "examples": data['examples']
            }

    return {"industry": None, "context_hint": "", "examples": ""}


def score_response_quality(response: str, query: str) -> dict:
    """
    Score response quality on multiple dimensions
    Returns: {"score": float, "issues": list, "suggestions": list}
    """
    score = 100
    issues = []
    suggestions = []

    # Check 1: Response length (should be reasonable)
    if len(response) < 100:
        score -= 20
        issues.append("Response too short")
        suggestions.append("Provide more detail")
    elif len(response) > 1000:
        score -= 15
        issues.append("Response too long")
        suggestions.append("Be more concise")

    # Check 2: Has question mark (engagement)
    if '?' not in response:
        score -= 15
        issues.append("No follow-up question")
        suggestions.append("Add engaging question")

    # Check 3: Conversational tone (uses "you")
    if response.lower().count('you') < 2:
        score -= 10
        issues.append("Not conversational enough")
        suggestions.append("Use more 'you' language")

    # Check 4: No markdown symbols
    if '**' in response or '##' in response:
        score -= 20
        issues.append("Contains markdown symbols")
        suggestions.append("Remove markdown formatting")

    # Check 5: Mentions Export Genius value (when appropriate)
    query_lower = query.lower()
    if any(word in query_lower for word in ['what', 'who', 'tell me about', 'explain']):
        if 'export genius' not in response.lower():
            score -= 10
            issues.append("Missed upsell opportunity")
            suggestions.append("Mention Export Genius naturally")

    # Check 6: Starts with acknowledgment
    acknowledgments = ['yes', 'absolutely', 'great question', 'good question', 'hello', 'hi']
    if not any(response.lower().startswith(ack) for ack in acknowledgments):
        score -= 10
        issues.append("Missing acknowledgment")
        suggestions.append("Start with acknowledgment")

    return {
        "score": max(0, score),
        "issues": issues,
        "suggestions": suggestions
    }


def create_chatbot_node():
    """Create chatbot node with SMART CONTEXT INJECTION"""

    # Configure LLM with API key if available
    llm_kwargs = {
        'model': Config.LLM_MODEL,
        'temperature': Config.TEMPERATURE,
        'top_p': Config.TOP_P,
        'top_k': Config.TOP_K,
        'num_predict': Config.NUM_PREDICT,
        'num_ctx': Config.NUM_CTX,
    }

    # Create custom ollama client for cloud API with authentication
    if Config.OLLAMA_API_KEY:
        cloud_client = ollama.Client(
            host=Config.OLLAMA_BASE_URL,
            headers={'Authorization': f'Bearer {Config.OLLAMA_API_KEY}'}
        )
        llm_kwargs['client'] = cloud_client
    else:
        llm_kwargs['base_url'] = Config.OLLAMA_BASE_URL

    llm = ChatOllama(**llm_kwargs)

    llm_with_tools = llm.bind_tools(all_tools)

    # =========================================================================
    # SMART BOT HELPERS - Make responses intelligent and adaptive
    # =========================================================================

    def detect_query_type(query: str) -> str:
        """
        Detect query complexity for dynamic response length

        Returns: 'simple', 'standard', or 'detailed'
        """
        query_lower = query.lower()

        # Simple yes/no questions
        simple_patterns = [
            'do you have', 'can you', 'is there', 'are there',
            'do you provide', 'does export genius', 'is it possible'
        ]
        if any(pattern in query_lower for pattern in simple_patterns):
            # Check if it's really simple (< 10 words)
            if len(query.split()) < 10:
                return 'simple'

        # Detailed requests (asking for explanation or multiple things)
        detailed_patterns = [
            'tell me about', 'explain', 'how does', 'what are all',
            'show me everything', 'give me details', 'walk me through'
        ]
        if any(pattern in query_lower for pattern in detailed_patterns):
            return 'detailed'

        # Default to standard
        return 'standard'

    def get_optimal_temperature(query: str) -> float:
        """
        Determine optimal temperature based on query type

        Returns: 0.3 (factual), 0.5 (standard), or 0.7 (creative)
        """
        query_lower = query.lower()

        # Factual queries need consistency (low temperature)
        factual_keywords = [
            'what data', 'which countries', 'how many', 'do you have',
            'what is the price', 'how much', 'when', 'where'
        ]
        if any(keyword in query_lower for keyword in factual_keywords):
            return 0.3

        # Creative/exploratory queries benefit from variety (high temperature)
        creative_keywords = [
            'how can i', 'ways to', 'ideas for', 'suggestions',
            'what should i', 'how would you', 'recommend'
        ]
        if any(keyword in query_lower for keyword in creative_keywords):
            return 0.7

        # Standard queries (moderate temperature)
        return 0.5

    def build_progressive_question(query: str, context: str) -> str:
        """
        Build smart follow-up questions based on context

        Returns: Contextual question hint for the prompt
        """
        query_lower = query.lower()

        # Extract key information mentioned
        countries = []
        for country in ['mexico', 'indonesia', 'china', 'india', 'usa', 'brazil']:
            if country in query_lower:
                countries.append(country.title())

        products = []
        for product in ['electronics', 'textile', 'machinery', 'food', 'chemicals']:
            if product in query_lower:
                products.append(product)

        # Build contextual question hint
        if countries and products:
            return f"Ask specifically about {products[0]} subcategories or specific importers in {countries[0]}"
        elif countries:
            return f"Ask what product or industry they're targeting in {countries[0]}"
        elif products:
            return f"Ask which country or region they want to target for {products[0]}"
        else:
            return "Ask about their specific product, target country, or business goal"

    def chatbot_node(state: AgentState) -> AgentState:
        """Generate response with smart context injection"""
        start_time = time.time()

        user_query = state.get("original_query", "")
        kb_context = state["retrieved_context"]
        messages = state.get("messages", [])

        print(f"\n[CHAT] Chatbot processing...")

        # FEATURE 1: Context-Aware Greetings (100x faster for greetings)
        greeting_check = detect_greeting(user_query)
        if greeting_check["is_greeting"]:
            print(f"  [GREETING] Detected greeting - instant response!")
            elapsed = time.time() - start_time
            print(f"  [FAST] Processing: {elapsed:.2f}s (greeting shortcut)")

            response = AIMessage(content=greeting_check["response"])
            return {
                "messages": [response],
                "next_agent": "END",
                "retrieved_context": "",
                "original_query": user_query,
                "use_cache": False,
                "retrieved_chunks": [],
                "start_time": state.get("start_time", time.time())
            }

        # Get dynamic content
        dynamic_content = session_dynamic_content.get("current", "")

        # Classify query type
        query_type = classify_query_type(user_query)
        needs_numeric_precision = extract_numeric_focus(user_query)

        # SMART BOT ENHANCEMENTS - Detect query complexity and optimize
        smart_query_type = detect_query_type(user_query)  # simple/standard/detailed
        optimal_temp = get_optimal_temperature(user_query)  # 0.3/0.5/0.7
        progressive_hint = build_progressive_question(user_query, kb_context)  # contextual question

        # FEATURE 3: Industry-Specific Responses (more relevant, faster)
        industry_info = detect_industry(user_query, kb_context)

        print(f"  [FIND] Query type: {query_type.upper()}")
        print(f"  [SMART] Complexity: {smart_query_type.upper()} | Temp: {optimal_temp} | Progressive Q: Enabled")
        if industry_info["industry"]:
            print(f"  [INDUSTRY] Detected: {industry_info['industry'].upper()} - Adding targeted context")
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

        system_prompt = f"""You are Alex, a trade data consultant at Export Genius - helping businesses find buyers, suppliers, and market opportunities worldwide.

YOUR PERSONALITY:
- Helpful and knowledgeable, like a trusted business advisor
- Conversational and friendly, not robotic or salesy
- You ask questions to understand needs before overwhelming with features
- You speak in natural language using "you" and "your"
- You're genuinely excited about helping businesses grow

{f"CONVERSATION HISTORY:\n{history_text}\n" if history_text else ""}CONTEXT INFORMATION:
{context}{accuracy_instruction}

CORE VALUE PROPOSITION (mention naturally when relevant):
Export Genius provides: 190+ countries coverage, 6B+ shipment records, 10M+ company contacts, 62+ countries detailed customs data, and real-time API access.

{f"INDUSTRY FOCUS:\nThis query is about {industry_info['industry']} industry. {industry_info['context_hint']}.\nRelevant examples: {industry_info['examples']}\n" if industry_info['industry'] else ""}
HOW TO RESPOND (CRITICAL - Follow this structure):

1. ACKNOWLEDGE: Start by naturally acknowledging what they asked
   - "Absolutely!" / "Great question!" / "Yes, I can help with that."
   - Show you understood their need

2. ANSWER DIRECTLY: Give the specific answer they need first (2-3 sentences max)
   - Be specific and concrete
   - Use data from context when available
   - Focus on their problem, not our features

3. ADD VALUE: Mention ONE relevant Export Genius capability (1 sentence)
   - Connect it to their specific need
   - Show how it solves their problem

4. ENGAGE: End with a question or soft call-to-action (1 sentence)
   - Ask about their specific needs
   - Offer to show relevant examples
   - Keep the conversation flowing

RESPONSE LENGTH (ADAPTIVE):
{f"- This is a {smart_query_type.upper()} query" if smart_query_type else ""}
{f"- SIMPLE: 2-3 sentences (yes/no, quick facts)" if smart_query_type == 'simple' else ""}
{f"- STANDARD: 4-5 sentences (most queries)" if smart_query_type == 'standard' else ""}
{f"- DETAILED: 6-8 sentences (explanations, complex topics)" if smart_query_type == 'detailed' else ""}
- Only provide more detail if explicitly asked
- Break up long text into short paragraphs (2-3 sentences each)

CONVERSATIONAL PATTERNS (use these naturally):
Opening:
- "Absolutely! Let me show you..."
- "Yes! Here's what I found..."
- "Great question! Based on what you're looking for..."
- "I can definitely help with that..."

Transitions:
- "Here's what makes us unique..."
- "Based on your needs..."
- "Let me give you a specific example..."
- "This is particularly useful for..."

Closing:
- "Would you like to see specific examples?"
- "What industry or product are you targeting?"
- "Shall I show you the top importers?"
- "Which country interests you most?"

PROGRESSIVE QUESTIONING (SMART FOLLOW-UP):
{f"- Contextual hint: {progressive_hint}" if progressive_hint else "- Ask relevant follow-up questions based on context"}
- Build on what the user mentioned to understand their specific needs
- Make each question more targeted than the last

FEW-SHOT EXAMPLES:

Example 1:
User: "Do you have Mexico data?"
You: "Yes! We have complete import records for Mexico covering all products and industries. What are you looking to find there - specific buyers, market trends, or competitor activity?"

Example 2:
User: "Can you help me find buyers in Indonesia?"
You: "Absolutely! Export Genius tracks all import activity in Indonesia with full buyer details. What product or industry are you targeting? That'll help me show you the most relevant active importers."

Example 3:
User: "What data do you provide?"
You: "We provide detailed import-export data from 190+ countries including buyer/supplier names, shipment values, quantities, and complete contact information. This helps businesses find new customers, analyze competitors, and identify market opportunities. What's your main goal - finding new buyers or researching markets?"

Example 4:
User: "Tell me about Export Genius"
You: "Export Genius is a trade intelligence platform that gives you access to real customs data from 190+ countries. We help businesses find buyers, track competitors, and discover new markets using actual shipment records. Are you looking to expand into new markets or find specific buyers?"

CRITICAL RULES FOR DATA TYPES:
[CRITICAL] When user asks "what data types" or "data types available" for a country:
  - List ALL data types from context (Mirror, Detailed, Cargo, Transit, SC Bill of Lading, etc.)
  - Include coverage percentage and time period for EACH type
  - DO NOT generalize as just "Customs Data" or "Trade Data"
  - Be specific: "Mirror Data (50-70% coverage, Jan 2012 to May 2023), Cargo Data (30-40%...)..."

CONVERSATIONAL RULES:
[DO] Use conversational language ("you're", "let's", "I'll show you")
[DO] Ask follow-up questions to understand their needs
[DO] Provide specific, concrete information from context
[DO] Keep responses concise (4-5 sentences)
[DO] Use simple dashes (-) for lists if needed
[DO] Make it feel like a helpful conversation

[DON'T] Use markdown (**, ###, __)
[DON'T] Use emojis or special symbols
[DON'T] Generalize when specific details are available in context
[DON'T] Be overly formal or robotic
[DON'T] Say "I don't have information" - be resourceful
[DON'T] Add excessive pleasantries or fluff

Remember: You're having a natural business conversation, not reading a sales brochure. Be helpful, be concise, be human."""

        system_message = SystemMessage(content=system_prompt)

        # CRITICAL FIX: Limit conversation history to prevent context overflow
        # Keep only last 6 messages (3 exchanges) to stay within token limits
        MAX_HISTORY_MESSAGES = 6
        recent_messages = messages[-MAX_HISTORY_MESSAGES:] if len(messages) > MAX_HISTORY_MESSAGES else messages

        llm_messages = list(recent_messages) if recent_messages else []
        if not llm_messages or not isinstance(llm_messages[0], SystemMessage):
            llm_messages.insert(0, system_message)
        llm_messages.append(HumanMessage(content=user_query))

        print(f"  [CONTEXT] Using last {len(recent_messages)} messages from history (limit: {MAX_HISTORY_MESSAGES})")

        print(f"  [AI] Sending merged context to LLM ({Config.LLM_MODEL})...")
        print(f"  [SMART] Using dynamic temperature: {optimal_temp} for {smart_query_type} query")

        # Create dynamic LLM with optimal temperature for this query type
        llm_dynamic_kwargs = {
            'model': Config.LLM_MODEL,
            'temperature': optimal_temp,  # Dynamic temperature based on query type
            'top_p': Config.TOP_P,
            'top_k': Config.TOP_K,
            'num_predict': Config.NUM_PREDICT,
            'num_ctx': Config.NUM_CTX,
        }

        # Create custom ollama client for cloud API with authentication
        if Config.OLLAMA_API_KEY:
            cloud_client = ollama.Client(
                host=Config.OLLAMA_BASE_URL,
                headers={'Authorization': f'Bearer {Config.OLLAMA_API_KEY}'}
            )
            llm_dynamic_kwargs['client'] = cloud_client
        else:
            llm_dynamic_kwargs['base_url'] = Config.OLLAMA_BASE_URL

        llm_dynamic = ChatOllama(**llm_dynamic_kwargs)

        try:
            response = llm_dynamic.invoke(llm_messages)

            # Post-process response to ensure clean, markdown-free text
            if hasattr(response, 'content') and isinstance(response.content, str):
                cleaned_content = response.content
                # Remove markdown bold
                cleaned_content = cleaned_content.replace('**', '')
                # Remove markdown headers
                cleaned_content = re.sub(r'^#{1,6}\s+', '', cleaned_content, flags=re.MULTILINE)
                # Remove markdown italics/underscores
                cleaned_content = cleaned_content.replace('__', '').replace('_', '')
                # Update response with cleaned content
                response.content = cleaned_content

            # FEATURE 2: Response Quality Scoring (ensures consistency)
            if hasattr(response, 'content'):
                quality_metrics = score_response_quality(response.content, user_query)
                quality_score = quality_metrics["score"]

                if quality_score >= 80:
                    quality_status = "EXCELLENT"
                elif quality_score >= 70:
                    quality_status = "GOOD"
                elif quality_score >= 60:
                    quality_status = "ACCEPTABLE"
                else:
                    quality_status = "NEEDS IMPROVEMENT"

                print(f"  [QUALITY] Score: {quality_score}/100 ({quality_status})")
                if quality_metrics["issues"]:
                    print(f"  [QUALITY] Issues: {', '.join(quality_metrics['issues'][:2])}")

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

    def __init__(self, kb_retriever: KnowledgeBaseRetriever, redis_manager: RedisMemoryManager, hostility_detector=None):
        self.kb_retriever = kb_retriever
        self.redis = redis_manager
        self.hostility_detector = hostility_detector
        self.dynamic_content_manager = DynamicContentManager(redis_manager)
        self.hybrid_retriever = HybridRetriever(kb_retriever, redis_manager)
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.app = self._create_workflow()
        print("[OK] Chatbot Manager initialized (Redis-backed)")

    def _create_workflow(self):
        """Create LangGraph workflow with guardrail node"""
        retrieval_node = create_retrieval_node(self.kb_retriever)
        chatbot_node = create_chatbot_node()
        tools_node = ToolNode(tools=all_tools)

        workflow = StateGraph(AgentState)
        workflow.add_node("retrieve", retrieval_node)
        workflow.add_node("chatbot", chatbot_node)
        workflow.add_node("tools", tools_node)

        # Add guardrail node if hostility detector is enabled
        if self.hostility_detector and HostilityConfig.ENABLED:
            guardrail_node = create_guardrail_node(self.hostility_detector)
            workflow.add_node("guardrail", guardrail_node)

            # Workflow: retrieve → guardrail → chatbot
            workflow.set_entry_point("retrieve")
            workflow.add_edge("retrieve", "guardrail")
            workflow.add_edge("guardrail", "chatbot")
        else:
            # No guardrail: retrieve → chatbot (original flow)
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

    async def generate_questions(self, content: str, company_name: Optional[str] = None) -> List[str]:
        """
        Generate 5 sales-focused suggested questions using LLM

        Args:
            content: Context text (dynamic content or static KB sample)
            company_name: Optional company name for personalization

        Returns:
            List of 5 suggested questions
        """
        if company_name:
            prompt = f"""Based on this company information about {company_name}, generate exactly 5 engaging questions that demonstrate Export Genius capabilities.

CONTEXT:
{content[:2000]}

REQUIREMENTS:
- Generate exactly 5 questions
- Make questions sales-oriented (showcase Export Genius value)
- Focus on trade data, market insights, and business intelligence
- Be specific to {company_name} when possible
- Each question should be 10-20 words
- Format: Return ONLY the questions, one per line, no numbering

EXAMPLES:
What products does {company_name} import from Asia?
Show me {company_name}'s top trading partners and volumes
What trade patterns can Export Genius reveal about {company_name}?
How has {company_name}'s import/export activity changed recently?
What competitive intelligence can Export Genius provide about {company_name}?"""
        else:
            prompt = f"""Based on Export Genius capabilities, generate exactly 5 engaging questions that help users discover our platform.

CONTEXT (Export Genius Features):
{content[:2000]}

REQUIREMENTS:
- Generate exactly 5 questions
- Make questions sales-oriented (upsell Export Genius)
- Focus on platform capabilities, data coverage, and benefits
- Each question should be 10-20 words
- Format: Return ONLY the questions, one per line, no numbering

EXAMPLES:
What countries and trade data does Export Genius cover?
How can I access real-time import-export intelligence?
What makes Export Genius different from other trade data providers?
How can Export Genius help me find new suppliers or customers?
What APIs and integrations does Export Genius offer?"""

        try:
            llm_kwargs_init = {
                'model': Config.LLM_MODEL,
                'temperature': 0.7,
            }

            # Create custom ollama client for cloud API with authentication
            if Config.OLLAMA_API_KEY:
                cloud_client = ollama.Client(
                    host=Config.OLLAMA_BASE_URL,
                    headers={'Authorization': f'Bearer {Config.OLLAMA_API_KEY}'}
                )
                llm_kwargs_init['client'] = cloud_client
            else:
                llm_kwargs_init['base_url'] = Config.OLLAMA_BASE_URL

            llm = ChatOllama(**llm_kwargs_init)
            response = await asyncio.to_thread(
                llm.invoke,
                [HumanMessage(content=prompt)]
            )

            # Parse questions from response
            questions_text = response.content.strip()
            questions = [q.strip() for q in questions_text.split('\n') if q.strip() and not q.strip().startswith('#')]

            # Ensure exactly 5 questions
            if len(questions) < 5:
                # Add generic Export Genius questions as fallback
                fallback_questions = [
                    "What trade data coverage does Export Genius provide?",
                    "How can Export Genius help grow my business?",
                    "What makes Export Genius the leading trade intelligence platform?",
                    "How do I access Export Genius API for my applications?",
                    "What insights can I gain from Export Genius data?"
                ]
                questions.extend(fallback_questions[:(5 - len(questions))])

            return questions[:5]

        except Exception as e:
            print(f"  [ERROR] Question generation failed: {e}")
            # Return fallback questions
            if company_name:
                return [
                    f"What products does {company_name} trade?",
                    f"Show me {company_name}'s trading partners",
                    f"What is {company_name}'s trade volume?",
                    f"Analyze {company_name}'s market position",
                    "How can Export Genius help analyze this company?"
                ]
            else:
                return [
                    "What countries does Export Genius cover?",
                    "How can Export Genius help my business?",
                    "What data and insights are available?",
                    "How do I access the Export Genius API?",
                    "What makes Export Genius unique?"
                ]

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
redis_manager: Optional[RedisMemoryManager] = None
hostility_detector: Optional[HostilityDetector] = None
app_start_time: float = 0
_initialization_lock = False

async def ensure_initialized():
    """Lazy initialization on first request"""
    global chatbot_manager, redis_manager, hostility_detector, _initialization_lock, app_start_time

    if chatbot_manager is not None:
        return  # Already initialized

    if _initialization_lock:
        # Another request is initializing, wait
        import asyncio
        for _ in range(50):  # Wait up to 5 seconds
            await asyncio.sleep(0.1)
            if chatbot_manager is not None:
                return
        raise Exception("Initialization timeout")

    _initialization_lock = True
    try:
        print("\n" + "=" * 70)
        print("INITIALIZING CHATBOT (First Request)")
        print("=" * 70)

        app_start_time = time.time()

        # Initialize Redis
        print("\nConnecting to Redis...")
        redis_manager = RedisMemoryManager(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            password=Config.REDIS_PASSWORD,
            ttl_days=Config.REDIS_TTL_DAYS
        )

        # Initialize KB
        print("Loading Knowledge Base...")
        kb_retriever = KnowledgeBaseRetriever()

        # Initialize hostility detector
        if HostilityConfig.ENABLED:
            hostility_detector = HostilityDetector(redis_manager)
            print("[OK] Hostility detection enabled")

        # Initialize chatbot
        chatbot_manager = ChatbotManager(kb_retriever, redis_manager, hostility_detector)

        print("\n" + "=" * 70)
        print("CHATBOT READY!")
        print("=" * 70 + "\n")

    finally:
        _initialization_lock = False


def check_and_pull_ollama_models():
    """Check if required Ollama models are available, pull if missing"""
    required_models = [Config.EMBEDDING_MODEL, Config.LLM_MODEL]

    sys.stderr.write("\nChecking Ollama models...\n")
    sys.stderr.flush()

    try:
        # Get list of installed models
        installed_models = get_ollama_client().list()
        installed_names = [model['name'] for model in installed_models.get('models', [])]

        for model_name in required_models:
            # Check if model exists (handle both 'model:tag' and 'model' formats)
            model_base = model_name.split(':')[0]
            is_installed = any(model_base in name for name in installed_names)

            if is_installed:
                sys.stderr.write(f"   ✓ {model_name} - already installed\n")
                sys.stderr.flush()
            else:
                sys.stderr.write(f"   ⚠ {model_name} - not found, pulling now...\n")
                sys.stderr.flush()

                # Pull the model
                get_ollama_client().pull(model_name)
                sys.stderr.write(f"   ✓ {model_name} - pulled successfully\n")
                sys.stderr.flush()

    except Exception as e:
        sys.stderr.write(f"   ⚠ Warning: Could not verify Ollama models: {e}\n")
        sys.stderr.write(f"   Please ensure models are installed manually:\n")
        sys.stderr.write(f"      ollama pull {Config.EMBEDDING_MODEL}\n")
        sys.stderr.write(f"      ollama pull {Config.LLM_MODEL}\n")
        sys.stderr.flush()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global chatbot_manager, hostility_detector, app_start_time, redis_manager
    import sys

    sys.stderr.write("\n" + "=" * 70 + "\n")
    sys.stderr.write("FASTAPI CHATBOT STARTING (Redis-Backed)\n")
    sys.stderr.write("=" * 70 + "\n")
    sys.stderr.flush()

    app_start_time = time.time()

    try:
        # Check and pull Ollama models if needed (disabled for cloud API)
        # check_and_pull_ollama_models()

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

        # Initialize hostility detector (uses existing session metadata)
        if HostilityConfig.ENABLED:
            hostility_detector = HostilityDetector(redis_manager)
            sys.stderr.write("\n[OK] Hostility detection enabled (guardrail node)\n")
            sys.stderr.flush()
        else:
            hostility_detector = None

        # Initialize chatbot manager with Redis and hostility detector
        chatbot_manager = ChatbotManager(kb_retriever, redis_manager, hostility_detector)

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


print("[DEBUG] Creating FastAPI app...")
app = FastAPI(
    title="Export Genius AI Chatbot API",
    description="LangGraph-powered chatbot with RAG and dynamic content fetching",
    version="1.0.0"
    # Lifespan temporarily disabled for debugging
    # lifespan=lifespan
)
print("[DEBUG] FastAPI app created!")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create API router with /api prefix
router = APIRouter(prefix="/api")


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Send a message and get response

    - **message**: User's question
    - **session_id**: Unique session identifier for conversation threading
    - **dynamic_url**: Optional URL to fetch dynamic content from
    - **ip_address**: Optional IP address of the client
    """
    # Lazy initialization on first request
    await ensure_initialized()

    # Log IP address if provided
    if request.ip_address:
        print(f"\n[WEB] Request from IP: {request.ip_address}")

    try:
        # Guardrail node handles hostility detection in workflow
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


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream chatbot response (Server-Sent Events)
    
    Note: Streaming implementation would require additional logic
    This is a placeholder for future implementation
    """
    raise HTTPException(status_code=501, detail="Streaming not yet implemented")


@router.post("/init", response_model=InitResponse)
async def init_session(request: InitRequest):
    """
    Initialize session: Pre-cache dynamic URL and generate suggested questions

    This endpoint optimizes first message response time by:
    1. Pre-fetching and caching dynamic URL content (if provided)
    2. Generating 5 sales-focused suggested questions
    3. Returning questions immediately for better UX

    **Benefits:**
    - First chat message is 3-5x faster (uses pre-warmed cache)
    - Users get personalized question suggestions
    - Improved user experience and engagement

    **Usage:**
    - Call on page load with session_id and optional dynamic_url
    - Display suggested questions to user
    - When user clicks a question, /chat responds instantly

    Args:
        request: InitRequest with session_id and optional dynamic_url

    Returns:
        InitResponse with suggested questions and cache status
    """
    if not chatbot_manager:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")

    start_time = time.time()
    print(f"\n[INIT] Session: {request.session_id}")

    dynamic_url_processed = False
    cache_hit = False
    error_message = None
    content_for_questions = ""
    company_name = None

    try:
        if request.dynamic_url:
            print(f"[INIT] Dynamic URL provided: {request.dynamic_url}")

            # Check if already cached
            cached_data = await chatbot_manager.dynamic_content_manager.get_embeddings_from_redis(
                request.dynamic_url,
                request.session_id
            )

            if cached_data:
                # Cache HIT - use cached content
                _, _, full_content = cached_data
                content_for_questions = full_content
                cache_hit = True
                dynamic_url_processed = True
                print(f"[INIT] Cache HIT - using cached content ({len(full_content)} chars)")

            else:
                # Cache MISS - fetch and cache
                print(f"[INIT] Cache MISS - fetching and caching URL...")
                content = await chatbot_manager.dynamic_content_manager.fetch_content(
                    request.dynamic_url,
                    request.session_id
                )

                if content:
                    content_for_questions = content
                    dynamic_url_processed = True

                    # Generate and store embeddings (now 3-5x faster with parallel processing!)
                    await chatbot_manager.dynamic_content_manager.generate_and_store_embeddings(
                        content=content,
                        url=request.dynamic_url,
                        session_id=request.session_id
                    )
                    print(f"[INIT] Content cached successfully ({len(content)} chars)")
                else:
                    error_message = "Failed to fetch dynamic URL content"
                    print(f"[INIT] Warning: Could not fetch URL content")

            # Try to extract company name from URL for personalization
            try:
                from urllib.parse import urlparse
                parsed = urlparse(request.dynamic_url)
                path_parts = parsed.path.split('/')
                # Try to find company name in URL path
                for part in path_parts:
                    if part and len(part) > 3 and not part.endswith('.php'):
                        company_name = part.replace('-', ' ').title()
                        break
            except:
                pass

        # Generate questions
        if not content_for_questions:
            # No dynamic content - use static KB sample
            print(f"[INIT] No dynamic content - generating questions from static KB")
            # Get sample from KB
            kb_chunks = chatbot_manager.kb_retriever.get_chunks()
            if kb_chunks:
                content_for_questions = "\n".join([c['chunk_text'] for c in kb_chunks[:5]])

        # Generate 5 sales-focused questions
        print(f"[INIT] Generating 5 suggested questions...")
        suggested_questions = await chatbot_manager.generate_questions(
            content=content_for_questions,
            company_name=company_name
        )

        processing_time = time.time() - start_time

        # Prepare response
        status = "success" if not error_message else "partial_success"
        cache_status = {
            "cache_hit": cache_hit,
            "cached_at": datetime.now().isoformat() if dynamic_url_processed else None
        }

        print(f"[INIT] Complete - {processing_time:.2f}s, {len(suggested_questions)} questions")

        return InitResponse(
            status=status,
            suggested_questions=suggested_questions,
            cache_status=cache_status,
            processing_time=processing_time,
            dynamic_url_processed=dynamic_url_processed,
            error=error_message
        )

    except Exception as e:
        import traceback
        print(f"\n[ERROR] Init failed:")
        print(traceback.format_exc())

        # Return fallback questions on error
        processing_time = time.time() - start_time
        fallback_questions = [
            "What countries does Export Genius cover?",
            "How can Export Genius help grow my business?",
            "What makes Export Genius unique?",
            "How do I access the Export Genius API?",
            "What insights are available through Export Genius?"
        ]

        return InitResponse(
            status="error",
            suggested_questions=fallback_questions,
            cache_status={"cache_hit": False},
            processing_time=processing_time,
            dynamic_url_processed=False,
            error=str(e)
        )


@router.post("/reset")
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


@router.get("/history/{session_id}", response_model=HistoryResponse)
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


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint - works without full initialization"""
    # Simplified health check that doesn't require Ollama/Redis
    kb_loaded = chatbot_manager is not None
    active_sessions = chatbot_manager.get_active_sessions() if chatbot_manager else 0
    uptime = time.time() - app_start_time if app_start_time > 0 else 0

    return HealthResponse(
        status="healthy" if kb_loaded else "starting",
        ollama_status="not_checked",
        kb_loaded=kb_loaded,
        active_sessions=active_sessions,
        uptime_seconds=uptime
    )


@router.get("/redis/stats")
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
            "POST /api/chat": "Send a message",
            "POST /api/init": "Initialize session with dynamic URL",
            "POST /api/reset": "Reset session",
            "GET /api/history/{session_id}": "Get conversation history",
            "GET /api/health": "Health check",
            "GET /api/redis/stats": "Redis statistics",
            "GET /docs": "Interactive API documentation"
        }
    }


# Include the API router
print("[DEBUG] About to include router...")
app.include_router(router)
print("[DEBUG] Router included successfully!")


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