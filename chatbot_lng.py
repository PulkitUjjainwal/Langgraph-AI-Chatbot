"""
LangGraph Multi-Agent Chatbot with RAG + Tool Capability (ULTIMATE WORKFLOW)

ENHANCED LANGGRAPH ARCHITECTURE:
    User Query
        ↓
    [Preprocess Node] → Query optimization & intelligent routing
        ↓
        ┌─────────────────┐
        │ Router Decision │
        └─────────────────┘
                ↓
        ╔═══════════════╗      ╔═══════════════════╗
        ║  CHATBOT NODE ║      ║   RAG WORKFLOW    ║
        ║ (With Tools!) ║      ║                   ║
        ╚═══════════════╝      ║ [Retrieve] → [Generate]
                │              ╚═══════════════════╝
                └─────────────────────┤
                                      ↓
                                [Final Response]

FEATURES:
    ✅ RAG Workflow: Knowledge base queries
    ✅ Chatbot Node: Tool-capable for calculations, future expansions
    ✅ Intelligent Routing: Preprocessing decides optimal path
    ✅ Tool System: Extensible tool framework
    ✅ Caching: Response and embedding caching
    ✅ Streaming: Real-time response generation
"""

import json
from pathlib import Path
from typing import TypedDict, Annotated, Sequence, Literal
import operator
import re

import numpy as np
import faiss
import ollama
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import gradio as gr


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Configuration for chatbot"""

    # Paths (matches your KB builder output)
    DATA_DIR = Path("data")
    CHUNKS_FILE = DATA_DIR / "kb_chunks.json"
    FAISS_INDEX_FILE = DATA_DIR / "faiss_normalized.index"

    # Models (OPTIMIZED for speed)
    EMBEDDING_MODEL = "nomic-embed-text"  # Same as KB builder
    LLM_MODEL = "deepseek-v3.1:671b-cloud"  # Faster model

    # RAG settings (OPTIMIZED)
    TOP_K_RESULTS = 2  # Reduced from 3 for faster response
    MAX_CHUNK_CHARS = 400  # Truncate chunks to reduce context size

    # LLM Performance settings (OPTIMIZED)
    TEMPERATURE = 0.3  # Lower = faster, more focused (was 0.7)
    NUM_PREDICT = 200  # Limit response length for speed
    NUM_CTX = 2048  # Reduce context window (default 4096)

    # LangGraph settings
    MAX_ITERATIONS = 5


# ============================================================================
# ENHANCED STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    """Enhanced state shared between agents with tool tracking"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_agent: str
    retrieved_context: str
    original_query: str
    optimized_query: str
    query_type: str  # simple, medium, complex, tool_required
    use_cache: bool
    retrieved_chunks: list
    # NEW: Tool execution tracking
    tool_calls: list  # Store tool calls and results
    last_tool_output: str  # Output from last tool execution


# ============================================================================
# KNOWLEDGE BASE RETRIEVER (RAG)
# ============================================================================

