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
import base64
from pathlib import Path
from typing import TypedDict, Annotated, Sequence, Dict, Any, Optional, List
import operator
import sys
import logging
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
    RedisStatsResponse,
    LeadCaptureRequest, LeadCaptureResponse,
    LeadSkipRequest, LeadSkipResponse,
    LeadStatsResponse,
    FeedbackRequest, FeedbackResponse, FeedbackStatsResponse,
    OdooContextRequest, OdooContextResponse,
    VoiceTokenRequest, VoiceTokenResponse,
    VoiceMessageRequest, VoiceMessageResponse,
    VoiceSessionStats,
    CallbackRequest, CallbackResponse, CallStatusUpdate
)

# Import Feedback Service
from chatbot.database.feedback_service import (
    FeedbackService, FeedbackData, FeedbackType,
    get_feedback_service, init_feedback_service
)

# Import Authentication
from chatbot.auth.dependencies import require_auth, require_super_admin, get_auth_db_service
from chatbot.auth.service import AuthService
from chatbot.auth.models import (
    LoginRequest, TokenResponse, RefreshTokenRequest, LogoutRequest,
    CreateUserRequest, UpdateUserRequest, UserResponse, UserListResponse
)

# Import Lead Manager
from lead_manager import LeadManager, get_lead_form_config

# Import Credit and Slot Managers
from chatbot.services.credit_manager import CreditManager, get_credit_manager, init_credit_manager
from chatbot.services.slot_manager import SlotManager, get_slot_manager, init_slot_manager
from chatbot.models.credit_models import (
    CreditState, CreditDeductionResult, CreditExhaustionResponse,
    ContinueChatRequest, ContinueChatResponse
)

# Import Voice Chat Service - Commented out (voice mode disabled for now)
# from chatbot.services.voice_chat_service import VoiceChatService, get_voice_chat_service
# from chatbot.services.twilio_callback_service import get_twilio_callback_service

# Stub functions for voice services (voice mode disabled)
def get_voice_chat_service():
    raise HTTPException(status_code=503, detail="Voice chat feature is currently disabled")

def get_twilio_callback_service():
    raise HTTPException(status_code=503, detail="Callback feature is currently disabled")

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

from decimal import Decimal
from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks, Response, Depends, Form
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import json as json_module


