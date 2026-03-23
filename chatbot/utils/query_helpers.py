"""
Query Classification and Analysis Helpers

Functions for analyzing user queries:
- Query type classification
- Numeric focus detection
- Greeting detection
"""

import random


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
            "Hi! I'm Alex from Market Inside. How can I help you with global trade intelligence today?",
            "Hi! I'm Alex from Market Inside. How can I help you with global trade intelligence today?",
            "Hi! I'm Alex from Market Inside. How can I help you with global trade intelligence today?"
        ]

        # Pick response based on variation
        response = random.choice(responses)

        return {"is_greeting": True, "response": response}

    return {"is_greeting": False, "response": None}
