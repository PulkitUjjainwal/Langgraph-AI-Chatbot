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

    async def analyze_and_collect_async(
        self,
        session_id: str,
        user_message: str,
        bot_response: str,
        message_count: int,
        conversation_history: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        FAST non-blocking analysis.

        Returns prompt immediately if we should collect, None otherwise.
        Extraction happens in background.
        """
        print(f"[COLLECTOR_INTERNAL] analyze_and_collect_async called: msg_count={message_count}")

        # Quick check: Do we need to collect anything?
        user_info = await self._get_user_info_fast(session_id)
        missing = self._get_missing_fields(user_info)
        print(f"[COLLECTOR_INTERNAL] user_info={user_info}, missing={missing}")

        if not missing:
            print(f"[COLLECTOR_INTERNAL] All info collected, returning None")
            return None  # All collected

        # Quick heuristic checks (no LLM needed for obvious cases)

        # Don't collect on message 1 (let them engage first)
        if message_count < 2:
            print(f"[COLLECTOR_INTERNAL] Message count < 2, returning None")
            return None

        # CRITICAL FIX: Check if current message contains user info BEFORE asking
        # Uses cached LLM detection (< 1ms) from previous background task
        # Falls back to fast heuristics if no cache available
        detected_in_message = self._get_cached_detection(session_id, user_message, missing)
        print(f"[COLLECTOR_INTERNAL] Detected in current message: {detected_in_message}")

        # Update missing list - remove fields detected in current message
        still_missing = [field for field in missing if field not in detected_in_message]
        print(f"[COLLECTOR_INTERNAL] Still missing after detection: {still_missing}")

        # Extract in background (non-blocking)
        print(f"[COLLECTOR_INTERNAL] Starting background extraction task")
        asyncio.create_task(
            self._extract_and_save_background(session_id, user_message, missing)
        )

        # Smart decision: Should we prompt now? (only for fields NOT in current message)
        should_prompt_now = self._fast_decision_heuristic(
            user_message=user_message,
            bot_response=bot_response,
            message_count=message_count,
            missing_fields=still_missing,  # Use updated list
            user_info=user_info,
            session_id=session_id  # Pass session_id to check for rejected emails
        )
        print(f"[COLLECTOR_INTERNAL] Decision result: {should_prompt_now}")

        if not should_prompt_now['should_ask']:
            print(f"[COLLECTOR_INTERNAL] Decision says don't ask, returning None")
            return None

        # Check if there's a custom message (e.g., for rejected disposable email)
        if 'custom_message' in should_prompt_now:
            prompt = should_prompt_now['custom_message']
            print(f"[COLLECTOR_INTERNAL] ⚠️ Using custom prompt for rejected email: {prompt[:60]}...")
        else:
            # Generate prompt (LLM-generated, personalized based on context)
            prompt = await self._generate_fast_contextual_prompt(
                field=should_prompt_now['field'],
                bot_response=bot_response,
                user_message=user_message
            )
            print(f"[COLLECTOR_INTERNAL] Generated prompt: {prompt}")

        return prompt

    def _get_cached_detection(
        self,
        session_id: str,
        user_message: str,
        missing_fields: List[str]
    ) -> List[str]:
        """
        INSTANT detection using cached LLM results (< 1ms).

        Falls back to fast heuristics if no cache available.
        LLM detection runs in background and populates cache for next message.
        """
        # Check cache (instant)
        cache_key = f"{session_id}:{user_message[:50]}"
        if cache_key in self._detection_cache:
            cached = self._detection_cache[cache_key]
            print(f"[COLLECTOR_INTERNAL] ⚡ Cache HIT for detection")
            return [f for f in cached if f in missing_fields]

        # No cache - use instant heuristics with conversation context (< 1ms)
        print(f"[COLLECTOR_INTERNAL] ⚡ Cache MISS - using fast heuristics")
        conversation = self.redis.get_conversation(session_id)
        return self._instant_heuristic_detection(user_message, missing_fields, conversation)

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
            # Check if bot just asked for name in last message
            elif conversation_context and len(conversation_context) >= 2:
                last_bot_msg = conversation_context[-1].get('content', '').lower()
                if 'name' in last_bot_msg and any(q in last_bot_msg for q in ['?', 'please', 'could you']):
                    # Bot asked for name, check if user provided simple text response
                    # Must be: 2-50 chars, mostly letters, not a question, not a common phrase
                    if (2 <= len(message_stripped) <= 50 and
                        sum(c.isalpha() or c.isspace() for c in message_stripped) / len(message_stripped) > 0.7 and
                        '?' not in message_stripped and
                        message_stripped.lower() not in ['yes', 'no', 'ok', 'sure', 'nope', 'yeah', 'hi', 'hello']):
                        detected.append('name')

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
        prompt = f"""Analyze this conversation and detect if the user's current message contains: {fields_str}.

Conversation history:
{context}

Current user message: "{user_message}"

CRITICAL RULES:
- Name: User providing their name in ANY form:
  * Explicit: "my name is John", "I'm Sarah", "call me Alex"
  * Direct answer: If bot asked "what's your name?" and user says "pulkit" → TRUE
  * Context-aware: If bot asks for name and user provides simple text (2-50 chars), likely a name → TRUE
  * NOT a name: Country names, company names, greetings, yes/no

- Email: Valid email address (user@domain.com)

- Phone: Phone number (+1234567890 or similar)

- Requirements: User expressing needs/wants
  * "I need import data", "looking for statistics", "want to find buyers"

IMPORTANT: Use conversation context! If bot asked "what's your name?" and user replied with a simple word, that's their name.

Return ONLY a JSON object (no markdown, no explanation):
{{"name": true/false, "email": true/false, "phone": true/false, "requirements": true/false}}"""

        try:
            # Fast LLM call for intelligent detection
            if not self._ollama_client:
                # Fallback to regex if no LLM client
                print("[COLLECTOR_INTERNAL] No Ollama client, using fallback regex detection")
                return self._fallback_regex_detection(user_message, missing_fields)

            response = self._ollama_client.chat(
                model='qwen3.5:cloud',  # Small cloud model (fast, GPU-accelerated, 1-2s response)
                messages=[{'role': 'user', 'content': prompt}],
                options={
                    'temperature': 0.1,  # Low temperature for consistent detection
                    'num_predict': 100  # Short response
                }
            )

            # Parse JSON response
            response_text = response['message']['content'].strip()

            # Remove markdown code blocks if present
            response_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()

            data = json.loads(response_text)
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
                print(f"[COLLECTOR_INTERNAL] ⚠️ Detected rejected disposable email - will ask for valid email")
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
            print(f"[LLM_COLLECTOR] ⚡ Generic prompt (instant): {generic_prompt[:50]}...")
            return generic_prompt

        # Check cache for LLM-generated prompt (instant)
        cache_key = f"{field}"
        if cache_key in self._prompt_cache:
            cached_prompt = self._prompt_cache[cache_key]
            print(f"[LLM_COLLECTOR] ⚡ Cached LLM prompt (instant): {cached_prompt[:50]}...")
            return cached_prompt

        # Use template immediately (instant)
        template_prompt = self._generate_template_prompt(field, user_message)
        print(f"[LLM_COLLECTOR] ⚡ Template prompt (instant): {template_prompt[:50]}...")

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
                print(f"[LLM_COLLECTOR] ⚡ Cached improved LLM prompt for '{field}': {llm_prompt[:60]}...")
        except Exception as e:
            print(f"[LLM_COLLECTOR] Background LLM prompt generation failed: {e}")

    async def _generate_llm_prompt(
        self,
        field: str,
        bot_response: str,
        user_message: str
    ) -> Optional[str]:
        """
        Use LLM to generate a personalized prompt based on conversation context.
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
            response = self._ollama_client.chat(
                model='ministral-3:8b',
                messages=[{'role': 'user', 'content': system_prompt}],
                options={
                    'temperature': 0.7,  # Creative but controlled
                    'num_predict': 80  # Short prompt
                }
            )

            generated_prompt = response['message']['content'].strip()

            # Clean up response (remove quotes if present)
            generated_prompt = generated_prompt.strip('"\'')

            # Validate prompt (basic checks)
            if (len(generated_prompt) > 15 and
                len(generated_prompt) < 200 and
                ('?' in generated_prompt or 'please' in generated_prompt.lower())):

                print(f"[LLM_COLLECTOR] ✓ Generated prompt for {field}: {generated_prompt[:60]}...")
                return generated_prompt

            return None

        except Exception as e:
            print(f"[LLM_COLLECTOR] LLM prompt generation error: {e}")
            return None

    def _generate_template_prompt(self, field: str, user_message: str) -> str:
        """
        Fallback template-based prompts (used if LLM fails).
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
        missing_fields: List[str]
    ):
        """
        Extract and save user info in BACKGROUND (non-blocking).

        Uses LLM-based intelligent extraction with conversation context.
        Allows updates to existing fields (e.g., "pulkit" → "pulkit ujjainwal").

        Also runs LLM detection and CACHES results for next message (instant lookup).
        """

        extracted = {}

        # Get conversation history AND current user info for context-aware extraction
        messages = self.redis.get_conversation(session_id)
        current_info = await self._get_user_info_fast(session_id)

        # RUN LLM DETECTION IN BACKGROUND with conversation context
        # This provides LLM accuracy without blocking main response
        try:
            detected_fields = await self._quick_detect_user_info(
                user_message,
                missing_fields,
                conversation_history=messages  # Pass conversation context for smarter detection
            )
            # Cache for next message (instant lookup)
            cache_key = f"{session_id}:{user_message[:50]}"
            self._detection_cache[cache_key] = detected_fields
            print(f"[COLLECTOR_INTERNAL] ⚡ Cached LLM detection for next message: {detected_fields}")

            # Cleanup old cache (keep last 10 per session)
            session_keys = [k for k in self._detection_cache.keys() if k.startswith(f"{session_id}:")]
            if len(session_keys) > 10:
                oldest_key = session_keys[0]
                del self._detection_cache[oldest_key]
        except Exception as e:
            print(f"[COLLECTOR_INTERNAL] LLM detection failed in background: {e}")

        # ALWAYS try to extract name (allows updates like "pulkit" → "pulkit ujjainwal")
        # The LLM will determine if this message contains a name
        name = await self._extract_name_llm(user_message, messages)
        if name:
            # Check if this is an UPDATE (better/more complete name)
            current_name = current_info.get('name')
            if current_name:
                # Update if new name is more complete (has more words)
                current_parts = current_name.split()
                new_parts = name.split()
                if len(new_parts) > len(current_parts):
                    print(f"[LLM_COLLECTOR] ⚡ Updating name: '{current_name}' → '{name}'")
                    extracted['name'] = name
                else:
                    print(f"[LLM_COLLECTOR] Name already complete: '{current_name}', ignoring '{name}'")
            else:
                # New name
                extracted['name'] = name

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
                    print(f"[LLM_COLLECTOR] ⚠️ Will notify user on next message")

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
            await self._save_extracted_info(session_id, extracted)

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
            'india', 'indonesia', 'china', 'japan', 'korea', 'brazil', 'mexico',
            'germany', 'france', 'italy', 'spain', 'russia', 'canada', 'australia',
            'singapore', 'thailand', 'vietnam', 'malaysia', 'philippines',
            'usa', 'uk', 'uae', 'pakistan', 'bangladesh', 'turkey', 'egypt',

            # Common business terms
            'company', 'business', 'enterprise', 'corporation', 'limited',
            'import', 'export', 'trade', 'supplier', 'buyer', 'vendor'
        }

        # Validation checks
        if (name_lower in invalid_names or  # In blocklist
            len(name.strip()) < 2 or  # Too short
            name.isdigit() or  # Just numbers
            not any(c.isalpha() for c in name)):  # No letters
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

            prompt = f"""Analyze this conversation and extract the user's PERSONAL NAME if provided.

Conversation context:
{context}

Current user message: "{user_message}"

Rules:
- Extract ONLY if user is providing their PERSONAL name (e.g., "I'm John Smith", "my name is Sarah", "call me Alex")
- DO NOT extract country names (e.g., "indonesia", "brazil"), company names, product names, or other entities
- DO NOT extract if user is just answering a question about countries/products/topics
- If the bot just asked "which country?" and user said "indonesia", that's NOT a name
- Return "none" if no personal name is provided

Return ONLY the extracted name in Title Case (e.g., "John Smith"), or "none" if not found:"""

            response = self._ollama_client.chat(
                model='ministral-3:8b',
                messages=[{'role': 'user', 'content': prompt}],
                options={
                    'temperature': 0.1,  # Very low for accurate extraction
                    'num_predict': 50  # Names are short
                }
            )

            name = response['message']['content'].strip()

            # Clean up response
            name = name.strip('"\'.,!')

            # Validate result
            if (name.lower() in ['none', 'n/a', 'not found', 'no name', 'unclear'] or
                len(name) < 2 or
                len(name) > 100 or
                not any(c.isalpha() for c in name)):
                return None

            # Additional validation - block if it looks like a greeting or invalid
            if not self._is_valid_name(name):
                print(f"[LLM_COLLECTOR] LLM extracted invalid name: '{name}' - rejected")
                return None

            print(f"[LLM_COLLECTOR] ✓ Extracted name via LLM: {name}")
            return name.title()

        except Exception as e:
            print(f"[LLM_COLLECTOR] LLM name extraction failed: {e}, using regex fallback")
            return self._extract_name_regex_fallback(user_message)

    def _extract_name_regex_fallback(self, user_message: str) -> Optional[str]:
        """
        Fallback regex-based name extraction (used if LLM unavailable).
        Only matches explicit name patterns like "my name is X" or "I'm X".
        """
        import re

        # Only match EXPLICIT name patterns (not just any capitalized word)
        patterns = [
            r"(?:my name is|i'm|i am|call me|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, user_message, re.IGNORECASE)
            if match:
                name = match.group(1).strip().title()
                if self._is_valid_name(name):
                    print(f"[LLM_COLLECTOR] ✓ Extracted name via regex: {name}")
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

            prompt = f"""Analyze this conversation and extract/update the user's comprehensive requirements for trade intelligence data.

Current requirements (if any): {current_req or 'None yet'}

Conversation history:
{context}

Current message: "{user_message}"

Your task:
1. Identify what trade intelligence the user needs (countries, products, import/export, etc.)
2. If current requirements exist, UPDATE/EXPAND them with new info from conversation
3. Build a COMPREHENSIVE requirement profile from the ENTIRE conversation
4. Include: data direction (import/export), countries, products/HS codes, specific needs

Examples of good requirements:
- "Import data for Indonesia - interested in electronics and machinery sectors"
- "Export statistics for Brazil, focusing on agricultural products"
- "Custom shipment data for USA-China trade, need supplier contact details"
- "Looking for buyer leads in automotive parts import market in Germany"

Rules:
- Extract from the FULL conversation, not just the current message
- If user mentioned countries/products in earlier messages, include them
- If requirements already exist, EXPAND them with new details
- Be specific and structured
- Return "none" only if there's truly no data need expressed

Return ONLY the extracted/updated requirement (no JSON, no explanation):"""

            response = self._ollama_client.chat(
                model='ministral-3:8b',
                messages=[{'role': 'user', 'content': prompt}],
                options={
                    'temperature': 0.3,  # Slightly higher for creative summarization
                    'num_predict': 150
                }
            )

            requirement = response['message']['content'].strip()

            # Clean up response
            requirement = requirement.strip('"\'')

            if requirement.lower() in ['none', 'n/a', 'no requirement', 'unclear', 'no data need']:
                return None

            if len(requirement) > 15 and len(requirement) < 500:
                if current_req and current_req != requirement:
                    print(f"[LLM_COLLECTOR] ⚡ UPDATED requirement: {requirement[:120]}...")
                else:
                    print(f"[LLM_COLLECTOR] ✓ Extracted requirement: {requirement[:120]}...")
                return requirement

            return None

        except Exception as e:
            print(f"[LLM_COLLECTOR] Smart requirements extraction failed: {e}, using fallback")
            return await self._extract_requirements_llm(user_message)

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

            response = self._ollama_client.chat(
                model='ministral-3:8b',
                messages=[{'role': 'user', 'content': prompt}],
                options={
                    'temperature': 0.2,
                    'num_predict': 100
                }
            )

            requirement = response['message']['content'].strip()

            # Clean up response
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
                        'completion_percentage': completion,  # ✅ Total completion
                        'fields_collected': list(all_collected_fields),  # ✅ All fields
                        f'{field}_ask_count': 0,
                        'collection_paused': False,
                        'last_field_asked': field
                    }
                )
                print(f"[LLM_COLLECTOR] [SAVED] {field}={value if field != 'requirements' else value[:50]+'...'}")
            except Exception as e:
                print(f"[LLM_COLLECTOR] Error saving {field}: {e}")