class KnowledgeBaseRetriever:
    """RAG system using FAISS and Ollama (OPTIMIZED with embedding cache)"""

    def __init__(self):
        print("📚 Loading Knowledge Base...")

        # Load FAISS index
        if not Config.FAISS_INDEX_FILE.exists():
            raise FileNotFoundError(
                f"FAISS index not found at {Config.FAISS_INDEX_FILE}\n"
                f"Please run build_kb_WORKING.py first!"
            )

        self.index = faiss.read_index(str(Config.FAISS_INDEX_FILE))

        # Load chunks
        if not Config.CHUNKS_FILE.exists():
            raise FileNotFoundError(
                f"Chunks file not found at {Config.CHUNKS_FILE}\n"
                f"Please run build_kb_WORKING.py first!"
            )

        with open(Config.CHUNKS_FILE, 'r', encoding='utf-8') as f:
            self.chunks = json.load(f)

        # OPTIMIZATION: Embedding cache to skip Ollama calls for repeated queries
        self.embedding_cache = {}
        self.max_cache_size = 100

        print(f"  ✓ Loaded {len(self.chunks)} chunks")
        print(f"  ✓ FAISS index ready")
        print(f"  ✓ Embedding cache enabled (max {self.max_cache_size} queries)")
    
    def retrieve(self, query: str, top_k: int = Config.TOP_K_RESULTS) -> list:
        """
        Retrieve relevant chunks for query using RAG (OPTIMIZED with caching)
        """
        # OPTIMIZATION: Check embedding cache first
        cache_key = query.strip().lower()
        if cache_key in self.embedding_cache:
            print("  ⚡ Using cached embedding")
            query_embedding = self.embedding_cache[cache_key]
        else:
            # Create query embedding
            response = ollama.embeddings(
                model=Config.EMBEDDING_MODEL,
                prompt=query
            )
            query_embedding = np.array([response['embedding']]).astype('float32')

            # CRITICAL: Normalize query (same as KB)
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

    def _add_to_embedding_cache(self, key: str, embedding: np.ndarray):
        """Add embedding to cache with size limit"""
        if len(self.embedding_cache) >= self.max_cache_size:
            # Remove oldest item (FIFO)
            self.embedding_cache.pop(next(iter(self.embedding_cache)))
        self.embedding_cache[key] = embedding
    
    def format_context(self, results: list) -> str:
        """Format retrieved chunks as context for LLM (OPTIMIZED - truncated)"""
        context_parts = []
        for i, result in enumerate(results, 1):
            # Truncate chunk text to reduce context size
            chunk_text = result['chunk_text']
            if len(chunk_text) > Config.MAX_CHUNK_CHARS:
                chunk_text = chunk_text[:Config.MAX_CHUNK_CHARS] + "..."

            context_parts.append(
                f"[Source {i}: {result['page_title']}]\n"
                f"{chunk_text}\n"
            )
        return "\n".join(context_parts)


# ============================================================================
# ENHANCED PREPROCESSING NODE WITH INTELLIGENT ROUTING
# ============================================================================

def create_enhanced_preprocessor():
    """Preprocessing with intelligent routing to chatbot vs RAG"""
    
    def preprocess_node(state: AgentState) -> AgentState:
        """Enhanced preprocessing with routing decision"""
        messages = state["messages"]
        original_query = messages[-1].content if messages else ""

        print(f"🔍 Preprocessing query...")

        query_lower = original_query.lower().strip()
        word_count = len(query_lower.split())

        # Enhanced query classification with tool detection
        tool_keywords = ['calculate', 'compute', 'sum', 'total', 'multiply', 'divide', 'add', 'subtract']
        math_symbols = ['+', '-', '*', '/', '%']
        
        has_tool_keyword = any(word in query_lower for word in tool_keywords)
        has_math_symbol = any(symbol in query_lower for symbol in math_symbols)
        has_numbers = bool(re.search(r'\d+', query_lower))

        if has_tool_keyword or (has_math_symbol and has_numbers):
            query_type = "tool_required"
            next_agent = "chatbot"  # Route to chatbot for tool usage
        elif word_count <= 3:
            query_type = "simple"
            next_agent = "rag_workflow"  # Simple queries go to RAG
        elif word_count <= 8:
            query_type = "medium" 
            next_agent = "rag_workflow"
        else:
            query_type = "complex"
            next_agent = "rag_workflow"

        # Query optimization
        optimized_query = original_query.strip()
        filler_words = ['please', 'can you', 'could you', 'tell me', 'i want to know', 'hey', 'hello']
        for filler in filler_words:
            optimized_query = optimized_query.lower().replace(filler, '').strip()
        
        # Capitalize for consistency
        if optimized_query:
            optimized_query = optimized_query.capitalize()

        print(f"  ✓ Query type: {query_type}")
        print(f"  ✓ Routing to: {next_agent}")
        if original_query != optimized_query:
            print(f"  ✓ Optimized: '{original_query}' → '{optimized_query}'")

        return {
            "messages": [],
            "next_agent": next_agent,
            "retrieved_context": "",
            "original_query": original_query,
            "optimized_query": optimized_query,
            "query_type": query_type,
            "use_cache": False,
            "retrieved_chunks": [],
            "tool_calls": [],
            "last_tool_output": ""
        }

    return preprocess_node


