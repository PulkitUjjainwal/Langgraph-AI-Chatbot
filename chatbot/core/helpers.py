"""
Production-Grade Helper Functions for LangGraph Workflow

Contains:
- Query classification functions
- Intent detection functions
- Response quality scoring
- Greeting detection
- Industry detection
"""

import random
from typing import Dict, Optional


# ============================================================================
# QUERY CLASSIFICATION
# ============================================================================

def classify_query_type(query: str) -> str:
    """
    Classify query type for smart context selection

    Args:
        query: User query string

    Returns:
        'company', 'trade_data', or 'general'
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
    """
    Check if query requires numeric precision

    Args:
        query: User query string

    Returns:
        True if query focuses on numbers/data
    """
    numeric_indicators = [
        'how many', 'how much', 'count', 'number',
        'total', 'sum', 'average', 'statistics',
        'volume', 'value', 'quantity', 'amount',
        'list all', 'show all', 'list', 'enumerate'
    ]
    return any(indicator in query.lower() for indicator in numeric_indicators)


def detect_query_type(query: str) -> str:
    """
    Detect query complexity for dynamic response length

    Args:
        query: User query string

    Returns:
        'simple', 'standard', or 'detailed'
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


def is_data_type_query(query: str) -> bool:
    """
    Check if query is asking about data types

    Args:
        query: User query string

    Returns:
        True if query is about data types
    """
    query_lower = query.lower()
    return any(term in query_lower for term in [
        'data type', 'data available', 'what data', 'which data'
    ])


# ============================================================================
# INTENT DETECTION
# ============================================================================

def detect_greeting(query: str) -> Dict[str, any]:
    """
    Detect if query is a greeting and return appropriate response

    Args:
        query: User query string

    Returns:
        Dict with keys: is_greeting (bool), response (str or None)
    """
    query_lower = query.lower().strip()

    # Greeting patterns
    greetings = [
        'hi', 'hello', 'hey', 'good morning',
        'good afternoon', 'good evening', 'greetings'
    ]

    # Check if query is a simple greeting (not part of longer question)
    if query_lower in greetings or (
        any(query_lower.startswith(g) for g in greetings) and len(query.split()) <= 3
    ):
        # Context-aware greeting responses
        responses = [
            "Hi! I'm Alex from Market Inside. How can I help you with global trade intelligence today?",
            "Hi! I'm Alex from Market Inside. How can I help you with global trade intelligence today?",
            "Hi! I'm Alex from Market Inside. How can I help you with global trade intelligence today?"
        ]

        # Pick response with variation
        response = random.choice(responses)

        return {"is_greeting": True, "response": response}

    return {"is_greeting": False, "response": None}


def detect_industry(query: str, context: str = "") -> Dict[str, Optional[str]]:
    """
    Detect industry mentioned in query and return specific context

    Args:
        query: User query string
        context: Additional context to search

    Returns:
        Dict with keys: industry, context_hint, examples
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


# ============================================================================
# RESPONSE QUALITY
# ============================================================================

def score_response_quality(response: str, query: str) -> Dict[str, any]:
    """
    Score response quality on multiple dimensions

    Args:
        response: Bot response to evaluate
        query: Original user query

    Returns:
        Dict with keys: score (float), issues (list), suggestions (list)
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


def get_optimal_temperature(query: str) -> float:
    """
    Determine optimal temperature based on query type

    Args:
        query: User query string

    Returns:
        Temperature value: 0.3 (factual), 0.5 (standard), or 0.7 (creative)
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
        'how can', 'what if', 'suggest', 'recommend', 'idea',
        'opportunity', 'strategy', 'grow my business'
    ]
    if any(keyword in query_lower for keyword in creative_keywords):
        return 0.7

    # Standard queries
    return 0.5
