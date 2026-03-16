"""
Chatbot Agent Service
Modular chatbot workflow with LangGraph integration
"""

import time
from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage, AIMessage
from langchain_ollama import ChatOllama

from .prompts import PromptBuilder, PromptConfig
from chatbot.config.settings import Settings, get_settings


class ChatbotAgent:
    """
    Modular chatbot agent that generates responses using LangGraph workflow

    Features:
    - Uses PromptBuilder for strong accuracy enforcement
    - Prevents LLM hallucination by forcing use of context data
    - Handles both static KB and dynamic company content
    - Optimized for trade data queries
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        llm_model: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        """
        Initialize ChatbotAgent

        Args:
            settings: Settings instance (defaults to global settings)
            llm_model: LLM model name override
            api_key: API key override
        """
        self.settings = settings or get_settings()
        self.prompt_builder = PromptBuilder()

        # Configure LLM with SMART ROUTING
        llm_kwargs = {
            'model': llm_model or self.settings.llm_model,
            'temperature': 0.5,  # Default temperature (can be adjusted per query)
        }

        # SMART ROUTING: Use local by default, cloud only if API key is set
        if api_key or self.settings.ollama_api_key:
            # Cloud Ollama with authentication
            llm_kwargs['base_url'] = self.settings.ollama_base_url
            llm_kwargs['api_key'] = api_key or self.settings.ollama_api_key
            print(f"[ChatbotAgent] Using CLOUD Ollama: {self.settings.ollama_base_url}")
        else:
            # Local Ollama (no authentication needed)
            llm_kwargs['base_url'] = 'http://localhost:11434'
            print(f"[ChatbotAgent] Using LOCAL Ollama: http://localhost:11434")

        self.llm = ChatOllama(**llm_kwargs)

    def process_query(
        self,
        state: Dict[str, Any],
        session_dynamic_content: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a chatbot query and generate response

        Args:
            state: AgentState from LangGraph workflow
            session_dynamic_content: Dynamic content for current session (company data)

        Returns:
            Updated state with AI response
        """
        start_time = time.time()

        user_query = state.get("original_query", "")
        kb_context = state["retrieved_context"]
        messages = state.get("messages", [])

        print(f"\n[CHAT] Chatbot processing...")

        # Check if it's a greeting (fast path)
        greeting_response = self._handle_greeting(user_query)
        if greeting_response:
            print(f"  [GREETING] Detected greeting - instant response!")
            elapsed = time.time() - start_time
            print(f"  [FAST] Processing: {elapsed:.2f}s (greeting shortcut)")

            return {
                "messages": [AIMessage(content=greeting_response)],
                "next_agent": "END",
                "retrieved_context": "",
                "original_query": user_query,
                "use_cache": False,
                "retrieved_chunks": [],
                "start_time": state.get("start_time", time.time())
            }

        # Get dynamic content
        dynamic_content = session_dynamic_content or ""

        # Classify query
        query_type = self._classify_query_type(user_query)
        query_complexity = self._detect_query_complexity(user_query)  # simple/standard/detailed

        print(f"  [FIND] Query type: {query_type.upper()}")
        print(f"  [SMART] Complexity: {query_complexity.upper()}")

        # Build context
        context = self._build_context(
            query_type=query_type,
            kb_context=kb_context,
            dynamic_content=dynamic_content
        )

        # Build conversation history
        conversation_history = self._build_conversation_history(messages)

        # Detect industry (optional enhancement)
        industry_info = self._detect_industry(user_query, kb_context)

        # Build system prompt using PromptBuilder
        prompt_config = PromptConfig(
            site_name=self.settings.site_name,
            context=context,
            has_dynamic_content=bool(dynamic_content),
            conversation_history=conversation_history,
            industry_info=industry_info,
            query_type=query_complexity
        )

        system_prompt = self.prompt_builder.build_system_prompt(prompt_config)

        # Adjust temperature based on query complexity
        temperature = self._get_optimal_temperature(user_query)
        self.llm.temperature = temperature
        print(f"  [LLM] Temperature: {temperature}")

        # Generate response
        print(f"  [LLM] Generating response...")
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]

        response = self.llm.invoke(llm_messages)
        import re as _re
        response_text = _re.sub(r'<think>.*?</think>', '', response.content, flags=_re.DOTALL).strip()

        elapsed = time.time() - start_time
        print(f"  [OK] Generated response in {elapsed:.2f}s")

        return {
            "messages": [AIMessage(content=response_text)],
            "next_agent": "END",
            "retrieved_context": kb_context,
            "original_query": user_query,
            "use_cache": False,
            "retrieved_chunks": state.get("retrieved_chunks", []),
            "start_time": state.get("start_time", time.time())
        }

    def _handle_greeting(self, query: str) -> Optional[str]:
        """
        Detect and handle greetings with instant responses

        Returns:
            Greeting response if detected, None otherwise
        """
        greetings = ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening']
        query_lower = query.lower().strip()

        if query_lower in greetings or any(query_lower.startswith(g) for g in greetings):
            return "Hello! I'm Alex, your trade data consultant. I can help you find buyers, suppliers, explore markets, and analyze trade opportunities. What would you like to know?"

        return None

    def _classify_query_type(self, query: str) -> str:
        """
        Classify query type for context prioritization

        Returns:
            'company', 'trade_data', or 'general'
        """
        query_lower = query.lower()

        # Company profile queries
        company_keywords = ['company', 'profile', 'about', 'who is', 'what does', 'overview']
        if any(kw in query_lower for kw in company_keywords):
            return 'company'

        # Trade data queries
        trade_keywords = [
            'turnover', 'shipment', 'export', 'import', 'buyer', 'supplier',
            'trade', 'revenue', 'volume', 'value', 'commodity', 'port',
            'country', 'partner', 'top', 'major', 'annual'
        ]
        if any(kw in query_lower for kw in trade_keywords):
            return 'trade_data'

        return 'general'

    def _detect_query_complexity(self, query: str) -> str:
        """
        Detect query complexity for response length optimization

        Returns:
            'simple', 'standard', or 'detailed'
        """
        query_lower = query.lower()

        # Simple queries (yes/no, single facts)
        if any(query_lower.startswith(q) for q in ['is ', 'does ', 'can ', 'do you ', 'are ', 'what is ']):
            if len(query.split()) <= 6:
                return 'simple'

        # Detailed queries (explanations, comparisons)
        detail_keywords = ['explain', 'compare', 'difference', 'how does', 'why', 'tell me about']
        if any(kw in query_lower for kw in detail_keywords):
            return 'detailed'

        return 'standard'

    def _build_context(
        self,
        query_type: str,
        kb_context: str,
        dynamic_content: str
    ) -> str:
        """
        Build optimal context based on query type

        Prioritizes dynamic company data for company/trade queries
        """
        print(f"\n  [STATS] CONTEXT MERGING DEBUG:")
        print(f"     • KB Context Available: {len(kb_context)} chars")
        print(f"     • Dynamic Content Available: {len(dynamic_content)} chars")
        print(f"     • Merging Strategy: {query_type.upper()}")

        if query_type == 'company':
            # Company queries → Prioritize dynamic content
            if dynamic_content:
                max_dynamic = 2500
                max_kb = 800
                context = f"""=== COMPANY PROFILE (PRIMARY SOURCE) ===
{dynamic_content[:max_dynamic]}

=== ADDITIONAL REFERENCE ===
{kb_context[:max_kb]}"""
                print(f"  [OK] MERGED: Company profile (dynamic={len(dynamic_content[:max_dynamic])} chars, kb={len(kb_context[:max_kb])} chars)")
            else:
                context = kb_context
                print(f"  [DATA] Context: KB only (no dynamic data available)")

        elif query_type == 'trade_data':
            # Trade data queries → PRIORITIZE company data when available
            if dynamic_content:
                max_dynamic = 3200  # Increased to capture full company profile
                max_kb = 600
                context = f"""=== COMPANY-SPECIFIC DATA (PRIMARY SOURCE - USE THIS FIRST) ===
{dynamic_content[:max_dynamic]}

=== SUPPLEMENTARY KNOWLEDGE BASE ===
{kb_context[:max_kb]}"""
                print(f"  [OK] MERGED: Company-first approach (dynamic={len(dynamic_content[:max_dynamic])} chars, kb={len(kb_context[:max_kb])} chars)")
            else:
                context = kb_context
                print(f"  [DATA] Context: KB only (no company data)")

        else:
            # General queries → KB only
            context = kb_context
            print(f"  [DATA] Context: KB only (general query)")

        print(f"  [DATA] FINAL CONTEXT SIZE: {len(context)} chars (~{len(context)//4} tokens)")
        return context

    def _build_conversation_history(self, messages: list) -> str:
        """
        Build formatted conversation history from messages using smart history manager

        Now supports:
        - Configurable context window (default 20 messages)
        - Token-aware truncation
        - Smart summarization for long conversations
        - Preservation of recent important context
        """
        from chatbot.utils.conversation_history_manager import build_conversation_history_from_settings

        return build_conversation_history_from_settings(messages, self.settings)

    def _detect_industry(self, query: str, context: str) -> dict:
        """
        Detect industry focus from query and context

        Returns:
            Dictionary with industry, context_hint, and examples
        """
        query_lower = query.lower()

        industries = {
            'chemicals': {
                'keywords': ['chemical', 'polymer', 'resin', 'acid', 'alkali'],
                'context_hint': 'Focus on chemical products, HS codes, and regulatory compliance',
                'examples': 'polymer exports, chemical imports, specialty chemicals'
            },
            'textiles': {
                'keywords': ['textile', 'fabric', 'garment', 'cotton', 'yarn'],
                'context_hint': 'Focus on fabric types, garment categories, and textile trade',
                'examples': 'fabric exports, garment suppliers, cotton imports'
            },
            'electronics': {
                'keywords': ['electronic', 'semiconductor', 'chip', 'circuit'],
                'context_hint': 'Focus on electronic components, tech products, and supply chains',
                'examples': 'semiconductor exports, electronic components, tech suppliers'
            },
            'agriculture': {
                'keywords': ['agricultural', 'crop', 'grain', 'seed', 'fertilizer'],
                'context_hint': 'Focus on agricultural products, commodities, and trade patterns',
                'examples': 'grain exports, fertilizer imports, agricultural suppliers'
            }
        }

        for industry, info in industries.items():
            if any(kw in query_lower for kw in info['keywords']):
                return {
                    'industry': industry,
                    'context_hint': info['context_hint'],
                    'examples': info['examples']
                }

        return {'industry': None, 'context_hint': '', 'examples': ''}

    def _get_optimal_temperature(self, query: str) -> float:
        """
        Get optimal temperature based on query type

        Returns:
            0.3 for factual/data queries, 0.5 for standard, 0.7 for creative
        """
        query_lower = query.lower()

        # Factual queries need low temperature
        factual_keywords = [
            'how many', 'what is', 'show me', 'list', 'number',
            'turnover', 'value', 'shipment', 'data', 'statistics'
        ]
        if any(kw in query_lower for kw in factual_keywords):
            return 0.3

        # Creative queries need higher temperature
        creative_keywords = ['suggest', 'recommend', 'idea', 'strategy', 'should i']
        if any(kw in query_lower for kw in creative_keywords):
            return 0.7

        return 0.5  # Default