# ============================================================================
# CHATBOT NODE WITH TOOL CAPABILITY
# ============================================================================

def create_chatbot_node():
    """
    Dedicated chatbot node that can use tools/function calling
    
    Future-ready for:
    - Calculator tools
    - API calls  
    - Database queries
    - External integrations
    """
    
    # Configure LLM with tool-calling capability
    llm = ChatOllama(
        model=Config.LLM_MODEL,
        temperature=Config.TEMPERATURE,
        num_predict=Config.NUM_PREDICT,
        num_ctx=Config.NUM_CTX,
    )

    # TOOLS - Start with simple calculator, easily extendable
    def calculator_tool(expression: str) -> str:
        """Evaluate mathematical expressions safely"""
        try:
            # Safe evaluation - only basic math operations
            allowed_chars = set('0123456789+-*/.() ')
            if all(c in allowed_chars for c in expression):
                # Use eval for simple math (in real production, use safer alternatives)
                result = eval(expression)
                return f"Calculation: {expression} = {result}"
            else:
                return "Error: Only basic math operations allowed (numbers, +, -, *, /, .)"
        except Exception as e:
            return f"Error calculating '{expression}': {str(e)}"

    # Available tools registry
    tools = [calculator_tool]
    tool_map = {"calculator": calculator_tool}

    def chatbot_node(state: AgentState) -> AgentState:
        """Chatbot node that can decide to use tools or respond directly"""
        user_query = state.get("original_query") or state["messages"][-1].content
        query_type = state.get("query_type", "medium")

        print(f"🤖 Chatbot node processing...")

        # Enhanced system prompt for tool usage
        system_prompt = """You are a helpful AI assistant that can use tools when needed.

Available tools:
- calculator: For mathematical calculations (use for questions involving numbers, math, calculations)

Instructions:
1. Analyze if the user's query requires tool usage
2. If it's a calculation question, use the calculator tool
3. If no tool is needed, respond directly as a helpful assistant
4. Always be helpful and concise

Examples:
User: "What's 15 * 24 + 30?" → Use calculator
User: "Tell me about your products" → Respond directly
User: "Calculate the sum of 100 and 250" → Use calculator
User: "Hello, how are you?" → Respond directly"""

        # Check if this looks like a tool-requiring query
        tool_keywords = ['calculate', 'compute', 'sum', 'total', 'multiply', 'divide', 'add', 'subtract']
        math_symbols = ['+', '-', '*', '/', '%']
        
        requires_tool = any(word in user_query.lower() for word in tool_keywords)
        has_math = any(symbol in user_query for symbol in math_symbols)
        has_numbers = bool(re.search(r'\d+', user_query))

        tool_used = False
        tool_result = ""

        if requires_tool or (has_math and has_numbers):
            print("  🛠️  Tool required - using calculator")
            # Extract mathematical expression
            math_pattern = r'[\d\+\-\*\/\.\(\) ]+'
            numbers_expr = re.findall(math_pattern, user_query)
            if numbers_expr:
                expression = numbers_expr[0].strip()
                # Clean up expression
                expression = re.sub(r'\s+', '', expression)  # Remove spaces
                try:
                    tool_result = calculator_tool(expression)
                    response = f"🔢 {tool_result}"
                    tool_used = True
                except Exception as e:
                    response = f"Sorry, I couldn't calculate that: {str(e)}"
            else:
                # If tool keywords but no clear expression, ask for clarification
                response = "I can help with calculations! Please provide a mathematical expression like '15 * 24 + 30' or 'calculate 100 + 250'."
        else:
            # Regular conversational response
            llm_messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_query)
            ]
            try:
                ai_response = llm.invoke(llm_messages)
                response = ai_response.content
            except Exception as e:
                response = f"I encountered an error: {str(e)}. Please try again."

        print(f"  ✓ Chatbot response ready")
        if tool_used:
            print(f"  🛠️  Tool used: calculator")

        return {
            "messages": [AIMessage(content=response)],
            "next_agent": "END",
            "retrieved_context": state.get("retrieved_context", ""),
            "original_query": state.get("original_query", ""),
            "optimized_query": state.get("optimized_query", ""),
            "query_type": query_type,
            "use_cache": False,
            "retrieved_chunks": state.get("retrieved_chunks", []),
            "tool_calls": ["calculator"] if tool_used else [],
            "last_tool_output": tool_result if tool_used else ""
        }

    return chatbot_node


