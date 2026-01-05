"""
Context Analysis Helpers

Functions for analyzing context and response quality:
- Industry detection
- Response quality scoring
"""


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

    # Check 2: Contains numbers (for numeric queries)
    if any(word in query.lower() for word in ['how many', 'count', 'number', 'total']):
        if not any(char.isdigit() for char in response):
            score -= 30
            issues.append("Missing numeric data for numeric query")
            suggestions.append("Include specific numbers/statistics")

    # Check 3: Generic phrases (avoid fluff)
    generic_phrases = [
        'i cannot', 'i do not have', 'i apologize',
        'unfortunately', 'i am unable'
    ]
    if any(phrase in response.lower() for phrase in generic_phrases):
        score -= 25
        issues.append("Contains apologetic/negative language")
        suggestions.append("Focus on what you CAN provide")

    # Check 4: Hallucination indicators
    uncertainty_phrases = [
        'it seems', 'it appears', 'might be', 'could be',
        'possibly', 'perhaps', 'maybe'
    ]
    uncertainty_count = sum(1 for phrase in uncertainty_phrases if phrase in response.lower())
    if uncertainty_count > 2:
        score -= 15
        issues.append("Too many uncertainty phrases")
        suggestions.append("Be more confident with factual data")

    # Check 5: Actionable information
    if '?' not in response and 'would you like' not in response.lower():
        # Good - not asking back too much
        pass
    else:
        # Deduct slight points for excessive questions back
        question_count = response.count('?')
        if question_count > 2:
            score -= 10
            issues.append("Too many questions back to user")
            suggestions.append("Provide more direct answers")

    return {
        "score": max(0, score),  # Don't go below 0
        "issues": issues,
        "suggestions": suggestions
    }