class _DecimalEncoder(json_module.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class DecimalJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json_module.dumps(
            content,
            cls=_DecimalEncoder,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")
import os
from pydantic import BaseModel, Field
import asyncio
from contextlib import asynccontextmanager

# Import Redis memory manager
from redis_memory import RedisMemoryManager, RedisCheckpointSaver

# Import hostility detection
from hostility_detector import HostilityDetector, HostilityConfig

# Import FAQ service for page-specific questions
try:
    from chatbot.database.faq_service import FAQService, get_faq_service, init_faq_service
    FAQ_SERVICE_AVAILABLE = True
except ImportError as e:
    FAQ_SERVICE_AVAILABLE = False
    print(f"[FAQ] FAQ service not available: {e}")

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
    # OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/api")
    # OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "006b1854cb5743d5a8a6e2baf09d163c.NQNQ-X28yY6S7WD0UtAp4_pb")

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

# Global source URL per session (for including in responses)
session_source_url: Dict[str, str] = {}


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


# =========================================================================
# MODULE-LEVEL HELPER (accessible from ChatbotManager streaming)
# =========================================================================

def detect_query_type_simple(query: str) -> str:
    """
    Detect query complexity for dynamic response length (module-level version)

    Returns: 'simple', 'standard', or 'detailed'
    """
    query_lower = query.lower()
    word_count = len(query.split())

    # DATA QUERIES: Even if short, treat as standard if they contain trade-specific terms
    # These queries need full context processing, not brief answers
    data_indicators = [
        'hs code', 'hs ', 'hscode', 'import', 'export', 'buyer', 'supplier',
        'shipment', 'trade', 'turnover', 'country', 'company', 'market',
        # Common country names
        'argentina', 'brazil', 'india', 'china', 'usa', 'mexico', 'germany',
        'japan', 'korea', 'indonesia', 'vietnam', 'thailand', 'philippines',
        'uk', 'france', 'italy', 'spain', 'canada', 'australia', 'russia',
    ]

    if any(indicator in query_lower for indicator in data_indicators):
        # This is a data query - treat as standard even if short
        return 'standard'

    # SIMPLE: Short queries, yes/no, general "about" questions (< 8 words)
    simple_patterns = [
        'do you have', 'can you', 'is there', 'are there',
        'do you provide', 'is it possible',
        'what is mi', 'what is market', 'tell me about mi',
        'tell me about market', 'about mi', 'about market inside',
        'what does mi', 'what do you do', 'who are you',
        'what is this', 'what are you', 'global trade data',
        'mi?', 'market inside?'
    ]
    if any(pattern in query_lower for pattern in simple_patterns) or word_count <= 5:
        return 'simple'

    # Explicit detailed indicators (user WANTS comprehensive info)
    detailed_indicators = [
        ' all ', 'everything', 'comprehensive', 'in detail',
        'complete list', 'full breakdown', 'entire', 'explain in detail'
    ]

    # Complex explanation patterns
    detailed_patterns = [
        'explain how', 'explain why', 'how does it work',
        'show me everything', 'give me all', 'walk me through',
        'break down', 'detailed analysis', 'what are all',
        'list all', 'show all', 'complete breakdown'
    ]

    # Only classify as detailed if EXPLICITLY requested or complex pattern + long query
    has_detailed_indicator = any(ind in query_lower for ind in detailed_indicators)
    has_detailed_pattern = any(pat in query_lower for pat in detailed_patterns)

    if has_detailed_pattern or (has_detailed_indicator and word_count > 8):
        return 'detailed'

    # Standard for most queries
    return 'standard'


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

    # Use local Ollama
    llm_kwargs['base_url'] = "http://localhost:11434"

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
        word_count = len(query.split())

        # DATA QUERIES: Even if short, treat as standard if they contain trade-specific terms
        data_indicators = [
            'hs code', 'hs ', 'hscode', 'import', 'export', 'buyer', 'supplier',
            'shipment', 'trade', 'turnover', 'country', 'company', 'market',
            'argentina', 'brazil', 'india', 'china', 'usa', 'mexico', 'germany',
            'japan', 'korea', 'indonesia', 'vietnam', 'thailand', 'philippines',
            'uk', 'france', 'italy', 'spain', 'canada', 'australia', 'russia',
        ]

        if any(indicator in query_lower for indicator in data_indicators):
            return 'standard'

        # SIMPLE: Short queries, yes/no, general "about" questions (< 8 words)
        simple_patterns = [
            'do you have', 'can you', 'is there', 'are there',
            'do you provide', 'is it possible',
            'what is mi', 'what is market', 'tell me about mi',
            'tell me about market', 'about mi', 'about market inside',
            'what does mi', 'what do you do', 'who are you',
            'what is this', 'what are you', 'global trade data',
            'mi?', 'market inside?'
        ]
        if any(pattern in query_lower for pattern in simple_patterns) or word_count <= 5:
            return 'simple'

        # Explicit detailed indicators (user WANTS comprehensive info)
        detailed_indicators = [
            ' all ', 'everything', 'comprehensive', 'in detail',
            'complete list', 'full breakdown', 'entire', 'explain in detail'
        ]

        # Complex explanation patterns
        detailed_patterns = [
            'explain how', 'explain why', 'how does it work',
            'show me everything', 'give me all', 'walk me through',
            'break down', 'detailed analysis', 'what are all',
            'list all', 'show all', 'complete breakdown'
        ]

        # Only classify as detailed if EXPLICITLY requested or complex pattern + long query
        has_detailed_indicator = any(ind in query_lower for ind in detailed_indicators)
        has_detailed_pattern = any(pat in query_lower for pat in detailed_patterns)

        if has_detailed_pattern or (has_detailed_indicator and word_count > 8):
            return 'detailed'

        # Standard for most queries
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
        global session_source_url  # For including source URL in responses
        start_time = time.time()

        user_query = state.get("original_query", "")
        kb_context = state["retrieved_context"]
        messages = state.get("messages", [])

        # DEBUG: Log message count for troubleshooting
        print(f"  [HISTORY] Chatbot node received {len(messages)} messages from state")

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

        # Get conversation history using smart history manager
        from chatbot.utils.conversation_history_manager import build_conversation_history
        history_text = build_conversation_history(messages)

        # ========================================================================
        # BUILD SYSTEM PROMPT USING MODULAR PromptBuilder
        # All prompt logic now lives in chatbot/services/agent/prompts.py
        # This ensures consistency across all entry points and prevents hallucination
        # ========================================================================
        # Get the source URL for including in response (global declared at top of function)
        current_source_url = session_source_url.get("current", "") if dynamic_content else ""

        prompt_config = PromptConfig(
            site_name=Config.SITE_NAME,
            context=context,
            has_dynamic_content=bool(dynamic_content),
            conversation_history=history_text,
            industry_info=industry_info if industry_info['industry'] else None,
            query_type=smart_query_type,
            source_url=current_source_url  # Include source URL for user to click
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
[DO] Provide specific, concrete information from context
[DO] Format large numbers with K (thousand), M (million), B (billion) - e.g., "$1.5M" instead of "$1,500,000"
[DO] Mention data date range when country or trade data is discussed - e.g., "For Argentina imports (Nov 2024 - Oct 2025)..."

[DON'T] Use markdown (**, ###, __)
[DON'T] Use emojis or special symbols
[DON'T] Be overly formal or robotic
[DON'T] Add excessive pleasantries, fluff, or filler phrases
[DON'T] Repeat yourself or rephrase the same point
[DON'T] Show full numbers like "$103,144,094,031.35" - use "$103.1B" instead

STRICT RESPONSE LENGTH (ENFORCED):
- General/about questions ("what is MI", "tell me about market inside"): 1-2 sentences MAX (20-30 words)
- Standard queries: 2-3 sentences MAX (40-50 words)
- ONLY give longer responses when user explicitly asks for details, stats, or comprehensive info

Remember: Brevity is key. Every word must add value. Shorter responses are ALWAYS better."""

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

        # Use local Ollama
        llm_dynamic_kwargs['base_url'] = "http://localhost:11434"

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
        self._stream_history: Dict[str, List[Dict[str, str]]] = {}  # Conversation history for streaming
        self._stream_context: Dict[str, str] = {}  # Last dynamic content for follow-up questions
        self._last_explore_url: str = ""  # Last explore URL generated for streaming
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

        # Use local Ollama
        llm_kwargs["base_url"] = "http://localhost:11434"

        self._intent_llm = ChatOllama(**llm_kwargs)
        return self._intent_llm

    def _check_greeting_or_general(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Quick check for greeting/general intents without calling LLM.
        Returns result dict if matched, None otherwise.
        """
        query_lower = query.lower().strip()

        # Greeting patterns
        greeting_patterns = [
            "hello", "hi", "hey", "hi there", "hello there",
            "good morning", "good afternoon", "good evening",
            "thanks", "thank you", "thx", "bye", "goodbye",
            "see you", "later", "cheers"
        ]

        for pattern in greeting_patterns:
            if query_lower == pattern or query_lower.startswith(pattern + " "):
                return {
                    "intent": "greeting",
                    "confidence": 1.0,
                    "params": {},
                    "url": ""
                }

        # Very short queries that are likely greetings
        if len(query_lower) < 4 and query_lower in ["hi", "hey", "yo"]:
            return {
                "intent": "greeting",
                "confidence": 1.0,
                "params": {},
                "url": ""
            }

        return None

    async def _detect_intent_and_entities(self, query: str) -> Dict[str, Any]:
        """
        LLM-based intent + entity extractor.
        Returns dict: {intent, confidence, params, missing_params, clarifying_question, url}.
        """
        # First check for greeting/general intents (no LLM needed)
        greeting_result = self._check_greeting_or_general(query)
        if greeting_result:
            return greeting_result

        system = """You are an intent-to-URL generator for a trade data application.

You must output ONLY valid JSON.
No explanations. No markdown. No extra text.

Your job:
- Understand the user query
- Decide the correct intent
- Extract parameters from the query
- Generate the EXACT final URL based on rules below

────────────────────────
INTENTS (SEVEN TOTAL)
────────────────────────

Choose exactly ONE intent:

1. search_trade_data
   → User wants SPECIFIC trade records for a product, hs_code, or named entity:
     - "top importers of [PRODUCT]" (e.g., "top importers of coal", "oil importers")
     - "top exporters of [PRODUCT]" (e.g., "steel exporters", "rice exporters")
     - "[PRODUCT] suppliers" or "[PRODUCT] buyers"
     - Trade data filtered by product or hs_code
   → IMPORTANT: If user mentions a PRODUCT (coal, oil, steel, rice, etc.), use search_trade_data
   → Output a /search-data/... URL

2. search_country_data
   → User wants HIGH-LEVEL country overview (NO specific product):
     - "What does [country] import/export?" (general overview)
     - "Top commodities of [country]"
     - "Trade partners of [country]"
     - "Top importers in [country]" (general, no product specified)
     - "Ports in [country]"
   → IMPORTANT: Only use if NO specific product is mentioned
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

5. general
   → User asks general questions about the platform, pricing, features
   → Questions about "what is Market Inside", "how does it work", "pricing"
   → No URL needed
   → Output url = ""

6. greeting
   → User says hello, hi, thanks, goodbye
   → Simple greetings or pleasantries
   → Output url = ""

7. out_of_scope
   → User asks about non-trade topics
   → Questions completely unrelated to trade data
   → Output url = ""

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

Entity → entity_type param mapping:
- "importers", "top importers" → entity_type: "importer"
- "exporters", "top exporters" → entity_type: "exporter"
- "suppliers" → entity_type: "suppliers"
- "buyers" → entity_type: "buyers"
- "trade data", general → entity_type: "trade"

IMPORTANT: Extract entity_type when user mentions importers/exporters/suppliers/buyers

Direction mapping:
- import → "import"
- export → "export"

URL rules:
- country is REQUIRED (ask if missing)
- At least ONE of: product, hs_code MUST be present for search_trade_data
- If NO product/hs_code, use search_country_data instead
- Default direction to "import" if not specified

CRITICAL EXAMPLES - Use search_trade_data when PRODUCT is mentioned:

"top importers of coal" → params: {product: "coal", entity_type: "importer", direction: "import"}
"top coal importers in India" → params: {country: "india", product: "coal", entity_type: "importer", direction: "import"}
"steel exporters" → params: {product: "steel", entity_type: "exporter", direction: "export"}
"oil suppliers in China" → params: {country: "china", product: "oil", entity_type: "suppliers", direction: "import"}

Use search_country_data when NO product (general overview):
"top importers in Indonesia" → intent: search_country_data (no product!)
"what does India export?" → intent: search_country_data (general overview)

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
- direction is OPTIONAL (defaults to "import" if not specified)

IMPORTANT: If user doesn't specify import/export, default to "import"

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
- hs_code is REQUIRED (2, 4, 6, or 8+ digits)
- direction is OPTIONAL (defaults to "import" if not specified)
- No product
- Country names must be lowercase

URL Pattern:
https://www.marketinsidedata.com/en/chapter/{country}-{import|export}-hs-code-{code}

HS Code Levels:
- 2 digits = Chapter (e.g., 01)
- 4 digits = Heading (e.g., 0101, 8471)
- 6 digits = Subheading (e.g., 010121)
- 8+ digits = Full HS Code (e.g., 84713020)

IMPORTANT: If user doesn't specify import/export, default to "import"

Examples:
https://www.marketinsidedata.com/en/chapter/india-import-hs-code-01
https://www.marketinsidedata.com/en/chapter/usa-export-hs-code-8471
https://www.marketinsidedata.com/en/chapter/belgium-import-hs-code-271012
https://www.marketinsidedata.com/en/chapter/afghanistan-import-hs-code-83

────────────────────────
FINAL OUTPUT FORMAT
────────────────────────

{
  "intent": "",
  "confidence": 0.0,
  "params": {
    "country": "",
    "direction": "",
    "product": "",
    "hs_code": "",
    "origin_country": "",
    "destination_country": "",
    "entity_type": ""
  },
  "url": ""
}

entity_type values (for search_trade_data only):
- "importer" → user asks about importers (e.g., "top importers of coal")
- "exporter" → user asks about exporters (e.g., "steel exporters")
- "suppliers" → user asks about suppliers
- "buyers" → user asks about buyers
- "trade" → general trade data (default if not specified)

────────────────────────
IMPORTANT
────────────────────────

- Output JSON only
- ALWAYS include "params" object with extracted values (empty string if not found)
- Do NOT add explanations
- Extract all params you can find, even if some are missing
- If direction is not specified, set direction to "import" in params (most common use case)
- Generate URL when you have the core required fields (country + hs_code for hs_code intent, etc.)
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
            return {"intent": "unknown", "confidence": 0.0, "params": {}, "url": ""}

        intent = parsed.get("intent", "unknown")
        valid_intents = (
            "search_country_data", "search_trade_data", "country_to_country",
            "hs_code", "general", "greeting", "out_of_scope", "unknown"
        )
        if intent not in valid_intents:
            intent = "unknown"

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except Exception:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        # Extract params from LLM response
        params = parsed.get("params", {})
        if not isinstance(params, dict):
            params = {}

        # Clean up params - remove empty strings
        params = {k: v for k, v in params.items() if v and isinstance(v, str) and v.strip()}

        # Validate country_to_country intent - reject if countries are invalid
        # This prevents invalid country names from being processed further
        if intent == "country_to_country":
            origin = params.get("origin_country", "").lower().strip().replace(" ", "-")
            destination = params.get("destination_country", "").lower().strip().replace(" ", "-")

            # Import slot manager to use its validation
            from chatbot.services.slot_manager import get_slot_manager
            slot_mgr = get_slot_manager()

            # Check if both countries are valid
            origin_valid = slot_mgr.is_valid_country(origin) if origin else False
            destination_valid = slot_mgr.is_valid_country(destination) if destination else False

            if not origin_valid or not destination_valid:
                invalid_countries = []
                if not origin_valid and origin:
                    invalid_countries.append(f"origin='{origin}'")
                if not destination_valid and destination:
                    invalid_countries.append(f"destination='{destination}'")

                print(f"  [INTENT] Rejecting country_to_country: invalid countries {', '.join(invalid_countries)}")
                print(f"  [INTENT] Downgrading to 'unknown' intent - will use KB fallback")

                # Downgrade to unknown intent if countries are invalid
                # This will cause the system to use KB/general response instead of API
                intent = "unknown"
                confidence = 0.0
                params = {}
                # Don't set URL - let it fall through to general handling

        url = parsed.get("url", "")
        if not isinstance(url, str):
            url = ""

        # Fix HS code URLs missing direction - default to "import"
        if intent == "hs_code" and url and "/chapter/" in url:
            # Check if URL is missing import/export direction
            url_lower = url.lower()
            if "-import-" not in url_lower and "-export-" not in url_lower:
                # Extract the last segment (e.g., "argentina-hs-code-83")
                import re
                match = re.search(r'/chapter/([^/]+)$', url)
                if match:
                    segment = match.group(1)
                    # Insert "import" before "hs-code"
                    if "-hs-code-" in segment.lower():
                        fixed_segment = re.sub(
                            r'-hs-code-',
                            '-import-hs-code-',
                            segment,
                            flags=re.IGNORECASE
                        )
                        url = url.replace(segment, fixed_segment)
                        print(f"  [INTENT] Fixed HS code URL (added default direction 'import'): {url}")

        print(f"  [INTENT] Detected: intent={intent}, confidence={confidence:.2f}, params={params}")

        return {"intent": intent, "confidence": confidence, "params": params, "url": url}

    async def handle_dynamic_api_call(
        self,
        message: str,
        session_id: str,
        extra_data: Optional[Dict[str, Any]] = None,
        intent_result: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Classify message intent + entities and (optionally) call external API.
        Returns a compact JSON string for downstream handling.

        Args:
            intent_result: Pre-computed intent result to avoid duplicate LLM calls.
                          If None, intent detection will be performed.
        """
        # Prefer explicit extra_data, else session meta
        dynamic_url_from_extra = ""
        if extra_data and isinstance(extra_data, dict):
            dynamic_url_from_extra = (extra_data.get("dynamic_url") or "").strip()

        # 1) Use pre-computed intent or detect (AVOID DUPLICATE CALLS)
        if intent_result is None:
            intent_result = await self._detect_intent_and_entities(message)
            print(f"  [INTENT] Detected intent (new call)")
        else:
            print(f"  [INTENT] Using pre-computed intent (skipped LLM call)")

        intent = intent_result["intent"]
        confidence = intent_result["confidence"]
        url = intent_result["url"]

        # Use dynamic_url from extra_data if intent detection didn't find a URL
        if not url and dynamic_url_from_extra:
            url = dynamic_url_from_extra
            print(f"  [INTENT] Using provided dynamic_url: {url[:80]}...")

        print(f"  [INTENT] Detected intent={intent} confidence={confidence:.2f} url={url[:80] if url else ''}")

        # Store the detected URL globally for response generation
        global session_source_url
        if url:
            session_source_url["current"] = url
            print(f"  [URL] Stored source URL for response: {url[:80]}...")

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

        # Declare global for source URL tracking
        global session_source_url

        # Fetch dynamic content if URL provided
        dynamic_content = ""
        sources_used = ["Knowledge Base"]

        print(f"  [DEBUG] dynamic_url parameter: {dynamic_url}")

        # OPTIMIZATION: Detect intent ONCE upfront and reuse throughout
        intent_result = await self._detect_intent_and_entities(message)
        print(f"  [INTENT] Detected once: {intent_result['intent']} (confidence: {intent_result['confidence']:.2f})")

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
                # Store the cached URL as source for response generation
                if dynamic_url:
                    session_source_url["current"] = dynamic_url
                    print(f"  [URL] Stored cached URL for response: {dynamic_url[:80]}...")
                print(f"  [DEBUG] Using cached content: {len(full_content)} chars")
            else:
                api_data = await self.handle_dynamic_api_call(message, session_id, extra_data={"data_type": dataType}, intent_result=intent_result)
                dynamic_content = api_data
                sources_used.append("Dynamic Content")
                # URL is stored by handle_dynamic_api_call
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
                print(f"  [DEBUG] Running API call with pre-computed intent...")
                api_data = await self.handle_dynamic_api_call(message, session_id, extra_data={"dynamic_url": dynamic_url}, intent_result=intent_result)
                fetched = api_data or None
                if fetched:
                    print(f"  [DEBUG] API call with pre-computed intent fetched: {len(fetched)} chars")
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
                        intent_result=intent_result,
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

    async def chat_stream(self, message: str, session_id: str, dynamic_url: Optional[str] = None):
        """
        Stream chat response - yields chunks as they're generated by the LLM.

        Enhanced with:
        1. Credit checking (deduct credits, handle exhaustion)
        2. Slot collection (gather missing parameters)
        3. Message persistence (save to Redis)
        4. Dynamic URL generation

        Yields:
            str: Chunks of the response text (JSON SSE format)
        """
        start_time = time.time()
        print(f"\n{'='*70}")
        print(f"[STREAM] Session: {session_id}")
        print(f"[STREAM] Query: {message[:100]}...")
        print(f"{'='*70}")

        # Get credit and slot managers
        from chatbot.services.credit_manager import get_credit_manager
        from chatbot.services.slot_manager import get_slot_manager

        credit_mgr = get_credit_manager(self.redis)
        slot_mgr = get_slot_manager(self.redis)

        # ========================================================================
        # STEP 0: Check if this is an answer to a clarifying question
        # ========================================================================
        prev_state = slot_mgr.get_slots(session_id)
        pending_slot = prev_state.last_asked_slot
        prev_intent = prev_state.intent

        # If we asked for a slot and user gives a short answer, treat it as slot fill
        is_slot_answer = False
        if pending_slot and prev_intent:
            # Short messages (1-3 words) are likely answers to clarifying questions
            word_count = len(message.strip().split())
            if word_count <= 3:
                is_slot_answer = True
                print(f"  [STREAM] Detected slot answer: '{message}' for slot '{pending_slot}' (intent: {prev_intent})")

                # CRITICAL: Validate slot answer before accepting it
                # Reject conversational phrases like "you suggest", "recommend", "any", etc.
                if pending_slot in ["country", "origin_country", "destination_country"]:
                    conversational_phrases = [
                        "you-suggest", "you suggest", "suggest", "any", "all", "anywhere",
                        "everywhere", "all-countries", "multiple", "many", "several",
                        "which", "what", "where", "recommend", "best", "whatever",
                        "doesn't matter", "dont care", "don't care", "idk", "i don't know"
                    ]

                    normalized_answer = message.lower().strip().replace("-", " ")
                    is_conversational = any(phrase in normalized_answer for phrase in conversational_phrases)

                    if is_conversational:
                        print(f"  [STREAM] Rejected conversational response '{message}' for slot '{pending_slot}'")
                        print(f"  [STREAM] User is asking for suggestions, not providing a valid country")

                        # Save user message
                        if self.redis:
                            self.redis.save_message(session_id, {"role": "user", "content": message})

                        # Return a helpful response asking the user to pick a specific country
                        question_text = "I need a specific country name to show you the data. Please choose one of the suggested countries, or type any country you're interested in:"
                        suggestions = ["India", "USA", "China", "Germany", "Indonesia"]

                        # Save assistant response
                        if self.redis:
                            self.redis.save_message(session_id, {
                                "role": "assistant",
                                "content": question_text,
                                "is_clarifying": True
                            })

                        # Yield clarifying question again
                        yield json.dumps({
                            "clarifying_question": True,
                            "question": question_text,
                            "slot_name": pending_slot,
                            "suggestions": suggestions
                        })
                        return

        # ========================================================================
        # STEP 1: Detect intent and extract params
        # ========================================================================
        # Track the query to send to LLM (may differ from raw message for slot answers)
        llm_query = message

        if is_slot_answer:
            # Use previous intent and fill the pending slot
            intent = prev_intent
            params = {pending_slot: message.strip()}
            intent_url = ""

            # Reconstruct a proper query for the LLM based on intent and filled slots
            # This prevents sending just "USA" to the LLM
            prev_slots = prev_state.slots
            if intent == "hs_code":
                hs_code = prev_slots.get("hs_code", "")
                direction = prev_slots.get("direction", "import")
                llm_query = f"Show me HS code {hs_code} {direction} data for {message.strip()}"
            elif intent == "search_country_data":
                direction = prev_slots.get("direction", "import")
                llm_query = f"Show me {direction} data for {message.strip()}"
            elif intent == "search_trade_data":
                product = prev_slots.get("product", "").replace("%20", " ")
                entity_type = prev_slots.get("entity_type", "trade")
                # Handle pluralization - don't add 's' if already ends with 's'
                entity_label = entity_type if entity_type.endswith("s") else f"{entity_type}s"
                if product and product != "my product":
                    llm_query = f"Show me {product} {entity_label} in {message.strip()}"
                else:
                    llm_query = f"Show me {entity_label} in {message.strip()}"
            elif intent == "country_to_country":
                origin = prev_slots.get("origin_country", "")
                destination = prev_slots.get("destination_country", "")
                if pending_slot == "origin_country":
                    llm_query = f"Show me exports from {message.strip()} to {destination}"
                else:
                    llm_query = f"Show me exports from {origin} to {message.strip()}"

            print(f"  [STREAM] Using previous intent '{intent}' with slot fill: {params}")
            print(f"  [STREAM] Reconstructed LLM query: '{llm_query}'")
        else:
            # Normal intent detection
            intent_result = await self._detect_intent_and_entities(message)
            intent = intent_result.get("intent", "unknown")
            params = intent_result.get("params", {})
            intent_url = intent_result.get("url", "")

        print(f"  [STREAM] Intent: {intent}, Params: {params}")

        # ========================================================================
        # STEP 2: Check and deduct credits
        # ========================================================================
        can_proceed, credit_state = credit_mgr.deduct_credits(session_id, intent)

        if not can_proceed:
            # Credits exhausted - yield exhaustion response
            exhaustion = credit_mgr.get_exhaustion_response()
            print(f"  [STREAM] Credits exhausted for session {session_id}")

            # Save user message before returning
            if self.redis:
                self.redis.save_message(session_id, {
                    "role": "user",
                    "content": message
                })

            # Yield credit exhaustion as special response
            yield json.dumps({
                "credit_exhausted": True,
                "message": exhaustion["message"],
                "actions": exhaustion["actions"]
            })
            return

        # ========================================================================
        # STEP 3: Update slots and check for missing params
        # ========================================================================
        # Only check slots for data-specific intents
        data_intents = ["search_trade_data", "search_country_data", "country_to_country", "hs_code"]
        explore_url = ""
        is_continent_query = False  # Flag for continent queries (use KB, not API)
        is_restricted_country = False  # Flag for restricted countries (redirect to support)
        continent_name = ""
        restricted_country_name = ""

        if intent in data_intents:
            # Get previous slots to detect if query changed
            prev_slots = slot_mgr.get_slots(session_id).slots.copy()

            # ================================================================
            # COMPLEX QUERY DETECTION - Check FIRST before any other processing
            # Complex queries (comparisons, multiple countries, trend analysis)
            # should redirect to support/dashboard instead of partial answers
            # ================================================================
            is_complex, complex_reason = slot_mgr.is_complex_query(message, params)
            if is_complex:
                print(f"  [STREAM] Complex query detected: {complex_reason} - redirecting to dashboard/support")

                # Save messages
                if self.redis:
                    self.redis.save_message(session_id, {"role": "user", "content": message})

                # Get response for complex queries (include original query for context)
                complex_response = slot_mgr.get_complex_query_response(complex_reason, message)

                # Save assistant response
                if self.redis:
                    self.redis.save_message(session_id, {
                        "role": "assistant",
                        "content": complex_response["message"]
                    })

                # Use credit_exhausted format to reuse the same UI component
                yield json.dumps({
                    "credit_exhausted": True,  # Reuse the same UI component as connect/support
                    "message": complex_response["message"],
                    "actions": complex_response["actions"],
                    "done": True
                })
                return

            # Check if query mentions a continent BEFORE slot processing
            # Continents should use KB data, not trigger slot questions
            country_param = params.get("country", "")

            # Check for RESTRICTED COUNTRIES (e.g., India)
            if country_param and slot_mgr.is_restricted_country(country_param):
                is_restricted_country = True
                restricted_country_name = slot_mgr.get_restricted_country_name(country_param)
                print(f"  [STREAM] Restricted country detected: {restricted_country_name} - redirecting to support")

                # Save messages
                if self.redis:
                    self.redis.save_message(session_id, {"role": "user", "content": message})

                # Response message
                restricted_message = f"We have comprehensive {restricted_country_name} trade data available on our dashboard! To access {restricted_country_name} import/export data, buyer/supplier information, and detailed shipment records, please connect with our team:"

                # Save assistant response
                if self.redis:
                    self.redis.save_message(session_id, {
                        "role": "assistant",
                        "content": restricted_message
                    })

                # Use credit_exhausted format to reuse the same UI component
                yield json.dumps({
                    "credit_exhausted": True,  # Reuse the same UI component as connect/support
                    "message": restricted_message,
                    "actions": [
                        {"type": "schedule_demo", "label": "Schedule a Demo"},
                        {"type": "chat_with_us", "label": "Chat"},
                        {"type": "whatsapp", "label": "WhatsApp"},
                        {"type": "continue_chat", "label": "Continue Chat"}
                    ],
                    "done": True
                })
                return

            # Check for CONTINENTS
            elif country_param and slot_mgr.is_continent(country_param):
                is_continent_query = True
                continent_name = slot_mgr.get_continent_name(country_param)
                explore_url = "https://www.marketinsidedata.com/en/search-data"
                print(f"  [STREAM] Continent detected early: {continent_name} - skipping slot processing, using KB data")
                # Don't process slots for continent queries - let KB handle it
                slot_state = slot_mgr.get_slots(session_id)  # Get existing state without updating
            else:
                # Normal country query - process slots
                slot_state = slot_mgr.update_slots(session_id, intent, params)

                # Check for missing slots
                missing_question = slot_mgr.get_missing_slot_question(session_id, intent, slot_state.slots)

                if missing_question:
                    # Check if we've asked too many times (loop detection)
                    if missing_question.get("too_many_attempts"):
                        print(f"  [STREAM] Too many attempts for slot: {missing_question['slot_name']}")

                        # Save messages
                        if self.redis:
                            self.redis.save_message(session_id, {"role": "user", "content": message})

                        # Escalate to support options
                        support_message = missing_question.get("message", "I'm having trouble understanding. Let me connect you with our team who can help you better:")

                        # Save assistant response
                        if self.redis:
                            self.redis.save_message(session_id, {
                                "role": "assistant",
                                "content": support_message
                            })

                        # Use credit_exhausted format to reuse the same UI component
                        yield json.dumps({
                            "credit_exhausted": True,  # Reuse the same UI component for support options
                            "message": support_message,
                            "actions": [
                                {"type": "schedule_demo", "label": "Schedule a Demo"},
                                {"type": "chat_with_us", "label": "Chat"},
                                {"type": "whatsapp", "label": "WhatsApp"},
                                {"type": "continue_chat", "label": "Continue Chat"}
                            ],
                            "done": True
                        })
                        return

                    # Need more info - yield clarifying question
                    print(f"  [STREAM] Missing slot: {missing_question['slot_name']}")

                    # Save messages
                    if self.redis:
                        self.redis.save_message(session_id, {"role": "user", "content": message})
                        self.redis.save_message(session_id, {
                            "role": "assistant",
                            "content": missing_question.get("question", ""),
                            "is_clarifying": True
                        })

                    yield json.dumps({
                        "clarifying_question": True,
                        "question": missing_question["question"],
                        "slot_name": missing_question["slot_name"],
                        "suggestions": missing_question.get("suggestions", [])
                    })
                    return

                # All slots collected - generate URL with defaults applied
                explore_url = slot_mgr.generate_url(intent, slot_state.slots) or intent_url
                print(f"  [STREAM] Generated explore_url: {explore_url}")

                # Check if this is a RESTRICTED COUNTRY (redirect to support)
                if explore_url and explore_url.startswith("RESTRICTED:"):
                    restricted_country_name = explore_url.replace("RESTRICTED:", "")
                    print(f"  [STREAM] Restricted country detected: {restricted_country_name} - redirecting to support")

                    # Save messages
                    if self.redis:
                        self.redis.save_message(session_id, {"role": "user", "content": message})

                    # Response message
                    restricted_message = f"We have comprehensive {restricted_country_name} trade data available on our dashboard! To access {restricted_country_name} import/export data, buyer/supplier information, and detailed shipment records, please connect with our team:"

                    # Save assistant response
                    if self.redis:
                        self.redis.save_message(session_id, {
                            "role": "assistant",
                            "content": restricted_message
                        })

                    # Use credit_exhausted format to reuse the same UI component
                    yield json.dumps({
                        "credit_exhausted": True,  # Reuse the same UI component as connect/support
                        "message": restricted_message,
                        "actions": [
                            {"type": "schedule_demo", "label": "Schedule a Demo"},
                            {"type": "chat_with_us", "label": "Chat"},
                            {"type": "whatsapp", "label": "WhatsApp"},
                            {"type": "continue_chat", "label": "Continue Chat"}
                        ],
                        "done": True
                    })
                    return

                # Check if this is a CONTINENT query (use KB data, not API)
                if explore_url and explore_url.startswith("CONTINENT:"):
                    is_continent_query = True
                    continent_name = explore_url.replace("CONTINENT:", "")
                    print(f"  [STREAM] Continent query detected: {continent_name} - using KB data only")
                    # Set explore_url to search-data page for the final link
                    explore_url = "https://www.marketinsidedata.com/en/search-data"

            # Clear cached context if query changed (different intent, country, hs_code, product, etc.)
            # This prevents using old country data when user asks for specific trade data
            # Note: prev_state is captured at the beginning of stream_response
            intent_changed = prev_state.intent and prev_state.intent != intent

            key_slots = ["country", "hs_code", "origin_country", "destination_country", "product"]
            slots_changed = any(
                slot_state.slots.get(k) != prev_slots.get(k)
                for k in key_slots
                if slot_state.slots.get(k)
            )

            query_changed = intent_changed or slots_changed
            print(f"  [STREAM] Context check: prev_intent={prev_state.intent}, new_intent={intent}, intent_changed={intent_changed}, slots_changed={slots_changed}")
            if query_changed:
                # Clear cached context to force fresh API call
                if session_id in self._stream_context:
                    print(f"  [STREAM] Query changed, clearing cached context")
                    del self._stream_context[session_id]
                # Also clear Redis cache for this session to force fresh data
                if self.redis:
                    try:
                        # Clear any cached embeddings for old URLs
                        print(f"  [STREAM] Clearing session cache for fresh data fetch")
                    except Exception as e:
                        print(f"  [STREAM] Cache clear warning: {e}")

        elif intent_url:
            # Use URL from intent detection for non-slot intents
            explore_url = intent_url

        # Initialize history for this session if not exists
        if session_id not in self._stream_history:
            self._stream_history[session_id] = []

        # Get dynamic content (same logic as chat())
        dynamic_content = ""
        global session_source_url

        # Clear source URL for non-data intents (general, greeting, etc.)
        # This prevents showing old data URLs for platform/API questions
        if intent not in data_intents:
            session_source_url["current"] = ""
            print(f"  [STREAM] Cleared source URL for non-data intent: {intent}")

        # Determine which URL to use for data fetching
        # Priority: explore_url from slots (more accurate) > dynamic_url from frontend
        # Only use dynamic_url if it's a valid marketinsidedata.com URL
        # SKIP API calls for continent queries - use KB data instead
        if is_continent_query:
            fetch_url = ""
            print(f"  [STREAM] Continent query - skipping API call, using KB data")
        elif explore_url and not explore_url.startswith("CONTINENT:"):
            fetch_url = explore_url
            print(f"  [STREAM] Using slot-generated URL: {fetch_url}")
        elif dynamic_url and "marketinsidedata.com" in dynamic_url:
            fetch_url = dynamic_url
            print(f"  [STREAM] Using frontend dynamic_url: {fetch_url}")
        else:
            fetch_url = ""
            if dynamic_url:
                print(f"  [STREAM] Ignoring invalid dynamic_url: {dynamic_url}")

        if fetch_url:
            print(f"  [STREAM] Fetching data from URL: {fetch_url}")
            cached_data = await self.dynamic_content_manager.get_embeddings_from_redis(fetch_url, session_id)
            if cached_data:
                _, _, full_content = cached_data
                related, score, _ = await self.is_query_related_via_llm(message, fetch_url, full_content)
                if related and score >= 0.5:
                    dynamic_content = full_content
                    # Store the cached URL as source
                    session_source_url["current"] = fetch_url
                    print(f"  [STREAM] Using cached content: {len(full_content)} chars")
            if not dynamic_content:
                try:
                    # Pass pre-computed intent to avoid duplicate LLM call
                    api_data = await self.handle_dynamic_api_call(
                        message, session_id,
                        extra_data={"dynamic_url": fetch_url},
                        intent_result={"intent": intent, "confidence": 1.0, "url": intent_url, "params": params}
                    )
                    dynamic_content = api_data or ""
                    # URL is stored by handle_dynamic_api_call
                    if dynamic_content:
                        session_source_url["current"] = fetch_url
                except Exception as e:
                    print(f"  [STREAM] API call failed: {e}")

        # For follow-up questions, use cached context from previous query
        if not dynamic_content and session_id in self._stream_context:
            dynamic_content = self._stream_context[session_id]
            print(f"  [STREAM] Using previous context for follow-up: {len(dynamic_content)} chars")

        # Cache successful dynamic content for follow-up questions
        if dynamic_content:
            self._stream_context[session_id] = dynamic_content

        # Get KB context using correct method and field name
        # Use llm_query (reconstructed) for better KB matching
        kb_context = ""
        if self.kb_retriever:
            try:
                kb_results = await asyncio.wait_for(
                    asyncio.to_thread(self.kb_retriever.retrieve, llm_query, 3),
                    timeout=5.0
                )
                # Use 'chunk_text' field (same as main chat function)
                kb_context = "\n".join([doc.get("chunk_text", "") for doc in kb_results[:3]])
                print(f"  [STREAM] KB context retrieved: {len(kb_context)} chars")
            except Exception as e:
                print(f"  [STREAM] KB retrieval failed: {e}")

        # Merge context
        merged_context = ""
        if dynamic_content:
            merged_context = f"DYNAMIC CONTENT:\n{dynamic_content[:2500]}\n\n"
            print(f"  [STREAM] Dynamic content added to context: {len(dynamic_content)} chars")
        else:
            print(f"  [STREAM] WARNING: No dynamic content available!")
        if kb_context:
            merged_context += f"KNOWLEDGE BASE:\n{kb_context[:1500]}"

        print(f"  [STREAM] Total merged context: {len(merged_context)} chars")

        # Build conversation history using smart history manager
        from chatbot.utils.conversation_history_manager import build_conversation_history
        history_messages = self._stream_history[session_id]
        history_text = build_conversation_history(history_messages)

        # DEBUG: Log history context being used
        print(f"  [HISTORY] Building context from {len(history_messages)} messages")
        print(f"  [HISTORY] Generated history: {len(history_text)} chars")
        if history_text:
            # Show first 200 chars of history for debugging
            preview = history_text[:200].replace('\n', ' | ')
            print(f"  [HISTORY] Preview: {preview}...")

        # Detect query type for response length (use llm_query for better detection)
        smart_query_type = detect_query_type_simple(llm_query)

        # ========================================================================
        # BUILD SYSTEM PROMPT USING SAME PromptBuilder AS chat() FUNCTION
        # This ensures consistent, high-quality responses
        # ========================================================================
        # Get the source URL for including in response (global already declared above)
        current_source_url = session_source_url.get("current", "") if dynamic_content else ""

        prompt_config = PromptConfig(
            site_name=Config.SITE_NAME,
            context=merged_context,
            has_dynamic_content=bool(dynamic_content),
            conversation_history=history_text,
            industry_info=None,
            query_type=smart_query_type,
            source_url=current_source_url  # Include source URL for user to click
        )

        system_prompt = PromptBuilder.build_system_prompt(prompt_config)

        # Add progressive questioning and few-shot examples (same as chat())
        system_prompt += f"""

ABSOLUTE FORMAT RULES — NEVER VIOLATE:
FORBIDDEN: "Let's break down" / "Let me analyze" / "## Step 1:" / "## Step 2:" / any "Step X:" headers / numbered analysis (1. Understand... 2. Analyze...) / section headers.
REQUIRED: Start with the direct answer. 1-3 sentences. No structured breakdown. No analytical framing.
WRONG: "Let's break down systematically. ## Step 1: Understand the Data..."
RIGHT: "Vietnam imported $1.2B of HS 94 in 2023, mainly from China. Want more details?"

PROGRESSIVE QUESTIONING (SMART FOLLOW-UP):
- Use conversation history to understand follow-up questions like "list all of them" or "the same"
- Build on what the user mentioned to understand their specific needs

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

Example 4 (COMPANY DATA - List actual names from context):
User: "top buyers?" or "list importers"
You: List the actual company names from the DYNAMIC CONTENT above. Never say "data is locked" if names are visible in context.

CONVERSATIONAL RULES:
[DO] Use conversational language ("you're", "let's", "I'll show you")
[DO] Provide specific, concrete information from context
[DO] Format large numbers with K/M/B (e.g., "$1.5M" instead of "$1,500,000")

[DON'T] Use markdown (**, ###, __)
[DON'T] Use emojis or special symbols
[DON'T] Add excessive pleasantries or fluff


# ### 1. API Products
# We offer 7 specific APIs. If asked "what APIs do you have?", list these:
# - **Global Import-Export Data API**: Full shipment records.
# - **Trade Data Retrieval API**: Targeted search for specific trade events.
# - **Group By Data API**: Aggregated data for analytics.
# - **Company Information API**: Firmographic details.
# - **Company People Details API**: Key contact information.
# - **Supply Chain Analysis API**: Buyer-seller relationship mapping.
# - **HS Code Finder API**: Product classification tools.

# **API Rule:** Do NOT say "We have a RESTful API" as the primary answer. Say "We offer 4 specialized APIs including [list top 2-3]..." Only mention "RESTful" if the user asks about integration or technical specs.

# ### 2. Data License (Offline Delivery)
# Data License is for **bulk data access** delivered OFFLINE.
built from verified Customs Data and Bill of Lading records
# - **Delivery Methods**: SFTP, AWS S3, Snowflake, CSV, Excel.
Work fully offline with clean, structured global trade data designed for procurement, analytics, compliance, government, and consulting teams
# - **CRITICAL DISTINCTION**: Data License is **NOT** the same as the Web Platform. Do not say "access via our platform" for Data License queries. Say "delivered directly to your system via SFTP, AWS, or Snowflake."

# ### 3. Web Platform
Answer according to Home page and Platform pages accurately list down all features of the web platform.
if query is for platform
"""

        # Create LLM for streaming
        llm_kwargs = {
            'model': Config.LLM_MODEL,
            'temperature': 0.5,
            'top_p': Config.TOP_P,
            'num_predict': Config.NUM_PREDICT,
            'num_ctx': Config.NUM_CTX,
            'request_timeout': 90.0,  # 90s timeout to prevent silent hangs
        }

        # Use local Ollama
        llm_kwargs['base_url'] = "http://localhost:11434"

        llm = ChatOllama(**llm_kwargs)

        # Prepare messages - use llm_query (reconstructed for slot answers) instead of raw message
        llm_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=llm_query)
        ]

        print(f"  [STREAM] Starting LLM streaming with {len(history_messages)} history messages...")
        print(f"  [STREAM] LLM query: '{llm_query[:100]}...'" if len(llm_query) > 100 else f"  [STREAM] LLM query: '{llm_query}'")
        chunk_count = 0
        full_response = ""

        try:
            # Stream the response, stripping <think>...</think> reasoning blocks
            raw_accumulated = ""
            yielded_length = 0
            in_think_block = False

            async for chunk in llm.astream(llm_messages):
                if not hasattr(chunk, 'content') or not chunk.content:
                    continue

                raw_accumulated += chunk.content

                # Track open/close think tags to know if we're mid-block
                open_tags = raw_accumulated.count('<think>')
                close_tags = raw_accumulated.count('</think>')
                in_think_block = open_tags > close_tags

                if in_think_block:
                    # Still inside a think block — don't yield anything yet
                    continue

                # Strip all complete <think>...</think> blocks from accumulated text
                import re as _re
                cleaned = _re.sub(r'<think>.*?</think>', '', raw_accumulated, flags=_re.DOTALL).strip()

                # Yield only the new portion we haven't sent yet
                new_content = cleaned[yielded_length:]
                if new_content:
                    chunk_count += 1
                    clean_chunk = new_content.replace('**', '').replace('__', '')
                    full_response += clean_chunk
                    yielded_length += len(new_content)
                    yield clean_chunk

            elapsed = time.time() - start_time
            print(f"  [STREAM] Completed: {chunk_count} chunks in {elapsed:.2f}s")

            # Store this exchange in history
            self._stream_history[session_id].append({"role": "user", "content": message})
            self._stream_history[session_id].append({"role": "assistant", "content": full_response})

            # Keep only last 40 messages (20 exchanges) to prevent memory bloat
            # This matches our history manager configuration
            history_count = len(self._stream_history[session_id])
            if history_count > 40:
                self._stream_history[session_id] = self._stream_history[session_id][-40:]
                print(f"  [HISTORY] Trimmed history: {history_count} -> 40 messages")
            else:
                print(f"  [HISTORY] Stored in history: {history_count} total messages for session {session_id}")

            # ========================================================================
            # STEP 4: Save messages to Redis for persistence
            # ========================================================================
            if self.redis:
                try:
                    self.redis.save_message(session_id, {
                        "role": "user",
                        "content": message
                    })
                    self.redis.save_message(session_id, {
                        "role": "assistant",
                        "content": full_response,
                        "intent": intent,
                        "explore_url": explore_url if explore_url else None
                    })
                    print(f"  [STREAM] Messages saved to Redis")
                except Exception as e:
                    print(f"  [STREAM] Failed to save messages: {e}")

            # ========================================================================
            # STEP 5: Yield stream completion with explore_url
            # ========================================================================
            # The final response with explore_url is yielded by the endpoint handler
            # We store explore_url in instance for the endpoint to use
            self._last_explore_url = explore_url if intent in data_intents else ""

        except Exception as e:
            print(f"  [STREAM] Error during streaming: {e}")
            yield f"\n\nI apologize, but I encountered an error. Please try again."

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

            # Use local Ollama
            llm_kwargs_init['base_url'] = "http://localhost:11434"

            llm = ChatOllama(**llm_kwargs_init)
            response = await asyncio.to_thread(
                llm.invoke,
                [HumanMessage(content=prompt)]
            )

            # Parse questions from response
            questions_text = response.content.strip()
            questions = [q.strip() for q in questions_text.split('\n') if q.strip() and not q.strip().startswith('#')]

            # Ensure exactly 5 questions
            if len(questions) < 3:
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
lead_manager: Optional[LeadManager] = None  # Lead generation manager
credit_manager: Optional[CreditManager] = None  # Credit tracking manager
slot_manager: Optional[SlotManager] = None  # Slot collection manager
faq_service: Optional['FAQService'] = None  # FAQ service for page-specific questions
app_start_time: float = 0
_initialization_lock = False

async def ensure_initialized():
    """Lazy initialization on first request"""
    global chatbot_manager, redis_manager, hostility_detector, lead_manager, credit_manager, slot_manager, faq_service, _initialization_lock, app_start_time

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

        # Initialize lead manager
        lead_manager = LeadManager(redis_manager)
        print("[OK] Lead generation enabled")

        # Initialize credit manager
        credit_manager = init_credit_manager(redis_manager)
        print("[OK] Credit tracking enabled")

        # Initialize slot manager
        slot_manager = init_slot_manager(redis_manager)
        print("[OK] Slot collection enabled")

        # Initialize FAQ service (for page-specific suggested questions)
        if FAQ_SERVICE_AVAILABLE:
            try:
                print("[FAQ] Initializing FAQ service...")
                faq_service = await init_faq_service()
                if faq_service and faq_service.is_available:
                    print("[OK] FAQ service enabled (MySQL)")
                else:
                    print("[INFO] FAQ service unavailable - using LLM fallback")
                    faq_service = None
            except Exception as e:
                print(f"[ERROR] FAQ service init failed: {e}")
                import traceback
                print(traceback.format_exc())
                print("[INFO] Using LLM fallback for question generation")
                faq_service = None
        else:
            print("[INFO] FAQ service module not available - using LLM fallback")
            faq_service = None

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
    global chatbot_manager, hostility_detector, lead_manager, credit_manager, slot_manager, app_start_time, redis_manager
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

        # Initialize lead manager
        lead_manager = LeadManager(redis_manager)
        sys.stderr.write("[OK] Lead generation enabled\n")
        sys.stderr.flush()

        # Initialize credit manager
        credit_manager = init_credit_manager(redis_manager)
        sys.stderr.write("[OK] Credit tracking enabled\n")
        sys.stderr.flush()

        # Initialize slot manager
        slot_manager = init_slot_manager(redis_manager)
        sys.stderr.write("[OK] Slot collection enabled\n")
        sys.stderr.flush()

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
    version="1.0.0",
    default_response_class=DecimalJSONResponse
    # Lifespan temporarily disabled for debugging
    # lifespan=lifespan
)
print("[DEBUG] FastAPI app created!")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

        # Check if we should prompt for lead capture
        lead_prompt = None
        if lead_manager:
            # Get message count from session
            session_info = chatbot_manager.sessions.get(request.session_id, {})
            message_count = session_info.get("message_count", 1)

            # Check if we should prompt
            should_prompt, prompt_type, prompt_message = lead_manager.should_prompt_for_lead(
                session_id=request.session_id,
                message=request.message,
                message_count=message_count
            )

            if should_prompt:
                lead_prompt = get_lead_form_config(prompt_type, prompt_message)
                # Record that we showed a prompt
                lead_manager.record_prompt(request.session_id, message_count, prompt_type)
                print(f"[LEAD] Prompting for lead capture (type: {prompt_type})")

        return ChatResponse(
            response=response,
            session_id=request.session_id,
            processing_time=processing_time,
            sources_used=sources_used,
            lead_prompt=lead_prompt
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


def is_connect_help_intent(message: str) -> bool:
    """
    Check if the user message indicates they want to connect with support/team.
    Returns True if connect/help intent is detected.
    """
    normalized = message.lower().strip()

    connect_keywords = [
        'connect me',
        'connect with',
        'connect to',
        'talk to someone',
        'talk to a person',
        'talk to support',
        'talk to agent',
        'talk to an agent',
        'talk to a agent',
        'talk to human',
        'speak to someone',
        'speak to a person',
        'speak to support',
        'speak to agent',
        'speak with someone',
        'speak with support',
        'human agent',
        'real person',
        'customer support',
        'customer service',
        'contact support',
        'contact team',
        'contact someone',
        'get help',
        'need help',
        'need assistance',
        'need support',
        'i need assistance',
        'i need support',
        'help me connect',
        'can you help',
        'could you help',
        'can you connect',
        'could you connect',
        'would you connect',
        'can i talk',
        'can i speak',
        'can i connect',
        'get in touch',
        'reach out',
        'want to connect',
        'looking to connect',
        'connect me with',
        'put me through',
        'transfer me',
        'live agent',
        'live support',
        'live chat',
        'talk to your team',
        'speak to your team',
        'connect with your team',
        'connect me to your team',
    ]

    for keyword in connect_keywords:
        if keyword in normalized:
            print(f"[CONNECT INTENT] Detected keyword '{keyword}' in message: {message}")
            return True

    return False


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream chatbot response using Server-Sent Events (SSE)

    Returns chunks of the response as they're generated by the LLM.

    Response formats:
    - Normal chunk: data: {"chunk": "text", "done": false}\n\n
    - Final message: data: {"chunk": "", "done": true, "processing_time": 1.23, "explore_url": "..."}\n\n
    - Credit exhausted: data: {"credit_exhausted": true, "message": "...", "actions": [...]}\n\n
    - Clarifying question: data: {"clarifying_question": true, "question": "...", "suggestions": [...]}\n\n
    - Connect support: data: {"credit_exhausted": true, "message": "...", "actions": [...]}\n\n (same format as credit exhausted)
    """
    await ensure_initialized()

    # Check for connect/help intent FIRST - before any LLM processing
    if is_connect_help_intent(request.message):
        print(f"[CHAT STREAM] Connect/help intent detected - returning support options")
        async def connect_support_response():
            response_data = {
                "credit_exhausted": True,  # Reuse the same UI component
                "message": "I'd be happy to connect you with our team! Choose the option that works best for you:",
                "actions": [
                    {"type": "schedule_demo", "label": "Schedule a Demo"},
                    {"type": "chat_with_us", "label": "Chat"},
                    {"type": "whatsapp", "label": "WhatsApp"},
                    {"type": "continue_chat", "label": "Continue Chat"}
                ],
                "done": True
            }
            yield f"data: {json.dumps(response_data)}\n\n"

        return StreamingResponse(
            connect_support_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )

    if not chatbot_manager:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")

    async def generate_stream():
        start_time = time.time()
        full_response = ""

        # Use a queue so we can interleave heartbeat events while the LLM
        # is doing its slow pre-processing (KB retrieval, relatedness check,
        # Ollama model loading). Without heartbeats the browser considers the
        # connection idle and the frontend's AbortController fires too early.
        _SENTINEL = object()
        queue: asyncio.Queue = asyncio.Queue()

        async def _produce():
            try:
                async for chunk in chatbot_manager.chat_stream(
                    message=request.message,
                    session_id=request.session_id,
                    dynamic_url=request.dynamic_url
                ):
                    await queue.put(chunk)
            except Exception as exc:
                await queue.put(exc)
            finally:
                await queue.put(_SENTINEL)

        producer = asyncio.create_task(_produce())

        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=10.0)
                except asyncio.TimeoutError:
                    # LLM is still thinking — send a keepalive so the browser
                    # doesn't close the connection and the JS timeout doesn't fire.
                    yield f"data: {json.dumps({'heartbeat': True})}\n\n"
                    continue

                # Producer finished
                if item is _SENTINEL:
                    break

                # Producer raised an exception
                if isinstance(item, Exception):
                    print(f"[ERROR] Streaming failed: {item}")
                    import traceback as _tb
                    _tb.print_exc()
                    yield f"data: {json.dumps({'error': str(item), 'done': True})}\n\n"
                    return

                chunk = item

                # Check if this is a special JSON response (credit exhaustion or clarifying question)
                chunk_stripped = chunk.strip()
                if chunk_stripped.startswith('{'):
                    try:
                        parsed = json.loads(chunk_stripped)
                        if parsed.get('credit_exhausted'):
                            parsed['done'] = True
                            print(f"  [STREAM] Sending credit exhaustion response: {parsed.get('message', '')[:50]}...")
                            yield f"data: {json.dumps(parsed)}\n\n"
                            return
                        if parsed.get('clarifying_question'):
                            parsed['done'] = True
                            print(f"  [STREAM] Sending clarifying question: {parsed.get('question', '')[:50]}...")
                            yield f"data: {json.dumps(parsed)}\n\n"
                            return
                    except json.JSONDecodeError as e:
                        print(f"  [STREAM] JSON parse error: {e}")

                # Normal text chunk
                full_response += chunk
                yield f"data: {json.dumps({'chunk': chunk, 'done': False})}\n\n"

            # Send final message with completion status and explore URL
            processing_time = time.time() - start_time
            explore_url = getattr(chatbot_manager, '_last_explore_url', '')

            final_data = {
                'chunk': '',
                'done': True,
                'processing_time': processing_time,
                'full_response': full_response
            }

            if explore_url:
                final_data['explore_url'] = explore_url

            yield f"data: {json.dumps(final_data)}\n\n"

        finally:
            producer.cancel()
            try:
                await producer
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.post("/init", response_model=InitResponse)
async def init_session(request: InitRequest):
    """
    Initialize session: Pre-cache dynamic URL and generate suggested questions

    This endpoint optimizes first message response time by:
    1. First trying to get page-specific questions from MySQL (fastest - ~10ms)
    2. Falling back to LLM-generated questions if MySQL unavailable
    3. Pre-fetching and caching dynamic URL content for future chat messages

    **Benefits:**
    - Page-specific questions from MySQL: ~10ms response time
    - First chat message is 3-5x faster (uses pre-warmed cache)
    - Users get relevant question suggestions for their current page

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
    suggested_questions = []
    questions_source = "none"

    try:
        # =====================================================================
        # STEP 1: Try to get questions from FAQ service (MySQL) - FASTEST
        # =====================================================================
        if faq_service and faq_service.is_available and request.dynamic_url:
            try:
                faq_questions = await faq_service.get_suggested_questions(
                    url=request.dynamic_url,
                    limit=5
                )
                if faq_questions and len(faq_questions) > 0:
                    suggested_questions = faq_questions
                    questions_source = "mysql"
                    print(f"[INIT] ✓ Got {len(faq_questions)} questions from MySQL (~10ms)")
            except Exception as e:
                print(f"[INIT] FAQ service error: {e} - will use LLM fallback")

        # =====================================================================
        # STEP 2: Pre-cache dynamic URL content (for future chat messages)
        # This runs even if we got questions from MySQL
        # =====================================================================
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

        # =====================================================================
        # STEP 3: If no questions from MySQL, generate with LLM (fallback)
        # =====================================================================
        if not suggested_questions or len(suggested_questions) == 0:
            # No dynamic content - use static KB sample
            if not content_for_questions:
                print(f"[INIT] No dynamic content - generating questions from static KB")
                kb_chunks = chatbot_manager.kb_retriever.get_chunks()
                if kb_chunks:
                    content_for_questions = "\n".join([c['chunk_text'] for c in kb_chunks[:5]])

            # Generate 5 sales-focused questions using LLM
            print(f"[INIT] Generating 5 suggested questions via LLM...")
            suggested_questions = await chatbot_manager.generate_questions(
                content=content_for_questions,
                company_name=company_name
            )
            questions_source = "llm"

        processing_time = time.time() - start_time

        # Prepare response
        status = "success"
        cache_status = {
            "cache_hit": cache_hit,
            "cached_at": datetime.now().isoformat() if dynamic_url_processed else None,
            "questions_source": questions_source  # Track where questions came from
        }

        print(f"[INIT] Complete - {processing_time:.2f}s, {len(suggested_questions)} questions (source: {questions_source})")

        firstThree = suggested_questions[:3]

        # Save suggested questions to Redis for persistence across refresh
        if redis_manager and firstThree:
            redis_manager.save_suggested_questions(request.session_id, firstThree)

        return InitResponse(
            status=status,
            suggested_questions=firstThree,
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
            "What countries does Market Inside cover?",
            "How can Market Inside help grow my business?",
            "What makes Market Inside unique?",
            "How do I access the Market Inside API?",
            "What insights are available through Market Inside?"
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

    return DecimalJSONResponse(
        content={
            "status": "success",
            "message": f"Session {request.session_id} reset successfully"
        }
    )


# ============================================================================
# LEAD CAPTURE ENDPOINTS
# ============================================================================

@router.post("/lead/capture", response_model=LeadCaptureResponse)
async def capture_lead(request: LeadCaptureRequest):
    """
    Capture lead information from user

    - **session_id**: Session identifier
    - **email**: User's email address (required)
    - **phone**: User's phone number (optional)
    - **company_name**: User's company name (optional)
    - **name**: User's name (optional)
    - **source_url**: Page URL where lead was captured (optional)
    """
    await ensure_initialized()

    if not lead_manager:
        raise HTTPException(status_code=503, detail="Lead manager not initialized")

    # Validate and save lead
    success, message = lead_manager.save_lead(
        session_id=request.session_id,
        email=request.email,
        phone=request.phone,
        company_name=request.company_name,
        name=request.name,
        source_url=request.source_url
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return LeadCaptureResponse(
        status="success",
        message="Thank you! I'll send you personalized insights.",
        session_id=request.session_id
    )


@router.post("/lead/skip", response_model=LeadSkipResponse)
async def skip_lead(request: LeadSkipRequest):
    """
    Record that user skipped the lead form

    - **session_id**: Session identifier
    """
    await ensure_initialized()

    if not lead_manager:
        raise HTTPException(status_code=503, detail="Lead manager not initialized")

    # Record the skip
    lead_manager.record_skip(request.session_id)

    return LeadSkipResponse(
        status="success",
        message="No problem! Let me know if you change your mind."
    )


@router.get("/lead/stats", response_model=LeadStatsResponse)
async def get_lead_stats(include_leads: bool = False, limit: int = 100):
    """
    Get lead capture statistics (admin endpoint)

    - **include_leads**: If true, include list of leads
    - **limit**: Maximum number of leads to return
    """
    await ensure_initialized()

    if not lead_manager:
        raise HTTPException(status_code=503, detail="Lead manager not initialized")

    stats = lead_manager.get_lead_stats()

    leads = None
    if include_leads:
        leads = lead_manager.get_all_leads(limit=limit)

    return LeadStatsResponse(
        total_leads=stats.get("total_leads", 0),
        leads=leads
    )


@router.get("/lead/{session_id}")
async def get_lead(session_id: str):
    """
    Get lead info for a specific session

    - **session_id**: Session identifier
    """
    await ensure_initialized()

    if not lead_manager:
        raise HTTPException(status_code=503, detail="Lead manager not initialized")

    lead = lead_manager.get_lead(session_id)

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found for this session")

    return lead


@router.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 50):
    """
    Get conversation history for a session.

    Returns messages persisted in Redis for page refresh recovery.

    - **session_id**: Session identifier
    - **limit**: Maximum number of messages to return (default: 50)
    """
    await ensure_initialized()

    if not redis_manager:
        raise HTTPException(status_code=503, detail="Redis not initialized")

    try:
        # Get messages from Redis
        messages = redis_manager.get_messages(session_id, limit=limit)

        # Get suggested questions if available
        suggested_questions = redis_manager.get_suggested_questions(session_id)

        # Check if session is active (has messages within TTL)
        session_active = len(messages) > 0

        return DecimalJSONResponse(content={
            "session_id": session_id,
            "messages": messages,
            "total_messages": len(messages),
            "suggested_questions": suggested_questions,
            "session_active": session_active
        })

    except Exception as e:
        print(f"[ERROR] History retrieval failed: {e}")
        return DecimalJSONResponse(content={
            "session_id": session_id,
            "messages": [],
            "total_messages": 0,
            "suggested_questions": [],
            "session_active": False
        })


@router.post("/continue-chat")
async def continue_chat(session_id: str):
    """
    Activate continue chat mode after credit exhaustion.

    Grants additional credits at 2x cost per query.

    - **session_id**: Session identifier (query parameter)
    """
    await ensure_initialized()

    if not credit_manager:
        raise HTTPException(status_code=503, detail="Credit manager not initialized")

    try:
        # Activate continue chat mode
        state = credit_manager.activate_continue_chat(session_id)

        return DecimalJSONResponse(content={
            "status": "success",
            "credits_remaining": state.get("remaining", 0),
            "message": "I'm happy to continue helping you explore our trade data. What would you like to know?"
        })

    except Exception as e:
        print(f"[ERROR] Continue chat failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to activate continue chat: {str(e)}")


@router.post("/odoo/send-context", response_model=OdooContextResponse)
async def send_context_to_odoo(request: OdooContextRequest):
    """
    Send chatbot conversation history to Odoo live chat as context.
    
    This endpoint:
    1. Fetches conversation history from Redis
    2. Formats it nicely for Odoo chat
    3. Sends it as a message in the Odoo live chat channel
    4. Returns success status (always allows opening Odoo chat even if sending fails)
    
    - **session_id**: Chatbot session identifier
    """
    await ensure_initialized()

    if not redis_manager:
        return OdooContextResponse(
            success=False,
            message="Redis not initialized",
            history_sent=False,
            message_count=0,
            error="Redis service unavailable"
        )

    try:
        guest_token = getattr(request, 'guest_token', None)
        channel_id_override = getattr(request, 'channel_id', None)
        print(f"[ODOO] /odoo/send-context called — session={request.session_id}, channel_id={channel_id_override}, guest_token={'***' if guest_token else 'NOT SET'}")

        # 1. Fetch conversation history
        messages = redis_manager.get_messages(request.session_id, limit=50)
        print(f"[ODOO] Messages in Redis for session: {messages}")

        if not messages:
            # No chat history, but if we have guest_token+channel_id we can still send the transfer message
            # if guest_token and channel_id_override:
                print(f"[ODOO] No history — sending transfer-only message via backend to channel {channel_id_override}")
                odoo_result = await _send_to_odoo_api(
                    "<b>🔄 Transferring to a live agent...</b>",
                    guest_token=guest_token,
                    channel_id_override=channel_id_override
                )
                return OdooContextResponse(
                    success=odoo_result.get("success", False),
                    message=odoo_result.get("message", "Transfer message sent (no chat history)"),
                    history_sent=False,
                    message_count=0,
                    odoo_channel_id=channel_id_override,
                    error=odoo_result.get("error")
                )
            # else:
            #     print(f"[ODOO] No history and no guest_token — nothing to send")
            #     return OdooContextResponse(
            #         success=True,
            #         message="No conversation history to send",
            #         history_sent=False,
            #         message_count=0,
            #         odoo_channel_id=None,
            #         error=None
            #     )

        # 2. Format conversation history for Odoo
        formatted_history = _format_history_for_odoo(messages)
        print(f"[ODOO] Formatted history ({len(messages)} msgs):\n{formatted_history[:500]}")

        if not formatted_history:
            print(f"[ODOO] Formatted history is empty — sending transfer-only message")
            formatted_history = "<b>🔄 Transferring to a live agent...</b><br><br><i>(No readable chat history available)</i>"

        # 3. Send to Odoo using guest_token + channel_id from the frontend get_session response
        odoo_result = await _send_to_odoo_api(formatted_history, guest_token=guest_token, channel_id_override=channel_id_override)

        return OdooContextResponse(
            success=odoo_result.get("success", False),
            message=odoo_result.get("message", "Context sent to Odoo"),
            history_sent=True,
            message_count=len(messages),
            odoo_channel_id=odoo_result.get("channel_id") or channel_id_override,
            error=odoo_result.get("error")
        )

    except Exception as e:
        print(f"[ODOO] Error sending context: {e}")
        import traceback
        traceback.print_exc()
        
        # Return success: False but allow client to still open Odoo chat
        return OdooContextResponse(
            success=False,
            message="Failed to send context, but Odoo chat will still open",
            history_sent=False,
            message_count=0,
            error=str(e)
        )


def _format_history_for_odoo(messages: List[Dict[str, Any]]) -> str:
    """
    Format conversation history as HTML for Odoo chat.

    Handles the actual Redis message structure:
    {
        "role": "user" | "assistant",
        "content": "...",          # primary field
        "text": "...",             # fallback field (older sessions)
        "timestamp": "...",
        "message_id": "...",
        "is_clarifying": bool,
        "intent": "...",
        "explore_url": "..."
    }

    Returns HTML string so Odoo renders bold labels, line breaks, etc.
    """
    import re

    formatted_blocks = []

    for msg in messages:
        role = msg.get("role", "unknown").capitalize()
        # Messages from Redis use "content"; older sessions may use "text"
        text = (msg.get("content") or msg.get("text") or "").strip()

        if not text:
            continue

        # Clean up markdown links  [label](url) → label
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # Remove bare URLs (http/https)
        text = re.sub(r'https?://\S+', '', text).strip()
        # Collapse extra blank lines left by URL removal
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        if not text:
            continue

        # Convert newlines to <br> for HTML rendering
        text_html = text.replace('\n', '<br>')

        if role == "Assistant":
            if msg.get("is_clarifying"):
                label_html = '<b>🤖 AI [clarifying]:</b>'
            else:
                label_html = '<b>🤖 AI:</b>'
        else:
            label_html = '<b>👤 User:</b>'

        formatted_blocks.append(f"{label_html} {text_html}")

    if not formatted_blocks:
        return ""

    # Join messages with a visible divider line between each turn
    body = '<br><hr style="border:none;border-top:1px solid #ccc;margin:6px 0;">'.join(formatted_blocks)

    header = (
        '<b>═══ 🤖 AI Chatbot Conversation History ═══</b><br><br>'
    )
    footer = (
        '<br><br><b>═══ End of History ═══</b>'
        '<br><br>'
        '<b>🔄 Transferring to a live agent...</b>'
    )

    return header + body + footer



async def _send_to_odoo_api(context_message: str, guest_token: Optional[str] = None, channel_id_override: Optional[int] = None) -> Dict[str, Any]:
    """
    Send context message to Odoo live chat API.

    Uses the endpoint: POST /im_livechat/cors/message/post
    Requires guest_token and channel_id from the Odoo get_session response.

    Args:
        context_message: Formatted conversation history to send
        guest_token: Odoo guest token from get_session (e.g. '8|c9f18fc2-...')
        channel_id_override: Odoo discuss.channel id from get_session (e.g. 18)

    Returns:
        Dict with keys: success (bool), message (str), channel_id (int), error (optional str)
    """
    import requests
    import json

    # Get Odoo config from environment
    odoo_base_url = os.getenv("ODOO_BASE_URL", "https://export-genius-pvt.odoo.com")
    # Use channel_id from frontend (get_session response) or fall back to env
    channel_id = channel_id_override if channel_id_override else int(os.getenv("ODOO_LIVECHAT_CHANNEL_ID", "1"))
    # Use guest_token from frontend (get_session response) or fall back to env
    resolved_guest_token = guest_token or os.getenv("ODOO_GUEST_TOKEN", None)

    print(f"[ODOO] _send_to_odoo_api — channel_id={channel_id}, guest_token={'set' if resolved_guest_token else 'NOT SET'}")

    url = f"https://export-genius-pvt.odoo.com/im_livechat/cors/message/post"

    # Prepare payload using guest_token from get_session
    payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "post_data": {
                "body": context_message,
                "email_add_signature": True,
                "message_type": "comment",
                "subtype_xmlid": "mail.mt_comment"
            },
            "thread_id":    channel_id,
            "thread_model": "discuss.channel",
            "guest_token":  resolved_guest_token,
            "context": {
                "temporary_id": 0.5
            }
        }
    }
    
    headers = {
        'accept': '*/*',
        'content-type': 'application/json',
        'origin': 'http://localhost:3000',
        'user-agent': 'Mozilla/5.0'
        # ,
        # 'Cookie': session_cookie
    }
    
    try:
        print(f"[ODOO] Sending POST to {url}")
        response = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload),
            timeout=10
        )
        
        print(f"[ODOO] Response status: {response.status_code}")
        print(f"[ODOO] Response: {response.text[:500]}")
        
        if response.status_code == 200:
            try:
                response_data = response.json()
                
                # Check for Odoo RPC errors
                if response_data.get("error"):
                    error_msg = response_data["error"].get("message", "Unknown Odoo error")
                    print(f"[ODOO] RPC Error: {error_msg}")
                    return {
                        "success": False,
                        "message": "Odoo API returned error",
                        "channel_id": None,
                        "error": error_msg
                    }
                
                # Extract channel ID from result if available
                channel_from_result = response_data.get("result", {}).get("channel_id")
                
                return {
                    "success": True,
                    "message": "Context sent to Odoo successfully",
                    "channel_id": channel_from_result,
                    "error": None
                }
            except json.JSONDecodeError:
                print(f"[ODOO] Failed to parse JSON response")
                return {
                    "success": False,
                    "message": "Invalid response from Odoo",
                    "channel_id": None,
                    "error": "Could not parse Odoo response"
                }
        else:
            print(f"[ODOO] Non-200 status code: {response.status_code}")
            return {
                "success": False,
                "message": f"Odoo API returned {response.status_code}",
                "channel_id": None,
                "error": f"HTTP {response.status_code}"
            }
    
    except requests.exceptions.Timeout:
        print(f"[ODOO] Request timeout")
        return {
            "success": False,
            "message": "Odoo API timeout",
            "channel_id": None,
            "error": "Request timeout"
        }
    except requests.exceptions.ConnectionError as e:
        print(f"[ODOO] Connection error: {e}")
        return {
            "success": False,
            "message": "Could not connect to Odoo",
            "channel_id": None,
            "error": str(e)
        }
    except Exception as e:
        print(f"[ODOO] Unexpected error: {e}")
        return {
            "success": False,
            "message": "Unexpected error sending to Odoo",
            "channel_id": None,
            "error": str(e)
        }


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

    return DecimalJSONResponse(
        content={
            "redis_stats": stats,
            "status": "healthy"
        }
    )


# ============================================================================
# FEEDBACK ENDPOINTS
# ============================================================================

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest):
    """
    Submit user feedback with conversation context.

    Stores feedback and the full conversation history for later analysis.
    Supports thumbs up/down, ratings, and comments.
    """
    try:
        feedback_service = await get_feedback_service()
        await feedback_service.initialize()

        # Convert conversation messages
        conversation = None
        if request.conversation:
            conversation = [
                {"role": msg.role, "content": msg.content, "message_id": msg.message_id}
                for msg in request.conversation
            ]

        # Create feedback data
        feedback_data = FeedbackData(
            session_id=request.session_id,
            feedback_type=request.feedback_type,
            rating=request.rating,
            comment=request.comment,
            message_id=request.message_id,
            assistant_message=request.assistant_message,
            user_query=request.user_query,
            page_url=request.page_url,
            conversation=conversation
        )

        # Store feedback
        result = await feedback_service.store_feedback(feedback_data)

        if result.get("success"):
            # Friendly response based on feedback type
            if request.feedback_type == "thumbs_up":
                message = "Thanks for the positive feedback! Glad I could help."
            elif request.feedback_type == "thumbs_down":
                message = "Thanks for letting us know. We'll use this to improve!"
            elif request.feedback_type == "rating":
                message = f"Thank you for rating us {request.rating}/5!"
            else:
                message = "Thank you for your feedback!"

            return FeedbackResponse(
                success=True,
                feedback_id=result.get("feedback_id"),
                message=message,
                storage=result.get("storage")
            )
        else:
            return FeedbackResponse(
                success=False,
                feedback_id=None,
                message="We couldn't save your feedback, but we appreciate it!",
                storage=None
            )

    except Exception as e:
        print(f"[Feedback] Error: {e}")
        # Don't fail the request - feedback is non-critical
        return FeedbackResponse(
            success=False,
            feedback_id=None,
            message="Thanks for the feedback!",
            storage=None
        )


@router.get("/feedback/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(days: int = 30):
    """
    Get feedback statistics for analysis.

    Returns aggregated feedback data for the specified period.
    """
    try:
        feedback_service = await get_feedback_service()
        await feedback_service.initialize()

        stats = await feedback_service.get_feedback_stats(days=days)

        if "error" in stats:
            raise HTTPException(status_code=503, detail=stats["error"])

        return FeedbackStatsResponse(
            period_days=stats.get("period_days", days),
            total_feedback=stats.get("total_feedback", 0),
            by_type=stats.get("by_type", {}),
            avg_rating=stats.get("avg_rating")
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Feedback] Stats error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get feedback stats")


@router.get("/feedback/negative")
async def get_negative_feedback(limit: int = 50):
    """
    Get recent negative feedback with conversation context for analysis.

    Useful for identifying problematic responses and improving the chatbot.
    """
    try:
        feedback_service = await get_feedback_service()
        await feedback_service.initialize()

        feedbacks = await feedback_service.get_negative_feedback(limit=limit)

        return DecimalJSONResponse(content={
            "count": len(feedbacks),
            "feedbacks": feedbacks
        })

    except Exception as e:
        print(f"[Feedback] Get negative error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get negative feedback")


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@router.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return access + refresh tokens.

    - **email**: User email address
    - **password**: User password

    Returns JWT access token (60min) and refresh token (30 days)
    """
    try:
        # Get auth database service
        auth_db = get_auth_db_service()
        await auth_db.initialize()

        # Create auth service
        auth_service = AuthService(auth_db)

        # Authenticate user
        user = await auth_service.authenticate_user(request.email, request.password)

        if not user:
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )

        # Generate tokens
        tokens = await auth_service.generate_tokens(user)

        # Remove password_hash from user object
        user_safe = {k: v for k, v in user.items() if k != "password_hash"}

        return TokenResponse(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            token_type="bearer",
            user=user_safe
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Auth] Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/auth/refresh")
async def refresh_token(request: RefreshTokenRequest):
    """
    Refresh access token using refresh token.

    - **refresh_token**: Valid refresh token from login

    Returns new access token
    """
    try:
        # Get auth database service
        auth_db = get_auth_db_service()
        await auth_db.initialize()

        # Create auth service
        auth_service = AuthService(auth_db)

        # Refresh access token
        access_token = await auth_service.refresh_access_token(request.refresh_token)

        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired refresh token"
            )

        return {
            "access_token": access_token,
            "token_type": "bearer"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Auth] Token refresh error: {e}")
        raise HTTPException(status_code=500, detail="Token refresh failed")


@router.post("/auth/logout")
async def logout(request: LogoutRequest, current_user = Depends(require_auth)):
    """
    Logout user by revoking refresh token.

    Requires authentication. Revokes the provided refresh token.
    """
    try:
        # Get auth database service
        auth_db = get_auth_db_service()
        await auth_db.initialize()

        # Create auth service
        auth_service = AuthService(auth_db)

        # Revoke refresh token
        success = await auth_service.logout(request.refresh_token)

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to logout"
            )

        return {
            "message": "Logged out successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Auth] Logout error: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")


@router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user = Depends(require_auth)):
    """
    Get current authenticated user information.

    Requires authentication. Returns user profile.
    """
    return UserResponse(**current_user)


# ============================================================================
# USER MANAGEMENT ENDPOINTS (Super Admin Only)
# ============================================================================

@router.post("/admin/users/create", response_model=UserResponse)
async def create_user(
    request: CreateUserRequest,
    current_user = Depends(require_super_admin)
):
    """
    Create a new user (super_admin only).

    - **username**: Unique username
    - **email**: User email address
    - **password**: Password (must meet security requirements)
    - **full_name**: Full name
    - **role**: User role (admin or user, cannot create super_admin)
    """
    try:
        # Get auth database service
        auth_db = get_auth_db_service()
        await auth_db.initialize()

        # Create auth service
        auth_service = AuthService(auth_db)

        # Create user
        user = await auth_service.create_user(
            username=request.username,
            email=request.email,
            password=request.password,
            full_name=request.full_name,
            role=request.role,
            creator_role=current_user["role"]
        )

        if not user:
            raise HTTPException(
                status_code=400,
                detail="Failed to create user. Email may already exist."
            )

        return UserResponse(**user)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Auth] Create user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/users/list", response_model=UserListResponse)
async def list_users(
    page: int = 1,
    page_size: int = 20,
    role: Optional[str] = None,
    current_user = Depends(require_super_admin)
):
    """
    List all users with pagination (super_admin only).

    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20)
    - **role**: Filter by role (optional)
    """
    try:
        # Get auth database service
        auth_db = get_auth_db_service()
        await auth_db.initialize()

        # Get paginated users
        result = await auth_db.list_users(page=page, page_size=page_size, role=role)

        # Convert users to UserResponse objects
        users = [UserResponse(**user) for user in result["users"]]

        return UserListResponse(
            users=users,
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"],
            total_pages=result["total_pages"]
        )

    except Exception as e:
        print(f"[Auth] List users error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list users")


@router.patch("/admin/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    current_user = Depends(require_super_admin)
):
    """
    Update user information (super_admin only).

    - **user_id**: ID of user to update
    - **full_name**: New full name (optional)
    - **role**: New role (optional, cannot set to super_admin)
    - **is_active**: Active status (optional, cannot deactivate super_admin)
    """
    try:
        # Get auth database service
        auth_db = get_auth_db_service()
        await auth_db.initialize()

        # Create auth service
        auth_service = AuthService(auth_db)

        # Update user
        success = await auth_service.update_user(
            user_id=user_id,
            full_name=request.full_name,
            role=request.role,
            is_active=request.is_active,
            updater_role=current_user["role"]
        )

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to update user"
            )

        # Get updated user
        updated_user = await auth_db.get_user_by_id(user_id)

        if not updated_user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        return UserResponse(**updated_user)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Auth] Update user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user = Depends(require_super_admin)
):
    """
    Delete (deactivate) user (super_admin only).

    Soft deletes user by setting is_active = False.
    Cannot delete super_admin users.
    """
    try:
        # Get auth database service
        auth_db = get_auth_db_service()
        await auth_db.initialize()

        # Create auth service
        auth_service = AuthService(auth_db)

        # Delete user
        success = await auth_service.delete_user(
            user_id=user_id,
            deleter_role=current_user["role"]
        )

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to delete user. Cannot delete super_admin users."
            )

        return {
            "message": f"User {user_id} deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Auth] Delete user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FEEDBACK MANAGEMENT ENDPOINTS (Admin/Dashboard)
# ============================================================================

@router.get("/admin/feedback/list")
async def get_feedback_list(
    current_user = Depends(require_auth),
    page: int = 1,
    page_size: int = 20,
    feedback_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    session_id: Optional[str] = None,
    min_rating: Optional[int] = None,
    max_rating: Optional[int] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc"
):
    """
    Get paginated list of all feedbacks with filters.

    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - feedback_type: Filter by type (thumbs_up, thumbs_down, rating, comment)
    - start_date: Filter by start date (YYYY-MM-DD)
    - end_date: Filter by end date (YYYY-MM-DD)
    - session_id: Filter by session ID
    - min_rating: Minimum rating (1-5)
    - max_rating: Maximum rating (1-5)
    - search: Search in user_query and assistant_message
    - sort_by: Sort field (created_at, rating, feedback_type)
    - sort_order: Sort order (asc, desc)
    """
    try:
        # Validate page_size
        page_size = min(page_size, 100)

        feedback_service = await get_feedback_service()
        await feedback_service.initialize()

        result = await feedback_service.get_feedback_list(
            page=page,
            page_size=page_size,
            feedback_type=feedback_type,
            start_date=start_date,
            end_date=end_date,
            session_id=session_id,
            min_rating=min_rating,
            max_rating=max_rating,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order
        )

        return DecimalJSONResponse(content=result)

    except Exception as e:
        print(f"[Feedback Admin] List error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/feedback/dashboard/stats")
async def get_dashboard_stats(
    current_user = Depends(require_auth),
    days: int = 30
):
    """
    Get comprehensive dashboard statistics.

    Query Parameters:
    - days: Number of days to include (default: 30)

    Returns:
    - total_feedback: Total feedback count
    - thumbs_up_count: Positive feedback count
    - thumbs_down_count: Negative feedback count
    - rating_count: Star rating count
    - comment_count: Comment count
    - avg_rating: Average star rating
    - satisfaction_rate: Percentage of positive vs negative feedback
    """
    try:
        feedback_service = await get_feedback_service()
        await feedback_service.initialize()

        stats = await feedback_service.get_dashboard_stats(days=days)

        return DecimalJSONResponse(content=stats)

    except Exception as e:
        print(f"[Feedback Admin] Dashboard stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/feedback/dashboard/timeseries")
async def get_feedback_timeseries(
    current_user = Depends(require_auth),
    days: int = 30
):
    """
    Get daily feedback data for time series charts.

    Query Parameters:
    - days: Number of days to include (default: 30)

    Returns:
    - data: Array of daily statistics
    - period_days: Number of days
    - start_date: Start of period
    - end_date: End of period
    """
    try:
        feedback_service = await get_feedback_service()
        await feedback_service.initialize()

        result = await feedback_service.get_time_series(days=days)

        return DecimalJSONResponse(content=result)

    except Exception as e:
        print(f"[Feedback Admin] Timeseries error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/feedback/dashboard/top-pages")
async def get_top_pages(
    current_user = Depends(require_auth),
    days: int = 30,
    limit: int = 10,
    feedback_type: Optional[str] = None
):
    """
    Get top pages by feedback count.

    Query Parameters:
    - days: Number of days to include (default: 30)
    - limit: Maximum pages to return (default: 10)
    - feedback_type: Optional filter (e.g., 'thumbs_down' for problem pages)
    """
    try:
        feedback_service = await get_feedback_service()
        await feedback_service.initialize()

        result = await feedback_service.get_top_pages(
            days=days,
            limit=limit,
            feedback_type=feedback_type
        )

        return DecimalJSONResponse(content=result)

    except Exception as e:
        print(f"[Feedback Admin] Top pages error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/feedback/session/{session_id}")
async def get_session_feedbacks(
    session_id: str,
    current_user = Depends(require_auth)
):
    """
    Get all feedbacks from a specific session.

    Path Parameters:
    - session_id: Session identifier
    """
    try:
        feedback_service = await get_feedback_service()
        await feedback_service.initialize()

        result = await feedback_service.get_session_feedbacks(session_id)

        return DecimalJSONResponse(content=result)

    except Exception as e:
        print(f"[Feedback Admin] Session feedbacks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/feedback/export")
async def export_feedbacks(
    current_user = Depends(require_auth),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    feedback_type: Optional[str] = None,
    include_conversations: bool = False,
    format: str = "json"
):
    """
    Export feedbacks for a given period.

    Query Parameters:
    - start_date: Start date (YYYY-MM-DD)
    - end_date: End date (YYYY-MM-DD)
    - feedback_type: Optional filter by type
    - include_conversations: Include full conversation history (default: false)
    - format: Export format - 'json' or 'csv' (default: json)

    Note: For large exports, consider adding date filters.
    """
    try:
        feedback_service = await get_feedback_service()
        await feedback_service.initialize()

        feedbacks = await feedback_service.export_feedbacks(
            start_date=start_date,
            end_date=end_date,
            feedback_type=feedback_type,
            include_conversations=include_conversations
        )

        if format.lower() == "csv":
            # Convert to CSV
            import csv
            import io

            output = io.StringIO()
            if feedbacks:
                # Get headers from first record (excluding conversation for CSV)
                headers = [k for k in feedbacks[0].keys() if k != 'conversation']
                writer = csv.DictWriter(output, fieldnames=headers)
                writer.writeheader()
                for fb in feedbacks:
                    row = {k: v for k, v in fb.items() if k != 'conversation'}
                    writer.writerow(row)

            csv_content = output.getvalue()
            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=feedbacks_export_{start_date or 'all'}_{end_date or 'all'}.csv"
                }
            )

        # Default: JSON
        return DecimalJSONResponse(content={
            "format": "json",
            "total_records": len(feedbacks),
            "data": feedbacks
        })

    except Exception as e:
        print(f"[Feedback Admin] Export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/feedback/{feedback_id}")
async def get_feedback_detail(
    feedback_id: int,
    current_user = Depends(require_auth)
):
    """
    Get full details of a single feedback including conversation history.

    Path Parameters:
    - feedback_id: ID of the feedback to retrieve
    """
    try:
        feedback_service = await get_feedback_service()
        await feedback_service.initialize()

        feedback = await feedback_service.get_feedback_detail(feedback_id)

        if not feedback:
            raise HTTPException(status_code=404, detail="Feedback not found")

        return DecimalJSONResponse(content=feedback)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Feedback Admin] Detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# VOICE CHAT ENDPOINTS
# Real-time voice conversation with LiveKit + OpenAI Whisper + TTS
# ============================================================================

# Tracks when TTS last finished per session (used to detect echo transcripts)
_voice_tts_end_time: dict = {}

# Short common phrases that are almost certainly echo artifacts, not real user input.
# If received within ECHO_GUARD_SECONDS of TTS finishing AND the transcript matches
# one of these patterns, the message is silently discarded.
_ECHO_PHRASES = {
    "thank you", "thanks", "thank you.", "thanks.", "okay", "ok", "ok.",
    "okay.", "you're welcome", "welcome", "great", "sure", "alright",
    "all right", "got it", "yes", "no", "bye", "goodbye", "hello",
    "hi", "hey", "please", "sorry", "excuse me", "you", "me",
    "great, thank you", "great thank you", "thanks a lot", "thank you so much",
}
ECHO_GUARD_SECONDS = 4.0  # Discard echo-like transcripts within this window after TTS

# Whisper commonly hallucinates these strings for silence / low-level noise.
# Trained on YouTube data, it produces these when audio contains no real speech.
# Always discard regardless of timing.
_WHISPER_HALLUCINATIONS = {
    ".", "..", "...", ",", "!", "?",
    # Single words that are nearly always hallucinations in isolation
    "you", "you.", "me", "me.", "um", "uh", "hmm", "hm", "oh", "ah",
    # With punctuation
    "you!", "you,", "you?",
    # Common YouTube-trained hallucinations
    "thank you.", "thanks.", "thank you!", "thanks!", "thanks for watching.",
    "thanks for watching!", "thank you for watching.", "thank you for watching!",
    "please like and subscribe.", "like and subscribe.", "subscribe.",
    "bye.", "bye!", "bye-bye.", "bye-bye!", "goodbye.", "goodbye!",
    "bye everyone.", "bye everyone!", "bye everybody.", "bye everybody!",
    "goodbye everyone.", "goodbye everyone!", "goodbye everybody.",
    "good night.", "good night!", "good night everyone.", "good night everyone!",
    "see you.", "see you!", "see you later.", "see you later!",
    "take care.", "take care!", "farewell.", "farewell!",
    "okay.", "ok.", "alright.", "all right.", "great.", "sure.", "yes.", "no.",
    "hmm.", "um.", "uh.", "ah.", "oh.", "mm-hmm.", "mm.", "hm.", "huh.",
    # OpenAI Whisper specific hallucinations on near-silence
    "you", "the", "a", "i", "",
    # Repeated noise patterns
    "[music]", "[applause]", "[laughter]", "(music)", "(applause)",
}

# Substring patterns — Whisper hallucinates these on silence / ambient audio.
# Checked with `any(phrase in transcript.lower() for phrase in ...)`.
_HALLUCINATION_SUBSTRINGS = {
    "thank you for coming",
    "thank you for being here",
    "thank you all for coming",
    "thanks for coming",
    "we hope to see you again",
    "hope to see you again",
    "see you again in the future",
    "see you in the next video",
    "see you next time",
    "see you in the next episode",
    "don't forget to subscribe",
    "please subscribe",
    "please like and subscribe",
    "like and subscribe",
    "hit the subscribe button",
    "click the subscribe",
    "this video is sponsored",
    "this episode is sponsored",
    "brought to you by",
    "copyright reserved",
    "all rights reserved",
    "i'll see you in the next",
    "we'll see you next time",
    "thanks for tuning in",
    "thank you for tuning in",
    "stay tuned",
    "until next time",
    "that's all for today",
    "that's all for now",
    "have a great day everyone",
    "have a wonderful day",
    "bye everyone",
    "bye everybody",
    "goodbye everyone",
    "goodbye everybody",
    "see you everyone",
    "good night everyone",
    "good night everybody",
    "take care everyone",
    "farewell everyone",
}

@router.post("/voice/token", response_model=VoiceTokenResponse)
async def get_voice_token(request: VoiceTokenRequest):
    """
    Generate LiveKit access token for voice chat session

    This endpoint:
    1. Creates a LiveKit room for the session
    2. Generates a JWT access token
    3. Returns connection details for the client

    The client uses this token to connect to LiveKit and start real-time audio streaming.

    Args:
        request: VoiceTokenRequest with session_id and optional participant_name

    Returns:
        VoiceTokenResponse with access token and connection details
    """
    try:
        voice_service = get_voice_chat_service()

        # Generate room name based on session
        room_name = f"voice_{request.session_id}"

        # Generate access token
        access_token = await voice_service.generate_access_token(
            room_name=room_name,
            participant_identity=request.session_id,
            participant_name=request.participant_name
        )

        # Register session
        voice_service.register_session(request.session_id, room_name)

        return VoiceTokenResponse(
            access_token=access_token,
            livekit_url=voice_service.config.livekit_url,
            room_name=room_name,
            participant_identity=request.session_id
        )

    except Exception as e:
        print(f"[Voice Chat] Error generating token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate voice token: {str(e)}")


@router.post("/voice/message", response_model=VoiceMessageResponse)
async def process_voice_message(request: VoiceMessageRequest):
    """
    Process voice message: STT → Chatbot → TTS

    This endpoint handles the complete voice conversation pipeline:
    1. Decode base64 audio data
    2. Transcribe speech to text using OpenAI Whisper
    3. Process text through chatbot logic
    4. Generate speech response using OpenAI TTS
    5. Return transcript, response text, and audio

    Args:
        request: VoiceMessageRequest with session_id and audio_data

    Returns:
        VoiceMessageResponse with transcript, response, and audio
    """
    start_time = time.time()

    try:
        # Lazy initialization
        await ensure_initialized()

        if not chatbot_manager:
            raise HTTPException(status_code=503, detail="Chatbot not initialized")

        voice_service = get_voice_chat_service()

        # Decode audio data from base64
        try:
            audio_bytes = base64.b64decode(request.audio_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid audio data: {str(e)}")

        print(f"[Voice Chat] Processing voice message for session {request.session_id}")
        print(f"[Voice Chat] Audio size: {len(audio_bytes)} bytes, format: {request.audio_format}")

        # Define chatbot handler function
        async def chatbot_handler(session_id: str, message: str) -> Dict[str, Any]:
            """Handle chatbot processing for voice message"""
            try:
                # Process through existing chatbot logic
                response_text, processing_time, sources_used = await chatbot_manager.chat(
                    message=message,
                    session_id=session_id,
                    dynamic_url=None
                )

                return {
                    "response": response_text,
                    "metadata": {
                        "sources_used": sources_used,
                        "processing_time": processing_time
                    }
                }
            except Exception as e:
                print(f"[Voice Chat] Chatbot error: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "response": "I'm sorry, I encountered an error processing your message.",
                    "metadata": {"error": str(e)}
                }

        # Process voice message
        print(f"[Voice Chat] Calling voice_service.handle_voice_message...")
        result = await voice_service.handle_voice_message(
            session_id=request.session_id,
            audio_data=audio_bytes,
            chatbot_handler=chatbot_handler,
            audio_format=request.audio_format
        )

        print(f"[Voice Chat] handle_voice_message result: {result is not None}")

        if not result:
            print(f"[Voice Chat] ERROR: handle_voice_message returned None - check logs above for details")
            raise HTTPException(status_code=500, detail="Failed to process voice message - check server logs for details")

        # Encode audio response to base64
        audio_base64 = base64.b64encode(result["audio_data"]).decode("utf-8")

        processing_time = time.time() - start_time

        print(f"[Voice Chat] Voice message processed in {processing_time:.2f}s")

        return VoiceMessageResponse(
            transcript=result["transcript"],
            response_text=result["response_text"],
            audio_data=audio_base64,
            audio_format=result["audio_format"],
            processing_time=processing_time,
            metadata=result.get("metadata")
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Voice Chat] Error processing voice message: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Voice message processing failed: {str(e)}")


@router.post("/voice/stream")
async def stream_voice_message(request: VoiceMessageRequest):
    """
    Stream voice message processing via SSE:
    1. Transcribe audio (STT) → immediately sends transcript event
    2. Stream LLM response text → sends text_chunk events
    3. Generate TTS for full response → sends audio event
    4. Sends done event
    """
    try:
        await ensure_initialized()

        if not chatbot_manager:
            raise HTTPException(status_code=503, detail="Chatbot not initialized")

        try:
            audio_bytes = base64.b64decode(request.audio_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid audio data: {str(e)}")

        voice_service = get_voice_chat_service()

        async def generate():
            # ── Queue + heartbeat pattern ─────────────────────────────────────
            # All processing runs in a background asyncio task (_process) that
            # puts SSE event dicts on a queue.  The generator reads from the queue
            # with an 8-second timeout and yields a heartbeat on each timeout so
            # the HTTP connection stays alive regardless of how long STT/LLM/TTS
            # takes.  This prevents the frontend AbortController from firing and
            # avoids "Response timed out" errors entirely.
            import asyncio
            _SENTINEL = object()
            queue: asyncio.Queue = asyncio.Queue()
            # Shared flag: True when _process sent an error fallback message.
            # The done-event handler reads this to suppress stale explore_urls.
            _had_error: list = [False]

            async def _process():
                try:
                    # ── Step 1: STT ───────────────────────────────────────────
                    print(f"[Voice Stream] Transcribing for session {request.session_id}")
                    try:
                        transcript = await asyncio.wait_for(
                            voice_service.transcribe_audio(audio_bytes, request.audio_format),
                            timeout=45.0
                        )
                    except asyncio.TimeoutError:
                        # Transcription took too long — silently discard, don't
                        # surface a visible error to the user (they'll just speak again)
                        print(f"[Voice Stream] Transcription timed out — discarding silently")
                        return

                    # Silence / noise / hallucination checks — all silent discards
                    if not transcript or not transcript.strip():
                        print(f"[Voice Stream] Empty transcript — silence, discarding")
                        return

                    transcript_clean = transcript.strip()

                    if transcript_clean.lower() in _WHISPER_HALLUCINATIONS or len(transcript_clean) <= 1:
                        print(f"[Voice Stream] Whisper hallucination (exact): '{transcript_clean}'")
                        return

                    lower_t = transcript_clean.lower()

                    # Substring hallucination check — catches multi-sentence ceremony phrases
                    if any(phrase in lower_t for phrase in _HALLUCINATION_SUBSTRINGS):
                        print(f"[Voice Stream] Whisper hallucination (pattern): '{transcript_clean[:80]}'")
                        return

                    # 3+ occurrences of "thank you" in one transcript = hallucination
                    if lower_t.count('thank you') >= 3:
                        print(f"[Voice Stream] Whisper hallucination (thank-you flood): '{transcript_clean[:80]}'")
                        return

                    words = transcript_clean.split()
                    if len(words) >= 6:
                        half = len(words) // 2
                        if words[:half] == words[half:half * 2]:
                            print(f"[Voice Stream] Repetition artifact: '{transcript_clean[:60]}'")
                            return

                    last_tts = _voice_tts_end_time.get(request.session_id, 0)
                    if time.time() - last_tts < ECHO_GUARD_SECONDS and \
                            transcript_clean.lower().rstrip('.!?,') in _ECHO_PHRASES:
                        print(f"[Voice Stream] Echo guard: discarding '{transcript_clean}'")
                        return

                    print(f"[Voice Stream] Transcript: {transcript_clean[:100]}")
                    await queue.put({'type': 'transcript', 'text': transcript_clean})

                    # ── Step 2: LLM streaming ─────────────────────────────────
                    sentence_buffer = ""
                    chunk_count = 0
                    tts_tasks = []
                    sent_error_message = False
                    print(f"[Voice Stream] Starting LLM stream...")
                    try:
                        # Use per-chunk wait_for so timeout fires even before the
                        # first token arrives (the old inline check only triggered
                        # after a chunk was already received).
                        llm_iter = chatbot_manager.chat_stream(
                            message=transcript_clean,
                            session_id=request.session_id,
                            dynamic_url=None
                        ).__aiter__()
                        stream_start = asyncio.get_event_loop().time()

                        while True:
                            try:
                                chunk = await asyncio.wait_for(
                                    llm_iter.__anext__(), timeout=25.0
                                )
                            except StopAsyncIteration:
                                break
                            except asyncio.TimeoutError:
                                raise   # bubbles up to outer except

                            # Belt-and-suspenders global wall-clock guard
                            if asyncio.get_event_loop().time() - stream_start > 90.0:
                                raise asyncio.TimeoutError()

                            chunk_count += 1
                            chunk_stripped = chunk.strip()
                            if chunk_stripped.startswith('{'):
                                try:
                                    parsed = json.loads(chunk_stripped)
                                    if parsed.get('credit_exhausted') or parsed.get('clarifying_question'):
                                        msg = parsed.get('message') or parsed.get('question', '')
                                        if msg:
                                            await queue.put({'type': 'text_chunk', 'text': msg})
                                            tts_tasks.append(asyncio.create_task(
                                                voice_service.generate_speech(msg)))
                                        break
                                    if parsed.get('done'):
                                        # Capture explore_url from the done chunk directly
                                        # (covers cases where _last_explore_url may lag)
                                        if parsed.get('explore_url'):
                                            chatbot_manager._last_explore_url = parsed['explore_url']
                                        break
                                except json.JSONDecodeError:
                                    pass
                            else:
                                sentence_buffer += chunk
                                await queue.put({'type': 'text_chunk', 'text': chunk})

                                is_sentence_end = any(sentence_buffer.rstrip().endswith(p)
                                                      for p in ['.', '!', '?'])
                                if is_sentence_end or '\n\n' in sentence_buffer or len(sentence_buffer) > 200:
                                    seg = sentence_buffer.strip()
                                    sentence_buffer = ""
                                    # Strip URLs before TTS so they are not spoken aloud
                                    seg_for_tts = re.sub(r'https?://\S+', '', seg).strip()
                                    if seg_for_tts and len(seg_for_tts) > 10:
                                        tts_tasks.append(asyncio.create_task(
                                            voice_service.generate_speech(seg_for_tts)))

                        print(f"[Voice Stream] LLM done. Chunks: {chunk_count}")

                    except asyncio.TimeoutError:
                        print(f"[Voice Stream] LLM timed out (chunk_count={chunk_count})")
                        sent_error_message = True
                        _had_error[0] = True
                        graceful = "I'm taking a bit longer than usual — please try again."
                        await queue.put({'type': 'text_chunk', 'text': graceful})
                        tts_tasks.append(asyncio.create_task(voice_service.generate_speech(graceful)))

                    except Exception as llm_err:
                        print(f"[Voice Stream] LLM error: {llm_err}")
                        sent_error_message = True
                        _had_error[0] = True
                        graceful = "Sorry, I had trouble with that. Please try again."
                        await queue.put({'type': 'text_chunk', 'text': graceful})
                        tts_tasks.append(asyncio.create_task(voice_service.generate_speech(graceful)))

                    # Only send "no response" fallback if nothing else was sent
                    if chunk_count == 0 and not sent_error_message:
                        _had_error[0] = True
                        graceful = "I didn't catch a response — please try again."
                        await queue.put({'type': 'text_chunk', 'text': graceful})
                        tts_tasks.append(asyncio.create_task(voice_service.generate_speech(graceful)))

                    if sentence_buffer.strip() and len(sentence_buffer.strip()) > 10:
                        remaining_for_tts = re.sub(r'https?://\S+', '', sentence_buffer).strip()
                        if remaining_for_tts and len(remaining_for_tts) > 10:
                            tts_tasks.append(asyncio.create_task(
                                voice_service.generate_speech(remaining_for_tts)))

                    # ── Step 3: audio from TTS (ran in parallel with LLM) ─────
                    for task in tts_tasks:
                        try:
                            audio_data = await asyncio.wait_for(task, timeout=30.0)
                            if audio_data:
                                await queue.put({
                                    'type': 'audio',
                                    'data': base64.b64encode(audio_data).decode("utf-8")
                                })
                        except Exception as tts_err:
                            print(f"[Voice Stream] TTS error: {tts_err}")

                    _voice_tts_end_time[request.session_id] = time.time()
                    print(f"[Voice Stream] Completed successfully")

                except Exception as e:
                    print(f"[Voice Stream] Background task error: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    await queue.put(_SENTINEL)

            producer = asyncio.create_task(_process())
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=8.0)
                    except asyncio.TimeoutError:
                        # Keep the SSE connection alive while backend is working
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                        continue

                    if item is _SENTINEL:
                        # Never attach an explore URL to error/fallback responses
                        explore_url = '' if _had_error[0] else getattr(chatbot_manager, '_last_explore_url', '')
                        done_data: dict = {'type': 'done'}
                        if explore_url:
                            done_data['explore_url'] = explore_url
                        yield f"data: {json.dumps(done_data)}\n\n"
                        break
                    if isinstance(item, Exception):
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        break
                    yield f"data: {json.dumps(item)}\n\n"
            finally:
                producer.cancel()

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Voice Stream] Outer error: {e}")
        raise HTTPException(status_code=500, detail=f"Voice stream failed: {str(e)}")


@router.get("/voice/sessions")
async def get_voice_sessions():
    """
    Get active voice chat sessions

    Returns statistics for all active voice chat sessions including:
    - Session ID
    - Room name
    - Start time
    - Message count

    Returns:
        List of VoiceSessionStats
    """
    try:
        voice_service = get_voice_chat_service()
        sessions = voice_service.get_active_sessions()

        return {
            "total_sessions": len(sessions),
            "sessions": [
                VoiceSessionStats(
                    session_id=session_id,
                    room_name=data["room_name"],
                    started_at=data["started_at"].isoformat(),
                    message_count=data["message_count"]
                )
                for session_id, data in sessions.items()
            ]
        }

    except Exception as e:
        print(f"[Voice Chat] Error getting sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/voice/session/{session_id}")
async def close_voice_session(session_id: str):
    """
    Close a voice chat session

    Unregisters the session and cleans up resources.

    Args:
        session_id: Session to close

    Returns:
        Success message
    """
    try:
        voice_service = get_voice_chat_service()
        voice_service.unregister_session(session_id)

        return {
            "status": "success",
            "message": f"Voice session {session_id} closed"
        }

    except Exception as e:
        print(f"[Voice Chat] Error closing session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TWILIO CALLBACK ENDPOINTS - Phone Call Feature
# ============================================================================

@router.post("/callback/request", response_model=CallbackResponse)
async def request_callback(request: CallbackRequest):
    """
    Request a phone callback to speak with the sales team

    This endpoint initiates a conference call connecting the user
    and the sales team via their phone numbers.

    Flow:
    1. User provides their phone number
    2. System calls the user's phone
    3. System calls the sales team's phone
    4. Both parties are connected in a conference call

    Args:
        request: CallbackRequest with session_id and phone_number

    Returns:
        CallbackResponse with call status and SIDs

    Raises:
        HTTPException: If Twilio is not configured or call fails
    """
    try:
        twilio_service = get_twilio_callback_service()

        if not twilio_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Phone callback feature is not available. Please configure Twilio credentials."
            )

        # Get the base URL from the request
        # For production, you'd want to set this via environment variable
        base_url = os.getenv("API_BASE_URL", "http://localhost:8000")

        result = await twilio_service.request_callback(
            session_id=request.session_id,
            user_phone=request.phone_number,
            base_url=base_url
        )

        logger.info(f"Callback initiated for session {request.session_id}")

        return CallbackResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/callback/status")
async def callback_status_webhook(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    From: Optional[str] = Form(None),
    To: Optional[str] = Form(None),
    Direction: Optional[str] = Form(None),
    Duration: Optional[str] = Form(None)
):
    """
    Twilio webhook endpoint for call status updates

    This endpoint receives status updates from Twilio about the calls.
    Configure this URL in your Twilio console as the status callback URL.

    Twilio sends POST requests to this endpoint with form-encoded data.

    Args:
        Various form fields sent by Twilio (CallSid, CallStatus, etc.)

    Returns:
        Empty response (Twilio doesn't need a specific response)
    """
    try:
        status_data = {
            "CallSid": CallSid,
            "CallStatus": CallStatus,
            "From": From,
            "To": To,
            "Direction": Direction,
            "Duration": Duration
        }

        twilio_service = get_twilio_callback_service()
        twilio_service.handle_call_status(CallSid, status_data)

        logger.info(f"Call status webhook - SID: {CallSid}, Status: {CallStatus}")

        # Twilio expects a 200 OK response
        return {"status": "received"}

    except Exception as e:
        logger.error(f"Error handling call status webhook: {e}")
        # Still return 200 to Twilio to avoid retries
        return {"status": "error", "message": str(e)}


@router.get("/callback/info/{session_id}")
async def get_callback_info(session_id: str):
    """
    Get callback information for a specific session

    Args:
        session_id: Session identifier

    Returns:
        Call information or null if not found
    """
    try:
        twilio_service = get_twilio_callback_service()
        call_info = twilio_service.get_call_info(session_id)

        if not call_info:
            return {"status": "not_found", "message": "No callback found for this session"}

        return {"status": "found", "call_info": call_info}

    except Exception as e:
        logger.error(f"Error getting callback info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
            "POST /api/voice/token": "Get LiveKit access token for voice chat",
            "POST /api/voice/message": "Process voice message (STT → Chat → TTS)",
            "GET /api/voice/sessions": "Get active voice sessions",
            "GET /docs": "Interactive API documentation"
        }
    }


# Include the API router
print("[DEBUG] About to include router...")
app.include_router(router)
print("[DEBUG] Router included successfully!")


# ============================================================================
# TEST ENDPOINT FOR HISTORY VERIFICATION
# ============================================================================

@router.post("/test/history")
async def test_history(request: ChatRequest):
    """
    Test endpoint to verify conversation history is working

    Returns the current history for the session
    """
    await ensure_initialized()

    if not chatbot_manager:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")

    session_id = request.session_id

    # Get streaming history if exists
    streaming_history = chatbot_manager._stream_history.get(session_id, [])

    # Get LangGraph history from checkpointer
    langgraph_messages = []
    try:
        if hasattr(chatbot_manager, 'app') and hasattr(chatbot_manager.app, 'checkpointer'):
            checkpointer = chatbot_manager.app.checkpointer
            if checkpointer:
                # Try to get checkpoint
                config = {"configurable": {"thread_id": session_id}}
                checkpoint = checkpointer.get(config)
                if checkpoint and 'channel_values' in checkpoint:
                    messages = checkpoint['channel_values'].get('messages', [])
                    for msg in messages:
                        langgraph_messages.append({
                            "type": type(msg).__name__,
                            "content": msg.content if hasattr(msg, 'content') else str(msg)
                        })
    except Exception as e:
        print(f"[TEST] Error getting LangGraph history: {e}")

    # Build history text using our manager
    from chatbot.utils.conversation_history_manager import build_conversation_history
    history_text = build_conversation_history(streaming_history) if streaming_history else "No history"

    return {
        "session_id": session_id,
        "streaming_history_count": len(streaming_history),
        "streaming_history": streaming_history,
        "langgraph_messages_count": len(langgraph_messages),
        "langgraph_messages": langgraph_messages,
        "formatted_history": history_text,
        "message": "History retrieved successfully"
    }


# ============================================================================
# STATIC FILE SERVING FOR CHATBOT WIDGET
# ============================================================================

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "backend", "assets")

# Log paths at startup for debugging
print(f"[WIDGET] Script directory: {SCRIPT_DIR}")
print(f"[WIDGET] Assets directory: {ASSETS_DIR}")
print(f"[WIDGET] Assets exists: {os.path.exists(ASSETS_DIR)}")

# Serve the chat widget JS file at /api/chat-widget.js
@app.get("/api/chat-widget.js")
async def serve_chat_widget():
    """Serve the chatbot widget JavaScript file"""
    widget_path = os.path.join(ASSETS_DIR, "chat-widget.js")
    print(f"[WIDGET] Requested chat-widget.js, path: {widget_path}, exists: {os.path.exists(widget_path)}")
    if os.path.exists(widget_path):
        return FileResponse(
            widget_path,
            media_type="application/javascript",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Access-Control-Allow-Origin": "*"
            }
        )
    # Better error message with path info
    raise HTTPException(status_code=404, detail=f"Widget not found at {widget_path}")

# Also serve at /chat-widget.js for backwards compatibility
@app.get("/chat-widget.js")
async def serve_chat_widget_legacy():
    """Serve the chatbot widget JavaScript file (legacy path)"""
    return await serve_chat_widget()

# Debug endpoint to check file paths
@app.get("/debug/paths")
async def debug_paths():
    """Debug endpoint to check file paths on server"""
    widget_path = os.path.join(ASSETS_DIR, "chat-widget.js")
    return {
        "script_dir": SCRIPT_DIR,
        "assets_dir": ASSETS_DIR,
        "assets_exists": os.path.exists(ASSETS_DIR),
        "widget_path": widget_path,
        "widget_exists": os.path.exists(widget_path),
        "assets_contents": os.listdir(ASSETS_DIR) if os.path.exists(ASSETS_DIR) else [],
        "cwd": os.getcwd()
    }

# Mount static assets directory for other files (images, etc.)
if os.path.exists(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
    print(f"[OK] Static assets mounted at /assets from {ASSETS_DIR}")
else:
    print(f"[WARN] Assets directory not found: {ASSETS_DIR}")


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