"""
Unified Stream Handler - Single LLM Call for Intent + Response

This module provides a drop-in replacement for ChatbotManager.stream_response()
that uses a single LLM streaming call with tool calling for intent detection.

ALL business logic is preserved:
- Credit checking and deduction
- Slot management (cross-questioning)
- URL building for all data queries
- Data validation
- Contact support handling
- Dashboard access handling
- India exclusion logic
- Data availability checking
- Redis history saving
- Performance tracking
- Error handling

Saves 5-8 seconds per request by eliminating separate intent detection call!
"""

import json
import time
import asyncio
import re
from typing import AsyncGenerator, Dict, Any, Optional, List
from datetime import datetime

# TOOL DEFINITIONS - All intents mapped to LangChain tools
INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_trade_data",
            "description": """Search for trade data for a specific product and country.

Use for: importers/exporters/shipments of product in country.
Example: "coffee importers USA"

Extract both product and country if mentioned.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "product": {
                        "type": "string",
                        "description": "Product name (e.g., 'coffee', 'steel', 'electronics'). Can be null if general trade query."
                    },
                    "country": {
                        "type": "string",
                        "description": "Country name (e.g., 'USA', 'India', 'China'). REQUIRED."
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": ["buyer", "supplier", "trade"],
                        "description": "Type of entity: 'buyer' for importers, 'supplier' for exporters, 'trade' for general shipments"
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["import", "export"],
                        "description": "Trade direction: 'import' for imports, 'export' for exports"
                    }
                },
                "required": ["country"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_country_data",
            "description": """Search for general country trade data without specific product.

Use when user asks about a SPECIFIC COUNTRY: "USA imports", "top importers Indonesia", "Germany data"

IMPORTANT: If country mentioned, use this (NOT dashboard_required).

Do NOT use if product mentioned - use search_trade_data instead.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "country": {
                        "type": "string",
                        "description": "Country name. REQUIRED."
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["import", "export"],
                        "description": "Trade direction"
                    }
                },
                "required": ["country"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "country_to_country",
            "description": """Search for trade flow between two countries.

Use for bilateral trade queries: "India to USA", "China UK trade"

Both origin and destination required.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_country": {
                        "type": "string",
                        "description": "Origin/exporting country. REQUIRED."
                    },
                    "destination_country": {
                        "type": "string",
                        "description": "Destination/importing country. REQUIRED."
                    },
                    "product": {
                        "type": "string",
                        "description": "Optional product filter"
                    }
                },
                "required": ["origin_country", "destination_country"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hs_code_search",
            "description": """Search by HS code (Harmonized System code).

Use when user mentions HS/HSN code: "HS 090111", "HSN 8471"

HS code REQUIRED. Country optional.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "hs_code": {
                        "type": "string",
                        "description": "HS code (6-10 digits). REQUIRED."
                    },
                    "country": {
                        "type": "string",
                        "description": "Country name (optional but recommended)"
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["import", "export"],
                        "description": "Trade direction"
                    }
                },
                "required": ["hs_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "contact_support",
            "description": """User wants to contact human sales/support OR asks about pricing/plans/purchase.

USE FOR:
- PRICING: "How much?", "What's the price?", "Plans?", "I want to buy", "Payment"
- CONTACT: "Talk to real person", "Connect with sales", "Schedule demo", "Call me"

DO NOT use for:
- Greetings: "hi", "hello" → Respond naturally
- General questions: "What do you do?" → Answer directly
- Data help: "Find importers" → Use data tool

NEVER mention specific prices - Market Inside has custom plans only.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why user wants to contact support (optional)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dashboard_required",
            "description": """Query requires dashboard for global rankings/analytics.

ONLY use when query CLEARLY asks for global country rankings WITH product:
✓ "Top coffee exporting countries" (has product)
✓ "Biggest steel importing countries" (has product)

DO NOT use for:
✗ Vague: "top importers" (use ask_clarification)
✗ Specific country: "USA coffee" (use search_trade_data)
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "description": "Type of dashboard query (global_ranking, market_analysis, trend_analysis, etc.)"
                    },
                    "details": {
                        "type": "string",
                        "description": "What user is asking for"
                    }
                },
                "required": ["query_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": """Ask user for missing information in a conversational way.

Use when query is ambiguous or missing critical params (country, product, HS code).

Examples: "top importers" (missing product), "trade data" (too vague)

Be conversational, provide suggestions, maintain friendly tone.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "missing_param": {
                        "type": "string",
                        "enum": ["country", "product", "direction", "hs_code", "origin_country", "destination_country", "unclear"],
                        "description": "Which parameter is missing or unclear"
                    },
                    "question": {
                        "type": "string",
                        "description": "Question to ask user"
                    },
                    "suggestions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Suggested values (e.g., popular countries)"
                    },
                    "original_intent": {
                        "type": "string",
                        "description": "The intended data tool (search_trade_data, etc.)"
                    },
                    "partial_params": {
                        "type": "object",
                        "description": "Parameters already extracted"
                    }
                },
                "required": ["missing_param", "question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "out_of_scope",
            "description": """User asks for services Market Inside does NOT provide.

DO NOT USE for questions ABOUT Market Inside - answer those directly.

ONLY use when user wants us to DO something we don't provide:
- Buying/selling products (we provide DATA, not products)
- Customs clearance/shipping (we provide DATA, not services)
- Direct introductions (we provide DATA, not connections)
- Business operations questions (competitors, investors)

Provide service_type to categorize the request.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_type": {
                        "type": "string",
                        "enum": ["buying_selling", "customs", "shipping", "connections", "other"],
                        "description": "Type of out-of-scope service requested"
                    },
                    "user_query": {
                        "type": "string",
                        "description": "What the user is asking for"
                    }
                },
                "required": ["service_type"]
            }
        }
    }
]