# ============================================================================
# RAG WORKFLOW NODES (Retrieval + Generation)
# ============================================================================

def create_retrieval_node(kb_retriever: KnowledgeBaseRetriever):
    """Dedicated retrieval node for RAG workflow"""

    def retrieval_node(state: AgentState) -> AgentState:
        """Retrieve relevant chunks from knowledge base"""
        # Use optimized query if available, otherwise original
        query = state.get("optimized_query") or state["messages"][-1].content

        print(f"🔎 Retrieving from knowledge base...")

        # Retrieve relevant context from KB
        results = kb_retriever.retrieve(query, top_k=Config.TOP_K_RESULTS)
        context = kb_retriever.format_context(results)

        print(f"  ✓ Retrieved {len(results)} chunks")

        return {
            "messages": [],
            "next_agent": "generation",
            "retrieved_context": context,
            "original_query": state.get("original_query", ""),
            "optimized_query": state.get("optimized_query", ""),
            "query_type": state.get("query_type", "medium"),
            "use_cache": False,
            "retrieved_chunks": results,
            "tool_calls": state.get("tool_calls", []),
            "last_tool_output": state.get("last_tool_output", "")
        }

    return retrieval_node


def create_generation_node():
    """Generation node that creates answer from retrieved context"""

    llm = ChatOllama(
        model=Config.LLM_MODEL,
        temperature=Config.TEMPERATURE,
        num_predict=Config.NUM_PREDICT,
        num_ctx=Config.NUM_CTX,
        streaming=True,
    )

    def generation_node(state: AgentState) -> AgentState:
        """Generate response using retrieved context"""
        user_query = state.get("original_query") or state["messages"][-1].content
        context = state["retrieved_context"]
        query_type = state.get("query_type", "medium")

        print(f"💬 Generating response...")

        # Adapt prompt based on query complexity
        if query_type == "simple":
            system_prompt = f"""Answer briefly using the context below.

Context:
{context}"""
        else:
            system_prompt = f"""Answer the question using only the context below. Be concise and cite sources.

Context:
{context}"""

        # Create messages for LLM
        system_message = SystemMessage(content=system_prompt)
        llm_messages = [system_message, HumanMessage(content=user_query)]

        # Get response from LLM
        response = llm.invoke(llm_messages)

        print(f"  ✓ Generated response ({len(response.content)} chars)")

        return {
            "messages": [AIMessage(content=response.content)],
            "next_agent": "END",
            "retrieved_context": context,
            "original_query": state.get("original_query", ""),
            "optimized_query": state.get("optimized_query", ""),
            "query_type": query_type,
            "use_cache": False,
            "retrieved_chunks": state.get("retrieved_chunks", []),
            "tool_calls": state.get("tool_calls", []),
            "last_tool_output": state.get("last_tool_output", "")
        }

    return generation_node


# ============================================================================
# ENHANCED LANGGRAPH WORKFLOW WITH CHATBOT NODE
# ============================================================================

