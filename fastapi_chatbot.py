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

def format_large_number(value, decimals=2):
    """
    Format large numbers into human-readable format with K, M, B suffixes

    Args:
        value: Number to format (can be int, float, or string)
        decimals: Number of decimal places

    Returns:
        Formatted string (e.g., "1.5M", "3.2B", "450K")
    """
    try:
        # Convert to float if string
        if isinstance(value, str):
            # Remove commas and dollar signs
            value = value.replace(',', '').replace('$', '').strip()
            value = float(value)

        num = float(value)

        # Negative numbers
        sign = '-' if num < 0 else ''
        num = abs(num)

        # Billions
        if num >= 1_000_000_000:
            return f"{sign}{num / 1_000_000_000:.{decimals}f}B"
        # Millions
        elif num >= 1_000_000:
            return f"{sign}{num / 1_000_000:.{decimals}f}M"
        # Thousands
        elif num >= 1_000:
            return f"{sign}{num / 1_000:.{decimals}f}K"
        # Less than 1000
        else:
            return f"{sign}{num:.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)

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

# Import OpenAI embeddings (DISABLED - using local Ollama instead for 10-20x speed boost)
# from openai_embeddings import get_openai_embeddings
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, tools_condition

# Import modular components for prompt building
from chatbot.services.agent.prompts import PromptBuilder, PromptConfig

# Import modular API models
from chatbot.models.api_models import (
    ChatRequest, ChatResponse,
    InitRequest, InitResponse,
    ResetRequest, ResetResponse,
    HistoryResponse, HealthResponse,
    RedisStatsResponse
)

# Import modular utility functions
from chatbot.utils import (
    classify_query_type,
    extract_numeric_focus,
    detect_greeting,
    detect_industry,
    score_response_quality,
    PerformanceMonitor
)
from chatbot.utils.exceptions import DynamicContentError

# Import production-grade retrieval components
from chatbot.services.retrieval.kb_retriever import KnowledgeBaseRetriever as ModularKBRetriever
from chatbot.services.retrieval.hybrid_retriever import HybridRetriever as ModularHybridRetriever
from chatbot.services.retrieval.dynamic_content import DynamicContentManager

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
    # Site identification (for multi-site deployments)
    SITE_ID = os.getenv("SITE_ID", "exportgenius")
    SITE_NAME = os.getenv("SITE_NAME", "Export Genius")

    # Data files (dynamically uses SITE_ID)
    DATA_DIR = Path("data")
    CHUNKS_FILE = Path(os.getenv("KB_CHUNKS_FILE", f"data/kb_{SITE_ID}_chunks.json"))
    FAISS_INDEX_FILE = Path(os.getenv("FAISS_INDEX_FILE", f"data/faiss_{SITE_ID}_normalized.index"))

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
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/api")
    OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "006b1854cb5743d5a8a6e2baf09d163c.NQNQ-X28yY6S7WD0UtAp4_pb")

    # Redis Configuration
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    REDIS_TTL_DAYS = int(os.getenv("REDIS_TTL_DAYS", "7"))

    # Session management
    SESSION_TIMEOUT_MINUTES = 30
    MAX_SESSIONS = 1000

    # Performance optimization
    DISABLE_CHECKPOINTING = os.getenv("DISABLE_CHECKPOINTING", "false").lower() == "true"  # Set to "true" for 10-15s faster responses


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
        """Generate embeddings using LOCAL Ollama (10-20x faster than OpenAI API)"""
        # Use LOCAL Ollama embeddings (nomic-embed-text)
        # This runs on your machine - NO API calls, NO network latency
        model = kwargs.get('model', Config.EMBEDDING_MODEL)
        prompt = kwargs.get('prompt', kwargs.get('input', ''))

        # Use local Ollama client for embeddings (fast!)
        response = self._get_local_client().embeddings(
            model=model,
            prompt=prompt
        )

        # Convert Ollama format to match OpenAI format for compatibility
        # Ollama: {'embedding': [...]}
        # OpenAI: {'embeddings': [[...]]}
        if 'embedding' in response and 'embeddings' not in response:
            response['embeddings'] = [response['embedding']]

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
# PYDANTIC MODELS & MONITORING - NOW USING MODULAR IMPORTS
# ============================================================================
# All models imported from: chatbot.models.api_models
# PerformanceMonitor imported from: chatbot.utils.monitoring
#
# Removed ~100 lines of duplicate model definitions
# ============================================================================
# Create PerformanceMonitor instance (imported from chatbot.utils.monitoring)
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
# DYNAMIC CONTENT MANAGER (Use Modular Version)
# ============================================================================

# Import modular DynamicContentManager that supports both Export Genius and Marketinside APIs
from chatbot.services.retrieval.dynamic_content import DynamicContentManager

# OLD class removed - now using modular version from chatbot/services/retrieval/dynamic_content.py
# The modular version supports:
# - Export Genius API
# - Marketinside API
# - Web scraping fallback
# - File loading

