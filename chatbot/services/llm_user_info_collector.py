"""
LLM-Driven User Information Collection

INTELLIGENT & FAST - Uses LLM for smart detection, prevents duplicate asks.

Strategy:
1. Fast LLM detection check (prevents asking for info user just provided)
2. Background extraction (doesn't block main response)
3. Contextual template-based prompts
4. Redis caching for speed
"""

import json
import asyncio
import re
import ollama
from typing import Optional, Dict, Any, List
from datetime import datetime

from chatbot.database.user_info_service import UserInfoService
from chatbot.integrations.redis.client import RedisMemoryManager
from chatbot.utils.email_validator import get_email_validator


class LLMUserInfoCollector:
    """
    Intelligent LLM-driven user info collector.

    Key features:
    - Smart LLM detection (prevents duplicate asks)
    - Runs in background (doesn't block main response)
    - Fast contextual prompts
    - Redis caching for speed
    """

    def __init__(
        self,
        redis_manager: RedisMemoryManager,
        user_info_service: UserInfoService,
        ollama_cloud_client: Optional[ollama.Client] = None
    ):
        self.redis = redis_manager
        self.db_service = user_info_service
        self._cache = {}  # In-memory cache for decisions
        self._detection_cache = {}  # Cache for LLM detection results (fast lookup)
        self._prompt_cache = {}  # Cache for LLM-generated prompts (field -> prompt)
        self._ollama_client = ollama_cloud_client  # For LLM detection calls

    async def _call_llm_with_timeout(self, model: str, messages: list, options: dict, timeout: float = 10.0):
        """
        Call LLM with timeout to prevent hanging.

        Args:
            model: Model name
            messages: Messages to send
            options: Ollama options
            timeout: Timeout in seconds (default 10s)

        Returns:
            Response dict or None if timeout/error
        """
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._ollama_client.chat,
                    model=model,
                    messages=messages,
                    options=options
                ),
                timeout=timeout
            )
            return response
        except asyncio.TimeoutError:
            print(f"[LLM_COLLECTOR] ⏱️ LLM call timed out after {timeout}s")
            return None
        except Exception as e:
            print(f"[LLM_COLLECTOR] ❌ LLM call error: {e}")
            return None

    async def analyze_and_collect_async(
        self,
        session_id: str,
        user_message: str,
        bot_response: str,
        message_count: int,
        conversation_history: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        INTELLIGENT USER INFO COLLECTION - LLM-driven, context-aware, natural.

        Next-Level Strategy:
        1. LLM analyzes conversation history to detect resistance patterns
        2. Intelligently decides WHICH field to ask for (or skip if user declined 4+ times)
        3. Natural, human-like adaptation to user preferences
        4. Background extraction (non-blocking)

        Performance: ~1-2ms for instant path, ~2-3s for LLM decision (first time, then cached)
        """
        print(f"[COLLECTOR_INTERNAL] analyze_and_collect_async: msg_count={message_count}")

        # Don't collect on message 1
        if message_count < 2:
            return None

        # Get current state (fast Redis check, ~1-2ms)
        user_info = await self._get_user_info_fast(session_id)
        missing = self._get_missing_fields(user_info)

        if not missing:
            return None  # All collected

        print(f"[COLLECTOR_INTERNAL] Missing: {missing}, starting background extraction")

        # Start background extraction (non-blocking, ~1ms to spawn)
        # All LLM detection and extraction happens in background
        asyncio.create_task(
            self._llm_analyze_and_collect_background(
                session_id=session_id,
                user_message=user_message,
                bot_response=bot_response,
                message_count=message_count,
                conversation_history=conversation_history,
                current_missing=missing
            )
        )

        # INTELLIGENT PROMPTING: INSTANT with background intelligence
        # Priority order for REAL-TIME collection: name > email > phone
        # NOTE: Requirements are collected AFTER session ends (not asked during conversation)
        missing_realtime = [f for f in missing if f != 'requirements']

        # Ask starting from message 2, then every 3 messages (2, 5, 8, 11...)
        # This gives user time to respond without being too pushy
        should_ask = message_count >= 2 and (message_count - 2) % 3 == 0

        if should_ask and missing_realtime:
            # INSTANT DECISION: Check cache first (0ms)
            cache_key = f"field_decision:{session_id}"
            cached_field = self._detection_cache.get(cache_key)

            if cached_field and cached_field in missing_realtime:
                # Use cached decision (instant)
                field_to_ask = cached_field
                print(f"[LLM_COLLECTOR] ⚡ Using cached field decision: '{field_to_ask}'")
            else:
                # No cache: Use priority order (instant fallback)
                priority_order = ['name', 'email', 'phone']
                field_to_ask = None
                for field in priority_order:
                    if field in missing_realtime:
                        field_to_ask = field
                        break

                if not field_to_ask:
                    return None

                print(f"[LLM_COLLECTOR] ⚡ Using priority order (instant): '{field_to_ask}'")

                # Run intelligent analysis in BACKGROUND for next time (non-blocking)
                asyncio.create_task(
                    self._intelligent_field_selection_background(
                        session_id=session_id,
                        missing_fields=missing_realtime,
                        conversation_history=conversation_history,
                        user_message=user_message
                    )
                )

            # INSTANT PROMPT: Check cache first
            prompt_cache_key = f"prompt:{field_to_ask}:{session_id}"
            cached_prompt = self._prompt_cache.get(prompt_cache_key)

            if cached_prompt:
                # Use cached prompt (instant)
                print(f"[LLM_COLLECTOR] ⚡ Using cached intelligent prompt: {cached_prompt[:60]}...")
                return f"\n\n{cached_prompt}"
            else:
                # No cache: Use template (instant)
                prompt = self._generate_template_prompt(field_to_ask, user_message)
                print(f"[LLM_COLLECTOR] ⚡ Using template prompt (instant): {prompt[:60]}...")

                # Generate intelligent prompt in BACKGROUND for next time (non-blocking)
                asyncio.create_task(
                    self._generate_intelligent_prompt_background(
                        session_id=session_id,
                        field=field_to_ask,
                        user_message=user_message,
                        bot_response=bot_response,
                        conversation_history=conversation_history
                    )
                )

                return f"\n\n{prompt}"

        return None

    async def _llm_analyze_and_collect_background(
        self,
        session_id: str,
        user_message: str,
        bot_response: str,
        message_count: int,
        conversation_history: List[Dict[str, str]],
        current_missing: List[str]
    ):
        """
        OPTIMIZED: Single-pass LLM extraction with caching.

        Performance improvements:
        1. Skip detection, go straight to extraction (faster)
        2. Cache results for next message
        3. No redundant LLM calls

        NOTE: Requirements are NOT extracted here - they're extracted when
        conversation is saved (end of session) for better accuracy.
        """
        try:
            print(f"[LLM_COLLECTOR] Background extraction started (name/email/phone only)")

            # Filter out requirements - they're collected after session ends
            missing_realtime = [f for f in current_missing if f != 'requirements']

            if missing_realtime:
                # OPTIMIZED: Skip separate detection call, go straight to extraction
                # This saves 1-2 LLM calls per message (2-4 seconds)
                await self._extract_and_save_background(session_id, user_message, missing_realtime, conversation_history)

            print(f"[LLM_COLLECTOR] Background extraction complete")

        except Exception as e:
            print(f"[LLM_COLLECTOR] Background error: {e}")
            import traceback
            traceback.print_exc()

    async def extract_requirements_from_full_history(
        self,
        session_id: str,
        conversation_history: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        Extract requirements from FULL conversation history after session ends.

        This is called when conversation is saved to analyze the complete
        conversation and extract what the user was looking for.

        Returns the extracted requirement or None.
        """
        if not conversation_history or len(conversation_history) < 2:
            print(f"[LLM_COLLECTOR] [POST-SESSION] Conversation too short, skipping requirements extraction")
            return None

        try:
            print(f"[LLM_COLLECTOR] [POST-SESSION] Extracting requirements from {len(conversation_history)} messages")

            # Check if requirements already exist
            user_info = await self._get_user_info_fast(session_id)
            if user_info.get('requirements'):
                print(f"[LLM_COLLECTOR] [POST-SESSION] Requirements already exist, skipping")
                return user_info['requirements']

            # Build conversation summary (last 10 user messages)
            user_queries = []
            for msg in conversation_history:
                if msg.get('role') == 'user':
                    content = msg.get('content', '').strip()
                    if content and len(content) > 5:
                        user_queries.append(content)

            if not user_queries:
                print(f"[LLM_COLLECTOR] [POST-SESSION] No user queries found")
                return None

            # Take last 10 queries for analysis
            recent_queries = user_queries[-10:]
            queries_text = "\n".join([f"- {q}" for q in recent_queries])

            # Use keyword extraction as primary method (faster, more reliable)
            requirement = self._extract_requirement_from_keywords(
                " ".join(recent_queries),
                conversation_history
            )

            if requirement and len(requirement) > 15:
                # Save to database
                print(f"[LLM_COLLECTOR] [POST-SESSION] Extracted requirement: {requirement[:100]}...")
                await self.db_service.save_user_info(session_id, 'requirements', requirement)
                return requirement

            print(f"[LLM_COLLECTOR] [POST-SESSION] No clear requirement found")
            return None

        except Exception as e:
            print(f"[LLM_COLLECTOR] [POST-SESSION] Requirements extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_cached_detection(
        self,
        session_id: str,
        user_message: str,
        missing_fields: List[str]
    ) -> List[str]:
        """
        INSTANT detection using cached LLM results (< 1ms).

        100% LLM-DRIVEN - no heuristic fallback.
        Returns empty if no cache (background LLM will handle detection).
        """
        # Check cache (instant)
        cache_key = f"{session_id}:{user_message[:50]}"
        if cache_key in self._detection_cache:
            cached = self._detection_cache[cache_key]
            print(f"[COLLECTOR_INTERNAL] * Cache HIT - LLM detected: {cached}")
            return [f for f in cached if f in missing_fields]

        # No cache - return empty (background LLM will detect and cache for next time)
        # This prevents asking for info the user just provided
        print(f"[COLLECTOR_INTERNAL] * Cache MISS - background LLM will handle detection")
        return []  # Trust LLM only, no heuristics

    def _instant_heuristic_detection(
        self,
        user_message: str,
        missing_fields: List[str],
        conversation_context: Optional[List[Dict[str, str]]] = None
    ) -> List[str]:
        """
        INSTANT heuristic detection (< 1ms, no LLM).

        Fast patterns that catch obvious cases:
        - Email: user@domain.com
        - Phone: +1234567890
        - Name: "my name is X", "I'm X", or direct answer after asking
        - Requirements: "I need X", "looking for X"
        """
        detected = []
        user_lower = user_message.lower()
        message_stripped = user_message.strip()

        # Detect email (instant regex)
        if 'email' in missing_fields:
            if re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', user_message):
                detected.append('email')

        # Detect phone (instant regex)
        if 'phone' in missing_fields:
            if re.search(r'\+?\d[\d\s\-()]{8,}\d', user_message):
                detected.append('phone')

        # Detect name (EXPLICIT patterns OR direct answer)
        if 'name' in missing_fields:
            # Pattern 1: Explicit ("my name is X", "I'm X")
            explicit_patterns = [
                r"my name is", r"i'm\s+[A-Z]", r"i am\s+[A-Z]",
                r"call me", r"this is\s+[A-Z]"
            ]
            if any(re.search(p, user_message, re.IGNORECASE) for p in explicit_patterns):
                detected.append('name')

            # Pattern 2: Direct answer after bot asked for name
            # Check if bot just asked for name in last message OR second-to-last message
            elif conversation_context and len(conversation_context) >= 1:
                # Check last 2 bot messages for name question
                bot_asked_for_name = False
                for msg in reversed(conversation_context[-4:]):  # Check last 4 messages (2 exchanges)
                    if msg.get('role') == 'assistant':
                        bot_msg_lower = msg.get('content', '').lower()
                        if (('name' in bot_msg_lower or 'who are you' in bot_msg_lower or "what's your name" in bot_msg_lower) and
                            any(q in bot_msg_lower for q in ['?', 'please', 'could you', 'may i', 'share your'])):
                            bot_asked_for_name = True
                            break

                if bot_asked_for_name:
                    # Bot asked for name, check if user provided simple text response
                    # Must be: 2-50 chars, mostly letters, not a question, not a common phrase
                    # Accept both capitalized AND lowercase names (e.g., "Pulkit" or "pulkit")
                    # CRITICAL: Filter out affirmations, negations, and common non-name responses
                    # This prevents "yes" (from "Was this helpful?") being treated as a name
                    affirmative_responses = ['yes', 'no', 'ok', 'sure', 'nope', 'yeah', 'yep', 'nah',
                                            'okay', 'fine', 'alright', 'thanks', 'thank you',
                                            'great', 'good', 'perfect', 'nice']
                    common_countries = ['usa', 'united kingdom', 'china', 'uk', 'brazil', 'germany', 'russia',
                                       'japan', 'france', 'canada', 'mexico', 'italy', 'spain']
                    greetings = ['hi', 'hello', 'hey', 'greetings', 'sup', 'howdy']

                    is_likely_name = (
                        2 <= len(message_stripped) <= 50 and
                        sum(c.isalpha() or c.isspace() for c in message_stripped) / len(message_stripped) > 0.6 and
                        '?' not in message_stripped and
                        message_stripped.lower() not in affirmative_responses and
                        message_stripped.lower() not in common_countries and
                        message_stripped.lower() not in greetings and
                        # Simple word with mostly letters (accept both "Pulkit" and "pulkit")
                        (len(message_stripped) <= 20 and
                         sum(c.isalpha() or c.isspace() for c in message_stripped) >= len(message_stripped) * 0.8)
                    )
                    if is_likely_name:
                        detected.append('name')
                        print(f"[COLLECTOR_INTERNAL] * Heuristic detected name: '{message_stripped}'")

        # Detect requirements (keyword-based)
        if 'requirements' in missing_fields:
            req_keywords = [
                'need', 'want', 'looking for', 'interested in', 'require',
                'import data', 'export data', 'trade data', 'shipment'
            ]
            if any(kw in user_lower for kw in req_keywords):
                detected.append('requirements')

        return detected

    async def _quick_detect_user_info(
        self,
        user_message: str,
        missing_fields: List[str],
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> List[str]:
        """
        Intelligent LLM-based detection with CONVERSATION CONTEXT.

        Returns list of fields detected (e.g., ['name', 'email']).
        Uses conversation history to understand if user is answering a question.
        """
        if not missing_fields:
            return []

        # Build conversation context (last 3 messages for context)
        context = ""
        if conversation_history and len(conversation_history) >= 2:
            recent = conversation_history[-6:]  # Last 3 exchanges
            for msg in recent:
                role = "Bot" if msg['role'] == 'assistant' else "User"
                content = msg['content'][:150]
                context += f"{role}: {content}\n"

        # Build focused prompt with context
        fields_str = ', '.join(missing_fields)
        prompt = f"""You are an intelligent data extraction assistant. Analyze the FULL conversation context to determine if the user provided: {fields_str}.

CONVERSATION CONTEXT (last few exchanges):
{context}

CURRENT USER MESSAGE: "{user_message}"

INTELLIGENT DETECTION RULES:

1. NAME:
   ✅ ACTUAL names: "My name is John", "I'm Sarah", "Call me Alex", "Pulkit", "John Smith", "Sarah Johnson"
   ✅ Direct answers to name questions: Bot asks "What's your name?" → User: "Michael"

   ❌ NOT affirmations: "yes", "no", "ok", "sure", "thanks", "great", "fine", "alright", "yeah", "yep"
   ❌ NOT acknowledgments to OTHER questions: If user says "yes" after "Was this helpful?", that's NOT their name!
   ❌ NOT countries/products: "USA", "United Kingdom", "Indonesia", "oil", "electronics"
   ❌ NOT polite rejections: "not now", "maybe later", "skip", "no thanks"

   CONTEXT MATTERS: Look at what the bot asked MOST RECENTLY. If bot asked "Was this helpful?" and user says "yes", that's an affirmation, NOT a name!

2. EMAIL:
   ✅ Valid format: user@domain.com, contact@company.co.uk

3. PHONE:
   ✅ Phone formats: +1234567890, (123) 456-7890, 123-456-7890

4. REQUIREMENTS:
   ✅ SPECIFIC needs: "I need Brazil import data", "Looking for electronics suppliers in Vietnam"
   ❌ NOT vague: "yes", "no", "help me", "tell me more", "sure"

CRITICAL ANALYSIS:
- Read the conversation history to understand what question the user is answering
- If bot just asked "Was this helpful?" and user says "yes" → that's an AFFIRMATION, not data
- If bot just asked "Could you share your name?" and user says "John" → that's a NAME
- Single word responses need context to interpret correctly!

OUTPUT FORMAT (JSON only):
{{"name": true/false, "email": true/false, "phone": true/false, "requirements": true/false}}

Your response:"""

        try:
            # Fast LLM call for intelligent detection
            if not self._ollama_client:
                # Fallback to regex if no LLM client
                print("[COLLECTOR_INTERNAL] No Ollama client, using fallback regex detection")
                return self._fallback_regex_detection(user_message, missing_fields)

            response = await self._call_llm_with_timeout(
                model='qwen3.5:cloud',  # Cloud model (same as main)
                messages=[{'role': 'user', 'content': prompt}],
                options={
                    'temperature': 0.0,  # Zero temperature for deterministic output
                    'num_predict': 100,  # Reduced for faster response
                    'thinking': False,  # Disable thinking output
                    'num_ctx': 2048  # Reduced context for speed
                },
                timeout=10.0
            )

            if not response:
                print("[COLLECTOR_INTERNAL] LLM detection timed out, using fallback")
                return self._fallback_regex_detection(user_message, missing_fields)

            # Parse JSON response with robust extraction
            # Handle models that put output in 'thinking' field (e.g., gpt-oss:20b-cloud)
            response_text = response['message'].get('content', '').strip()
            if not response_text and 'thinking' in response['message']:
                response_text = response['message']['thinking'].strip()

            print(f"[COLLECTOR_INTERNAL] Raw LLM response: content={response['message'].get('content', '')[:100]}, has_thinking={('thinking' in response['message'])}")

            # ROBUST JSON EXTRACTION - handles thinking text and various formats
            def extract_json_from_text(text: str) -> Optional[dict]:
                """Extract JSON from text that may contain thinking/explanation"""
                if not text:
                    return None

                # Remove markdown code blocks
                text = re.sub(r'```(?:json)?\s*|\s*```', '', text).strip()

                # Try to find JSON object - look for {...} pattern with boolean values
                # Match JSON objects that contain true/false values (our expected format)
                json_patterns = [
                    r'\{[^{}]*(?:"name"|"email"|"phone"|"requirements")[^{}]*\}',  # Contains our keys
                    r'\{(?:[^{}]|"[^"]*")*\}',  # Any valid JSON object
                ]

                for pattern in json_patterns:
                    matches = re.finditer(pattern, text, re.DOTALL)
                    for match in matches:
                        try:
                            candidate = match.group(0)
                            parsed = json.loads(candidate)
                            # Validate it has at least one of our expected keys
                            if any(k in parsed for k in ['name', 'email', 'phone', 'requirements']):
                                return parsed
                        except json.JSONDecodeError:
                            continue

                # If all else fails, try to parse the whole text
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return None

            data = extract_json_from_text(response_text)

            if not data:
                print(f"[COLLECTOR_INTERNAL] Failed to extract JSON from: {response_text[:200]}")
                raise ValueError("No valid JSON found in response")
            print(f"[COLLECTOR_INTERNAL] LLM detection result: {data}")

            # Build detected list
            detected = []
            if data.get('name') and 'name' in missing_fields:
                detected.append('name')
            if data.get('email') and 'email' in missing_fields:
                detected.append('email')
            if data.get('phone') and 'phone' in missing_fields:
                detected.append('phone')
            if data.get('requirements') and 'requirements' in missing_fields:
                detected.append('requirements')

            return detected

        except Exception as e:
            print(f"[COLLECTOR_INTERNAL] LLM detection failed: {e}, using fallback regex")
            # Fallback to regex on error
            return self._fallback_regex_detection(user_message, missing_fields)

    def _fallback_regex_detection(
        self,
        user_message: str,
        missing_fields: List[str]
    ) -> List[str]:
        """
        Fallback regex-based detection if LLM fails.
        """
        detected = []
        user_lower = user_message.lower()

        # Detect name
        if 'name' in missing_fields:
            patterns = [
                r"(?:my name is|i'm|i am|call me|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
                r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)$"
            ]
            for pattern in patterns:
                match = re.search(pattern, user_message, re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
                    if name.lower() not in ['hi', 'hello', 'hey', 'yes', 'no', 'ok']:
                        detected.append('name')
                        break

        # Detect requirements (keyword-based fallback)
        if 'requirements' in missing_fields:
            requirement_keywords = [
                'need', 'want', 'looking for', 'interested in', 'require',
                'import data', 'export data', 'shipment', 'customs data',
                'trade statistics', 'buyer', 'supplier', 'market intelligence'
            ]
            if any(kw in user_lower for kw in requirement_keywords):
                detected.append('requirements')

        # Detect email
        if 'email' in missing_fields:
            pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            if re.search(pattern, user_message):
                detected.append('email')

        # Detect phone
        if 'phone' in missing_fields:
            pattern = r'\+?\d[\d\s\-()]{8,}\d'
            match = re.search(pattern, user_message)
            if match:
                phone = re.sub(r'[^\d+]', '', match.group(0))
                if len(phone) >= 10:
                    detected.append('phone')

        return detected

    def _fast_decision_heuristic(
        self,
        user_message: str,
        bot_response: str,
        message_count: int,
        missing_fields: List[str],
        user_info: Dict[str, Any],
        session_id: str = None
    ) -> Dict[str, Any]:
        """
        FAST decision using heuristics (no LLM call).

        NEW Priority Order:
        0. Check for rejected disposable emails (notify user)
        1. Name (message 2-3)
        2. Email OR Phone (after name, prioritize email unless they mention call/demo)
        3. Requirements (after contact info collected)
        """

        user_lower = user_message.lower()
        bot_lower = bot_response.lower()

        # Priority 0: Check if we rejected a disposable email - ask again with explanation
        if session_id and 'email' in missing_fields:
            rejection_key = f"email_rejected:{session_id}"
            if rejection_key in self._cache:
                rejection_info = self._cache[rejection_key]
                del self._cache[rejection_key]  # Clear after use
                print(f"[COLLECTOR_INTERNAL] [WARN] Detected rejected disposable email - will ask for valid email")
                return {
                    'should_ask': True,
                    'field': 'email',
                    'custom_message': f"To send you professional trade insights and detailed reports, I'll need a work email address. Could you share your company email?"
                }

        # Don't collect user info if bot couldn't help (said "Sorry", etc.)
        if self._is_out_of_scope_response(bot_response):
            return {'should_ask': False, 'field': None}

        # CRITICAL: Never ask for user info when bot failed to provide value
        # This prevents desperate behavior when queries fail
        bot_failed_indicators = [
            'not available in the data',
            "i don't have",
            'unable to find',
            "couldn't locate",
            'no data available',
            'data is not available',
            'cannot find',
            'not found',
        ]
        if bot_response and any(indicator in bot_lower for indicator in bot_failed_indicators):
            print(f"[COLLECTOR_INTERNAL] 🚫 Bot couldn't help - skipping user info collection (not desperate)")
            return {'should_ask': False, 'field': None}

        # Priority 1: Name (ask first)
        if 'name' in missing_fields:
            # Ask at message 2 or 3, or if they're asking about pricing/demo
            if (message_count in [2, 3] or
                any(word in user_lower for word in ['price', 'pricing', 'demo', 'buy', 'purchase', 'service'])):
                return {'should_ask': True, 'field': 'name'}

        # Check if we have contact info (email OR phone)
        has_contact_info = user_info.get('email') or user_info.get('phone')

        # Priority 2: Email OR Phone (get at least ONE contact method after name)
        if user_info.get('name') and not has_contact_info:
            # Prioritize phone if they mention call/demo/contact
            if 'phone' in missing_fields:
                if any(word in user_lower for word in ['call', 'demo', 'speak', 'talk', 'phone', 'contact', 'callback']):
                    return {'should_ask': True, 'field': 'phone'}

            # Otherwise prioritize email
            if 'email' in missing_fields:
                # Ask after name collected, or if they ask for info to be sent
                if (message_count >= 3 or
                    any(word in user_lower for word in ['send', 'email', 'report', 'details', 'information', 'share', 'price'])):
                    return {'should_ask': True, 'field': 'email'}

        # Priority 3: Requirements (ask AFTER we have contact info)
        if 'requirements' in missing_fields and has_contact_info:
            # Ask if engaged or they mention needing something
            if (message_count >= 4 or
                any(word in user_lower for word in ['need', 'want', 'looking for', 'interested in', 'help', 'data', 'service'])):
                return {'should_ask': True, 'field': 'requirements'}

        # Priority 4: Get second contact method (email if we have phone, or vice versa)
        if user_info.get('name') and has_contact_info:
            # If we have requirements, try to get second contact method
            if user_info.get('requirements'):
                if 'email' in missing_fields and user_info.get('phone'):
                    if message_count >= 6:
                        return {'should_ask': True, 'field': 'email'}
                if 'phone' in missing_fields and user_info.get('email'):
                    if message_count >= 6:
                        return {'should_ask': True, 'field': 'phone'}

        return {'should_ask': False, 'field': None}

    async def _generate_fast_contextual_prompt(
        self,
        field: str,
        bot_response: str,
        user_message: str
    ) -> str:
        """
        INSTANT prompt generation using templates (< 1ms).

        LLM-based personalization runs in background and caches for future use.
        This keeps main response fast while still providing good prompts.
        """

        # Use generic prompt if bot said "Sorry" or couldn't help
        if self._is_out_of_scope_response(bot_response):
            generic_prompt = self._generate_generic_prompt(field)
            print(f"[LLM_COLLECTOR] * Generic prompt (instant): {generic_prompt[:50]}...")
            return generic_prompt

        # Check cache for LLM-generated prompt (instant)
        cache_key = f"{field}"
        if cache_key in self._prompt_cache:
            cached_prompt = self._prompt_cache[cache_key]
            print(f"[LLM_COLLECTOR] * Cached LLM prompt (instant): {cached_prompt[:50]}...")
            return cached_prompt

        # Use template immediately (instant)
        template_prompt = self._generate_template_prompt(field, user_message)
        print(f"[LLM_COLLECTOR] * Template prompt (instant): {template_prompt[:50]}...")

        # Generate better LLM prompt in background for future use
        if self._ollama_client:
            asyncio.create_task(
                self._generate_and_cache_llm_prompt(field, bot_response, user_message)
            )

        return template_prompt

    async def _generate_and_cache_llm_prompt(
        self,
        field: str,
        bot_response: str,
        user_message: str
    ):
        """
        Generate LLM prompt in BACKGROUND and cache for future use.
        This improves prompts over time without blocking responses.
        """
        try:
            llm_prompt = await self._generate_llm_prompt(field, bot_response, user_message)
            if llm_prompt:
                cache_key = f"{field}"
                self._prompt_cache[cache_key] = llm_prompt
                print(f"[LLM_COLLECTOR] * Cached improved LLM prompt for '{field}': {llm_prompt[:60]}...")
        except Exception as e:
            print(f"[LLM_COLLECTOR] Background LLM prompt generation failed: {e}")

    async def _intelligent_field_selection_background(
        self,
        session_id: str,
        missing_fields: List[str],
        conversation_history: List[Dict[str, str]],
        user_message: str
    ):
        """
        BACKGROUND TASK: Run intelligent field selection and cache for next time.
        This doesn't block the response - results are cached for future use.
        """
        try:
            field = await self._intelligent_field_selection(
                session_id=session_id,
                missing_fields=missing_fields,
                conversation_history=conversation_history,
                user_message=user_message
            )

            if field:
                # Cache for next time (instant decision)
                cache_key = f"field_decision:{session_id}"
                self._detection_cache[cache_key] = field
                print(f"[LLM_COLLECTOR] 💾 Cached field decision for next time: '{field}'")

        except Exception as e:
            print(f"[LLM_COLLECTOR] ❌ Background field selection error: {e}")

    async def _generate_intelligent_prompt_background(
        self,
        session_id: str,
        field: str,
        user_message: str,
        bot_response: str,
        conversation_history: List[Dict[str, str]]
    ):
        """
        BACKGROUND TASK: Generate intelligent prompt and cache for next time.
        This doesn't block the response - results are cached for future use.
        """
        try:
            prompt = await self._generate_intelligent_prompt(
                field=field,
                user_message=user_message,
                bot_response=bot_response,
                conversation_history=conversation_history
            )

            if prompt:
                # Cache for next time (instant prompt)
                cache_key = f"prompt:{field}:{session_id}"
                self._prompt_cache[cache_key] = prompt
                print(f"[LLM_COLLECTOR] 💾 Cached intelligent prompt for next time: {prompt[:60]}...")

        except Exception as e:
            print(f"[LLM_COLLECTOR] ❌ Background prompt generation error: {e}")

    async def _intelligent_field_selection(
        self,
        session_id: str,
        missing_fields: List[str],
        conversation_history: List[Dict[str, str]],
        user_message: str
    ) -> Optional[str]:
        """
        INTELLIGENT FIELD SELECTION using LLM.

        The LLM analyzes the full conversation to:
        1. Detect if user has declined specific fields multiple times (4+)
        2. Understand user's willingness to share different types of info
        3. Intelligently select which field to ask for next
        4. Skip fields that user clearly doesn't want to provide

        Returns: Field name to ask for, or None if should skip this turn
        """
        if not self._ollama_client or not conversation_history:
            # Fallback: simple priority order
            return missing_fields[0] if missing_fields else None

        try:
            # Build conversation context (last 10 exchanges)
            context = ""
            bot_ask_history = {field: [] for field in ['name', 'email', 'phone']}

            # Track what we've asked for and user's responses
            for i, msg in enumerate(conversation_history[-20:]):  # Last 20 messages
                role = "Bot" if msg['role'] == 'assistant' else "User"
                content = msg['content'][:200]
                context += f"{role}: {content}\n"

                # Track when bot asked for specific fields
                msg_lower = content.lower()
                if role == "Bot":
                    if 'name' in msg_lower and any(q in msg_lower for q in ['?', 'share', 'could', 'may i']):
                        bot_ask_history['name'].append(i)
                    if 'email' in msg_lower and any(q in msg_lower for q in ['?', 'share', 'could', 'may i']):
                        bot_ask_history['email'].append(i)
                    if 'phone' in msg_lower and any(q in msg_lower for q in ['?', 'share', 'could', 'may i']):
                        bot_ask_history['phone'].append(i)

            # Count how many times each field was asked
            ask_counts = {field: len(asks) for field, asks in bot_ask_history.items()}

            # Build intelligent prompt for LLM
            missing_str = ', '.join(missing_fields)
            ask_summary = '\n'.join([f"- {field}: asked {count} times" for field, count in ask_counts.items() if count > 0])

            system_prompt = f"""You are an intelligent assistant analyzing user behavior to optimize information collection.

CONVERSATION HISTORY (last 10 exchanges):
{context}

MISSING INFORMATION: {missing_str}

ASK HISTORY:
{ask_summary if ask_summary else 'No fields asked yet'}

YOUR TASK: Analyze the conversation and decide which field to ask for next (or skip).

INTELLIGENT DECISION RULES:

1. DETECT RESISTANCE PATTERNS:
   - If user declined a specific field 4+ times → PERMANENTLY SKIP that field
   - Examples of decline signals:
     * Direct: "no", "skip", "prefer not to", "don't want to share"
     * Indirect: ignoring the question, changing topic, giving fake info
     * Repeated vague answers without providing the info

2. FIELD-SPECIFIC INTELLIGENCE:
   - User may be willing to share EMAIL but not PHONE
   - User may be willing to share NAME but not EMAIL
   - Each field is independent - don't give up on all fields if one is declined

3. SELECTION PRIORITY:
   - Prefer: name > email > phone
   - BUT: Skip fields with 4+ decline signals
   - AND: Consider user's current context (what they're asking about)

4. CONTEXT-AWARE:
   - If user is asking about pricing → good time for email
   - If user mentions callback/demo → good time for phone
   - If user is engaged and helpful → good time for name

ANALYZE THE PATTERN:
- How many times was each field asked?
- How did user respond each time?
- Is there a clear pattern of declining specific fields?
- Which field should we ask for now (or should we skip)?

OUTPUT FORMAT (JSON only):
{{
  "field_to_ask": "name|email|phone|none",
  "reason": "brief explanation",
  "declined_fields": ["list", "of", "fields", "user", "declined", "4+", "times"]
}}

Your response:"""

            response = await self._call_llm_with_timeout(
                model='qwen3.5:cloud',
                messages=[{'role': 'user', 'content': system_prompt}],
                options={
                    'temperature': 0.1,  # Low temperature for consistent decisions
                    'num_predict': 150,
                    'thinking': False,
                    'num_ctx': 4096
                },
                timeout=10.0
            )

            if not response:
                print("[LLM_COLLECTOR] ⏱️ Field selection timed out - using fallback")
                return missing_fields[0] if missing_fields else None

            # Parse JSON response
            response_text = response['message'].get('content', '').strip()
            if not response_text and 'thinking' in response['message']:
                response_text = response['message']['thinking'].strip()

            # ROBUST JSON EXTRACTION - handle thinking text and various formats
            import re

            # Remove markdown code blocks
            response_text = re.sub(r'```(?:json)?\s*|\s*```', '', response_text).strip()

            # Remove thinking process text (common prefix in responses)
            response_text = re.sub(r'^.*?Thinking Process:.*?\n\n', '', response_text, flags=re.DOTALL | re.IGNORECASE)
            response_text = re.sub(r'^.*?Analysis:.*?\n\n', '', response_text, flags=re.DOTALL | re.IGNORECASE)

            # Find JSON object - look for {...} with our expected keys
            json_patterns = [
                r'\{[^{}]*"field_to_ask"[^{}]*\}',  # Contains our key
                r'\{(?:[^{}]|"[^"]*")*\}',  # Any valid JSON object
            ]

            json_match = None
            for pattern in json_patterns:
                json_match = re.search(pattern, response_text, re.DOTALL)
                if json_match:
                    break

            if json_match:
                try:
                    data = json.loads(json_match.group(0))
                    field = data.get('field_to_ask', '').lower()
                    reason = data.get('reason', '')
                    declined = data.get('declined_fields', [])

                    print(f"[LLM_COLLECTOR] 🧠 Intelligent decision: field='{field}', reason='{reason}'")
                    if declined:
                        print(f"[LLM_COLLECTOR] 🚫 User declined: {declined}")

                    if field == 'none' or field not in missing_fields:
                        return None

                    return field
                except json.JSONDecodeError as e:
                    print(f"[LLM_COLLECTOR] ⚠️ JSON parse error: {e}, using fallback")
                    return missing_fields[0] if missing_fields else None
            else:
                print(f"[LLM_COLLECTOR] ⚠️ No JSON found in response, using fallback")
                print(f"[LLM_COLLECTOR] Response preview: {response_text[:200]}")
                return missing_fields[0] if missing_fields else None

        except Exception as e:
            print(f"[LLM_COLLECTOR] ❌ Intelligent field selection error: {e}")
            import traceback
            traceback.print_exc()
            return missing_fields[0] if missing_fields else None

    async def _generate_intelligent_prompt(
        self,
        field: str,
        user_message: str,
        bot_response: str,
        conversation_history: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        GENERATE INTELLIGENT, CONTEXT-AWARE PROMPT using LLM.

        The LLM creates a natural, conversational prompt that:
        1. Matches the tone and context of the conversation
        2. References what user is asking about
        3. Explains value of providing the info
        4. Feels human and not robotic

        Returns: Natural prompt string
        """
        if not self._ollama_client:
            return self._generate_template_prompt(field, user_message)

        try:
            # Build context
            context = ""
            if conversation_history:
                recent = conversation_history[-6:]  # Last 3 exchanges
                for msg in recent:
                    role = "Bot" if msg['role'] == 'assistant' else "User"
                    content = msg['content'][:150]
                    context += f"{role}: {content}\n"

            field_descriptions = {
                'name': 'their name (to personalize the conversation)',
                'email': 'their work email (to send detailed information and resources)',
                'phone': 'their phone number (for callback or demo scheduling)'
            }

            system_prompt = f"""You are a friendly, professional assistant for Market Inside Data (trade intelligence platform).

CONVERSATION CONTEXT:
{context}
User's latest: "{user_message}"
Bot's response: "{bot_response[:200]}..."

YOUR TASK: Generate a natural, conversational prompt to ask for {field_descriptions.get(field, field)}.

REQUIREMENTS:
1. Be warm, friendly, and professional
2. Reference the conversation context naturally
3. Explain briefly WHY you need this info (value for the user)
4. Keep it SHORT (1 sentence, max 20 words)
5. Make it feel human, not scripted or robotic
6. Match the user's communication style

EXAMPLES:
- "To send you that pricing breakdown, what's your work email?"
- "I'd love to personalize this - may I know your name?"
- "For a quick callback about the demo, what number works best?"

Generate ONLY the prompt (no quotes, no explanation):"""

            response = await self._call_llm_with_timeout(
                model='qwen3.5:cloud',
                messages=[{'role': 'user', 'content': system_prompt}],
                options={
                    'temperature': 0.7,  # Creative for natural variation
                    'num_predict': 60,
                    'thinking': False
                },
                timeout=10.0
            )

            if not response:
                return self._generate_template_prompt(field, user_message)

            prompt = response['message'].get('content', '').strip()
            if not prompt and 'thinking' in response['message']:
                prompt = response['message']['thinking'].strip()

            # Clean up
            prompt = prompt.strip('"\'')
            if '\n' in prompt:
                lines = [l.strip() for l in prompt.split('\n') if l.strip()]
                for line in reversed(lines):
                    if '?' in line and 10 < len(line) < 150:
                        prompt = line.strip('"\'')
                        break

            # Validate
            if 10 < len(prompt) < 150 and ('?' in prompt or 'please' in prompt.lower()):
                return prompt

            # Fallback to template
            return self._generate_template_prompt(field, user_message)

        except Exception as e:
            print(f"[LLM_COLLECTOR] ❌ Intelligent prompt error: {e}")
            return self._generate_template_prompt(field, user_message)

    async def _generate_contextual_prompt(
        self,
        field: str,
        user_message: str,
        bot_response: str,
        conversation_history: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        INTELLIGENT LLM-driven prompt generation with FULL conversation context.

        The LLM analyzes the conversation to decide:
        1. Should we ask right now? (or skip if user just said "yes"/"no" to something else)
        2. If yes, what's the most natural way to ask given the context?
        3. How to handle affirmations ("Thanks for confirmation! Could you share...?")
        4. How to handle negations (skip gracefully or wait)

        Returns: Prompt string OR None (if LLM decides not to ask now)
        """
        if not self._ollama_client:
            # Fallback to template if no LLM
            return self._generate_template_prompt(field, user_message)

        # Define what we're asking for
        field_descriptions = {
            'name': 'their name',
            'email': 'their work email address',
            'phone': 'their phone number'
        }

        # Build conversation context (last 4 exchanges for better understanding)
        context = ""
        if conversation_history:
            recent = conversation_history[-8:]  # Last 4 exchanges
            for msg in recent:
                role = "Bot" if msg['role'] == 'assistant' else "User"
                content = msg['content'][:200]
                context += f"{role}: {content}\n"

        # Add current exchange
        context += f"Bot: {bot_response[:200]}\nUser: {user_message}\n"

        # INTELLIGENT LLM prompt that understands context
        system_prompt = f"""You are an intelligent assistant for Market Inside Data. Analyze the FULL conversation to decide how to ask for {field_descriptions.get(field, field)}.

CONVERSATION HISTORY:
{context}

CRITICAL ANALYSIS - What is the user responding to?
1. Look at the MOST RECENT bot message (the one right before user's response)
2. Determine what question the user is answering

SCENARIO HANDLING:

IF bot just asked "Could you share your name?" AND user said "yes"/"sure"/"okay":
→ User is confirming they're WILLING to share
→ Acknowledge confirmation + ask for ACTUAL {field}
→ Response: "Great! Thanks for confirming. What's your {field}?"

IF bot just asked "Was this helpful?" AND user said "yes":
→ User is answering THAT question (not about sharing {field})
→ Don't ask for {field} yet - return "SKIP"

IF bot asked about {field} AND user said "no"/"not now":
→ User declined
→ Return exactly "SKIP"

IF user asked a substantive question (>5 words):
→ Ask naturally: "I'd love to help! To personalize this, could you share {field_descriptions.get(field, field)}?"

RULES:
- SHORT responses (1-2 words like "yes", "no", "sure") are answers to the MOST RECENT bot question
- Check what the bot asked LAST to understand user's answer
- If asking for {field} is appropriate, be warm and natural (max 25 words)
- If not appropriate right now, return exactly "SKIP"

OUTPUT:
- The prompt text (if asking is appropriate)
- OR "SKIP" (if not appropriate now)

Your response:"""

        try:
            # Add timeout to prevent hanging (max 10 seconds)
            import asyncio
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._ollama_client.chat,
                        model='qwen3.5:cloud',
                        messages=[{'role': 'user', 'content': system_prompt}],
                        options={
                            'temperature': 0.7,
                            'num_predict': 100,
                            'thinking': False
                        }
                    ),
                    timeout=10.0  # 10 second timeout
                )
            except asyncio.TimeoutError:
                print(f"[LLM_COLLECTOR] ⏱️ LLM prompt generation timed out after 10s - using fallback")
                return self._generate_template_prompt(field, user_message)

            generated = response['message'].get('content', '').strip()

            # Check if LLM decided to skip
            if 'SKIP' in generated.upper() or len(generated) < 10:
                print(f"[LLM_COLLECTOR] ⚡ LLM decided to skip asking for '{field}' (context: '{user_message}')")
                return None

            # Clean up response
            generated = generated.strip('"\'')

            # Extract just the prompt if there's extra text
            if '\n' in generated:
                lines = [l.strip() for l in generated.split('\n') if l.strip()]
                for line in reversed(lines):
                    if '?' in line and len(line) > 15:
                        generated = line.strip('"\'')
                        break

            # Validate prompt
            if len(generated) > 15 and len(generated) < 200:
                print(f"[LLM_COLLECTOR] ✓ LLM generated contextual prompt: {generated[:60]}...")
                return generated

            return None

        except Exception as e:
            print(f"[LLM_COLLECTOR] Contextual prompt error: {e}, using fallback")
            return self._generate_template_prompt(field, user_message)

    async def _generate_llm_prompt(
        self,
        field: str,
        bot_response: str,
        user_message: str
    ) -> Optional[str]:
        """
        Use LLM to generate a personalized prompt based on conversation context.
        (Legacy function - kept for backward compatibility)
        """

        # Define what we're asking for
        field_descriptions = {
            'name': 'their name',
            'email': 'their work email address',
            'phone': 'their phone number',
            'requirements': 'what specific trade data or services they are interested in'
        }

        # Build context-aware LLM prompt
        system_prompt = f"""You are a friendly, professional sales assistant for Market Inside Data (global trade intelligence platform).

Generate a polite, conversational prompt to ask the user for {field_descriptions.get(field, field)}.

Guidelines:
1. Use phrases like "To make this conversation more personalized, could you please..."
2. Explain WHY you need the information (to help them better, send details, etc.)
3. Match the tone of the conversation (if user is formal, be formal; if casual, be friendly)
4. Keep it ONE sentence, maximum 25 words
5. Be warm and welcoming, never pushy
6. Reference the conversation context naturally

User's last message: "{user_message}"
Bot's last response: "{bot_response[:200]}..."

Generate ONLY the prompt text (no quotes, no explanation):"""

        try:
            response = await self._call_llm_with_timeout(
                model='qwen3.5:cloud',  # Cloud model (same as main)
                messages=[{'role': 'user', 'content': system_prompt}],
                options={
                    'temperature': 0.7,  # Creative but controlled
                    'num_predict': 100,  # Increased for qwen
                    'thinking': False  # Disable thinking output
                },
                timeout=10.0
            )

            if not response:
                print(f"[LLM_COLLECTOR] Prompt generation timed out")
                return None

            # Handle models that put output in 'thinking' field
            generated_prompt = response['message'].get('content', '').strip()
            if not generated_prompt and 'thinking' in response['message']:
                generated_prompt = response['message']['thinking'].strip()

            # Clean up response (remove quotes if present)
            generated_prompt = generated_prompt.strip('"\'')

            # Extract just the prompt if there's thinking text
            if generated_prompt and '\n' in generated_prompt:
                # Take last line that looks like a question
                lines = [l.strip() for l in generated_prompt.split('\n') if l.strip()]
                for line in reversed(lines):
                    if '?' in line and len(line) > 15:
                        generated_prompt = line.strip('"\'')
                        break

            # Validate prompt (basic checks)
            if (len(generated_prompt) > 15 and
                len(generated_prompt) < 200 and
                ('?' in generated_prompt or 'please' in generated_prompt.lower())):

                print(f"[LLM_COLLECTOR] [OK] Generated prompt for {field}: {generated_prompt[:60]}...")
                return generated_prompt

            return None

        except Exception as e:
            print(f"[LLM_COLLECTOR] LLM prompt generation error: {e}")
            return None

    def _generate_template_prompt(self, field: str, user_message: str) -> str:
        """
        Simple fallback template-based prompts (used if LLM fails).
        No manual affirmation checking - LLM should handle that.
        """

        user_lower = user_message.lower()

        # Template prompts (fallback)
        prompts = {
            'name': {
                'pricing': "To provide you with accurate pricing details, could you please share your name?",
                'demo': "I'd be happy to arrange a personalized demo for you. Could you please share your name?",
                'data': "I'd love to help you with that data. To make this conversation more personalized, could you please share your name?",
                'default': "To make this conversation more personalized, could you please share your name?"
            },
            'requirements': {
                'data': "To better assist you, could you please tell me what specific trade data you're looking for?",
                'pricing': "To recommend the right plan for you, could you share what type of data access you need - web platform, API, or data license?",
                'service': "I'd love to help! Could you please share what you're hoping to accomplish with our global trade intelligence?",
                'help': "I'm here to help! Could you please tell me what brings you to Market Inside Data today?",
                'default': "To provide you with the most relevant information, could you please share what type of trade intelligence data you're interested in?"
            },
            'email': {
                'send': "I'd be happy to send that to you. Could you please share your email address?",
                'report': "I can email you a detailed report. Could you please provide your email address?",
                'information': "I'd be happy to send you more information. May I have your email address?",
                'default': "To send you detailed information, could you please share your work email address?"
            },
            'phone': {
                'demo': "For a personalized demo, could you please share the best number to reach you?",
                'call': "I'd be happy to arrange a callback. Could you please provide your phone number?",
                'default': "In case we need to reach you, could you please share your phone number?"
            }
        }

        # Detect context
        if 'price' in user_lower or 'pricing' in user_lower:
            context = 'pricing'
        elif 'demo' in user_lower:
            context = 'demo'
        elif 'send' in user_lower or 'email' in user_lower:
            context = 'send'
        elif 'report' in user_lower or 'analysis' in user_lower:
            context = 'report'
        elif 'information' in user_lower or 'details' in user_lower:
            context = 'information'
        elif 'data' in user_lower or 'trade' in user_lower:
            context = 'data'
        elif 'service' in user_lower or 'platform' in user_lower:
            context = 'service'
        elif 'help' in user_lower or 'need' in user_lower:
            context = 'help'
        elif 'call' in user_lower or 'phone' in user_lower:
            context = 'call'
        else:
            context = 'default'

        return prompts.get(field, {}).get(context, prompts[field]['default'])

    async def _extract_and_save_background(
        self,
        session_id: str,
        user_message: str,
        missing_fields: List[str],
        conversation_history: Optional[List[Dict[str, str]]] = None
    ):
        """
        OPTIMIZED: Extract and save user info in one pass.

        Performance improvements:
        1. Use provided conversation_history to avoid Redis fetch
        2. Skip redundant detection call
        3. Go straight to extraction
        """

        extracted = {}

        # Get current user info for context-aware extraction
        current_info = await self._get_user_info_fast(session_id)

        # Get conversation history (use provided or fetch)
        messages = conversation_history if conversation_history else self.redis.get_conversation(session_id)

        # ALWAYS try to extract name (allows updates like "pulkit" -> "pulkit ujjainwal")
        # Use LLM ONLY for name extraction (no regex fallback)
        # Regex is unreliable and causes false positives like "Looking For"
        name = await self._extract_name_llm(user_message, messages)

        # Trust LLM result - if LLM says no name, don't use unreliable regex

        if name:
            # Check if this is an UPDATE (better/more complete name)
            current_name = current_info.get('name')
            if current_name:
                # Update if new name is more complete (has more words)
                current_parts = current_name.split()
                new_parts = name.split()
                if len(new_parts) > len(current_parts):
                    print(f"[LLM_COLLECTOR] * Updating name: '{current_name}' → '{name}'")
                    extracted['name'] = name
                else:
                    print(f"[LLM_COLLECTOR] Name already complete: '{current_name}', ignoring '{name}'")
            else:
                # New name
                extracted['name'] = name
                print(f"[LLM_COLLECTOR] * Extracted new name: '{name}'")

        # Extract email (only if missing - email doesn't need updates)
        if 'email' in missing_fields:
            import re
            pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            match = re.search(pattern, user_message)
            if match:
                email = match.group(0).lower()

                # Validate email (block disposable/temporary emails)
                validator = get_email_validator()
                is_valid, email_type, message = validator.validate_email(email)

                if is_valid and email_type != "disposable":
                    extracted['email'] = email
                    print(f"[LLM_COLLECTOR] [VALID] Email validated: {email} (type: {email_type})")
                else:
                    # Disposable email detected - cache rejection to inform user on next message
                    rejection_key = f"email_rejected:{session_id}"
                    self._cache[rejection_key] = {
                        'email': email,
                        'reason': 'disposable',
                        'message': 'We noticed you used a temporary email. Please provide your work email for better service.'
                    }
                    print(f"[LLM_COLLECTOR] [BLOCKED] Email rejected: {email} (type: {email_type}) - {message[:80]}...")
                    print(f"[LLM_COLLECTOR] [WARN] Will notify user on next message")

        # Extract phone (only if missing - phone doesn't need updates)
        if 'phone' in missing_fields:
            import re
            pattern = r'\+?\d[\d\s\-()]{8,}\d'
            match = re.search(pattern, user_message)
            if match:
                phone = re.sub(r'[^\d+]', '', match.group(0))
                if len(phone) >= 10:
                    extracted['phone'] = phone

        # ALWAYS try to extract requirements (can be updated/refined)
        requirement = await self._extract_requirements_llm_smart(user_message, current_info, messages)
        if requirement:
            extracted['requirements'] = requirement

        # Save extracted info
        if extracted:
            print(f"[COLLECTOR_INTERNAL] About to save: {extracted}")
            try:
                await self._save_extracted_info(session_id, extracted)
                print(f"[COLLECTOR_INTERNAL] Save completed successfully")
            except Exception as e:
                print(f"[COLLECTOR_INTERNAL] [ERROR] Save failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[COLLECTOR_INTERNAL] No extracted info to save")

    async def _get_user_info_fast(self, session_id: str) -> Dict[str, Any]:
        """Fast get user info (uses Redis cache)"""
        print(f"[COLLECTOR_INTERNAL] _get_user_info_fast for session: {session_id}")

        # Try Redis first (super fast)
        redis_key = f"user_info:{session_id}"
        cached = self.redis.client.get(redis_key)
        print(f"[COLLECTOR_INTERNAL] Redis cache result: {cached is not None}")

        if cached:
            try:
                data = json.loads(cached)

                # Validate name - filter out greetings/invalid names
                name = data.get('name')
                if name and not self._is_valid_name(name):
                    print(f"[COLLECTOR_INTERNAL] Filtered out invalid name from cache: '{name}'")
                    name = None  # Treat as missing

                result = {
                    'name': name,
                    'email': data.get('email'),
                    'phone': data.get('phone'),
                    'requirements': data.get('requirements')
                }
                print(f"[COLLECTOR_INTERNAL] From Redis: {result}")
                return result
            except Exception as e:
                print(f"[COLLECTOR_INTERNAL] Redis parse error: {e}")

        # Fallback to DB
        print(f"[COLLECTOR_INTERNAL] Checking database...")
        info = await self.db_service.get_user_info(session_id)
        if info:
            # Validate name - filter out greetings/invalid names
            name = info.get('name')
            if name and not self._is_valid_name(name):
                print(f"[COLLECTOR_INTERNAL] Filtered out invalid name: '{name}' (greeting/invalid)")
                name = None  # Treat as missing

            result = {
                'name': name,
                'email': info.get('email'),
                'phone': info.get('phone'),
                'requirements': info.get('requirements')
            }
            print(f"[COLLECTOR_INTERNAL] From DB: {result}")
            return result

        print(f"[COLLECTOR_INTERNAL] No user info found, returning empty")
        return {'name': None, 'email': None, 'phone': None, 'requirements': None}

    def _is_valid_name(self, name: str) -> bool:
        """
        Validate if a name is legitimate (not a greeting or invalid input).

        Returns True if name is valid, False if it's a greeting/invalid.
        """
        if not name or not isinstance(name, str):
            return False

        name_lower = name.strip().lower()

        # Comprehensive blocklist
        invalid_names = {
            # Greetings
            'hi', 'hello', 'hey', 'hola', 'howdy', 'greetings',
            'good morning', 'good afternoon', 'good evening', 'good night',
            'morning', 'afternoon', 'evening', 'night',

            # Common responses
            'yes', 'no', 'ok', 'okay', 'sure', 'nope', 'yep', 'yeah', 'nah',
            'thanks', 'thank you', 'please', 'sorry', 'excuse me',

            # Test/Demo
            'test', 'testing', 'demo', 'sample', 'example',
            'asdf', 'qwerty', 'abc', 'xyz', 'foo', 'bar', 'user',

            # Common words
            'help', 'info', 'information', 'data', 'pricing', 'price',

            # Common country names (prevent "indonesia" mistake)
            'united kingdom', 'indonesia', 'china', 'japan', 'korea', 'brazil', 'mexico',
            'germany', 'france', 'italy', 'spain', 'russia', 'canada', 'australia',
            'singapore', 'thailand', 'vietnam', 'malaysia', 'philippines',
            'usa', 'uk', 'uae', 'pakistan', 'bangladesh', 'turkey', 'egypt',

            # Common business terms
            'company', 'business', 'enterprise', 'corporation', 'limited',
            'import', 'export', 'trade', 'supplier', 'buyer', 'vendor',

            # Query patterns (prevent extracting user queries as names)
            'general', 'overview', 'phones', 'used phones', 'data for',
            'tell me', 'show me', 'find', 'search', 'get', 'about',
            'looking for', 'looking in', 'intrested in', 'interested in'
        }

        # Validation checks
        if (name_lower in invalid_names or  # In blocklist
            len(name.strip()) < 2 or  # Too short
            len(name.strip()) > 50 or  # Too long (likely a query)
            name.isdigit() or  # Just numbers
            not any(c.isalpha() for c in name) or  # No letters
            name.count(' ') > 5):  # Too many words (likely a query)
            return False

        # Check if it looks like a query (contains common query words)
        query_keywords = ['import', 'export', 'overview', 'data', 'about', 'tell', 'show', 'find', 'search', 'get', 'for', 'in', 'the', 'used', 'phones', 'general', 'looking', 'intrested', 'interested']
        word_count = len(name.split())
        query_word_count = sum(1 for word in name.lower().split() if word in query_keywords)

        # If more than 30% of words are query keywords, it's likely a query, not a name
        # Changed from > 2 to >= 2 to catch 2-word invalid names like "Looking For"
        if word_count >= 2 and (query_word_count / word_count) > 0.3:
            return False

        return True

    def _get_missing_fields(self, user_info: Dict[str, Any]) -> List[str]:
        """Determine missing fields"""
        missing = []

        # Priority 1: Name (must have)
        # Validate name is not a greeting/invalid
        name = user_info.get('name')
        if not name or not self._is_valid_name(name):
            missing.append('name')

        # Priority 2: Email OR Phone (at least one contact method)
        if not user_info.get('email'):
            missing.append('email')
        if not user_info.get('phone'):
            missing.append('phone')

        # Priority 3: Requirements (ask after we have contact info)
        if not user_info.get('requirements'):
            missing.append('requirements')

        return missing

    def _is_out_of_scope_response(self, bot_response: str) -> bool:
        """
        Detect if bot couldn't provide specific help (e.g., said "Sorry").

        Returns True if bot response indicates unavailable data or out-of-scope query.
        """
        bot_lower = bot_response.lower()

        # Strong patterns that definitively indicate bot couldn't help
        # These are reliable indicators even if "sorry" appears
        strong_patterns = [
            "i can only answer",
            "i can't",
            "i don't have",
            "unavailable",
            "out of scope",
            "not in my knowledge",
            "unable to help",
            "unable to provide",
            "don't have access",
            "cannot answer"
        ]

        # Check strong patterns first
        if any(pattern in bot_lower for pattern in strong_patterns):
            return True

        # Check for "sorry" but only if NOT in a polite/helpful context
        # (e.g., "sorry for the delay" while still providing help)
        if 'sorry' in bot_lower:
            # Exclude polite apologies that still provide help
            polite_contexts = [
                'sorry for the delay',
                'sorry for the wait',
                'sorry about that',
                'sorry to hear',
                'sorry for any confusion'
            ]

            # If "sorry" appears with helpful context, it's NOT out-of-scope
            if any(ctx in bot_lower for ctx in polite_contexts):
                return False

            # Otherwise, "sorry" likely means couldn't help
            return True

        return False

    def _generate_generic_prompt(self, field: str) -> str:
        """
        Generate simple, generic prompts when bot couldn't help with specific query.

        These prompts DON'T reference the unavailable data/topic.
        """
        generic_prompts = {
            'name': "To make this conversation more personalized, could you please share your name?",
            'email': "To send you relevant information in the future, may I have your email address?",
            'phone': "Would you like to provide a contact number for future assistance?",
            'requirements': "To better understand how I can help you, could you share what you're looking for?"
        }

        return generic_prompts.get(field, generic_prompts['name'])

    async def _extract_name_llm(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        Use LLM to intelligently extract user's name from message with conversation context.

        This prevents false positives like treating "indonesia" (country name) as a person's name.
        Returns extracted name or None if not found.
        """
        if not self._ollama_client:
            # Fallback to simple regex if no LLM
            return self._extract_name_regex_fallback(user_message)

        try:
            # Build context from last 3 messages
            context = ""
            if conversation_history:
                recent = conversation_history[-6:]  # Last 3 exchanges
                for msg in recent:
                    role = "User" if msg['role'] == 'user' else "Bot"
                    context += f"{role}: {msg['content'][:100]}\n"

            prompt = f"""Extract the user's personal name from this conversation.

Conversation:
{context}

Latest message: "{user_message}"

Extract ONLY personal names (e.g., "John Smith", "Sarah", "Alex").
DO NOT extract: country names, company names, greetings, products.

Return ONLY the name in Title Case, or "none" if not found.

Your response:"""

            response = await self._call_llm_with_timeout(
                model='qwen3.5:cloud',  # Cloud model (same as main)
                messages=[{'role': 'user', 'content': prompt}],
                options={
                    'temperature': 0.0,  # Deterministic for consistent extraction
                    'num_predict': 30,  # Names are very short, reduced for speed
                    'thinking': False,  # Disable thinking output
                    'num_ctx': 1024  # Reduced context for faster processing
                },
                timeout=10.0  # 10 second timeout
            )

            if not response:
                print(f"[LLM_COLLECTOR] Name extraction timed out or failed")
                # Fallback to regex for explicit patterns like "my name is X"
                return self._extract_name_regex_explicit(user_message)

            # Handle models that put output in 'thinking' field
            raw_response = response['message'].get('content', '').strip()
            if not raw_response and 'thinking' in response['message']:
                raw_response = response['message']['thinking'].strip()

            # DEBUG: Log the actual LLM response
            print(f"[LLM_COLLECTOR] [DEBUG] Raw LLM response: '{raw_response[:200]}'")

            # ROBUST: Extract actual answer from thinking text
            name = self._extract_answer_from_thinking(raw_response, expected_type='name')

            if not name:
                print(f"[LLM_COLLECTOR] No name found in parsed LLM response, trying regex fallback")
                # Try explicit regex patterns as safety net
                name = self._extract_name_regex_explicit(user_message)
                if name:
                    print(f"[LLM_COLLECTOR] [OK] Regex fallback extracted: {name}")
                    return name.title()
                return None

            # Clean up extracted name
            name = name.strip('"\'.,!')

            # If multi-line, try to extract a clean name
            if name and '\n' in name:
                # Take first line that looks like a proper name
                for line in name.split('\n'):
                    line = line.strip('"\'.,!-*# ')
                    if (line and 2 <= len(line) <= 50 and
                        any(c.isalpha() for c in line) and
                        not any(ind in line.lower() for ind in thinking_indicators)):
                        name = line
                        break

            # Validate result
            if (name.lower() in ['none', 'n/a', 'not found', 'no name', 'unclear'] or
                len(name) < 2 or
                len(name) > 100 or
                not any(c.isalpha() for c in name) or
                any(indicator in name.lower() for indicator in thinking_indicators)):
                return None

            # Additional validation - block if it looks like a greeting or invalid
            if not self._is_valid_name(name):
                print(f"[LLM_COLLECTOR] LLM extracted invalid name: '{name}' - rejected")
                return None

            print(f"[LLM_COLLECTOR] [OK] Extracted name via LLM: {name}")
            return name.title()

        except Exception as e:
            print(f"[LLM_COLLECTOR] LLM name extraction failed: {e}")
            # Don't use regex fallback - it's unreliable
            return None

    def _extract_answer_from_thinking(self, text: str, expected_type: str = 'text') -> Optional[str]:
        """
        CRITICAL FIX: Extract actual answer from thinking text.

        LLM may return thinking process despite instructions.
        This extracts the actual answer from patterns like:
        "Thinking Process: ... Output: [ANSWER]"
        "Answer: [ANSWER]"
        "Result: [ANSWER]"
        """
        if not text:
            return None

        # Remove markdown formatting
        text = re.sub(r'\*\*|\`\`\`', '', text)
        text_lower = text.lower()

        # Pattern 1: Look for "Output:", "Answer:", "Result:" followed by content
        answer_patterns = [
            r'(?:output|answer|result|response):\s*([^\n]+)',
            r'(?:extracted|final)\s+(?:name|requirement):\s*([^\n]+)',
            r'\*\*(?:Output|Answer|Result):\*\*\s*([^\n]+)',
        ]

        for pattern in answer_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                answer = match.group(1).strip().strip('"\'.,*-#')
                if answer and answer.lower() not in ['none', 'n/a', 'not found']:
                    return answer

        # Pattern 2: For name extraction, if response is very short and clean, use it directly
        if expected_type == 'name':
            text_stripped = text.strip().strip('"\'.,*-#')
            # If it's a single word or two words (name), and no thinking indicators, use it
            if (2 <= len(text_stripped) <= 50 and
                text_stripped.count('\n') == 0 and
                text_stripped.count(' ') <= 3 and
                not any(ind in text_lower for ind in ['thinking', 'analyze', 'extract', 'input:', 'output:', 'step', 'rule', 'context', 'task:'])):
                # Looks like a clean name response
                if text_stripped.lower() not in ['none', 'n/a', 'not found', 'unclear', 'no name']:
                    print(f"[LLM_COLLECTOR] [DEBUG] Using direct response as name: '{text_stripped}'")
                    return text_stripped

        # Pattern 3: If no markers, take last line that doesn't look like thinking
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        thinking_indicators = [
            'thinking', 'analyze', 'request', 'input:', 'step', 'rule',
            'context', 'task:', 'note:', 'explanation:', '1.', '2.', '3.',
            'conclusion', '**', 'process:', 'extract'
        ]

        for line in reversed(lines):
            line_clean = line.strip('"\'.,*-#')
            # Skip thinking lines
            if any(indicator in line.lower() for indicator in thinking_indicators):
                continue
            # Skip very short or very long lines
            if len(line_clean) < 2 or len(line_clean) > 200:
                continue
            # Skip lines that are just punctuation
            if not any(c.isalnum() for c in line_clean):
                continue
            # Found potential answer
            if line_clean.lower() not in ['none', 'n/a', 'not found', 'unclear']:
                return line_clean

        return None

    def _extract_name_regex_explicit(self, user_message: str) -> Optional[str]:
        """
        SAFE regex extraction for EXPLICIT name patterns only.

        Only matches clear patterns like:
        - "my name is John"
        - "I'm Sarah"
        - "call me Alex"

        Does NOT match ambiguous patterns that cause false positives.
        """
        import re

        # Only explicit name introduction patterns
        explicit_patterns = [
            r"(?:my name is|my name's)\s+([a-z]+(?:\s+[a-z]+)?)",
            r"(?:i'm|i am)\s+([a-z]+)\s*(?:\.|!|$)",
            r"(?:call me|this is)\s+([a-z]+(?:\s+[a-z]+)?)",
        ]

        for pattern in explicit_patterns:
            match = re.search(pattern, user_message.lower())
            if match:
                name = match.group(1).strip().title()
                # Validate it's a reasonable name
                if self._is_valid_name(name) and len(name) >= 2:
                    print(f"[LLM_COLLECTOR] [OK] Regex explicit pattern matched: {name}")
                    return name

        return None

    def _extract_name_regex_fallback(self, user_message: str) -> Optional[str]:
        """
        Fallback regex-based name extraction (used if LLM unavailable).
        Matches explicit name patterns OR simple capitalized words (likely names).
        """
        import re

        # Pattern 1: EXPLICIT name patterns (highest confidence)
        explicit_patterns = [
            r"(?:my name is|i'm|i am|call me|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        ]

        for pattern in explicit_patterns:
            match = re.search(pattern, user_message, re.IGNORECASE)
            if match:
                name = match.group(1).strip().title()
                if self._is_valid_name(name):
                    print(f"[LLM_COLLECTOR] [OK] Extracted name via regex (explicit): {name}")
                    return name

        # Pattern 2: Simple capitalized word or short alphabetic name (likely a direct answer)
        # Match: "Pulkit", "John Smith", "Sarah" etc.
        message_stripped = user_message.strip()
        if (2 <= len(message_stripped) <= 50 and
            (message_stripped[0].isupper() or message_stripped.isalpha()) and
            sum(c.isalpha() or c.isspace() for c in message_stripped) / len(message_stripped) > 0.8):

            # Extract just the name part (remove punctuation)
            name = re.sub(r'[^\w\s]', '', message_stripped).strip().title()
            if name and self._is_valid_name(name):
                print(f"[LLM_COLLECTOR] [OK] Extracted name via regex (simple): {name}")
                return name

        return None

    async def _extract_requirements_llm_smart(
        self,
        user_message: str,
        current_info: Dict[str, Any],
        conversation_history: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        NEXT-LEVEL intent-based requirement extraction.

        Uses conversation history AND chatbot intents to intelligently build requirements.
        Combines multiple interactions into a comprehensive requirement profile.
        """
        if not self._ollama_client:
            return await self._extract_requirements_llm(user_message)

        try:
            # Build conversation context (last 10 messages)
            context = ""
            if conversation_history:
                recent = conversation_history[-10:]
                for msg in recent:
                    role = "User" if msg['role'] == 'user' else "Bot"
                    content = msg['content'][:150]
                    context += f"{role}: {content}\n"

            # Get current requirements if exists
            current_req = current_info.get('requirements', '')

            # SIMPLE PROMPT - Avoid complex instructions that models echo back
            prompt = f"""User said: "{user_message}"

What trade data do they want? Write it in 1 sentence.

Examples:
- Mobile phone shipments for USA
- Indonesia detailed import data
- Iran import statistics

Your answer:"""

            response = await self._call_llm_with_timeout(
                model='qwen3.5:cloud',  # Cloud model (same as main)
                messages=[{'role': 'user', 'content': prompt}],
                options={
                    'temperature': 0.3,  # Moderate for natural responses
                    'num_predict': 50,  # Short answer expected
                    'thinking': False  # Disable thinking output
                },
                timeout=10.0
            )

            if not response:
                print(f"[LLM_COLLECTOR] Requirements extraction timed out")
                return None

            # Handle models that put output in 'thinking' field
            raw_response = response['message'].get('content', '').strip()
            if not raw_response and 'thinking' in response['message']:
                raw_response = response['message']['thinking'].strip()

            # ROBUST EXTRACTION: Handle various response formats
            requirement = None

            # Remove common prefixes/suffixes from response
            clean_response = raw_response
            for prefix in ['answer:', 'requirement:', 'your answer:', 'response:', 'output:']:
                if clean_response.lower().startswith(prefix):
                    clean_response = clean_response[len(prefix):].strip()
                    break

            # Take first line if multi-line
            if '\n' in clean_response:
                lines = [l.strip() for l in clean_response.split('\n') if l.strip()]
                # Find first line that doesn't look like instructions
                for line in lines:
                    if (len(line) > 10 and
                        not line.lower().startswith(('example', 'note:', 'constraint', 'return', 'write'))):
                        requirement = line
                        break
                if not requirement and lines:
                    requirement = lines[0]
            else:
                requirement = clean_response

            if not requirement:
                return None

            # Clean up requirement
            requirement = requirement.strip('"\'.-*# ')

            # CRITICAL: Filter out meta-text and thinking patterns
            meta_text_indicators = [
                'thinking process', 'analyze', 'input:', 'output:',
                'task:', 'step 1', 'step 2', 'conclusion:', 'analysis:',
                'conversation history', 'current message', 'prompt', 'context',
                'return only', 'examples provided', 'constraint', 'goal:',
                'your response', 'format:', 'rules:', 'extract from', 'instruction',
                'user message:', 'bot:', 'assistant:', 'current:', 'latest:',
                'user:', '-> ', 'formulate', 'max 2 sentences', 'write it in'
            ]

            # Final validation - ensure it's not meta-text or echoed instructions
            requirement_lower = requirement.lower()
            if any(indicator in requirement_lower for indicator in meta_text_indicators):
                print(f"[LLM_COLLECTOR] [BLOCKED] Meta-text in requirement: {requirement[:100]}...")
                return None

            # Block if starts with common instruction words
            if any(requirement_lower.startswith(word) for word in ['example', 'note', 'constraint', 'return', 'write', 'extract', 'user said']):
                print(f"[LLM_COLLECTOR] [BLOCKED] Instruction-like requirement: {requirement[:100]}...")
                return None

            # CRITICAL: Block truncated/incomplete requirements
            if (requirement.endswith('->') or
                requirement.endswith('a') or
                len(requirement.split()[-1]) < 3):
                print(f"[LLM_COLLECTOR] [BLOCKED] Truncated requirement: {requirement}")
                return None

            # Additional validation: Must contain trade-related keywords or be a meaningful request
            # Block generic phrases that aren't actual requirements
            invalid_requirements = [
                'none', 'n/a', 'no requirement', 'unclear', 'no data need',
                'general', 'overview', 'information', 'details', 'help', 'examples',
                'conversation', 'message', 'greeting', 'hi', 'hello'
            ]

            requirement_lower = requirement.lower().strip()
            if requirement_lower in invalid_requirements or len(requirement_lower.split()) <= 2:
                print(f"[LLM_COLLECTOR] [BLOCKED] Invalid/generic requirement: {requirement}")
                return None

            # Must be substantial (more than 15 chars but not too long)
            if len(requirement) > 15 and len(requirement) < 500:
                if current_req and current_req != requirement:
                    print(f"[LLM_COLLECTOR] * UPDATED requirement: {requirement[:120]}...")
                else:
                    print(f"[LLM_COLLECTOR] [OK] Extracted requirement: {requirement[:120]}...")
                return requirement

            print(f"[LLM_COLLECTOR] [BLOCKED] Requirement too short ({len(requirement)} chars), trying keyword fallback")

            # FALLBACK: Extract keywords from user's actual message
            return self._extract_requirement_from_keywords(user_message, conversation_history)

        except Exception as e:
            print(f"[LLM_COLLECTOR] Smart requirements extraction failed: {e}, using keyword fallback")
            return self._extract_requirement_from_keywords(user_message, conversation_history)

    def _extract_requirement_from_keywords(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Optional[str]:
        """
        FALLBACK: Extract requirements from keywords when LLM fails.

        Looks for trade-related terms in user message and recent conversation.
        """
        # Combine user message with recent queries
        text = user_message.lower()

        if conversation_history:
            recent = conversation_history[-3:]  # Last 3 messages
            for msg in recent:
                if msg.get('role') == 'user':
                    text += " " + msg['content'].lower()

        # Extract key trade terms
        countries = []
        products = []
        directions = []

        # Country keywords
        country_patterns = [
            r'\b(usa|united states|america|china|united kingdom|indonesia|brazil|germany|japan|uk|france|canada|mexico|australia|korea|vietnam|thailand|singapore|malaysia|philippines|taiwan|hong kong|russia|iran|iraq|turkey|egypt|saudi arabia|uae|south africa|nigeria|kenya|argentina|chile|peru|colombia)\b'
        ]

        for pattern in country_patterns:
            matches = re.findall(pattern, text)
            countries.extend(matches)

        # Product keywords
        if re.search(r'\b(mobile|phone|smartphone|electronics|machinery|computer|textile|apparel|garment|steel|iron|chemical|automotive|vehicle|car|food|grain|wheat|rice|oil|petroleum|coal|furniture|plastic|rubber)\b', text):
            products = re.findall(r'\b(mobile phone|smartphone|electronics|machinery|computer|textile|apparel|garment|steel|iron|chemical|automotive|vehicle|car|food|grain|wheat|rice|oil|petroleum|coal|furniture|plastic|rubber)\b', text)

        # Direction keywords
        if re.search(r'\b(import|export|shipment|trade)\b', text):
            if 'export' in text:
                directions.append('export')
            else:
                directions.append('import')

        # Build requirement string
        parts = []
        if products:
            parts.append(products[0].title())
        if directions:
            parts.append(directions[0])
        if countries:
            parts.append(f"for {countries[0].upper()}")

        if parts:
            requirement = " ".join(parts) + " data"
            if len(requirement) > 15:
                print(f"[LLM_COLLECTOR] [FALLBACK] Keyword-based requirement: {requirement}")
                return requirement

        # Last resort: use user message if it contains trade terms
        trade_keywords = ['shipment', 'trade', 'import', 'export', 'data', 'statistics', 'detailed']
        if any(kw in text for kw in trade_keywords):
            requirement = user_message[:100]  # First 100 chars
            if len(requirement) > 15:
                print(f"[LLM_COLLECTOR] [FALLBACK] User message as requirement: {requirement}")
                return requirement

        return None

    async def _extract_requirements_llm(self, user_message: str) -> Optional[str]:
        """
        Fallback: Use LLM to extract user requirements from current message only.

        Returns structured requirement string or None if not found.
        """
        if not self._ollama_client:
            # Fallback: try simple keyword detection
            keywords = ['need', 'want', 'looking for', 'interested in', 'require',
                       'import', 'export', 'data', 'shipment', 'trade', 'customs']
            if any(kw in user_message.lower() for kw in keywords):
                return user_message[:200]  # Save first 200 chars as requirement
            return None

        try:
            prompt = f"""Extract the user's requirement or need from this message. If the user is expressing what they need, want, or are looking for, extract it concisely.

User message: "{user_message}"

Rules:
- If user expresses a need/want/requirement, extract it in 1-2 sentences
- Focus on WHAT they need (e.g., "import data for electronics", "export statistics for Brazil")
- If no clear requirement, return "none"

Return ONLY the extracted requirement (no JSON, no explanation):"""

            response = await self._call_llm_with_timeout(
                model='qwen3.5:cloud',  # Cloud model (same as main)
                messages=[{'role': 'user', 'content': prompt}],
                options={
                    'temperature': 0.2,
                    'num_predict': 100,
                    'thinking': False  # Disable thinking output
                }
            )

            # Handle models that put output in 'thinking' field
            requirement = response['message'].get('content', '').strip()
            if not requirement and 'thinking' in response['message']:
                requirement = response['message']['thinking'].strip()

            # Clean up response - extract requirement text
            requirement = requirement.strip('"\'')
            if requirement and '\n' in requirement:
                lines = [l.strip('"\'.-*# ') for l in requirement.split('\n') if l.strip()]
                for line in lines:
                    if (len(line) > 10 and len(line) < 500 and
                        not line.lower().startswith(('thinking', 'rule', 'analysis'))):
                        requirement = line
                        break

            if requirement.lower() in ['none', 'n/a', 'no requirement', 'unclear']:
                return None

            if len(requirement) > 10 and len(requirement) < 500:
                print(f"[LLM_COLLECTOR] Extracted requirement: {requirement[:100]}...")
                return requirement

            return None

        except Exception as e:
            print(f"[LLM_COLLECTOR] Requirements extraction failed: {e}")
            return None

    async def _save_extracted_info(
        self,
        session_id: str,
        extracted_info: Dict[str, str]
    ):
        """Save extracted info to DB with correct completion tracking"""

        # Get current user info to calculate TOTAL completion (not just current batch)
        current_info = await self._get_user_info_fast(session_id)

        # Build set of ALL collected fields (existing + new)
        all_collected_fields = set()

        # Add existing fields
        if current_info:
            if current_info.get('name'):
                all_collected_fields.add('name')
            if current_info.get('email'):
                all_collected_fields.add('email')
            if current_info.get('phone'):
                all_collected_fields.add('phone')
            if current_info.get('requirements'):
                all_collected_fields.add('requirements')

        # Add newly extracted fields
        all_collected_fields.update(extracted_info.keys())

        # Calculate CORRECT completion (4 total fields: name, email, phone, requirements)
        completion = len(all_collected_fields) * 0.25

        print(f"[LLM_COLLECTOR] Completion tracking: {len(all_collected_fields)}/4 fields = {completion*100:.0f}%")

        for field, value in extracted_info.items():
            try:
                await self.db_service.save_user_info(
                    session_id=session_id,
                    field=field,
                    value=value,
                    state_data={
                        'completion_percentage': completion,  # [OK] Total completion
                        'fields_collected': list(all_collected_fields),  # [OK] All fields
                        f'{field}_ask_count': 0,
                        'collection_paused': False,
                        'last_field_asked': field
                    }
                )
                print(f"[LLM_COLLECTOR] [SAVED] {field}={value if field != 'requirements' else value[:50]+'...'}")
            except Exception as e:
                print(f"[LLM_COLLECTOR] Error saving {field}: {e}")