def create_enhanced_workflow():
    """
    Create enhanced workflow with chatbot node and conditional routing
    """
    print("🔧 Building Enhanced LangGraph workflow...")

    kb_retriever = KnowledgeBaseRetriever()

    # Create all nodes
    preprocessing_node = create_enhanced_preprocessor()
    retrieval_node = create_retrieval_node(kb_retriever)
    generation_node = create_generation_node()
    chatbot_node = create_chatbot_node()

    workflow = StateGraph(AgentState)

    # Add all nodes
    workflow.add_node("preprocess", preprocessing_node)
    workflow.add_node("retrieve", retrieval_node)
    workflow.add_node("generate", generation_node)
    workflow.add_node("chatbot", chatbot_node)

    # Set entry point
    workflow.set_entry_point("preprocess")

    # Conditional routing from preprocess
    def route_after_preprocess(state: AgentState) -> str:
        """Route to appropriate node based on query type"""
        next_agent = state.get("next_agent", "rag_workflow")
        
        if next_agent == "chatbot":
            return "chatbot"
        else:
            return "retrieve"  # Continue with RAG workflow

    workflow.add_conditional_edges(
        "preprocess",
        route_after_preprocess,
        {
            "chatbot": "chatbot",
            "retrieve": "retrieve"
        }
    )

    # RAG workflow continues as before
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)
    workflow.add_edge("chatbot", END)  # Chatbot can also end directly

    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)

    print("  ✓ Enhanced workflow compiled:")
    print("    → Preprocess (intelligent routing)")
    print("    → Chatbot Node (with tool capability)") 
    print("    → RAG Workflow (retrieve → generate)")
    print("    → Conditional routing based on query type")
    print()

    return app


# ============================================================================
# ENHANCED CHATBOT CLASS
# ============================================================================

class EnhancedChatbot:
    """Enhanced chatbot with both RAG and tool-capable chatbot nodes"""

    def __init__(self):
        self.app = create_enhanced_workflow()
        self.thread_id = "default_session"
        self.query_cache = {}
        self.max_cache_size = 50

    def chat(self, user_message: str) -> str:
        """Send message through enhanced workflow"""
        cache_key = user_message.strip().lower()
        if cache_key in self.query_cache:
            print("  ⚡ Using cached response")
            return self.query_cache[cache_key]

        config = {"configurable": {"thread_id": self.thread_id}}

        result = self.app.invoke(
            {
                "messages": [HumanMessage(content=user_message)],
                "next_agent": "",
                "retrieved_context": "",
                "original_query": "",
                "optimized_query": "",
                "query_type": "medium", 
                "use_cache": False,
                "retrieved_chunks": [],
                "tool_calls": [],
                "last_tool_output": ""
            },
            config=config
        )

        if result["messages"]:
            response = result["messages"][-1].content
            self._add_to_cache(cache_key, response)
            
            # Log which path was taken
            if result.get("tool_calls"):
                print(f"  🛠️  Response via Chatbot Node (tools used: {result['tool_calls']})")
            else:
                print(f"  📚 Response via RAG Workflow")
                
            return response
        else:
            return "I'm sorry, I couldn't process that request."

    def stream_chat(self, user_message: str):
        """Stream chatbot response token by token"""
        cache_key = user_message.strip().lower()
        if cache_key in self.query_cache:
            yield self.query_cache[cache_key]
            return

        config = {"configurable": {"thread_id": self.thread_id}}

        full_response = ""
        for chunk in self.app.stream(
            {
                "messages": [HumanMessage(content=user_message)],
                "next_agent": "",
                "retrieved_context": "",
                "original_query": "",
                "optimized_query": "",
                "query_type": "medium",
                "use_cache": False,
                "retrieved_chunks": [],
                "tool_calls": [],
                "last_tool_output": ""
            },
            config=config
        ):
            # Extract messages from chunk
            for node_name, node_output in chunk.items():
                if node_output and "messages" in node_output:
                    content = node_output["messages"][-1].content
                    full_response = content
                    yield content

        # Cache the complete response
        if full_response:
            self._add_to_cache(cache_key, full_response)

    def _add_to_cache(self, key: str, value: str):
        """Add item to cache with size limit"""
        if len(self.query_cache) >= self.max_cache_size:
            self.query_cache.pop(next(iter(self.query_cache)))
        self.query_cache[key] = value

    def reset_conversation(self):
        """Reset conversation history"""
        import uuid
        self.thread_id = str(uuid.uuid4())
        print("🔄 Conversation reset")

    def clear_cache(self):
        """Clear query cache"""
        self.query_cache.clear()
        print("🗑️  Cache cleared")


