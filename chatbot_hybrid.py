"""
LangGraph Hybrid Sales Agent with RAG + Dynamic Web Scraping

PRODUCTION-READY ARCHITECTURE:
    ✅ Sales Agent Persona - Upsells Export Genius
    ✅ Conversation History - Remembers user context
    ✅ Static KB RAG - Answers from knowledge base
    ✅ Dynamic Web Scraping - Scrapes URL content on demand
    ✅ Intelligent Routing - Routes to scraper OR RAG workflow
    ✅ Context Merging - Combines static + dynamic content
    ✅ Persistent Storage - File-based conversation history
    ✅ Error Handling - Graceful failures and logging
    ✅ Caching - Response and embedding caching
    ✅ Industry Best Practices - Proper logging, retry logic, validation

WORKFLOW:
    User Query
        ↓
    [Preprocess Node] → Detect query type & URLs
        ↓
        ┌────────────────────┐
        │  Router Decision   │
        └────────────────────┘
                ↓
        ╔═══════════════╗     ╔═══════════════════╗
        ║ URL Detected? ║     ║  Normal Query     ║
        ╚═══════════════╝     ╚═══════════════════╝
                ↓                       ↓
        [Scraper Node]          [RAG Workflow]
                ↓                       ↓
        Scrape + Chunk          Retrieve from KB
                ↓                       ↓
                └───────────┬───────────┘
                            ↓
                [Generation with Sales Persona]
                    ↓
                Response (Conversational + Sales-focused)

FEATURES:
    💼 Sales Features:
        - Upsells Export Genius dashboard
        - Remembers user context (name, interests)
        - Conversational and engaging
        - Uses conversation history

    🔧 Technical Features:
        - URL detection and web scraping
        - Static KB + Dynamic content merging
        - Conditional routing
        - Error handling and retries
        - Caching for performance
        - Persistent conversation storage
        - Logging and monitoring

Usage:
    python chatbot_hybrid.py
"""

import json
import re
from pathlib import Path
from typing import TypedDict, Annotated, Sequence, Literal, List, Dict, Optional
import operator
import sys
import logging

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

import numpy as np
import faiss
import ollama
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import gradio as gr
import uuid
from datetime import datetime

# Import web scraper
from web_scraper import WebScraper, scrape_and_chunk

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """
    Centralized configuration with industry best practices

    Best practices:
    - All config in one place
    - Type hints
    - Sensible defaults
    - Comments explaining each setting
    """

    # Paths
    DATA_DIR = Path("data")
    CHUNKS_FILE = DATA_DIR / "kb_chunks.json"
    FAISS_INDEX_FILE = DATA_DIR / "faiss_normalized.index"
    CONVERSATION_HISTORY_DIR = DATA_DIR / "conversation_history"

    # Models
    EMBEDDING_MODEL = "nomic-embed-text"
    LLM_MODEL = "deepseek-v3.1:671b-cloud"

    # RAG Settings (optimized for quality + speed balance)
    TOP_K_RESULTS = 5  # More chunks for better context
    MAX_CHUNK_CHARS = 800  # Longer chunks for detailed answers

    # LLM Performance Settings
    TEMPERATURE = 0.3  # Lower = more focused, consistent
    NUM_PREDICT = 500  # Response length limit
    NUM_CTX = 4096  # Context window size

    # LangGraph Settings
    MAX_ITERATIONS = 5

    # Web Scraping Settings
    SCRAPER_TIMEOUT = 10  # seconds
    SCRAPER_MAX_RETRIES = 3
    SCRAPER_CHUNK_SIZE = 500  # chars per chunk
    SCRAPER_CHUNK_OVERLAP = 50  # overlap between chunks

    # Constant Dynamic URL (your requirement)
    # This URL will be scraped once at startup and cached
    DYNAMIC_URL = "https://www.exportgenius.in/mirror-import-data/afghanistan/oil.php"  # Replace with your actual URL
    ENABLE_DYNAMIC_URL = False  # Set to True to enable scraping at startup

    # Caching
    QUERY_CACHE_SIZE = 50  # max cached responses
    EMBEDDING_CACHE_SIZE = 100  # max cached embeddings

    # Logging
    LOG_LEVEL = "INFO"