# ============================================================================
# OLD DynamicContentManager class has been completely removed
# It's available in git history if needed for reference

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
        self.max_cache_size = 50  # Reduced from 100 to save ~0.15MB RAM
        
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
            # Extract first embedding from the embeddings array
            query_embedding = np.array([response['embeddings'][0]]).astype('float32')
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

        # Unpack all three values (embeddings, chunks, full_content)
        embeddings, chunks, full_content = cached

        # Create temporary FAISS index
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)

        # Generate query embedding - FIXED: Wrap in asyncio.to_thread
        response = await asyncio.to_thread(
            get_ollama_client().embeddings,
            model=Config.EMBEDDING_MODEL,
            prompt=query
        )
        # Extract first embedding from the embeddings array
        query_embedding = np.array([response['embeddings'][0]]).astype('float32')
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

        # 1. KB Retrieval - FIXED: Wrap in asyncio.to_thread to avoid blocking
        kb_results = await asyncio.to_thread(
            self.kb_retriever.retrieve,
            query,
            top_k=kb_top_k
        )
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
# QUERY HELPERS - NOW USING MODULAR IMPORTS FROM chatbot.utils
# ============================================================================
# classify_query_type() and extract_numeric_focus() now imported from chatbot.utils

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
        'timeout': 30.0,  # CRITICAL FIX: 30 second timeout to prevent hanging (reduced from 60s)
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

        # DEBUG: Log dynamic content status
        print(f"  [DEBUG] Dynamic content length: {len(dynamic_content)} chars")
        if dynamic_content:
            print(f"  [DEBUG] Dynamic content preview: {dynamic_content[:200]}...")
        else:
            print(f"  [DEBUG] WARNING: No dynamic content available!")

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
        print(f"     - KB Context Available: {len(kb_context)} chars")
        print(f"     - Dynamic Content Available: {len(dynamic_content)} chars")
        print(f"     - Merging Strategy: {query_type.upper()}")

        # CRITICAL FIX: If dynamic content is available, ALWAYS use it (regardless of query type)
        # The user has loaded company-specific data, so they want answers about that company
        if dynamic_content:
            # Company data is available → ALWAYS prioritize it
            if query_type == 'company':
                max_dynamic = 2500
                max_kb = 800
            else:
                # For any other query type (including GENERAL), still use dynamic content first
                max_dynamic = 3200
                max_kb = 600

            context = f"""=== COMPANY-SPECIFIC DATA (PRIMARY SOURCE - USE THIS FIRST) ===
{dynamic_content[:max_dynamic]}

=== SUPPLEMENTARY KNOWLEDGE BASE ===
{kb_context[:max_kb]}"""
            print(f"  [OK] MERGED: Company data PRIORITIZED (dynamic={len(dynamic_content[:max_dynamic])} chars, kb={len(kb_context[:max_kb])} chars)")
            print(f"     [RATIO] Dynamic content ratio: {len(dynamic_content[:max_dynamic]) / (len(dynamic_content[:max_dynamic]) + len(kb_context[:max_kb])) * 100:.1f}%")
        else:
            # No dynamic content → Use KB only
            context = kb_context
            print(f"  [DATA] Context: KB only (no dynamic data available)")

        print(f"  [DATA] FINAL CONTEXT SIZE: {len(context)} chars (~{len(context)//4} tokens)")

        # Get conversation history
        conversation_history = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                conversation_history.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                conversation_history.append(f"Assistant: {msg.content}")

        history_text = "\n".join(conversation_history[-4:]) if conversation_history else ""

        # ========================================================================
        # BUILD SYSTEM PROMPT USING MODULAR PromptBuilder
        # All prompt logic now lives in chatbot/services/agent/prompts.py
        # This ensures consistency across all entry points and prevents hallucination
        # ========================================================================
        prompt_config = PromptConfig(
            site_name=Config.SITE_NAME,
            context=context,
            has_dynamic_content=bool(dynamic_content),
            conversation_history=history_text,
            industry_info=industry_info if industry_info['industry'] else None,
            query_type=smart_query_type
        )

        system_prompt = PromptBuilder.build_system_prompt(prompt_config)

        # Add progressive questioning hint (legacy feature support)
        system_prompt += f"""

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
You: "Absolutely! {Config.SITE_NAME} tracks all import activity in Indonesia with full buyer details. What product or industry are you targeting? That'll help me show you the most relevant active importers."

Example 3:
User: "What data do you provide?"
You: "We provide detailed import-export data from 190+ countries including buyer/supplier names, shipment values, quantities, and complete contact information. This helps businesses find new customers, analyze competitors, and identify market opportunities. What's your main goal - finding new buyers or researching markets?"

Example 4:
User: "Tell me about {Config.SITE_NAME}"
You: "{Config.SITE_NAME} is a trade intelligence platform that gives you access to real customs data from 190+ countries. We help businesses find buyers, track competitors, and discover new markets using actual shipment records. Are you looking to expand into new markets or find specific buyers?"

Example 5 (COMPANY DATA):
User: "top buyers?" or "give me names?"
You: "Here are the top buyers for this company:
1. IDEMITSU KOSAN COMPANY LIMITED (Japan) - 67.55% of exports
2. MITSUI CHEMICALS INC - 15.42%
3. PETROCHEMICAL INDUSTRIES CO KSC
4. VIETSEA COMPANY PTE LIMITED (Singapore) - $101.9M
5. PETROLIMEX SINGAPORE PTE LIMITED

Would you like contact details or shipment history for any of these buyers?"

CRITICAL RULES FOR DATA TYPES:
[CRITICAL] When user asks "what data types" or "data types available" for a country:
  - List ALL data types from context (Mirror, Detailed, Cargo, Transit, SC Bill of Lading, Statistical, etc.)
  - If context only shows 1-2 types but you know there could be more, say: "Based on the data I have, we offer [types listed]. For the complete list, I can check our API for you."
  - Include coverage percentage and time period for EACH type
  - DO NOT generalize as just "Customs Data" or "Trade Data"
  - Be specific: "Mirror Data (50-70% coverage, Jan 2012 to May 2023), Transit Data (20-30% coverage, Jul 2020 to Oct 2024), Cargo Data (30-40%...)..."
  - IMPORTANT: If you see Cargo or Transit mentioned in context but not for this specific country, acknowledge that these data types exist for other countries

CONVERSATIONAL RULES:
[DO] Use conversational language ("you're", "let's", "I'll show you")
[DO] Ask follow-up questions to understand their needs
[DO] Provide specific, concrete information from context
[DO] Keep responses concise (4-5 sentences for general queries, can be longer for specific data requests)
[DO] Use simple dashes (-) for lists if needed
[DO] Make it feel like a helpful conversation
[DO] Format large numbers with K (thousand), M (million), B (billion) - e.g., "$1.5M" instead of "$1,500,000"
[DO] Mention data date range when country or trade data is discussed - e.g., "For Argentina imports (Nov 2024 - Oct 2025)..."

[DON'T] Use markdown (**, ###, __)
[DON'T] Use emojis or special symbols
[DON'T] Generalize when specific details are available in context
[DON'T] Be overly formal or robotic
[DON'T] Say "I don't have information" - be resourceful
[DON'T] Add excessive pleasantries or fluff
[DON'T] Show full numbers like "$103,144,094,031.35" - use "$103.1B" instead

RESPONSE LENGTH GUIDELINES:
- General questions (capabilities, services, general info): 4-5 lines maximum
- Specific data requests (top importers, shipments, statistics): Provide full details with formatted numbers
- If user asks vague question about a country (e.g., "tell me about Argentina"), keep it brief (4-5 lines) with key stats and ask what specifically they're looking for

Remember: You're having a natural business conversation, not reading a sales brochure. Be helpful, be concise, be human. Use human-readable numbers (K, M, B) and mention date ranges for context."""

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
            'timeout': 30.0,  # CRITICAL FIX: 30 second timeout to prevent hanging (reduced from 60s)
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

    async def get_country_data_type(self, country_name: str) -> str:
        """Fetch country data_type from /detailed-mirror-countries-list API.
        
        Returns:
            "detailed" if any detailed_* exists for the country, else "mirror"
        """
        import httpx

        api_base = "https://api-dp.marketinsidedata.com/api/v1/users"
        url = f"https://api-dp.marketinsidedata.com/api/v1/users/detailed-mirror-countries-list"

        headers = {
            "Content-Type": "application/json",
            "Origin":"https://www.marketinsidedata.com",
            "accept": "application/json",
            "Authorization": f"Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjMwNzk0OWNiLWZmODItNGVkOS1hNzZhLWMxOGRmOThiZDZkYyIsImlhdCI6MTcwNDU0OTU4MH0.sMR6ZZ52KNkiXG8V-Y6JxjkscCOOEDY7DPEFc5nMU88",
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={}, headers=headers)
            
            if resp.status_code != 200:
                print(f"  [WARN] Country list API returned {resp.status_code}")
                return "mirror"
            
            data = resp.json()
            countries = data.get("data", data) if isinstance(data, dict) else data
            
            if not isinstance(countries, list):
                return "mirror"
            
            # Find matching country (case-insensitive)
            country_lower = (country_name or "").lower().strip()
            if not country_lower:
                return "mirror"

            # If caller provided ISO code, allow matching by code too.
            country_upper = (country_name or "").strip().upper()
            for country in countries:
                if not isinstance(country, dict):
                    continue
                
                c_name = (country.get("country_name") or "").strip().lower()
                c_code = (country.get("country_code") or "").strip().upper()
                if (
                    c_name == country_lower
                    or c_name.replace(" ", "-") == country_lower
                    or (len(country_upper) == 2 and c_code == country_upper)
                ):
                    data_types = country.get("data_type", [])
                    if isinstance(data_types, list):
                        # Check if any detailed_* exists
                        for dt in data_types:
                            if str(dt).startswith("detailed_"):
                                return "detailed"
                    break
            
            return "mirror"
            
        except Exception as e:
            print(f"  [ERROR] Failed to fetch country data_type: {e}")
            return "mirror"

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

        # Use checkpoint saver (in-memory by default for speed)
        if Config.DISABLE_CHECKPOINTING:
            print("[PERF] Checkpointing DISABLED - responses will be 10-15s faster but no conversation history")
            return workflow.compile()  # No checkpointer = faster but no memory
        else:
            # CRITICAL FIX: Use MemorySaver instead of RedisCheckpointSaver
            # MemorySaver is 100x faster (in-memory vs network calls)
            # Trade-off: Lost on restart, but works for session-based conversations
            from langgraph.checkpoint.memory import MemorySaver
            memory = MemorySaver()  # In-memory checkpointing (FAST!)
            print("[PERF] Using MemorySaver (in-memory) for conversation history - responses will be 15-20s faster than Redis")
            return workflow.compile(checkpointer=memory)
        
        # ...existing code...
    async def is_query_related_via_llm(
        self,
        message: str,
        dynamic_url: str,
        dynamic_content: str,
        timeout: float = 8.0,
    ) -> tuple[bool, float, Optional[str]]:
        """\
        Quick LLM classifier+extractor.

        Returns:
            (related, score 0-1, country or None)

        Country is returned ONLY if explicitly mentioned in the user query.
        Falls back to a conservative heuristic on failure.
        """

        def _normalize_space(s: str) -> str:
            return " ".join((s or "").strip().split())

        def _build_country_variant_map() -> Dict[str, str]:
            """Build variant->canonical mapping using UnifiedAPIClient fallback list."""
            variants: Dict[str, str] = {}
            try:
                from chatbot.integrations.apis.unified_api_client import UnifiedAPIClient
                keys = list(getattr(UnifiedAPIClient, "COUNTRY_NAME_TO_ISO", {}).keys())
            except Exception:
                keys = []

            def canonicalize(slug: str) -> str:
                s = (slug or "").strip().lower()
                special = {
                    "usa": "United States",
                    "united-states": "United States",
                    "uk": "United Kingdom",
                    "united-kingdom": "United Kingdom",
                    "uae": "United Arab Emirates",
                    "united-arab-emirates": "United Arab Emirates",
                    "ivory-coast": "Ivory Coast",
                    "south-korea": "South Korea",
                    "north-macedonia": "North Macedonia",
                    "czech-republic": "Czech Republic",
                    "hong-kong": "Hong Kong",
                    "new-zealand": "New Zealand",
                    "sri-lanka": "Sri Lanka",
                }
                if s in special:
                    return special[s]
                return " ".join(part.capitalize() for part in s.replace("-", " ").split())

            for k in keys:
                if not isinstance(k, str) or not k:
                    continue
                canon = canonicalize(k)

                # Common textual variants to match against user query
                variants[k] = canon                       # hyphenated
                variants[k.replace("-", " ")] = canon   # spaced

            # Add extra alias variants for acronyms that users type
            variants["u.s."] = "United States"
            variants["u.s"] = "United States"
            variants["us"] = "United States"
            variants["u.k."] = "United Kingdom"
            variants["u.k"] = "United Kingdom"

            return {k.lower(): v for k, v in variants.items() if k}

        def _extract_country_explicit(query: str) -> Optional[str]:
            """Return a canonical country name only if explicitly present in query."""
            import re

            q = _normalize_space(query).lower()
            if not q:
                return None

            variant_map = getattr(self, "_country_variant_map", None)
            if not isinstance(variant_map, dict) or not variant_map:
                variant_map = _build_country_variant_map()
                self._country_variant_map = variant_map

            # Prefer longest match to avoid partial collisions
            candidates = sorted(variant_map.items(), key=lambda kv: len(kv[0]), reverse=True)
            for variant, canonical in candidates:
                v = variant.strip()
                if not v:
                    continue
                # Word-boundary style match, but safe for multi-word variants.
                pattern = r"(?<![a-z0-9])" + re.escape(v) + r"(?![a-z0-9])"
                if re.search(pattern, q, flags=re.IGNORECASE):
                    return canonical
            return None

        # Build concise prompt (keep content excerpt small)
        excerpt = _normalize_space((dynamic_content or "")[:1200].replace("\n", " "))
        prompt = (
            "You are a strict classifier and extractor.\n\n"
            "Tasks:\n"
            "1. Determine whether the user query is related to the given URL/page content and check country is same as the country in url and the country in query text.\n"
            "2. Extract the country name from the user query IF AND ONLY IF a real country is explicitly mentioned.\n\n"
            "Rules:\n"
            "- Return ONLY valid JSON.\n"
            "- Do not explain.\n"
            "- Do not infer a country unless it is explicitly present in the query text.\n"
            "- If no country is found, return null.\n"
            "- Country name must be properly capitalized (e.g., \"Afghanistan\", not \"afghanistan\").\n\n"
            "Output JSON format:\n"
            "{\n"
            "  \"related\": true | false,\n"
            "  \"score\": number between 0.0 and 1.0,\n"
            "  \"country\": string | null\n"
            "}\n\n"
            f"Inputs:\nQuery: {message}\n\nURL: {dynamic_url}\n\nPage excerpt: {excerpt}"
        )

        try:
            llm = self._get_intent_classifier_llm()
            resp = await asyncio.wait_for(
                asyncio.to_thread(llm.invoke, [HumanMessage(content=prompt)]),
                timeout=timeout,
            )

            text = (getattr(resp, "content", "") or "").strip()
            parsed = self._extract_json_object(text)
            if not isinstance(parsed, dict):
                raise ValueError("Classifier did not return JSON object")

            related = bool(parsed.get("related", False))
            try:
                score = float(parsed.get("score", 0.0))
            except Exception:
                score = 0.0
            score = max(0.0, min(1.0, score))

            country_val = parsed.get("country", None)
            country: Optional[str]
            if isinstance(country_val, str):
                country = _normalize_space(country_val) or None
            else:
                country = None

            # Enforce "explicitly present" rule (avoid LLM hallucinating a country).
            explicit_country = _extract_country_explicit(message)
            if country is not None:
                # Accept only if the returned country aligns with an explicit mention.
                if explicit_country is None:
                    country = None
                else:
                    # If user explicitly mentioned a country, trust that canonical.
                    country = explicit_country

            return related, score, country

        except Exception:
            # Fallback heuristic: token overlap + URL param match
            try:
                from urllib.parse import urlparse, parse_qs

                qparams = parse_qs(urlparse(dynamic_url or "").query) if dynamic_url else {}

                # Extract country from URL
                url_country = qparams.get('country', [''])[0].lower().strip()

                # Extract country from query (look for common country names)
                query_lower = (message or "").lower()

                # List of common countries to check (you can expand this)
                common_countries = [
                    'afghanistan', 'albania', 'algeria', 'argentina', 'australia', 'austria',
                    'bahrain', 'bangladesh', 'belgium', 'bolivia', 'brazil', 'bulgaria',
                    'cambodia', 'canada', 'chile', 'china', 'colombia', 'croatia', 'cuba', 'cyprus',
                    'denmark', 'egypt', 'estonia', 'ethiopia', 'finland', 'france',
                    'germany', 'ghana', 'greece', 'hungary', 'iceland', 'india', 'indonesia',
                    'iran', 'iraq', 'ireland', 'israel', 'italy', 'japan', 'jordan', 'kazakhstan',
                    'kenya', 'kuwait', 'latvia', 'lebanon', 'libya', 'lithuania', 'luxembourg',
                    'malaysia', 'mexico', 'morocco', 'myanmar', 'nepal', 'netherlands', 'nigeria',
                    'norway', 'oman', 'pakistan', 'peru', 'philippines', 'poland', 'portugal',
                    'qatar', 'romania', 'russia', 'saudi arabia', 'serbia', 'singapore', 'slovakia',
                    'slovenia', 'south africa', 'south korea', 'spain', 'sri lanka', 'sudan', 'sweden',
                    'switzerland', 'syria', 'taiwan', 'thailand', 'turkey', 'uganda', 'ukraine',
                    'united arab emirates', 'uae', 'united kingdom', 'uk', 'united states', 'usa',
                    'uruguay', 'uzbekistan', 'venezuela', 'vietnam', 'yemen', 'zambia', 'zimbabwe'
                ]

                # Find country mentioned in query
                query_country = None
                for country in common_countries:
                    # Check for exact word match or handle typos
                    if country in query_lower or query_lower.replace(' ', '') == country.replace(' ', ''):
                        query_country = country.replace(' ', '-')
                        break
                    # Also check with hyphens
                    if country.replace(' ', '-') in query_lower:
                        query_country = country.replace(' ', '-')
                        break

                print(f"  [FALLBACK HEURISTIC] URL country: '{url_country}', Query country: '{query_country}'")

                # CRITICAL: If both countries are identified, they MUST match
                if url_country and query_country:
                    countries_match = (url_country == query_country) or (url_country == query_country.replace('-', ''))
                    if not countries_match:
                        print(f"  [FALLBACK HEURISTIC] ❌ Country mismatch! Query asks about '{query_country}' but cached data is for '{url_country}'. Not related.")
                        return False, 0.0

                # If countries match or can't be determined, check other tokens
                tokens = set(w for w in query_lower.split() if len(w) > 2)
                param_tokens = set()
                for v in qparams.values():
                    for vv in v:
                        param_tokens.update(x for x in vv.lower().split() if len(x) > 2)


                overlap = len(tokens & param_tokens)
                content_overlap = sum(1 for t in tokens if t in (dynamic_content or "").lower())
                score = min(1.0, (overlap * 0.6 + content_overlap * 0.2) / max(1, len(tokens)))
                related = (overlap >= 1) or (content_overlap >= 2)
                country = _extract_country_explicit(message)
                return related, float(score), country
            except Exception:
                return False, 0.0, None

    @staticmethod
    def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
        """Best-effort JSON extraction: parse full text or first {...} block."""
        if not text:
            return None
        text = text.strip()

        try:
            return json.loads(text)
        except Exception:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None

    def _get_intent_classifier_llm(self) -> ChatOllama:
        """
        Lazily create and reuse a deterministic LLM instance for classification.
        Avoids reconstructing clients on every call.
        """
        cached = getattr(self, "_intent_llm", None)
        if cached is not None:
            return cached

        llm_kwargs = {
            "model": Config.LLM_MODEL,
            "temperature": 0.0,
            "timeout": 8.0,
        }

        if Config.OLLAMA_API_KEY:
            cloud_client = ollama.Client(
                host=Config.OLLAMA_BASE_URL,
                headers={"Authorization": f"Bearer {Config.OLLAMA_API_KEY}"},
            )
            llm_kwargs["client"] = cloud_client
        else:
            llm_kwargs["base_url"] = Config.OLLAMA_BASE_URL

        self._intent_llm = ChatOllama(**llm_kwargs)
        return self._intent_llm

    async def _detect_intent_and_entities(self, query: str) -> Dict[str, Any]:
        """
        LLM-based intent + entity extractor.
        Returns dict: {intent, confidence, params}.
        """
        system = """You are an intent-to-URL generator for a trade data application.

You must output ONLY valid JSON.
No explanations. No markdown. No extra text.

Your job:
- Understand the user query
- Decide the correct intent
- Generate the EXACT final URL based on rules below

────────────────────────
INTENTS (ONLY FOUR)
────────────────────────

Choose exactly ONE intent:

1. search_trade_data
   → User wants trade-related records only when product, hscode ,importer or exporter with direction import, export is specified such as:
     - Trade data (import/export)
     - Importers
     - Exporters
     - Suppliers
     - Buyers
   → Output a /search-data/... URL

2. search_country_data
   → User wants high-level country overview data such as:
     - What a country exports or imports
     - Top commodities
     - HS chapters
     - Trade partners
     - Ports
     - Top Exporters (summary)
     - Top Importers (summary)
     - Shipment overview (summary only)
   → Output a /country/... URL

3. country_to_country
   → User asks about trade BETWEEN TWO specific countries
   → Key phrases: "exports TO", "imports FROM", "trade between X and Y"
   → Examples:
     - "Belgium's exports to France"
     - "India's imports from China"
     - "Trade between USA and Mexico"
   → Output a /cntry/... URL

4. hs_code
   → User asks about HS code, chapter, heading, or subheading
   → Key phrases: "HS code", "chapter", "heading"
   → Examples:
     - "India's chapter 01 imports"
     - "Show HS code 8471 data for USA"
     - "Belgium's heading 2710 exports"
   → Output a /chapter/... URL

If unclear, set intent = "unknown" and url = "".

────────────────────────
GLOBAL RULES
────────────────────────

- Output must be valid JSON only
- confidence must be between 0 and 1
- url must be a complete URL or empty string ""
- Do NOT invent missing data
- Country names must be lowercase and URL-safe (use %20 for spaces)
- product must be URL-safe (lowercase, spaces replaced with %20)
- hs_code must be numeric only
- For search_trade_data: Use "import" or "export" (NOT "mirror_import" or "mirror_export")
- For hs_code and country_to_country: Use "import" or "export"
- Default language path: /en/

────────────────────────
INTENT: search_trade_data
────────────────────────

Base URL:
https://www.marketinsidedata.com/en/search-data/

Entity → Endpoint mapping:
- trade     → trade
- importer  → importer
- exporter  → exporter
- supplier  → suppliers
- buyer     → buyers

Direction → type mapping (SMART SELECTION):
- import → "import" (system automatically selects detailed_import if available, else mirror_import)
- export → "export" (system automatically selects detailed_export if available, else mirror_export)

IMPORTANT: Always use "import" or "export" (not "mirror_import" or "mirror_export")
The backend will intelligently choose the best available data type for each country.

URL rules:
- country is REQUIRED
- At least ONE of the following MUST be present: product, hs_code, importer, exporter, origin_country, destination_country
- If NONE of these are present, use search_country_data intent instead (e.g., /country/{country}/imports)
- Do NOT include both product AND hs_code unless user explicitly asks
- If direction is missing, do NOT generate URL (url = "")

Examples of when to use search_trade_data vs search_country_data:

CORRECT - Use search_trade_data (has product):
- "top oil importers in Indonesia" → .../importer?type=import&country=indonesia&product=oil
- "steel exporters in Germany" → .../exporter?type=export&country=germany&product=steel

INCORRECT - Use search_country_data (no product):
- "top importers in Indonesia" → .../country/indonesia/imports (NOT search-data!)
- "all exporters in Albania" → .../country/albania/exports (NOT search-data!)

URL formats:

Trade:
https://www.marketinsidedata.com/en/search-data/trade?type={import|export}&country={country}&product={product}
https://www.marketinsidedata.com/en/search-data/trade?type={import|export}&country={country}&hs_code={hs_code}

Importer:
https://www.marketinsidedata.com/en/search-data/importer?type=import&country={country}&product={product}
https://www.marketinsidedata.com/en/search-data/importer?type=import&country={country}&hs_code={hs_code}

Exporter:
https://www.marketinsidedata.com/en/search-data/exporter?type=export&country={country}&product={product}
https://www.marketinsidedata.com/en/search-data/exporter?type=export&country={country}&hs_code={hs_code}

Supplier:
https://www.marketinsidedata.com/en/search-data/suppliers?type=import&country={country}&product={product}
https://www.marketinsidedata.com/en/search-data/suppliers?type=import&country={country}&hs_code={hs_code}

Buyer:
https://www.marketinsidedata.com/en/search-data/buyers?type=export&country={country}&product={product}
https://www.marketinsidedata.com/en/search-data/buyers?type=export&country={country}&hs_code={hs_code}

────────────────────────
INTENT: search_country_data
────────────────────────

Base URL:
https://www.marketinsidedata.com/en/country/

Rules:
- country is REQUIRED
- No product
- No hs_code
- direction decides imports or exports

URL formats:
https://www.marketinsidedata.com/en/country/{country}/imports
https://www.marketinsidedata.com/en/country/{country}/exports

────────────────────────
INTENT: country_to_country
────────────────────────

Base URL:
https://www.marketinsidedata.com/en/cntry/

Rules:
- TWO countries are REQUIRED (origin and destination)
- direction is REQUIRED (import or export)
- No product
- No hs_code
- Country names must be title case (capitalize first letter of each word)
- Use %20 for spaces in country names

URL Pattern:
https://www.marketinsidedata.com/en/cntry/{OriginCountry}-{import|export}-{DestinationCountry}

Direction Logic:
- If query says "Country A exports TO Country B":
  → origin = Country A, direction = export, destination = Country B
  → URL: /cntry/Country-A-export-Country-B

- If query says "Country A imports FROM Country B":
  → origin = Country A, direction = import, destination = Country B
  → URL: /cntry/Country-A-import-Country-B

Examples:
https://www.marketinsidedata.com/en/cntry/Belgium-export-France
https://www.marketinsidedata.com/en/cntry/India-import-United%20States
https://www.marketinsidedata.com/en/cntry/United%20States-export-Mexico

────────────────────────
INTENT: hs_code
────────────────────────

Base URL:
https://www.marketinsidedata.com/en/chapter/

Rules:
- country is REQUIRED
- direction is REQUIRED (import or export)
- hs_code is REQUIRED (2, 4, 6, or 8+ digits)
- No product
- Country names must be lowercase

URL Pattern:
https://www.marketinsidedata.com/en/chapter/{country}-{import|export}-hs-code-{code}

HS Code Levels:
- 2 digits = Chapter (e.g., 01)
- 4 digits = Heading (e.g., 0101, 8471)
- 6 digits = Subheading (e.g., 010121)
- 8+ digits = Full HS Code (e.g., 84713020)

Examples:
https://www.marketinsidedata.com/en/chapter/india-import-hs-code-01
https://www.marketinsidedata.com/en/chapter/usa-export-hs-code-8471
https://www.marketinsidedata.com/en/chapter/belgium-import-hs-code-271012
https://www.marketinsidedata.com/en/chapter/germany-export-hs-code-84713020

────────────────────────
FINAL OUTPUT FORMAT
────────────────────────

{
  "intent": "",
  "confidence": 0.0,
  "url": ""
}

────────────────────────
IMPORTANT
────────────────────────

- Output JSON only
- Do NOT add params
- Do NOT add explanations
- If required fields are missing, return url = ""
        """
        parsed: Optional[Dict[str, Any]] = None
        try:
            llm = self._get_intent_classifier_llm()
            resp = await asyncio.to_thread(
                llm.invoke,
                [SystemMessage(content=system), HumanMessage(content=f"User query: {query}")],
            )
            parsed = self._extract_json_object((getattr(resp, "content", "") or "").strip())
        except Exception:
            parsed = None

        if not isinstance(parsed, dict):
            return {"intent": "unknown", "confidence": 0.0, "url": {}}

        intent = parsed.get("intent", "unknown")
        if intent not in ("search_country_data", "search_trade_data", "country_to_country", "hs_code", "unknown"):
            intent = "unknown"

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except Exception:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        url = parsed.get("url", "")
        if not isinstance(url, str):
            url = ""

        return {"intent": intent, "confidence": confidence, "url": url}

    async def handle_dynamic_api_call(
        self,
        message: str,
        session_id: str,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Classify message intent + entities and (optionally) call external API.
        Returns a compact JSON string for downstream handling.
        """
        # Prefer explicit extra_data, else session meta
        # dynamic_url = ""
        # if extra_data and isinstance(extra_data, dict):
        #     dynamic_url = (extra_data.get("dynamic_url") or "").strip()

        # if not dynamic_url:
        #     try:
        #         session_meta = self.redis.get_session_meta(session_id) if hasattr(self.redis, "get_session_meta") else {}
        #     except Exception:
        #         session_meta = {}
        #     dynamic_url = (session_meta.get("dynamic_url") or "").strip()

        #0 now need to check whether do we  have mirror data or import data for the country in question

        # direction = await 

        # 1) Detect intent and entities
        intent_result = await self._detect_intent_and_entities(message)
        intent = intent_result["intent"]
        confidence = intent_result["confidence"]
        url = intent_result["url"]

        # Use dynamic_url from extra_data if intent detection didn't find a URL
        if not url and dynamic_url_from_extra:
            url = dynamic_url_from_extra
            print(f"  [INTENT] Using provided dynamic_url: {url[:80]}...")

        print(f"  [INTENT] Detected intent={intent} confidence={confidence:.2f} url={url[:80] if url else ''}")

        payload: Dict[str, Any] = {
            "intent": intent,
            "confidence": confidence,
            "url": url,
        }

        # 2) Optional API augmentation
        #     if API_CLIENT_AVAILABLE and dynamic_url and intent in (
        #     "search_data_product",
        #     "search_data_importers",
        #     "data_availability",
        # ):
        if API_CLIENT_AVAILABLE and intent in (
            "search_country_data",
            "search_trade_data",
            "country_to_country",
            "hs_code",
            "unknown",
        ):
            try:
                fetched = await self.dynamic_content_manager.fetch_content(url, session_id)
                print(f"  [API] Fetched data from external API: {fetched} chars")
                return fetched

            except DynamicContentError as e:
                print(f"  [API] External API call failed (DynamicContentError): {e}")
                print(f"  [API] Falling back to knowledge base")
                payload.update({"source": "intent_only", "dynamic_url": url})
                return ""  # Return empty string on failure
            except Exception as e:
                print(f"  [API] External API call failed: {e}")
                payload.update({"source": "intent_only", "dynamic_url": url})

        # return json.dumps(payload)
    
        
    async def chat(self, message: str, session_id: str, dynamic_url: Optional[str] = None) -> tuple[str, float, List[str]]:
        """
        Process chat message with Redis-backed embeddings

        Returns:
            (response, processing_time, sources_used)
        """
        start_time = time.time()
        print(f"\n{'='*70}")
        print(f"[CHAT START] Session: {session_id}")
        print(f"[CHAT START] Query: {message[:100]}...")
        print(f"{'='*70}")

        # Fetch dynamic content if URL provided
        dynamic_content = ""
        sources_used = ["Knowledge Base"]

        print(f"  [DEBUG] dynamic_url parameter: {dynamic_url}")

        # if dynamic_url:
        print(f"  [DEBUG] [OK] dynamic_url provided in chat()")
        # print(f"  [DEBUG] Looking up cached data for URL: {dynamic_url[:100] if len(dynamic_url) > 100 else dynamic_url}...")

        # Check if embeddings already exist in Redis
        cached_data = await self.dynamic_content_manager.get_embeddings_from_redis(dynamic_url, session_id)

        if cached_data:
            # Extract embeddings, chunks, and full content from cache
            embeddings, chunks, full_content = cached_data
            # dynamic_content = full_content
            related, score, detected_country = await self.is_query_related_via_llm(
                message, dynamic_url or "", full_content
            )
            if detected_country:
                dataType = await self.get_country_data_type(detected_country)
                print(f"  [DATA TYPE] Country={detected_country} -> dataType={dataType}")

            if related and score >= 0.5:
                dynamic_content = full_content
                sources_used.append("Dynamic Content (Redis)")
                print(f"  [DEBUG] Using cached content: {len(full_content)} chars")
            else:
                api_data = await self.handle_dynamic_api_call(message, session_id,extra_data={"data_type": dataType})
                dynamic_content = api_data
                sources_used.append("Dynamic Content")
                print(f"  [DEBUG] LLM determined cached content is NOT related, fetched API data: {api_data}")

            print(f"  [DEBUG] [OK] CACHE HIT - Found cached data: {len(dynamic_content)} chars")
            print(f"  [FAST] Using cached embeddings from Redis")
            print(f"  [CACHE HIT] Content loaded: {len(dynamic_content)} chars")
            # sources_used.append("Dynamic Content (Redis)")
        else:
            print(f"  [DEBUG] [CACHE MISS] - No cached data found")
            # ALWAYS use intent detection for cache misses to generate the correct URL
            # Don't blindly use the provided dynamic_url (could be invalid, truncated, or wrong country)
            try:
                print(f"  [DEBUG] Running intent detection to determine correct URL...")
                api_data = await self.handle_dynamic_api_call(message, session_id, extra_data={"dynamic_url": dynamic_url})
                fetched = api_data or None
                if fetched:
                    print(f"  [DEBUG] Intent detection generated valid URL, fetched: {len(fetched)} chars")
                else:
                    print(f"  [DEBUG] Intent detection returned no data")
            except DynamicContentError as e:
                print(f"  [WARN] Failed to fetch dynamic content (DynamicContentError): {e}")
                print(f"  [INFO] Falling back to knowledge base only")
                fetched = None
            except Exception as e:
                print(f"  [WARN] Failed to call API (Exception): {e}")
                print(f"  [INFO] Falling back to knowledge base only")
                fetched = None
            if fetched:
                related, score, detected_country = await self.is_query_related_via_llm(
                    message, dynamic_url or "", fetched
                )

                if detected_country:
                    dataType = await self.get_country_data_type(detected_country)
                    print(f"  [DATA TYPE] Country={detected_country} -> dataType={dataType}")

                if related and score >= 0.5:
                    dynamic_content = fetched
                    sources_used.append("Dynamic Content")
                    print(f"  [DEBUG] Using fetched content: {len(fetched)} chars")
                else:
                    api_data = await self.handle_dynamic_api_call(
                        message,
                        session_id,
                        extra_data={"data_type": dataType} if dataType else None,
                    )
                    dynamic_content = api_data
                    sources_used.append("Dynamic Content")
                    print(f"  [DEBUG] LLM determined fetched content is NOT related, fetched API data: {api_data}")

                print(f"  [DEBUG] Fetched content -> LLM relevance: {related} (score={score:.2f})")
            else:
                dynamic_content = ""

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

        # Invoke workflow - CRITICAL FIX: Direct invoke (no thread pool overhead)
        print(f"\n[WORKFLOW] Invoking LangGraph workflow...")
        workflow_start = time.time()

        try:
            # CRITICAL FIX: Call invoke() in thread pool with timeout
            # Use run_in_executor for better cancellation than asyncio.to_thread\
            # this will invoke the workflow to get the data from the kb
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,  # Use default thread pool executor
                    lambda: self.app.invoke(
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
                        config
                    )
                ),
                timeout=60.0  # 60 second timeout to allow for Redis checkpoint overhead
            )

            workflow_time = time.time() - workflow_start
            print(f"[WORKFLOW] [OK] Completed in {workflow_time:.2f}s")

            # Detailed performance breakdown
            print(f"[PERF] Workflow breakdown:")
            print(f"  - Total workflow time: {workflow_time:.2f}s")
            print(f"  - Processing time (from start): {time.time() - start_time:.2f}s")

            if workflow_time > 40.0:
                print(f"[WARN] Workflow took {workflow_time:.1f}s (expected <40s)")
                print(f"[WARN] Possible causes:")
                print(f"        1. Redis checkpoint saving is slow (check Redis latency)")
                print(f"        2. LLM API is slow (check Ollama/Deepseek response time)")
                print(f"        3. Network latency (check internet connection)")

        except asyncio.TimeoutError:
            workflow_time = time.time() - workflow_start
            print(f"[WORKFLOW] [FAILED] TIMEOUT after {workflow_time:.1f}s")
            print(f"[ERROR] Workflow exceeded 60s timeout")
            print(f"[DEBUG] Breakdown: chatbot finished around 33s, but workflow took {workflow_time:.1f}s total")
            print(f"[DEBUG] This suggests Redis checkpoint saving is taking 20-30+ seconds")
            print(f"[FIX] Consider:")
            print(f"      1. Using local Redis instead of remote")
            print(f"      2. Disabling checkpointing (lose conversation history)")
            print(f"      3. Using faster Redis instance")
            raise HTTPException(
                status_code=504,
                detail=f"Request timeout after {workflow_time:.1f}s. Redis or network is too slow."
            )
        except Exception as e:
            import traceback
            workflow_time = time.time() - workflow_start
            print(f"\n[ERROR] Workflow invocation failed after {workflow_time:.1f}s:")
            print(traceback.format_exc())

            # Check if it's a timeout-like issueDynamic URL provided:
            if workflow_time > 40.0:
                raise HTTPException(
                    status_code=504,
                    detail=f"Request took too long ({workflow_time:.1f}s). The system is overloaded. Please try again."
                )
            raise

        # Extract response
        response = ""
        if result["messages"]:
            response = result["messages"][-1].content
        else:
            response = "I'm sorry, I couldn't process that request."

        processing_time = time.time() - start_time
        print(f"\n[CHAT END] Total time: {processing_time:.2f}s")
        print(f"{'='*70}\n")

        # Update session info (both in-memory and Redis)
        self.sessions[session_id] = {
            "last_activity": datetime.now(),
            "thread_id": thread_id,
            "message_count": self.sessions.get(session_id, {}).get("message_count", 0) + 1
        }

        return response, processing_time, sources_used

    # async def chat1(self,message:str, session_id:str,dynamic_url:Optional[str]=None) ->tuple[str,float,List[str]]:        
    #     return await self.chat(message,session_id,dynamic_url)

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
                'timeout': 30.0,  # CRITICAL FIX: 30 second timeout for question generation
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
                sys.stderr.write(f"   [OK] {model_name} - already installed\n")
                sys.stderr.flush()
            else:
                sys.stderr.write(f"   [WARN] {model_name} - not found, pulling now...\n")
                sys.stderr.flush()

                # Pull the model
                get_ollama_client().pull(model_name)
                sys.stderr.write(f"   [OK] {model_name} - pulled successfully\n")
                sys.stderr.flush()

    except Exception as e:
        sys.stderr.write(f"   [WARN] Warning: Could not verify Ollama models: {e}\n")
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
        # Debug logging
        print(f"\n[DEBUG] Chat request received:")
        print(f"  - message: {request.message}")
        print(f"  - session_id: {request.session_id}")
        print(f"  - dynamic_url: {request.dynamic_url}")

        # Guardrail node handles hostility detection in workflow
        # Add timeout to prevent indefinite hanging
        try:
            response, processing_time, sources_used = await asyncio.wait_for(
                chatbot_manager.chat(
                    message=request.message,
                    session_id=request.session_id,
                    dynamic_url=request.dynamic_url
                ),
                timeout=90.0  # 90 second max timeout for entire chat operation
            )
        except asyncio.TimeoutError:
            print(f"[ERROR] Chat operation timed out after 90 seconds")
            raise HTTPException(
                status_code=504,
                detail="Request timeout - the AI model took too long to respond. Please try again."
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
        try:
            print(error_details)
        except UnicodeEncodeError:
            # Windows console encoding issue - print without special chars
            print(error_details.encode('ascii', 'ignore').decode('ascii'))
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
    # Lazy initialization on first request
    await ensure_initialized()

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
                try:
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
                except Exception as e:
                    error_message = f"Error fetching URL: {str(e)}"
                    print(f"[INIT] Warning: Error fetching URL - {e}")
                    print(f"[INIT] Will generate generic suggested questions")

            # For search data URLs, pre-fetch country data types for faster processing
            try:
                from urllib.parse import urlparse
                parsed = urlparse(request.dynamic_url)
                if '/search-data/' in parsed.path.lower():
                    # Import the unified client to detect platform and pre-cache country data types
                    try:
                        from chatbot.integrations.apis.unified_api_client import UnifiedAPIClient
                        client = UnifiedAPIClient()
                        platform = client.detect_platform(request.dynamic_url)

                        # Pre-fetch and cache country data types for faster chat responses
                        await client._get_country_data_types(platform)
                        await client.close_all()
                        print(f"[INIT] ✓ Pre-cached country data types for search data URL")
                    except Exception as e:
                        print(f"[INIT] Warning: Could not pre-cache country data types: {e}")
            except:
                pass

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
        # Always return success if we have suggested questions
        # Error message is informational only
        status = "success"
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
            error=error_message,
            session_id=request.session_id  # Include session_id in response
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

    # Check Redis connection
    redis_connected = False
    try:
        if chatbot_manager and chatbot_manager.redis:
            chatbot_manager.redis.client.ping()
            redis_connected = True
    except:
        redis_connected = False

    return HealthResponse(
        status="healthy" if kb_loaded else "starting",
        version="1.0.0",
        redis_connected=True,
        ollama_status="not_checked",
        kb_loaded=kb_loaded,
        # redis_connected=redis_connected,
        # active_sessions=active_sessions,
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