# ============================================================================
# GRADIO UI
# ============================================================================

def create_gradio_interface():
    """Create Gradio UI for enhanced chatbot"""
    
    # Initialize chatbot
    print("🤖 Initializing Enhanced Chatbot...")
    chatbot = EnhancedChatbot()
    print("✅ Enhanced Chatbot ready!")
    print("   - RAG Workflow: Knowledge base queries")
    print("   - Chatbot Node: Tool-capable for calculations")
    print("   - Intelligent Routing: Automatic path selection")
    print()

    def chat_fn(message, history):
        """Chat function for Gradio"""
        if not message:
            return ""

        # Get bot response
        response = chatbot.chat(message)
        return response
    
    def reset_fn():
        """Reset conversation"""
        chatbot.reset_conversation()
        return "Conversation reset!"

    # Enhanced examples showing both capabilities
    examples = [
        "What are your pricing plans?",
        "Calculate 25 * 48 + 120",
        "How do I get started?",
        "What's the sum of 150 and 275?",
        "Tell me about your products",
        "Compute 15% of 200"
    ]

    # Create Gradio ChatInterface
    demo = gr.ChatInterface(
        fn=chat_fn,
        title="🤖 Enhanced Import/Export Data Chatbot",
        description="""Ask me anything about our products OR use calculation tools!
        
**Features:**
- 📚 Knowledge Base: Products, pricing, features  
- 🛠️ Tools: Mathematical calculations
- 🧠 Intelligent routing automatically chooses the best approach

**Examples:** Try asking about products OR calculations!""",
        examples=examples,
        theme=gr.themes.Soft(),
        chatbot=gr.Chatbot(height=500, show_copy_button=True),
        textbox=gr.Textbox(placeholder="Type your question or calculation here...", container=False, scale=7),
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
    """Main entry point"""
    import sys
    
    print()
    print("=" * 70)
    print("🚀 ENHANCED LANGGRAPH CHATBOT WITH RAG + TOOLS")
    print("=" * 70)
    print()
    
    # Check if KB files exist
    if not Config.FAISS_INDEX_FILE.exists() or not Config.CHUNKS_FILE.exists():
        print("❌ Knowledge base not found!")
        print()
        print("Please build your knowledge base first:")
        print("  python build_kb_WORKING.py")
        print()
        sys.exit(1)
    
    # Check Ollama
    try:
        ollama.list()
    except Exception:
        print("❌ Ollama not running!")
        print()
        print("Please start Ollama:")
        print("  1. Ensure Ollama is installed")
        print("  2. Run: ollama pull deepseek-v3.1:671b-cloud")
        print("  3. Run: ollama pull nomic-embed-text")
        print()
        sys.exit(1)
    
    # Check if LLM model exists
    try:
        response = ollama.list()
        models = []
        if isinstance(response, dict) and 'models' in response:
            models = [m.get('name', m.get('model', '')) for m in response['models']]

        if not any(Config.LLM_MODEL in str(m) for m in models):
            print(f"⚠️  Model {Config.LLM_MODEL} not found. Pulling...")
            ollama.pull(Config.LLM_MODEL)
            print(f"  ✓ Downloaded {Config.LLM_MODEL}")
        else:
            print(f"  ✓ Using model: {Config.LLM_MODEL}")
    except Exception as e:
        print(f"⚠️  Could not verify LLM model: {e}")
    
    try:
        # Create and launch Gradio interface
        demo = create_gradio_interface()
        
        print("=" * 70)
        print("✅ ENHANCED CHATBOT READY!")
        print("=" * 70)
        print()
        print("🌐 Opening Gradio interface...")
        print("   URL will appear below")
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
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()