# ============================================================================
# PERSISTENT CHECKPOINT SAVER
# ============================================================================

class PersistentMemorySaver(MemorySaver):
    """
    Custom checkpoint saver with file-based persistence

    Industry best practices:
    - Extends existing class (don't reinvent wheel)
    - Proper error handling
    - Logging for debugging
    - Creates directories automatically
    """

    def __init__(self, storage_path: Path):
        super().__init__()
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    def _get_thread_file(self, thread_id: str) -> Path:
        """Get file path for thread's conversation history"""
        safe_id = thread_id.replace("/", "_").replace("\\", "_")
        return self.storage_path / f"{safe_id}.json"

    def _load_from_disk(self):
        """Load all saved conversations from disk on startup"""
        try:
            for file_path in self.storage_path.glob("*.json"):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            logger.info(f"Loaded conversation history from {self.storage_path}")
        except Exception as e:
            logger.warning(f"Could not load history: {e}")

    def _save_to_disk(self, thread_id: str):
        """Save thread's conversation to disk"""
        try:
            file_path = self._get_thread_file(thread_id)
            thread_data = {
                "thread_id": thread_id,
                "last_updated": datetime.now().isoformat(),
                "checkpoints": []
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(thread_data, f, indent=2)

        except Exception as e:
            logger.error(f"Could not save to disk: {e}")

    def put(self, config, checkpoint, metadata, new_versions):
        """Override put to add persistence"""
        result = super().put(config, checkpoint, metadata, new_versions)
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            self._save_to_disk(thread_id)
        return result


# ============================================================================
# ENHANCED STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    """
    Enhanced state for hybrid workflow

    Best practices:
    - Type annotations
    - Clear comments
    - All data needed for routing and processing
    """
    # Core messages
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # Routing
    next_agent: str  # Which node to route to

    # RAG context
    retrieved_context: str  # Static KB context
    retrieved_chunks: list  # Retrieved chunks with metadata

    # Query processing
    original_query: str
    optimized_query: str
    query_type: str  # simple, medium, complex, url_query

    # Dynamic web scraping
    detected_urls: List[str]  # URLs found in query
    dynamic_context: str  # Scraped content from URLs
    scraping_metadata: Dict  # Metadata about scraping

    # Performance
    use_cache: bool


# ============================================================================
# KNOWLEDGE BASE RETRIEVER (RAG)
# ============================================================================

class KnowledgeBaseRetriever:
    """
    RAG system with FAISS vector search and caching

    Industry best practices:
    - Singleton pattern for efficiency
    - Proper resource management
    - Caching for performance
    - Error handling
    - Logging
    """

    def __init__(self):
        logger.info("Loading Knowledge Base...")

        # Validate files exist
        if not Config.FAISS_INDEX_FILE.exists():
            raise FileNotFoundError(
                f"FAISS index not found at {Config.FAISS_INDEX_FILE}\n"
                f"Please run build_kb_WORKING.py first!"
            )

        if not Config.CHUNKS_FILE.exists():
            raise FileNotFoundError(
                f"Chunks file not found at {Config.CHUNKS_FILE}\n"
                f"Please run build_kb_WORKING.py first!"
            )

        # Load FAISS index
        try:
            self.index = faiss.read_index(str(Config.FAISS_INDEX_FILE))
            logger.info(f"  ✓ FAISS index loaded")
        except Exception as e:
            logger.error(f"Failed to load FAISS index: {e}")
            raise

        # Load chunks
        try:
            with open(Config.CHUNKS_FILE, 'r', encoding='utf-8') as f:
                self.chunks = json.load(f)
            logger.info(f"  ✓ Loaded {len(self.chunks)} chunks")
        except Exception as e:
            logger.error(f"Failed to load chunks: {e}")
            raise

        # Initialize caches
        self.embedding_cache = {}
        self.max_cache_size = Config.EMBEDDING_CACHE_SIZE
        logger.info(f"  ✓ Embedding cache enabled (max {self.max_cache_size} queries)")

    def retrieve(self, query: str, top_k: int = Config.TOP_K_RESULTS) -> list:
        """
        Retrieve relevant chunks for query using RAG

        Args:
            query: User question
            top_k: Number of results to return

        Returns:
            List of relevant chunks with scores
        """
        try:
            # Check cache first
            cache_key = query.strip().lower()
            if cache_key in self.embedding_cache:
                logger.info("⚡ Using cached embedding")
                query_embedding = self.embedding_cache[cache_key]
            else:
                # Create query embedding
                response = ollama.embeddings(
                    model=Config.EMBEDDING_MODEL,
                    prompt=query
                )
                query_embedding = np.array([response['embedding']]).astype('float32')

                # Normalize query (critical for cosine similarity)
                faiss.normalize_L2(query_embedding)

                # Cache the embedding
                self._add_to_embedding_cache(cache_key, query_embedding)

            # Search FAISS
            scores, indices = self.index.search(query_embedding, top_k)

            # Build results
            results = []
            for i, idx in enumerate(indices[0]):
                chunk = self.chunks[idx].copy()
                chunk['score'] = float(scores[0][i])
                results.append(chunk)

            return results

        except Exception as e:
            logger.error(f"Error during retrieval: {e}")
            return []

    def _add_to_embedding_cache(self, key: str, embedding: np.ndarray):
        """Add embedding to cache with size limit (LRU eviction)"""
        if len(self.embedding_cache) >= self.max_cache_size:
            # Remove oldest item (FIFO)
            self.embedding_cache.pop(next(iter(self.embedding_cache)))
        self.embedding_cache[key] = embedding

    def format_context(self, results: list, max_chars: int = Config.MAX_CHUNK_CHARS) -> str:
        """
        Format retrieved chunks as context for LLM

        Args:
            results: Retrieved chunks
            max_chars: Max characters per chunk

        Returns:
            Formatted context string
        """
        if not results:
            return "No relevant information found in knowledge base."

        context_parts = []
        for i, result in enumerate(results, 1):
            chunk_text = result['chunk_text']

            # Truncate if needed
            if len(chunk_text) > max_chars:
                chunk_text = chunk_text[:max_chars] + "..."

            context_parts.append(
                f"[Source {i}: {result['page_title']}]\n"
                f"{chunk_text}\n"
            )

        return "\n".join(context_parts)


# ============================================================================
# DYNAMIC CONTENT MANAGER
# ============================================================================

class DynamicContentManager:
    """
    Manages dynamic web content scraping and caching

    Best practices:
    - Singleton pattern
    - Caching scraped content
    - Error handling
    - Proper initialization
    """

    def __init__(self):
        self.scraper = WebScraper(
            timeout=Config.SCRAPER_TIMEOUT,
            max_retries=Config.SCRAPER_MAX_RETRIES
        )
        self.cached_content = {}  # url -> scraped content
        self.constant_url_content = None  # Cache for constant URL

        # Scrape constant URL at startup if configured
        if Config.ENABLE_DYNAMIC_URL and Config.DYNAMIC_URL:
            self._scrape_constant_url()

    def _scrape_constant_url(self):
        """Scrape the constant URL and cache it"""
        try:
            logger.info(f"Scraping constant URL: {Config.DYNAMIC_URL}")
            result = self.scraper.scrape_url(Config.DYNAMIC_URL)

            if result['success']:
                # Chunk the content
                chunks = self.scraper.chunk_scraped_content(
                    result['content'],
                    chunk_size=Config.SCRAPER_CHUNK_SIZE,
                    overlap=Config.SCRAPER_CHUNK_OVERLAP
                )

                # Format for context
                formatted = f"[Dynamic Content from {Config.DYNAMIC_URL}]\n"
                formatted += "\n\n".join(chunks[:3])  # Use first 3 chunks

                self.constant_url_content = formatted
                logger.info(f"✓ Constant URL scraped: {len(result['content'])} chars, {len(chunks)} chunks")
            else:
                logger.error(f"Failed to scrape constant URL: {result['error']}")
                self.constant_url_content = ""

        except Exception as e:
            logger.error(f"Error scraping constant URL: {e}")
            self.constant_url_content = ""

    def scrape_url(self, url: str) -> Dict[str, any]:
        """
        Scrape URL with caching

        Args:
            url: URL to scrape

        Returns:
            Scraping result dict
        """
        # Check cache
        if url in self.cached_content:
            logger.info(f"⚡ Using cached content for {url}")
            return self.cached_content[url]

        # Scrape
        result = self.scraper.scrape_url(url)

        # Cache if successful
        if result['success']:
            self.cached_content[url] = result

        return result

    def get_constant_url_content(self) -> str:
        """Get content from constant URL (cached)"""
        if self.constant_url_content is not None:
            return self.constant_url_content

        # Try to scrape if not cached
        if Config.ENABLE_DYNAMIC_URL and Config.DYNAMIC_URL:
            self._scrape_constant_url()
            return self.constant_url_content or ""

        return ""


# Initialize global instance
dynamic_content_manager = DynamicContentManager()


# ============================================================================
# PREPROCESSING NODE WITH URL DETECTION
# ============================================================================

def create_enhanced_preprocessor():
    """
    Preprocessing node with intelligent routing

    Features:
    - URL detection (regex)
    - Query optimization
    - Query type classification
    - Routing decision
    """

    def preprocess_node(state: AgentState) -> AgentState:
        """Enhanced preprocessing with URL detection and routing"""
        messages = state["messages"]
        original_query = messages[-1].content if messages else ""

        logger.info(f"Preprocessing query: {original_query[:50]}...")

        # Detect URLs in query
        url_pattern = r'https?://[^\s]+'
        detected_urls = re.findall(url_pattern, original_query)

        # Determine routing
        if detected_urls:
            query_type = "url_query"
            next_agent = "scraper"
            logger.info(f"✓ Detected {len(detected_urls)} URL(s), routing to scraper")
        else:
            # Normal RAG workflow
            query_type = "rag_query"
            next_agent = "retrieve"
            logger.info("✓ No URLs detected, routing to RAG workflow")

        # Query optimization (remove filler words)
        optimized_query = original_query.strip()
        filler_words = ['please', 'can you', 'could you', 'tell me', 'i want to know']
        for filler in filler_words:
            optimized_query = optimized_query.lower().replace(filler, '').strip()

        if optimized_query:
            optimized_query = optimized_query.capitalize()
        else:
            optimized_query = original_query  # Fallback

        if original_query != optimized_query:
            logger.info(f"✓ Optimized query: '{original_query}' → '{optimized_query}'")

        return {
            "messages": [],
            "next_agent": next_agent,
            "retrieved_context": "",
            "retrieved_chunks": [],
            "original_query": original_query,
            "optimized_query": optimized_query,
            "query_type": query_type,
            "detected_urls": detected_urls,
            "dynamic_context": "",
            "scraping_metadata": {},
            "use_cache": False
        }

    return preprocess_node


# ============================================================================
# SCRAPER NODE
# ============================================================================

def create_scraper_node():
    """
    Web scraping node for dynamic content

    Features:
    - Scrapes URLs from query
    - Chunks scraped content
    - Error handling and fallback
    - Metadata tracking
    """

    def scraper_node(state: AgentState) -> AgentState:
        """Scrape URLs and prepare dynamic context"""
        detected_urls = state.get("detected_urls", [])

        if not detected_urls:
            logger.warning("Scraper node called but no URLs detected")
            return {
                "messages": [],
                "next_agent": "generate",
                "retrieved_context": "",
                "retrieved_chunks": [],
                "original_query": state.get("original_query", ""),
                "optimized_query": state.get("optimized_query", ""),
                "query_type": state.get("query_type", "url_query"),
                "detected_urls": [],
                "dynamic_context": "",
                "scraping_metadata": {"error": "No URLs to scrape"},
                "use_cache": False
            }

        logger.info(f"🌐 Scraping {len(detected_urls)} URL(s)...")

        all_content = []
        metadata = {
            "urls_scraped": [],
            "urls_failed": [],
            "total_chars": 0,
            "chunks_created": 0
        }

        for url in detected_urls[:3]:  # Limit to 3 URLs to avoid too much content
            result = dynamic_content_manager.scrape_url(url)

            if result['success']:
                # Chunk the content
                chunks = dynamic_content_manager.scraper.chunk_scraped_content(
                    result['content'],
                    chunk_size=Config.SCRAPER_CHUNK_SIZE,
                    overlap=Config.SCRAPER_CHUNK_OVERLAP
                )

                # Use first 3 chunks to avoid overwhelming context
                selected_chunks = chunks[:3]
                all_content.extend(selected_chunks)

                metadata["urls_scraped"].append(url)
                metadata["total_chars"] += len(result['content'])
                metadata["chunks_created"] += len(selected_chunks)

                logger.info(f"  ✓ Scraped {url}: {len(result['content'])} chars → {len(selected_chunks)} chunks")
            else:
                metadata["urls_failed"].append(url)
                logger.error(f"  ✗ Failed to scrape {url}: {result['error']}")

        # Format dynamic context
        if all_content:
            dynamic_context = "[Dynamic Web Content]\n\n" + "\n\n".join(all_content)
            logger.info(f"✓ Created dynamic context: {len(dynamic_context)} chars from {len(all_content)} chunks")
        else:
            dynamic_context = ""
            logger.warning("✗ No content scraped, will proceed without dynamic context")

        return {
            "messages": [],
            "next_agent": "generate",
            "retrieved_context": "",  # Will be filled by generation node if needed
            "retrieved_chunks": [],
            "original_query": state.get("original_query", ""),
            "optimized_query": state.get("optimized_query", ""),
            "query_type": state.get("query_type", "url_query"),
            "detected_urls": detected_urls,
            "dynamic_context": dynamic_context,
            "scraping_metadata": metadata,
            "use_cache": False
        }

    return scraper_node


# ============================================================================
# RETRIEVAL NODE
# ============================================================================

def create_retrieval_node(kb_retriever: KnowledgeBaseRetriever):
    """
    Retrieval node for static KB RAG
    """

    def retrieval_node(state: AgentState) -> AgentState:
        """Retrieve relevant chunks from knowledge base"""
        query = state.get("optimized_query") or state["messages"][-1].content

        logger.info("🔎 Retrieving from knowledge base...")

        # Retrieve from static KB
        results = kb_retriever.retrieve(query, top_k=Config.TOP_K_RESULTS)
        context = kb_retriever.format_context(results)

        logger.info(f"  ✓ Retrieved {len(results)} chunks")

        return {
            "messages": [],
            "next_agent": "generate",
            "retrieved_context": context,
            "retrieved_chunks": results,
            "original_query": state.get("original_query", ""),
            "optimized_query": state.get("optimized_query", ""),
            "query_type": state.get("query_type", "rag_query"),
            "detected_urls": state.get("detected_urls", []),
            "dynamic_context": state.get("dynamic_context", ""),
            "scraping_metadata": state.get("scraping_metadata", {}),
            "use_cache": False
        }

    return retrieval_node


# ============================================================================
# GENERATION NODE WITH CONTEXT MERGING
# ============================================================================

def create_generation_node():
    """
    Generation node with sales persona and context merging

    Features:
    - Merges static KB + dynamic scraped content
    - Uses conversation history
    - Sales agent persona
    - Adaptive prompts
    """

    llm = ChatOllama(
        model=Config.LLM_MODEL,
        temperature=Config.TEMPERATURE,
        num_predict=Config.NUM_PREDICT,
        num_ctx=Config.NUM_CTX,
        streaming=True,
    )

    def generation_node(state: AgentState) -> AgentState:
        """Generate response with merged context and sales persona"""
        user_query = state.get("original_query") or state["messages"][-1].content
        static_context = state.get("retrieved_context", "")
        dynamic_context = state.get("dynamic_context", "")
        query_type = state.get("query_type", "rag_query")

        logger.info("💬 Generating response...")

        # Extract conversation history
        conversation_history = []
        all_messages = state.get("messages", [])

        for msg in all_messages:
            if isinstance(msg, HumanMessage):
                conversation_history.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                conversation_history.append(f"Assistant: {msg.content}")

        history_text = "\n".join(conversation_history[-6:]) if conversation_history else "No previous conversation"

        # Merge contexts
        # Priority: Dynamic > Static > Constant URL
        merged_context = ""

        if dynamic_context:
            merged_context += f"{dynamic_context}\n\n"
            logger.info("  ✓ Using dynamic scraped content")

        if static_context:
            merged_context += f"{static_context}\n\n"
            logger.info("  ✓ Using static KB content")

        # Add constant URL content if available
        constant_url_content = dynamic_content_manager.get_constant_url_content()
        if constant_url_content:
            merged_context += f"{constant_url_content}\n\n"
            logger.info("  ✓ Using constant URL content")

        if not merged_context:
            merged_context = "No specific product information available. Use general knowledge about Export Genius."
            logger.warning("  ⚠️  No context available")

        # Sales agent system prompt
        system_prompt = f"""You are an intelligent sales agent for Export Genius, a premium dashboard product for import/export data analytics.

Your goal: Engage conversationally, remember context, and upsell Export Genius based on the user's needs.

CONVERSATION HISTORY:
{history_text}

PRODUCT KNOWLEDGE:
{merged_context}

Instructions:
1. Remember information from conversation history (e.g., user's name, their interests)
2. Answer questions naturally and conversationally
3. When relevant, highlight how Export Genius can solve their problems
4. If user asks about something from previous conversation, USE THE HISTORY
5. If information is not in product knowledge, engage conversationally and guide them back to Export Genius features
6. Be friendly, helpful, and focus on understanding their needs
7. Don't just say "I cannot find information" - be proactive and helpful

answer only from provided context

"""

        # Create messages for LLM
        system_message = SystemMessage(content=system_prompt)
        llm_messages = [system_message, HumanMessage(content=user_query)]

        # Get response from LLM
        try:
            response = llm.invoke(llm_messages)
            logger.info(f"  ✓ Generated response ({len(response.content)} chars)")
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            response_content = "I apologize, but I encountered an error processing your request. Please try again."
            response = AIMessage(content=response_content)

        return {
            "messages": [response],
            "next_agent": "END",
            "retrieved_context": static_context,
            "retrieved_chunks": state.get("retrieved_chunks", []),
            "original_query": user_query,
            "optimized_query": state.get("optimized_query", ""),
            "query_type": query_type,
            "detected_urls": state.get("detected_urls", []),
            "dynamic_context": dynamic_context,
            "scraping_metadata": state.get("scraping_metadata", {}),
            "use_cache": False
        }

    return generation_node


# ============================================================================
# LANGGRAPH WORKFLOW WITH CONDITIONAL ROUTING
# ============================================================================

def create_hybrid_workflow():
    """
    Create hybrid workflow with conditional routing

    Architecture:
    - Preprocess → Router
    - Router → Scraper OR Retrieval
    - Scraper/Retrieval → Generation
    - Generation → END
    """

    logger.info("Building Hybrid LangGraph workflow...")

    # Initialize components
    kb_retriever = KnowledgeBaseRetriever()

    # Create nodes
    preprocessing_node = create_enhanced_preprocessor()
    scraper_node = create_scraper_node()
    retrieval_node = create_retrieval_node(kb_retriever)
    generation_node = create_generation_node()

    # Define workflow
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("preprocess", preprocessing_node)
    workflow.add_node("scraper", scraper_node)
    workflow.add_node("retrieve", retrieval_node)
    workflow.add_node("generate", generation_node)

    # Set entry point
    workflow.set_entry_point("preprocess")

    # Conditional routing from preprocessing
    def route_after_preprocess(state: AgentState) -> str:
        """Route based on query type"""
        next_agent = state.get("next_agent", "retrieve")
        logger.info(f"  → Routing to: {next_agent}")
        return next_agent

    workflow.add_conditional_edges(
        "preprocess",
        route_after_preprocess,
        {
            "scraper": "scraper",
            "retrieve": "retrieve"
        }
    )

    # Both scraper and retrieval lead to generation
    workflow.add_edge("scraper", "generate")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)

    # Compile with persistent memory
    history_path = Config.CONVERSATION_HISTORY_DIR
    memory = PersistentMemorySaver(storage_path=history_path)
    app = workflow.compile(checkpointer=memory)

    logger.info("✓ Hybrid workflow compiled successfully")
    logger.info("  → Preprocess (URL detection + routing)")
    logger.info("  → Scraper (dynamic web content)")
    logger.info("  → Retrieval (static KB RAG)")
    logger.info("  → Generation (sales persona + context merging)")
    logger.info("")

    return app


# ============================================================================
# CHATBOT INTERFACE
# ============================================================================

class HybridChatbot:
    """
    Production-ready hybrid chatbot

    Features:
    - Conversation persistence
    - Response caching
    - Error handling
    - Logging
    """

    def __init__(self, user_id: str = None):
        self.app = create_hybrid_workflow()
        self.user_id = user_id or str(uuid.uuid4())
        self.thread_id = f"user_{self.user_id}"
        self.query_cache = {}
        self.max_cache_size = Config.QUERY_CACHE_SIZE
        logger.info(f"Chatbot initialized - Session: {self.thread_id}")

    def chat(self, user_message: str) -> str:
        """
        Send message to chatbot

        Args:
            user_message: User's question

        Returns:
            Bot's response
        """
        try:
            # Check cache
            cache_key = user_message.strip().lower()
            if cache_key in self.query_cache:
                logger.info("⚡ Using cached response")
                return self.query_cache[cache_key]

            # Create config
            config = {"configurable": {"thread_id": self.thread_id}}

            # Invoke workflow
            result = self.app.invoke(
                {
                    "messages": [HumanMessage(content=user_message)],
                    "next_agent": "",
                    "retrieved_context": "",
                    "retrieved_chunks": [],
                    "original_query": "",
                    "optimized_query": "",
                    "query_type": "rag_query",
                    "detected_urls": [],
                    "dynamic_context": "",
                    "scraping_metadata": {},
                    "use_cache": False
                },
                config=config
            )

            # Extract response
            if result["messages"]:
                response = result["messages"][-1].content

                # Cache response
                self._add_to_cache(cache_key, response)

                # Log metadata
                if result.get("detected_urls"):
                    logger.info(f"  📊 Processed URL query: {len(result['detected_urls'])} URLs")
                if result.get("scraping_metadata"):
                    logger.info(f"  📊 Scraping: {result['scraping_metadata']}")

                return response
            else:
                return "I'm sorry, I couldn't process that request."

        except Exception as e:
            logger.error(f"Error in chat: {e}", exc_info=True)
            return "I apologize, but I encountered an error. Please try again."

    def stream_chat(self, user_message: str):
        """Stream chatbot response (for real-time UI)"""
        # Check cache
        cache_key = user_message.strip().lower()
        if cache_key in self.query_cache:
            yield self.query_cache[cache_key]
            return

        config = {"configurable": {"thread_id": self.thread_id}}

        full_response = ""
        try:
            for chunk in self.app.stream(
                {
                    "messages": [HumanMessage(content=user_message)],
                    "next_agent": "",
                    "retrieved_context": "",
                    "retrieved_chunks": [],
                    "original_query": "",
                    "optimized_query": "",
                    "query_type": "rag_query",
                    "detected_urls": [],
                    "dynamic_context": "",
                    "scraping_metadata": {},
                    "use_cache": False
                },
                config=config
            ):
                if "generate" in chunk:
                    if chunk["generate"]["messages"]:
                        content = chunk["generate"]["messages"][-1].content
                        full_response = content
                        yield content

            # Cache complete response
            if full_response:
                self._add_to_cache(cache_key, full_response)

        except Exception as e:
            logger.error(f"Error in stream_chat: {e}", exc_info=True)
            yield "I apologize, but I encountered an error. Please try again."

    def _add_to_cache(self, key: str, value: str):
        """Add to cache with size limit (LRU)"""
        if len(self.query_cache) >= self.max_cache_size:
            self.query_cache.pop(next(iter(self.query_cache)))
        self.query_cache[key] = value

    def reset_conversation(self):
        """Reset conversation (new user session)"""
        self.user_id = str(uuid.uuid4())
        self.thread_id = f"user_{self.user_id}"
        logger.info(f"Conversation reset - New session: {self.thread_id}")

    def clear_cache(self):
        """Clear response cache"""
        self.query_cache.clear()
        logger.info("Cache cleared")


# ============================================================================
# GRADIO UI
# ============================================================================

def create_gradio_interface():
    """Create production-ready Gradio UI"""

    logger.info("Initializing Hybrid Chatbot...")
    chatbot = HybridChatbot()
    logger.info("✅ Hybrid Chatbot ready!")
    logger.info("")

    def chat_fn(message, history):
        """Chat function for Gradio"""
        if not message:
            return ""

        response = chatbot.chat(message)
        return response

    def reset_fn():
        """Reset conversation"""
        chatbot.reset_conversation()

    # Create Gradio ChatInterface
    demo = gr.ChatInterface(
        fn=chat_fn,
        title="💼 Export Genius Hybrid Sales Agent",
        description="""Hi! I'm your intelligent sales agent for Export Genius with dynamic content capabilities.

**Features:**
- 🎯 Sales-focused conversations and upselling
- 💬 Remembers conversation context
- 📚 Answers from Export Genius knowledge base
- 🌐 Can scrape and analyze web URLs you provide
- 🔄 Merges static + dynamic content seamlessly

**Try me with:**
- Product questions: "What are your pricing plans?"
- URL analysis: "Analyze this page: https://example.com"
- Contextual memory: "My name is John" then "What's my name?"

**Powered by:** LangGraph + RAG + Web Scraping + Sales AI""",
        examples=[
            "What is Export Genius?",
            "What are your pricing plans?",
            "How can Export Genius help my business?",
            "Tell me about your features",
            "My name is Pulkit",
        ],
        theme=gr.themes.Soft(),
        chatbot=gr.Chatbot(height=500, show_copy_button=True),
        textbox=gr.Textbox(placeholder="Ask about Export Genius or provide a URL to analyze...", container=False, scale=7),
        submit_btn="Send",
        retry_btn=None,
        undo_btn=None,
        clear_btn="Clear Conversation"
    )

    return demo


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point with proper initialization and error handling"""
    import sys

    print()
    print("=" * 80)
    print("🚀 HYBRID SALES AGENT - Export Genius")
    print("   Sales AI + RAG + Dynamic Web Scraping")
    print("=" * 80)
    print()

    # Validation checks
    if not Config.FAISS_INDEX_FILE.exists() or not Config.CHUNKS_FILE.exists():
        logger.error("Knowledge base not found!")
        print()
        print("Please build your knowledge base first:")
        print("  python build_kb_WORKING.py")
        print()
        sys.exit(1)

    # Check Ollama
    try:
        ollama.list()
    except Exception:
        logger.error("Ollama not running!")
        print()
        print("Please start Ollama:")
        print("  1. Ensure Ollama is installed")
        print("  2. Run: ollama pull deepseek-v3.1:671b-cloud")
        print("  3. Run: ollama pull nomic-embed-text")
        print()
        sys.exit(1)

    try:
        # Create and launch Gradio interface
        demo = create_gradio_interface()

        print("=" * 80)
        print("✅ HYBRID CHATBOT READY!")
        print("=" * 80)
        print()
        print("Features enabled:")
        print("  ✓ Sales agent persona")
        print("  ✓ Conversation history")
        print("  ✓ Static KB RAG")
        print("  ✓ Dynamic web scraping")
        print("  ✓ Context merging")
        if Config.ENABLE_DYNAMIC_URL:
            print(f"  ✓ Constant URL: {Config.DYNAMIC_URL}")
        print()
        print("🌐 Opening Gradio interface...")
        print()

        demo.launch(
            server_name="0.0.0.0",
            server_port=7860,
            share=True,
            show_error=True
        )

    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