class UnifiedStreamHandler:
    """
    Unified streaming handler with single LLM call for intent + response.

    Preserves ALL existing business logic:
    - Credits, slots, URL building, validation, etc.
    """

    def __init__(self, chatbot_manager):
        """
        Initialize with reference to existing ChatbotManager.

        This allows us to reuse all existing services:
        - kb_retriever, redis, llm, hybrid_retriever, etc.
        """
        self.manager = chatbot_manager
        self.llm = chatbot_manager._get_intent_classifier_llm()  # Get LLM instance
        self.redis = chatbot_manager.redis
        self.kb_retriever = chatbot_manager.kb_retriever
        self.hybrid_retriever = chatbot_manager.hybrid_retriever

        # Reuse existing caches and state
        self._stream_history = chatbot_manager._stream_history
        self._stream_context = chatbot_manager._stream_context
        self._last_explore_url = ""
        self._show_support_buttons = False
        self._request_cache = {
            "fixed_urls": {},  # Initialize fixed_urls cache
            "data_availability_fetched": False
        }

    async def stream_response(
        self,
        message: str,
        session_id: str,
        dynamic_url: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Main streaming handler - single LLM call with tool calling.

        Yields:
            - Text chunks for streaming response
            - JSON metadata at the end
            - Special JSON for UI actions (clarifications, support, etc.)
        """

        start_time = time.time()
        print(f"\n{'='*80}")
        print(f"[UNIFIED-STREAM] Session: {session_id}")
        print(f"[UNIFIED-STREAM] Message: {message[:100]}")
        print(f"[UNIFIED-STREAM] Time: {datetime.now().isoformat()}")
        print(f"{'='*80}\n")

        # Clear request cache for new request
        self._request_cache = {}

        # Performance tracking
        perf_timings = {
            "llm_stream": 0,
            "url_building": 0,
            "validation": 0,
            "total": 0
        }

        # ====================================================================
        # STEP 0: INSTANT CACHE for common queries
        # ====================================================================
        import string
        message_lower = message.lower().strip()
        # Remove punctuation for cache matching (so "mi?" matches "mi")
        message_cleaned = message_lower.strip(string.punctuation).strip()

        common_responses = {
            'hi': "Hi! I'm Alex from Market Inside - your trade data expert. What would you like to know about global trade data or finding buyers/suppliers?",
            'hello': "Hello! I'm Alex from Market Inside. I help businesses find buyers, suppliers, and market opportunities worldwide. What would you like to know?",
            'hey': "Hey! I'm Alex from Market Inside. How can I help you with global trade intelligence today?",
            'hi there': "Hi there! I'm Alex from Market Inside - your trade data consultant. What can I help you with today?",
            'good morning': "Good morning! I'm Alex from Market Inside. How can I assist you with global trade data today?",
            'good afternoon': "Good afternoon! I'm Alex from Market Inside. What trade intelligence can I help you with?",
            'thanks': "You're welcome! Let me know if you need anything else about global trade data.",
            'thank you': "You're welcome! Feel free to ask if you have more questions about our trade intelligence services.",
            'ok': "Great! How else can I help you with trade data?",
            'okay': "Perfect! What other information do you need?",
            'yes': "Great! What specific information can I help you find?",
            'no': "No problem! Is there anything else I can help you with?",

            # Market Inside variations (CRITICAL - instant response, zero latency)
            'mi': "Market Inside is a global trade intelligence platform. We provide comprehensive data on importers, exporters, shipments, and trade flows across 200+ countries. What would you like to know?",
            'tell me about mi': "Market Inside is a global trade intelligence platform providing data on 14.9M+ importers, 21.6M+ exporters, and billions of shipment records across 200+ countries. We help businesses find buyers, suppliers, and market opportunities worldwide. What specific information do you need?",
            'what is mi': "Market Inside is a global trade intelligence platform providing data on 14.9M+ importers, 21.6M+ exporters, and billions of shipment records across 200+ countries. What would you like to know?",
            'about mi': "Market Inside is a global trade intelligence platform providing comprehensive trade data and market intelligence across 200+ countries. What specific information can I help you with?",
            'tell me about market inside': "Market Inside is a global trade intelligence platform. We provide comprehensive data on 14.9M+ importers, 21.6M+ exporters, and billions of shipment records across 200+ countries. We help businesses find buyers, suppliers, and market opportunities worldwide. What specific information do you need?",
            'what is market inside': "Market Inside is a global trade intelligence platform providing data on 14.9M+ importers, 21.6M+ exporters, and billions of shipment records. We help businesses find buyers, suppliers, and market opportunities worldwide. What would you like to know?",
            'about market inside': "Market Inside provides comprehensive global trade data and market intelligence. We track 14.9M+ importers, 21.6M+ exporters, and billions of shipments across 200+ countries. What can I help you with?",
            'what do you do': "I help businesses find buyers, suppliers, and market opportunities worldwide using Market Inside's trade data covering 200+ countries. What specific information are you looking for?",
            'what can you do': "I can help you find importers, exporters, trade data, shipment records, and market intelligence for products and countries worldwide. What are you interested in?",
        }

        # Check both cleaned and original for cache hit
        if message_cleaned in common_responses:
            cached_response = common_responses[message_cleaned]
            print(f"[UNIFIED] ⚡⚡⚡ Instant cache hit: {message_cleaned}")
        elif message_lower in common_responses:
            cached_response = common_responses[message_lower]
            print(f"[UNIFIED] ⚡⚡⚡ Instant cache hit: {message_lower}")
        else:
            cached_response = None

        if cached_response:

            # Send instant response
            yield cached_response

            self._save_to_history(session_id, message, cached_response)

            # CRITICAL: Send done event so frontend doesn't wait
            yield json.dumps({
                "done": True,
                "intent_detected": "general",
                "processing_time": time.time() - start_time
            })
            return

        # ====================================================================
        # STEP 0.5: INDIA DATA GUARDRAIL (ZERO LATENCY, 100% RELIABLE)
        # Pre-check for India queries BEFORE LLM call
        # ====================================================================
        import re
        india_patterns = [
            r'\bindia\b',
            r'\bindian\b',
            r'\bindia\'?s\b',
        ]

        if any(re.search(pattern, message_lower) for pattern in india_patterns):
            # Check if it's a direct question about India data availability
            direct_query_patterns = [
                r'do you (have|offer|provide|cover)',
                r'can (i|we) (get|see|access)',
                r'is india (available|covered|included)',
                r'what (about|data for) india',
            ]

            is_direct_query = any(re.search(pattern, message_lower) for pattern in direct_query_patterns)

            if is_direct_query:
                india_response = "No, Market Inside does not provide trade data for India. However, I can help you with:\n\n- Trade data for other Asian countries (China, Vietnam, Thailand, Indonesia, Bangladesh, Malaysia)\n- Alternative markets for your products/industries\n- Global trade insights from 200+ other countries\n\nWhat specific information are you looking for?"

                print(f"[UNIFIED] 🚫 India data query detected - providing clear NO response (zero latency)")
                yield india_response

                self._save_to_history(session_id, message, india_response)

                # CRITICAL: Send done event
                yield json.dumps({
                    "done": True,
                    "intent_detected": "india_blocked",
                    "processing_time": time.time() - start_time
                })
                return
            else:
                # User mentioned India in context (like "exports FROM india" or "to india")
                # Let LLM handle it with the India exclusion rules in system prompt
                print(f"[UNIFIED] ⚠️ India mentioned in query context - LLM will handle with exclusion rules")

        # ====================================================================
        # STEP 1: Initialize managers
        # ====================================================================
        from chatbot.services.credit_manager import get_credit_manager
        from chatbot.services.slot_manager import get_slot_manager

        credit_mgr = get_credit_manager(self.redis)
        slot_mgr = get_slot_manager(self.redis)

        # ====================================================================
        # STEP 1.5: PRE-CHECK Mirror-to-Mirror Countries (FAST PATH)
        # If BOTH countries are mirror-only, redirect to support immediately
        # ====================================================================
        mirror_check_result = await self._precheck_mirror_to_mirror(message)
        if mirror_check_result:
            print(f"[UNIFIED] 🚫 Mirror-to-mirror detected - showing support options")

            support_message = "Both countries in your query only have mirror trade data available (partner country records). For comprehensive bilateral trade analysis, our dashboard offers advanced comparison tools. Would you like to connect with our team for a demo?"

            self._save_to_history(session_id, message, support_message)

            yield json.dumps({
                "credit_exhausted": True,  # Reuse existing UI
                "message": support_message,
                "actions": [
                    {"type": "schedule_demo", "label": "Schedule a Demo"},
                    {"type": "chat_with_us", "label": "Talk to Live Agent"},
                    # WhatsApp removed - will add QR code later
                    {"type": "continue_chat", "label": "Continue Chat"}
                ],
                "done": True
            })
            return

        # ====================================================================
        # STEP 2: Check for slot answer (cross-questioning continuation)
        # ====================================================================
        prev_state = slot_mgr.get_slots(session_id)
        pending_slot = prev_state.last_asked_slot
        prev_intent = prev_state.intent

        is_slot_answer = False

        # ====================================================================
        # CRITICAL: Check if last message was USER INFO prompt (name/email/phone)
        # If yes, SKIP slot detection and let LLM handle it with full context
        # ====================================================================
        last_assistant_msg = ""
        history = self._stream_history.get(session_id, [])
        if history:
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    last_assistant_msg = msg.get("content", "").lower()
                    break

        # Detect if we just asked for user info
        user_info_prompts = [
            "share your name", "your name", "could you please share",
            "your email", "email address", "your phone", "phone number",
            "contact information", "how can we reach you"
        ]
        is_user_info_context = any(prompt in last_assistant_msg for prompt in user_info_prompts)

        if is_user_info_context:
            print(f"[UNIFIED] 👤 User info context detected - skipping slot detection, letting LLM handle: '{message}'")
            # Skip slot detection entirely - let LLM handle with full context
            # LLM will understand this is a name/email/phone, not a data slot
        elif pending_slot and prev_intent:
            word_count = len(message.strip().split())
            message_lower = message.lower()

            # CRITICAL: Check if this is a NEW query (not a slot answer)
            # Query keywords indicate a new search, not an answer to previous question
            query_keywords = [
                'importer', 'exporter', 'buyer', 'supplier', 'shipment',
                'trade', 'import', 'export', 'show', 'find', 'get', 'search',
                'top', 'list', 'data', 'information', 'company', 'companies'
            ]

            is_new_query = any(keyword in message_lower for keyword in query_keywords)

            if is_new_query:
                # This is a NEW query, not a slot answer - clear slot state
                print(f"[UNIFIED] 🔄 New query detected (not slot answer): '{message}' - clearing slot state")
                slot_mgr.clear_slots(session_id)
                # Continue to normal LLM processing below
            elif word_count <= 3:
                # Short message without query keywords - could be slot answer
                # Check if user has tried too many times (prevent infinite loops)
                # Use slot_ask_counts dict to get count for this specific slot
                slot_attempts = prev_state.slot_ask_counts.get(pending_slot, 0) if prev_state.slot_ask_counts else 0

                if slot_attempts >= 3:
                    print(f"[UNIFIED] ⚠️ Too many slot attempts ({slot_attempts}) for slot '{pending_slot}' - escalating to support")

                    # Escalate to contact support
                    await self._handle_contact_support(session_id, message, full_response)

                    CONTACT_PHONE_NUMBER = "+44 7727 449124"
                    contact_message = (
                        f"I'm having trouble understanding your requirement. Let me connect you with our team:\n\n"
                        f"📞 Phone: {CONTACT_PHONE_NUMBER}\n\n"
                        "Or choose an option below to get assistance:"
                    )

                    yield json.dumps({
                        "credit_exhausted": True,
                        "final_response": contact_message,
                        "show_support_buttons": True,
                        "support_actions": [
                            {"type": "schedule_demo", "label": "Schedule a Demo"},
                            {"type": "chat_with_us", "label": "Talk to Live Agent"},
                            # WhatsApp removed - will add QR code later
                            {"type": "continue_chat", "label": "Try Again"}
                        ],
                        "done": True
                    })
                    return

                is_slot_answer = True
                print(f"[UNIFIED] 🎯 Slot answer detected: '{message}' for slot '{pending_slot}' (prev intent: {prev_intent})")

        # ====================================================================
        # STEP 3: LLM STREAMING with Tool Calling (Intent Detection)
        # ====================================================================
        intent = None
        params = {}
        full_response = ""
        tool_calls = []

        if is_slot_answer:
            # Use previous intent and fill the missing slot
            intent = prev_intent
            slot_value = message.strip()

            # Get previous slots and fill the missing one
            prev_slots = prev_state.slots or {}
            params = {**prev_slots, pending_slot: slot_value}

            print(f"[UNIFIED] Using prev intent '{intent}' with params: {params}")

            # CRITICAL: Check if India is in the params (slot filling path)
            country_value = params.get('country', '').lower()
            origin_country = params.get('origin_country', '').lower()
            destination_country = params.get('destination_country', '').lower()

            if 'india' in country_value or 'india' in origin_country or 'india' in destination_country:
                print(f"[UNIFIED] 🚫 INDIA DETECTED in slot filling - BLOCKING data query")
                india_block_response = "I apologize, but Market Inside does not provide trade data for India. However, I can help you with:\n\n- Trade data for other Asian countries (China, Vietnam, Thailand, Indonesia, Bangladesh, Malaysia)\n- Alternative markets for your products/industries\n- Global trade insights from 200+ other countries\n\nWould you like to explore data for a different country?"

                yield india_block_response
                self._save_to_history(session_id, message, india_block_response)

                # Clear slot state so user can start fresh
                slot_mgr.clear_slots(session_id)

                yield json.dumps({
                    "done": True,
                    "intent_detected": "india_blocked",
                    "processing_time": time.time() - start_time
                })
                return

            # Generate quick acknowledgment
            acknowledgment = f"Got it! Let me find that information for you..."
            yield acknowledgment

            # IMPORTANT: Set full_response to empty so that after data fetch,
            # we generate a proper data-based response instead of using acknowledgment
            full_response = ""

            # Note: Slot has been filled, proceeding with intent execution

        else:
            # Normal flow: LLM stream with tool calling
            t_llm_start = time.time()

            # Build conversation context with aggressive trimming for performance
            history = self._stream_history.get(session_id, [])

            # CRITICAL PERFORMANCE FIX: Limit history to last 6 messages (3 exchanges)
            # Tool calling LLMs are slow with long context - keep only recent conversation
            # Keep 6 to ensure lead prompts (name/email) aren't trimmed before user responds
            if len(history) > 6:
                history = history[-6:]
                self._stream_history[session_id] = history

            messages = self._build_messages(history, message, dynamic_url)

            print(f"[UNIFIED] Starting LLM stream with {len(INTENT_TOOLS)} tools...")
            print(f"[UNIFIED] Using model: {self.llm.__class__.__name__}")

            # PERFORMANCE WARNING: Track slow LLM calls
            if hasattr(self.llm, 'model'):
                print(f"[UNIFIED] Model: {getattr(self.llm, 'model', 'unknown')}")

            try:
                # SINGLE STREAMING CALL with tools
                raw_accumulated = ""
                yielded_length = 0
                chunk_count = 0

                async for chunk in self.llm.astream(messages, tools=INTENT_TOOLS):

                    # Capture tool calls (intent detection)
                    if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                        for tc in chunk.tool_calls:
                            try:
                                # Handle both dict and object formats
                                if isinstance(tc, dict):
                                    tool_name = tc.get('name', '')
                                    tool_args = tc.get('args', {})
                                    if isinstance(tool_args, str):
                                        tool_args = json.loads(tool_args) if tool_args else {}
                                else:
                                    # Object format
                                    tool_name = tc.function.name if hasattr(tc, 'function') else tc.get('name', '')
                                    tool_args_str = tc.function.arguments if hasattr(tc, 'function') else tc.get('args', '{}')

                                    # Parse JSON arguments
                                    tool_args = json.loads(tool_args_str) if tool_args_str else {}

                                tool_calls.append({
                                    "name": tool_name,
                                    "arguments": tool_args
                                })

                                # First tool call is the primary intent
                                if not intent:
                                    intent = tool_name
                                    params = tool_args
                                    print(f"[UNIFIED] 🔧 Tool call: {tool_name}")
                                    print(f"[UNIFIED] 📋 Arguments: {tool_args}")

                            except json.JSONDecodeError as e:
                                print(f"[UNIFIED] ⚠️ Failed to parse tool args: {e}")
                                continue

                    # Stream text content to user (with think block filtering)
                    if hasattr(chunk, 'content') and chunk.content:
                        content = chunk.content
                        raw_accumulated += content

                        # Filter out <think>...</think> blocks in real-time
                        cleaned = re.sub(r'<think>.*?</think>', '', raw_accumulated, flags=re.DOTALL)
                        cleaned = re.sub(r'<think>[^<]*$', '', cleaned)

                        # Remove internal reasoning markers (list format: * Context: ... or * **Context:** ...)
                        cleaned = re.sub(
                            r'^\s*[\*\-]\s+\*?\*?(?:Context|Note|Internal|Reasoning|Analysis|Thought|Summary|Background|Explanation)[:|\s].*?$',
                            '', cleaned, flags=re.MULTILINE | re.IGNORECASE
                        )

                        # Also remove standalone context lines (without list markers: **Context:** ...)
                        cleaned = re.sub(
                            r'^\s*\*?\*?(?:Context|Note|Internal|Reasoning|Analysis|Thought|Summary|Background|Explanation)\*?\*?[:|\s].*?$',
                            '', cleaned, flags=re.MULTILINE | re.IGNORECASE
                        )

                        # Clean up empty list markers
                        cleaned = re.sub(r'^\s*[\*\-]\s+$', '', cleaned, flags=re.MULTILINE)

                        # Yield only new content
                        new_content = cleaned[yielded_length:]
                        if new_content:
                            chunk_count += 1
                            clean_chunk = new_content.replace('**', '').replace('__', '')
                            full_response += clean_chunk
                            yielded_length = len(cleaned)
                            yield clean_chunk

                perf_timings["llm_stream"] = time.time() - t_llm_start
                print(f"[UNIFIED] ✅ LLM stream complete: {perf_timings['llm_stream']:.2f}s")
                print(f"[UNIFIED] Intent: {intent}, Chunks: {chunk_count}, Response length: {len(full_response)}")

                # PERFORMANCE WARNING: Alert if LLM is too slow
                if perf_timings['llm_stream'] > 10:
                    print(f"[UNIFIED] ⚠️⚠️⚠️ LLM TOO SLOW: {perf_timings['llm_stream']:.2f}s (target: <5s)")
                    print(f"[UNIFIED] Recommendation: Use local Ollama or switch to faster model")

            except Exception as e:
                import traceback
                print(f"[UNIFIED] ❌ LLM stream error: {type(e).__name__}: {str(e)}")
                print(f"[UNIFIED] Traceback:\n{traceback.format_exc()}")

                # Fallback response
                error_msg = "I apologize, but I encountered an error. Please try again or contact our support team."
                yield error_msg
                self._save_to_history(session_id, message, error_msg)
                return

        # If no intent detected, treat as general conversation
        if not intent:
            intent = "general"
            print(f"[UNIFIED] ℹ️ No tool calls - treating as general conversation")

        # ====================================================================
        # STEP 4: Check Credits
        # ====================================================================
        can_proceed, credit_state = credit_mgr.deduct_credits(session_id, intent)

        if not can_proceed:
            if credit_state.get("exhaustion_notified"):
                print(f"[UNIFIED] 💳 Credits exhausted, already notified")
                return

            # Show credit exhaustion
            exhaustion = credit_mgr.get_exhaustion_response()
            print(f"[UNIFIED] 💳 Credits exhausted")

            self._save_to_history(session_id, message, full_response)

            yield json.dumps({
                "credit_exhausted": True,
                "message": exhaustion["message"],
                "actions": exhaustion["actions"]
            })
            return

        # ====================================================================
        # STEP 5: Handle ask_clarification Tool (Cross-Questioning)
        # ====================================================================
        if intent == "ask_clarification":
            # Generate context text if LLM didn't produce any
            if not full_response or len(full_response.strip()) == 0:
                # Generate helpful context based on partial params
                partial_params = params.get("partial_params", {})
                missing_param = params.get("missing_param", "")

                context_text = "I can help you with that. "
                if partial_params.get("product"):
                    context_text += f"You're looking for {partial_params['product']} data. "
                if partial_params.get("country"):
                    context_text += f"For {partial_params['country']}. "

                yield context_text
                full_response = context_text

            await self._handle_clarification(
                session_id, message, params, slot_mgr, full_response
            )

            # Yield clarification UI
            yield json.dumps({
                "clarifying_question": True,
                "question": params.get("question", "Could you provide more details?"),
                "suggestions": params.get("suggestions", []),
                "slot": params.get("missing_param", "unclear"),
                "done": True
            })
            return

        # ====================================================================
        # STEP 5.4: INDIA BLOCKING (After LLM Call - Check Params)
        # ====================================================================
        if intent in ["search_trade_data", "search_country_data", "country_to_country", "hs_code_search"]:
            # CRITICAL: Block India in ALL data query params (zero overhead - single check)
            country_value = params.get('country', '').lower()
            origin_country = params.get('origin_country', '').lower()
            destination_country = params.get('destination_country', '').lower()

            if 'india' in country_value or 'india' in origin_country or 'india' in destination_country:
                print(f"[UNIFIED] 🚫 INDIA DETECTED in LLM tool params - BLOCKING immediately")
                india_block_response = "I apologize, but Market Inside does not provide trade data for India. However, I can help you with:\n\n- Trade data for other Asian countries (China, Vietnam, Thailand, Indonesia, Bangladesh, Malaysia)\n- Alternative markets for your products/industries\n- Global trade insights from 200+ other countries\n\nWould you like to explore data for a different country?"

                yield india_block_response
                self._save_to_history(session_id, message, india_block_response)

                yield json.dumps({
                    "done": True,
                    "intent_detected": "india_blocked",
                    "processing_time": time.time() - start_time
                })
                return

        # ====================================================================
        # STEP 5.5: Check for Complex Queries (BEFORE slot processing)
        # ====================================================================
        if intent in ["search_trade_data", "search_country_data", "country_to_country", "hs_code_search"]:
            # Check if query requires dashboard (comparisons, rankings, multi-country)
            params_with_intent = {**params, "intent": intent}
            is_complex, complex_reason = slot_mgr.is_complex_query(message, params_with_intent)

            if is_complex:
                if not complex_reason:
                    complex_reason = "comparison" if "compar" in message.lower() or " vs " in message.lower() else "ranking"
                print(f"[UNIFIED] 🚫 Complex query detected: {complex_reason}")

                # Build support message
                complex_message = "This type of analysis requires our dashboard for comprehensive insights and comparisons. Our team can provide a demo and help you get started with advanced features."

                self._save_to_history(session_id, message, complex_message)

                # Yield dashboard access UI
                yield json.dumps({
                    "credit_exhausted": True,  # Reuse credit exhaustion UI
                    "message": complex_message,
                    "actions": [
                        {"type": "schedule_demo", "label": "Schedule a Demo"},
                        {"type": "chat_with_us", "label": "Talk to Live Agent"},
                        # WhatsApp removed - will add QR code later
                        {"type": "continue_chat", "label": "Continue Chat"}
                    ],
                    "done": True
                })
                return

        # ====================================================================
        # STEP 5.7: Handle Out-of-Scope Service Mismatch
        # ====================================================================
        if intent == "out_of_scope":
            service_type = params.get("service_type", "other")

            print(f"[UNIFIED] 🚫 Out-of-scope detected: {service_type}")

            # Check if we should show support options (frequency threshold)
            from chatbot.services.support_trigger_tracker import get_support_trigger_tracker

            support_tracker = get_support_trigger_tracker(self.redis)

            # Get current message count from session history
            message_count = len(self._stream_history.get(session_id, [])) // 2

            should_show, block_reason = support_tracker.should_show_support(
                session_id=session_id,
                trigger_type="service_scope_mismatch",
                current_message_count=message_count
            )

            if should_show:
                # Record the trigger
                support_tracker.record_trigger(
                    session_id=session_id,
                    trigger_type="service_scope_mismatch",
                    message_count=message_count
                )

                print(f"[UNIFIED] ✅ Showing support options for service mismatch ({service_type})")

                # Track interaction in database
                if hasattr(self, 'support_interaction_service') and self.support_interaction_service:
                    try:
                        from chatbot.database.support_interaction_service import SupportInteraction, SupportInteractionType
                        await self.support_interaction_service.track_interaction(
                            SupportInteraction(
                                session_id=session_id,
                                interaction_type=SupportInteractionType.OTHER,
                                interaction_data={
                                    "trigger_type": "service_scope_mismatch",
                                    "query": message,
                                    "service_type": service_type,
                                    "out_of_scope_type": "service_mismatch",
                                    "shown_support": True
                                },
                                page_url="",
                                message_context=message[:200]
                            )
                        )
                    except Exception as e:
                        print(f"[UNIFIED] ⚠️ Could not track service mismatch: {e}")

                # Generate contextual response message based on service type
                service_messages = {
                    "buying_selling": "We don't provide buying or selling services. Market Inside provides trade DATA - shipment records, buyer databases, and market intelligence. Our team can show you how to find the right buyers/suppliers using our data. Would you like to connect?",
                    "customs": "We don't handle customs clearance or shipping logistics. Market Inside provides customs RECORDS and trade data that can help you make informed decisions. Our team can show you the data we offer. Interested?",
                    "shipping": "We don't provide shipping or logistics services. Market Inside specializes in trade DATA - shipment records and trade flow analysis. Our team can help you explore relevant data for your needs. Want to connect?",
                    "connections": "We don't directly facilitate buyer-supplier introductions. Market Inside provides comprehensive trade databases where you can identify and research potential partners yourself. Our team can demonstrate how to use our platform effectively. Interested?",
                    "other": "Market Inside provides trade DATABASE and analytics - we don't directly provide execution services. Our team can help you explore relevant data for your needs. Would you like to connect?"
                }

                support_message = service_messages.get(service_type, service_messages["other"])

                # Save to history
                self._save_to_history(session_id, message, support_message)

                # Yield support UI
                yield json.dumps({
                    "credit_exhausted": True,  # Reuse existing UI component
                    "message": support_message,
                    "actions": [
                        {"type": "schedule_demo", "label": "Schedule a Demo"},
                        {"type": "chat_with_us", "label": "Talk to Live Agent"},
                        # WhatsApp removed - will add QR code later
                        {"type": "continue_chat", "label": "Continue Chat"}
                    ],
                    "done": True
                })
                return
            else:
                print(f"[UNIFIED] ⏸️ Service mismatch threshold reached ({block_reason}) - providing fallback response")

                # If LLM generated no text for out-of-scope, create fallback response
                if not full_response or len(full_response.strip()) == 0:
                    fallback_msg = "I'm here to help you explore trade data and market insights. What would you like to know about imports, exports, or trade flows?"
                    full_response = fallback_msg
                    yield fallback_msg
                else:
                    # Use whatever response the LLM generated
                    yield full_response

                # Save to history and end
                self._save_to_history(session_id, message, full_response)

                # Send done event
                yield json.dumps({
                    "done": True,
                    "processing_time": time.time() - start_time,
                    "full_response": full_response
                })
                return

        # ====================================================================
        # STEP 6: Validate Slots for Data Intents (Auto-detect missing params)
        # ====================================================================
        if intent in ["search_trade_data", "search_country_data", "country_to_country", "hs_code_search"]:
            missing_param = self._check_missing_params(intent, params)

            if missing_param:
                question, suggestions = self._get_clarification_for_param(missing_param)

                print(f"[UNIFIED] ❓ Missing '{missing_param}' - triggering clarification")

                # Save slot state and increment ask count
                slot_state = slot_mgr.update_slots(session_id, intent, params)

                # Track which slot we're asking about and increment count
                slot_state.last_asked_slot = missing_param
                if missing_param not in slot_state.slot_ask_counts:
                    slot_state.slot_ask_counts[missing_param] = 0
                slot_state.slot_ask_counts[missing_param] += 1

                # Save updated state with incremented count
                slot_mgr._save_state(session_id, slot_state)

                ask_count = slot_state.slot_ask_counts[missing_param]
                print(f"[UNIFIED] Asking for slot '{missing_param}' (attempt {ask_count}/3)")

                # Check if we've asked too many times (escalate after 3 attempts)
                if ask_count >= 3:
                    print(f"[UNIFIED] ⚠️ Too many attempts for slot '{missing_param}' - escalating to support")

                    CONTACT_PHONE_NUMBER = "+44 7727 449124"
                    contact_message = (
                        f"I'm having trouble understanding the {missing_param}. "
                        f"Let me connect you with our team:\n\n"
                        f"📞 Phone: {CONTACT_PHONE_NUMBER}\n\n"
                        "Or choose an option below to get assistance:"
                    )

                    await self._handle_contact_support(session_id, message, contact_message)

                    yield json.dumps({
                        "credit_exhausted": True,
                        "final_response": contact_message,
                        "show_support_buttons": True,
                        "support_actions": [
                            {"type": "schedule_demo", "label": "Schedule a Demo"},
                            {"type": "chat_with_us", "label": "Talk to Live Agent"},
                            # WhatsApp removed - will add QR code later
                            {"type": "continue_chat", "label": "Try Again"}
                        ],
                        "done": True
                    })
                    return

                self._save_to_history(session_id, message, question, is_clarifying=True)

                # Yield clarification UI
                yield json.dumps({
                    "clarifying_question": True,
                    "question": question,
                    "suggestions": suggestions,
                    "slot": missing_param,
                    "done": True
                })
                return

        # ====================================================================
        # STEP 7: Handle contact_support Intent
        # ====================================================================
        if intent == "contact_support":
            await self._handle_contact_support(session_id, message, full_response)

            # LLM already provided context in full_response - use it or provide default
            if not full_response or len(full_response.strip()) < 20:
                # No LLM response - provide comprehensive message
                contact_message = (
                    "I'd be happy to connect you with our team!\n\n"
                    "Our specialists can help you with:\n"
                    "• Custom pricing and plans tailored to your needs\n"
                    "• Product demos and feature walkthroughs\n"
                    "• Enterprise solutions and API access\n"
                    "• Detailed trade data inquiries\n\n"
                    "Choose how you'd like to connect:"
                )
            else:
                # LLM already provided context - just show buttons
                contact_message = full_response

            yield json.dumps({
                "credit_exhausted": True,
                "message": contact_message,
                "actions": [
                    {"type": "schedule_demo", "label": "Schedule a Demo"},
                    {"type": "chat_with_us", "label": "Talk to Live Agent"},
                    # WhatsApp removed - will add QR code later
                    {"type": "continue_chat", "label": "Continue Chat"}
                ],
                "done": True
            })
            return

        # ====================================================================
        # STEP 8: Handle dashboard_required Intent
        # ====================================================================
        if intent == "dashboard_required":
            tool_result = await self._handle_dashboard_required(
                session_id, message, params, full_response
            )

            yield json.dumps({
                "credit_exhausted": True,
                "message": tool_result,
                "actions": [
                    {"type": "schedule_demo", "label": "Schedule a Demo"},
                    {"type": "chat_with_us", "label": "Talk to Live Agent"},
                    # WhatsApp removed - will add QR code later
                    {"type": "continue_chat", "label": "Continue Chat"}
                ],
                "done": True
            })
            return

        # ====================================================================
        # STEP 9: Build URL for Data Queries
        # ====================================================================
        explore_url = ""
        dynamic_content = ""

        if intent in ["search_trade_data", "search_country_data", "country_to_country", "hs_code_search"]:
            # ================================================================
            # STEP 8.5: Detect Query Changes (Clear cached context)
            # ================================================================
            prev_state = slot_mgr.get_slots(session_id)
            prev_slots = prev_state.slots.copy() if prev_state.slots else {}

            # Check if intent changed
            intent_changed = prev_state.intent and prev_state.intent != intent

            # Check if key slots changed
            key_slots = ["country", "hs_code", "origin_country", "destination_country", "product"]
            slots_changed = any(
                params.get(k) != prev_slots.get(k)
                for k in key_slots
                if params.get(k)
            )

            query_changed = intent_changed or slots_changed

            if query_changed:
                print(f"[UNIFIED] 🔄 Query changed - clearing cached context")
                print(f"[UNIFIED] Intent: {prev_state.intent} → {intent}, Slots changed: {slots_changed}")

                # Clear in-memory context
                if session_id in self._stream_history:
                    # Keep only last 2 messages to maintain conversation flow
                    if len(self._stream_history[session_id]) > 4:
                        self._stream_history[session_id] = self._stream_history[session_id][-4:]

            # Send heartbeat before potentially slow URL building
            yield json.dumps({"heartbeat": True})

            explore_url, mirror_country_info = await self._build_url_for_intent(
                intent, params, dynamic_url, perf_timings, session_id, slot_mgr
            )

            # If mirror country info exists, append explanation to response for user context
            if mirror_country_info and len(full_response) < 300:
                mirror_explanation = f"\n\nNote: {mirror_country_info.get('explanation', '')}"
                full_response += mirror_explanation
                # Note: Not yielded separately as it's informational context

            # ================================================================
            # STEP 9.5: FETCH DYNAMIC CONTENT FROM API (like original stream)
            # This is what makes the chatbot answer with actual data!
            # ================================================================
            if explore_url and not any(explore_url.startswith(prefix) for prefix in ["MIRROR_ONLY:", "RESTRICTED:", "CONTINENT:"]):
                # Send heartbeat before potentially slow API fetch
                yield json.dumps({"heartbeat": True})

                print(f"[UNIFIED] 🌐 Fetching dynamic content from API: {explore_url[:100]}...")
                t_fetch_start = time.time()

                try:
                    # Check Redis cache first
                    cached_data = await self.manager.dynamic_content_manager.get_embeddings_from_redis(explore_url, session_id)
                    if cached_data:
                        _, _, full_content = cached_data
                        dynamic_content = full_content
                        print(f"[UNIFIED] ✅ Using cached content: {len(full_content)} chars")
                    else:
                        # Fetch fresh data from API
                        api_data = await self.manager.handle_dynamic_api_call(
                            message, session_id,
                            extra_data={"dynamic_url": explore_url},
                            intent_result={"intent": intent, "confidence": 1.0, "url": explore_url, "params": params}
                        )
                        dynamic_content = api_data or ""
                        print(f"[UNIFIED] ✅ Fetched {len(dynamic_content)} chars from API")

                    perf_timings["content_fetch"] = time.time() - t_fetch_start
                    print(f"[UNIFIED] ⏱️  Content fetch: {perf_timings['content_fetch']:.2f}s")

                except Exception as e:
                    print(f"[UNIFIED] ⚠️ API fetch failed: {e}")
                    import traceback
                    traceback.print_exc()

            # CRITICAL FIX: If LLM called tool but generated no text, use dynamic content or add fallback
            if not full_response or len(full_response.strip()) == 0:
                print(f"[UNIFIED] ⚠️ LLM called tool but generated no text - generating response from data")

                # Generate response using dynamic_content if available, otherwise fallback
                country = params.get('country') or params.get('origin_country') or params.get('destination_country', '')
                product = params.get('product', '')

                if dynamic_content and len(dynamic_content) > 100:
                    # We have API data - create intelligent, conversational response
                    print(f"[UNIFIED] ✅ Creating conversational response from {len(dynamic_content)} chars")

                    fallback_response = self._create_conversational_response(
                        dynamic_content, intent, params, message
                    )

                else:
                    # No API data available, use simple generic response (matching /stream endpoint)
                    print(f"[UNIFIED] ⚠️ No API data, using simple generic fallback")

                    if intent == "search_country_data":
                        direction = params.get('direction', 'trade')
                        direction_text = "import" if direction == "import" else "export" if direction == "export" else "trade"
                        fallback_response = f"Here's the {direction_text} data for {country}."
                    elif intent == "search_trade_data":
                        entity_type = params.get('entity_type', 'companies')
                        entity_text = "importers" if entity_type == "buyer" else "exporters" if entity_type == "supplier" else "companies"
                        if product:
                            fallback_response = f"I found {product} {entity_text} in {country}."
                        else:
                            fallback_response = f"Here are the {entity_text} in {country}."
                    elif intent == "country_to_country":
                        origin = params.get('origin_country', '')
                        dest = params.get('destination_country', '')
                        if product:
                            fallback_response = f"I found trade data for {product} from {origin} to {dest}."
                        else:
                            fallback_response = f"Here's the trade flow data from {origin} to {dest}."
                    elif intent == "hs_code_search":
                        hs_code = params.get('hs_code', '')
                        fallback_response = f"I found HS code {hs_code} data{' for ' + country if country else ''}."
                    else:
                        fallback_response = "I found the data you're looking for."

                full_response = fallback_response

                # Send data response
                yield fallback_response

        # ====================================================================
        # STEP 10: Fetch Data Availability (Add to LLM Context)
        # ====================================================================
        data_availability_info = ""
        if intent in ["search_trade_data", "search_country_data", "hs_code_search"]:
            data_availability_info = await self._fetch_data_availability(params)

            # If data availability info exists and LLM response is short, append context
            if data_availability_info and len(full_response) < 200:
                # Add data coverage info to help LLM provide informed response
                coverage_note = f"\n\nData Coverage: {data_availability_info}"
                full_response += coverage_note
                # Note: We don't yield this as it's informational context, not main response

        # ====================================================================
        # STEP 11: Save to History (with explore_url for link persistence)
        # ====================================================================
        self._save_to_history(session_id, message, full_response, explore_url=explore_url)

        # ====================================================================
        # STEP 12: Yield Final Metadata
        # ====================================================================
        perf_timings["total"] = time.time() - start_time

        print(f"\n[UNIFIED] ✅ Request complete:")
        print(f"  - Total time: {perf_timings['total']:.2f}s")
        print(f"  - LLM stream: {perf_timings['llm_stream']:.2f}s")
        print(f"  - URL building: {perf_timings['url_building']:.2f}s")
        print(f"  - Intent: {intent}")
        print(f"  - URL generated: {bool(explore_url)}\n")

        yield json.dumps({
            "done": True,
            "explore_url": explore_url,
            "intent_detected": intent,
            "processing_time": perf_timings["total"]
        })

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _build_messages(
        self, history: List[Dict], current_message: str, dynamic_url: Optional[str] = None
    ) -> List[Dict]:
        """Build messages for LLM with system prompt"""

        import os
        SITE_NAME = os.getenv("SITE_NAME", "Export Genius")

        system_prompt = f"""You are Alex from Market Inside - helping businesses find buyers/suppliers using global trade data.

TOOL SELECTION (choose the right tool based on query):

1. GREETINGS/INFO - Respond directly (NO tool):
   • "Hi", "Thanks", user shares name/email/phone
   • Questions about Market Inside

2. DATA QUERIES - Call appropriate tool:
   • Product + Country → search_trade_data(product, country)
   • Country only → search_country_data(country)
   • Country to Country → country_to_country(origin, destination)
   • HS code → hs_code_search(hs_code, country)

3. PRICING/PLANS/PURCHASE → contact_support
4. GLOBAL RANKINGS (only if product specified) → dashboard_required
5. VAGUE/INCOMPLETE → ask_clarification
6. CONTACT REQUEST → contact_support

CRITICAL RULES:
- NEVER generate URLs (checkout, payment, pricing links) or mention prices ($X)
- Market Inside has CUSTOM plans only - redirect pricing queries to contact_support
- Market Inside provides DATA (not products/shipping/customs services)
- No markdown bold/italic in responses
- Be concise and professional
- NEVER include internal context, notes, reasoning, or meta-commentary in responses
- DO NOT add lines like "Context:", "Note:", "Analysis:", etc. - just respond naturally
"""

        return [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": current_message}
        ]

    def _check_missing_params(self, intent: str, params: Dict) -> Optional[str]:
        """Check if required params are missing for data intents"""

        if intent == "search_trade_data":
            if not params.get("country"):
                return "country"

        elif intent == "search_country_data":
            if not params.get("country"):
                return "country"

        elif intent == "country_to_country":
            if not params.get("origin_country"):
                return "origin_country"
            if not params.get("destination_country"):
                return "destination_country"

        elif intent == "hs_code_search":
            if not params.get("hs_code"):
                return "hs_code"

        return None

    def _get_clarification_for_param(self, param: str) -> tuple:
        """Get clarification question and suggestions for a parameter"""

        clarifications = {
            "country": (
                "Which country are you interested in?",
                ["USA", "UK", "Germany", "China", "Japan", "Vietnam"]
            ),
            "origin_country": (
                "Which country is exporting?",
                ["USA", "China", "Germany", "Vietnam", "Thailand"]
            ),
            "destination_country": (
                "Which country is importing?",
                ["USA", "UK", "Germany", "Japan", "Canada"]
            ),
            "product": (
                "Which product are you looking for?",
                []
            ),
            "hs_code": (
                "Please provide the HS code you'd like to search for.",
                []
            )
        }

        return clarifications.get(param, ("Could you provide more details?", []))

    async def _build_url_for_intent(
        self,
        intent: str,
        params: Dict,
        dynamic_url: Optional[str],
        perf_timings: Dict,
        session_id: str,
        slot_mgr
    ) -> tuple[str, Dict]:
        """Build URL for data queries using existing SlotManager.generate_url()

        Returns:
            tuple: (explore_url, mirror_country_info dict)
        """

        t_url_start = time.time()
        print(f"[UNIFIED] 🔗 Building URL for intent '{intent}'...")

        try:
            # Use SlotManager.generate_url() - this is the ACTUAL URL builder used by old endpoint
            # It handles ALL business logic: mirror/detailed, India exclusion, etc.

            explore_url = slot_mgr.generate_url(intent, params)
            print(f"[UNIFIED] Generated URL from SlotManager: {explore_url[:120] if explore_url else 'None'}...")

            # Apply _fix_url_data_type to handle mirror vs detailed data
            if explore_url and not explore_url.startswith("CONTINENT:") and not explore_url.startswith("RESTRICTED:") and not explore_url.startswith("MIRROR_ONLY:"):
                if not self._request_cache.get("url_fixed"):
                    print(f"[UNIFIED] Applying _fix_url_data_type...")

                    # Ensure manager's request cache is properly initialized
                    if not hasattr(self.manager, '_request_cache'):
                        self.manager._request_cache = {}
                    if "fixed_urls" not in self.manager._request_cache:
                        self.manager._request_cache["fixed_urls"] = {}

                    explore_url = await self.manager._fix_url_data_type(explore_url, intent, params)
                    self._request_cache["url_fixed"] = True
                    print(f"[UNIFIED] ✅ URL after fix: {explore_url[:120]}...")

            # Handle special URL prefixes (MIRROR_ONLY, CONTINENT, RESTRICTED)
            mirror_country_info = {}
            if explore_url and explore_url.startswith("MIRROR_ONLY:"):
                # Extract mirror country info
                parts = explore_url.replace("MIRROR_ONLY:", "").split(":")
                if parts[0] == "BOTH":
                    # Both countries are mirror - return empty (will be handled by dashboard/support logic)
                    print(f"[UNIFIED] Both countries mirror-only - empty URL")
                    explore_url = ""
                else:
                    # Single mirror country - generate country page URL
                    mirror_country_name = parts[0] if len(parts) > 0 else "Unknown"
                    mirror_direction = parts[1] if len(parts) > 1 else "import"
                    country_slug = mirror_country_name.lower().replace(' ', '-')
                    direction_suffix = "imports" if mirror_direction == "import" else "exports"
                    explore_url = f"https://www.marketinsidedata.com/en/country/{country_slug}/{direction_suffix}"
                    print(f"[UNIFIED] Mirror country URL: {explore_url}")

                    # Store mirror country info for LLM context
                    mirror_country_info = {
                        "country": mirror_country_name,
                        "direction": mirror_direction,
                        "data_type": "mirror",
                        "explanation": f"{mirror_country_name} provides mirror data only. We show {mirror_direction} statistics from partner countries."
                    }
                    print(f"[UNIFIED] Mirror country info stored: {mirror_country_info}")

            elif explore_url and explore_url.startswith("CONTINENT:"):
                # Continent query - use search-data page
                continent_name = explore_url.replace("CONTINENT:", "")
                print(f"[UNIFIED] Continent query: {continent_name}")
                explore_url = "https://www.marketinsidedata.com/en/search-data"

            elif explore_url and explore_url.startswith("RESTRICTED:"):
                # Restricted country - will be handled by support logic
                print(f"[UNIFIED] Restricted country detected")
                explore_url = ""

            # ================================================================
            # CRITICAL: Validate URL has actual data before showing to user
            # This prevents 404s and empty result pages
            # ================================================================
            if explore_url and not any(explore_url.startswith(prefix) for prefix in ["MIRROR_ONLY:", "RESTRICTED:", "CONTINENT:", "https://www.marketinsidedata.com/en/country/", "https://www.marketinsidedata.com/en/search-data"]):
                try:
                    # Get URL validator from manager
                    url_validator = getattr(self.manager, 'url_validator', None)
                    if url_validator and hasattr(url_validator, 'should_show_url'):
                        # Validate URL will show actual data
                        should_show, validation_msg = url_validator.should_show_url(intent, params, None)

                        if not should_show:
                            print(f"[UNIFIED] ⚠️ URL validation failed - URL won't show data: {validation_msg}")
                            # Clear URL so chatbot provides general response instead
                            explore_url = ""
                        else:
                            print(f"[UNIFIED] ✅ URL validated - has data")
                except Exception as e:
                    print(f"[UNIFIED] ⚠️ URL validation error (continuing): {e}")

            perf_timings["url_building"] = time.time() - t_url_start
            return explore_url, mirror_country_info

        except Exception as e:
            import traceback
            print(f"[UNIFIED] ⚠️ URL building error: {e}")
            print(traceback.format_exc())
            return "", {}

    async def _fetch_data_availability(self, params: Dict) -> str:
        """Fetch data availability for country if not already fetched

        Returns:
            Data availability info string (truncated to 500 chars) for LLM context
        """

        country = params.get('country') or params.get('origin_country') or params.get('destination_country')

        if country and not self._request_cache.get("data_availability_fetched"):
            try:
                # Import the tool function
                import sys
                import os
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                from fastapi_chatbot import fetch_data_availability

                data_info = await fetch_data_availability(country)
                print(f"[UNIFIED] ✅ Data availability checked for {country}")
                self._request_cache["data_availability_fetched"] = True

                # Return truncated data for LLM context (avoid overwhelming LLM)
                if data_info and len(data_info) > 500:
                    return data_info[:500] + "..."
                return data_info or ""

            except Exception as e:
                print(f"[UNIFIED] ⚠️ Data availability check failed: {e}")
                return ""

        return ""

    async def _handle_clarification(
        self,
        session_id: str,
        message: str,
        params: Dict,
        slot_mgr,
        full_response: str
    ):
        """Handle clarification request - save slot state"""

        missing_param = params.get("missing_param", "unclear")
        question = params.get("question", "Could you provide more details?")
        original_intent = params.get("original_intent", "unknown")
        partial_params = params.get("partial_params", {})

        print(f"[UNIFIED] ❓ Clarification needed for '{missing_param}'")

        # Save slot state and track ask count
        slot_state = slot_mgr.update_slots(session_id, original_intent, partial_params)

        # Track which slot we're asking about and increment count
        slot_state.last_asked_slot = missing_param
        if missing_param not in slot_state.slot_ask_counts:
            slot_state.slot_ask_counts[missing_param] = 0
        slot_state.slot_ask_counts[missing_param] += 1

        # Save updated state with incremented count
        slot_mgr._save_state(session_id, slot_state)

        ask_count = slot_state.slot_ask_counts[missing_param]
        print(f"[UNIFIED] Asking for slot '{missing_param}' (attempt {ask_count}/3)")

        self._save_to_history(session_id, message, question, is_clarifying=True)

    async def _handle_contact_support(
        self,
        session_id: str,
        message: str,
        full_response: str
    ):
        """Handle contact support intent - track interaction"""

        print(f"[UNIFIED] 📞 Contact support triggered")

        # Track interaction in database if available
        if hasattr(self.manager, 'support_interaction_service') and self.manager.support_interaction_service:
            try:
                from chatbot.database.support_interaction_service import SupportInteraction, SupportInteractionType
                await self.manager.support_interaction_service.track_interaction(
                    SupportInteraction(
                        session_id=session_id,
                        interaction_type=SupportInteractionType.OTHER,
                        interaction_data={
                            "trigger_type": "contact_support_intent",
                            "query": message,
                            "detected_by": "unified_stream_tool_calling"
                        },
                        page_url="",
                        message_context=message[:200]
                    )
                )
            except Exception as e:
                print(f"[UNIFIED] ⚠️ Could not track contact support: {e}")

        CONTACT_PHONE_NUMBER = "+44 7727 449124"
        contact_message = (
            f"📞 You can reach us at: {CONTACT_PHONE_NUMBER}\n\n"
            "Our team is available to assist you with:\n"
            "• Trade data inquiries\n"
            "• Custom reports and analysis\n"
            "• Dashboard demos and onboarding\n"
            "• Enterprise solutions\n\n"
            "Feel free to call us, or choose an option below:"
        )

        self._save_to_history(session_id, message, contact_message)

    async def _handle_dashboard_required(
        self,
        session_id: str,
        message: str,
        params: Dict,
        full_response: str
    ) -> str:
        """Handle dashboard required intent - call dashboard tool"""

        print(f"[UNIFIED] 🖥️ Dashboard access required")

        try:
            # Import and call the dashboard tool
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from fastapi_chatbot import require_dashboard_access

            tool_result = require_dashboard_access(
                query_type=params.get('query_type', 'analytics'),
                reason='This query requires dashboard features for detailed analysis',
                user_query=message
            )

            self._save_to_history(session_id, message, tool_result)
            return tool_result

        except Exception as e:
            print(f"[UNIFIED] ⚠️ Dashboard tool error: {e}")
            fallback = "This type of analysis requires our dashboard for comprehensive insights. Our team can provide a demo and help you get started."
            self._save_to_history(session_id, message, fallback)
            return fallback

    def _save_to_history(self, session_id: str, user_msg: str, assistant_msg: str, is_clarifying: bool = False, explore_url: str = ""):
        """Save messages to history and Redis with optional explore_url for link persistence"""

        self._stream_history.setdefault(session_id, []).extend([
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg}
        ])

        # CRITICAL PERFORMANCE FIX: Trim history immediately after saving
        # Keep only last 8 messages (4 exchanges) to prevent unbounded growth
        # Allows room for lead prompts and slot filling
        if len(self._stream_history[session_id]) > 8:
            self._stream_history[session_id] = self._stream_history[session_id][-8:]

        if self.redis:
            try:
                self.redis.save_message(session_id, {"role": "user", "content": user_msg})

                # Build assistant message with metadata
                assistant_data = {"role": "assistant", "content": assistant_msg}

                if is_clarifying:
                    assistant_data["is_clarifying"] = True

                # CRITICAL: Save explore_url for link persistence on refresh
                if explore_url:
                    assistant_data["explore_url"] = explore_url
                    print(f"[UNIFIED] 💾 Saving explore_url to Redis: {explore_url[:80]}...")

                self.redis.save_message(session_id, assistant_data)
            except Exception as e:
                print(f"[UNIFIED] ⚠️ Failed to save to Redis: {e}")

    def _create_conversational_response(self, dynamic_content: str, intent: str, params: Dict, user_query: str) -> str:
        """
        Create intelligent, conversational response from API data

        Style: Conversational, transparent, medium length (5-10 items + context)
        - Sounds like a real person helping you
        - Transparent about what data is/isn't available
        - No mention of explore link (UI handles that)
        """
        import re

        lines = dynamic_content.split('\n')
        country = params.get('country') or params.get('origin_country') or params.get('destination_country', '')
        product = params.get('product', '')

        # Extract key statistics from the data
        # Handle multiple API response formats
        stats = {}
        for line in lines:
            # Total Value (matches both "Total Value:" and "Total Shipment Value:")
            if 'Total Value:' in line or 'Total Shipment Value:' in line:
                stats['total_value'] = line.split(':', 1)[1].strip()
            # Total Records/Shipments (matches both formats)
            elif 'Total Shipments:' in line or 'Total Shipment Records:' in line:
                stats['total_records'] = line.split(':', 1)[1].strip()
            # Number of Importers (flexible matching)
            elif 'Importers:' in line and ('Number' in line or 'Total' in line):
                stats['num_importers'] = line.split(':', 1)[1].strip()
            # Number of Exporters (flexible matching)
            elif 'Exporters:' in line and ('Number' in line or 'Total' in line):
                stats['num_exporters'] = line.split(':', 1)[1].strip()
            # Number of Suppliers (flexible matching)
            elif 'Suppliers:' in line and ('Number' in line or 'Total' in line):
                stats['num_suppliers'] = line.split(':', 1)[1].strip()
            # Number of Buyers (flexible matching)
            elif 'Buyers:' in line and ('Number' in line or 'Total' in line):
                stats['num_buyers'] = line.split(':', 1)[1].strip()
            # Foreign Buyers
            elif 'Foreign Buyers:' in line:
                stats['num_buyers'] = line.split(':', 1)[1].strip()
            # Date Range
            elif 'Date Range:' in line:
                stats['date_range'] = line.split(':', 1)[1].strip()

        # Extract company/entity list
        companies = []
        capture = False
        for line in lines:
            # Start capturing at TOP section
            if any(marker in line for marker in ["[TOP IMPORTERS]", "[TOP EXPORTERS]", "[TOP COMPANIES]", "[TOP SUPPLIERS]", "[TOP BUYERS]"]):
                capture = True
                continue
            # Stop at next section
            elif line.startswith("[") and capture:
                break
            # Capture company names (lines starting with numbers)
            elif capture and line.strip():
                # Extract just company name (line format: "  1. Company Name")
                match = re.match(r'\s*\d+\.\s*(.+)', line)
                if match:
                    company_name = match.group(1).strip()
                    # Remove "Value: N/A" type suffixes
                    company_name = re.sub(r'\s*Value:.*$', '', company_name)
                    company_name = re.sub(r'\s*Shipments:.*$', '', company_name)
                    if company_name and company_name != "N/A":
                        companies.append(company_name)

        # Build conversational response
        response_parts = []

        # INTRO - Conversational and context-aware
        if intent == "search_country_data":
            direction = params.get('direction', 'import')
            entity_type = "importers" if direction == "import" else "exporters"

            if companies:
                # Conversational intro with key stat
                if stats.get('total_value'):
                    value_clean = stats['total_value'].replace('$', '').replace(',', '')
                    try:
                        # Format large numbers nicely
                        value_num = float(value_clean)
                        if value_num >= 1_000_000_000:
                            value_formatted = f"${value_num/1_000_000_000:.1f}B"
                        elif value_num >= 1_000_000:
                            value_formatted = f"${value_num/1_000_000:.1f}M"
                        else:
                            value_formatted = stats['total_value']
                    except:
                        value_formatted = stats['total_value']

                    intro = f"I found {country}'s top {entity_type}! "

                    if stats.get('num_importers') or stats.get('num_exporters'):
                        num_entities = stats.get('num_importers') or stats.get('num_exporters')
                        intro += f"There are {num_entities} total {entity_type} handling {value_formatted} in trade."
                    else:
                        intro += f"The data shows {value_formatted} in total trade value."
                else:
                    intro = f"Here are {country}'s leading {entity_type}:"
            else:
                intro = f"I found {country}'s {direction} data:"

        elif intent == "search_trade_data":
            entity_type = params.get('entity_type', 'companies')
            entity_text = "importers" if entity_type == "buyer" else "exporters" if entity_type == "supplier" else "companies"

            if product:
                intro = f"I found the top {product} {entity_text} in {country}!"
            else:
                intro = f"Here are {country}'s leading {entity_text}:"

        elif intent == "country_to_country":
            origin = params.get('origin_country', '')
            dest = params.get('destination_country', '')
            if product:
                intro = f"I found {product} trade data from {origin} to {dest}!"
            else:
                intro = f"Here's the trade flow from {origin} to {dest}:"

        elif intent == "hs_code_search":
            hs_code = params.get('hs_code', '')
            intro = f"I found HS code {hs_code} trade data:"
        else:
            intro = "Here's what I found:"

        response_parts.append(intro)

        # COMPANY LIST - Clean, no N/A values
        if companies:
            response_parts.append("")  # Blank line

            # Show top 5-10 companies (medium length for best UX)
            num_to_show = min(8, len(companies))
            for i, company in enumerate(companies[:num_to_show], 1):
                response_parts.append(f"{i}. {company}")

            # If we have more companies, mention it
            if len(companies) > num_to_show:
                response_parts.append(f"...and {len(companies) - num_to_show} more")

            # TRANSPARENCY - Explain missing data if needed
            has_na_values = "Value: N/A" in dynamic_content or "Shipments: N/A" in dynamic_content
            if has_na_values:
                response_parts.append("")  # Blank line
                response_parts.append("Note: Individual company values aren't available in the current dataset, but you can explore detailed shipment records.")

        else:
            # No companies found - try to extract other useful data
            # Extract top commodities or HS codes instead
            commodities = []
            capture_commodities = False
            for line in lines:
                if "[TOP COMMODITIES]" in line or "[TOP HS CODE" in line:
                    capture_commodities = True
                    continue
                elif line.startswith("[") and capture_commodities:
                    break
                elif capture_commodities and line.strip():
                    match = re.match(r'\s*\d+\.\s*(.+?):\s*(.+)', line)
                    if match:
                        commodity = match.group(1).strip()
                        value = match.group(2).strip()
                        if commodity and commodity != "N/A":
                            commodities.append(f"{commodity}: ${value}")

            if commodities:
                response_parts.append("")
                response_parts.append("Top traded products:")
                for i, commodity in enumerate(commodities[:6], 1):
                    response_parts.append(f"{i}. {commodity}")
            else:
                # No companies/commodities - show comprehensive stats instead
                if stats:
                    response_parts.append("")

                    # Format and display all available stats
                    if stats.get('total_records'):
                        records_num = stats['total_records'].replace(',', '')
                        try:
                            records_int = int(records_num)
                            if records_int >= 1000:
                                records_formatted = f"{records_int:,}"
                            else:
                                records_formatted = str(records_int)
                            response_parts.append(f"📊 Total Shipments: {records_formatted}")
                        except:
                            response_parts.append(f"📊 Total Shipments: {stats['total_records']}")

                    if stats.get('total_value'):
                        value_clean = stats['total_value'].replace('$', '').replace(',', '')
                        try:
                            value_num = float(value_clean)
                            if value_num >= 1_000_000_000:
                                value_formatted = f"${value_num/1_000_000_000:.1f}B"
                            elif value_num >= 1_000_000:
                                value_formatted = f"${value_num/1_000_000:.1f}M"
                            else:
                                value_formatted = f"${value_num:,.0f}"
                            response_parts.append(f"💰 Total Value: {value_formatted}")
                        except:
                            response_parts.append(f"💰 Total Value: {stats['total_value']}")

                    if stats.get('num_exporters'):
                        response_parts.append(f"🏢 Exporters: {stats['num_exporters']}")
                    elif stats.get('num_suppliers'):
                        response_parts.append(f"🏢 Suppliers: {stats['num_suppliers']}")

                    if stats.get('num_importers'):
                        response_parts.append(f"🏢 Importers: {stats['num_importers']}")
                    elif stats.get('num_buyers'):
                        response_parts.append(f"🏢 Buyers: {stats['num_buyers']}")

                    if stats.get('date_range'):
                        response_parts.append(f"📅 Period: {stats['date_range']}")

                    response_parts.append("")
                    response_parts.append("Click 'Explore More Details' to see shipment records and detailed analysis.")
                else:
                    response_parts.append("")
                    response_parts.append("The dataset covers comprehensive shipment records.")

        return '\n'.join(response_parts)

    async def _precheck_mirror_to_mirror(self, message: str) -> bool:
        """
        Fast pre-check if query is country-to-country with BOTH countries being mirror-only.
        Returns True if both are mirror (should show support), False otherwise.

        This runs BEFORE LLM call for performance optimization.
        """
        import re
        import httpx

        # Quick regex check if message looks like country-to-country query
        # Patterns: "X to Y", "from X to Y", "X exports to Y", etc.
        country_to_country_patterns = [
            r'\b(\w+(?:\s+\w+)?)\s+to\s+(\w+(?:\s+\w+)?)',  # "USA to China"
            r'from\s+(\w+(?:\s+\w+)?)\s+to\s+(\w+(?:\s+\w+)?)',  # "from USA to China"
            r'(\w+(?:\s+\w+)?)\s+(?:exports?|imports?)\s+(?:to|from)\s+(\w+(?:\s+\w+)?)'  # "USA exports to China"
        ]

        origin = None
        dest = None

        for pattern in country_to_country_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                origin = match.group(1).strip()
                dest = match.group(2).strip() if len(match.groups()) > 1 else None
                break

        if not origin or not dest:
            return False  # Not a country-to-country query

        # Filter out non-country words
        non_countries = ['top', 'best', 'biggest', 'largest', 'leading', 'major', 'main', 'companies', 'importers', 'exporters']
        if origin.lower() in non_countries or dest.lower() in non_countries:
            return False

        print(f"[UNIFIED-MIRROR-CHECK] Detected country-to-country: {origin} -> {dest}")

        # Check if BOTH countries are mirror-only
        try:
            api_url = "https://api-dp.marketinsidedata.com/api/v1/users/detailed-mirror-countries-list"
            request_body = {
                "data_type": "",
                "continent": "",
                "direction": "",
                "searchQuery": "",
                "pageNumber": 1,
                "pageSize": 100000
            }

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(api_url, json=request_body)

                if response.status_code != 200:
                    print(f"[UNIFIED-MIRROR-CHECK] API returned {response.status_code}, skipping check")
                    return False  # Optimistic: continue if API fails

                data = response.json()

                # Parse response
                countries_list = []
                if isinstance(data, dict):
                    if "countries" in data:
                        countries_list = data["countries"]
                    elif "message" in data:
                        countries_list = data["message"]
                    elif "data" in data:
                        countries_list = data["data"]
                elif isinstance(data, list):
                    countries_list = data

                if not countries_list:
                    print(f"[UNIFIED-MIRROR-CHECK] No countries list, skipping check")
                    return False  # Optimistic

                # Check both countries
                origin_is_mirror_only = self._is_country_mirror_only(origin, countries_list)
                dest_is_mirror_only = self._is_country_mirror_only(dest, countries_list)

                print(f"[UNIFIED-MIRROR-CHECK] {origin} mirror-only: {origin_is_mirror_only}, {dest} mirror-only: {dest_is_mirror_only}")

                # Return True only if BOTH are mirror-only
                return origin_is_mirror_only and dest_is_mirror_only

        except Exception as e:
            print(f"[UNIFIED-MIRROR-CHECK] Error: {e}")
            return False  # Optimistic: continue on error

    def _is_country_mirror_only(self, country_name: str, countries_list: list) -> bool:
        """
        Check if a country has ONLY mirror data (no detailed data).
        Returns True if mirror-only, False if has detailed data or not found.
        """
        country_lower = country_name.lower().strip().replace('-', ' ')

        for c in countries_list:
            if not isinstance(c, dict):
                continue

            c_name = (c.get("country_name") or "").strip().lower()
            c_code = (c.get("country_code") or "").strip().upper()

            # Match by name or code
            name_matches = (
                c_name == country_lower or
                c_name.replace(" ", "-") == country_lower.replace(" ", "-") or
                (len(country_name) == 2 and c_code == country_name.upper())
            )

            if name_matches:
                data_types = c.get("data_type", [])

                # Check if has ANY detailed data
                has_detailed = "detailed_import" in data_types or "detailed_export" in data_types

                # Mirror-only = has mirror but NO detailed
                has_mirror = "mirror_import" in data_types or "mirror_export" in data_types

                is_mirror_only = has_mirror and not has_detailed

                print(f"[UNIFIED-MIRROR-CHECK]   {c_name}: types={data_types}, mirror_only={is_mirror_only}")

                return is_mirror_only

        # Not found - optimistic: assume it has detailed data
        print(f"[UNIFIED-MIRROR-CHECK]   {country_lower}: not found in list, assuming has detailed data")
        return False
