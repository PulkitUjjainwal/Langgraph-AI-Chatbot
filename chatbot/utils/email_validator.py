"""
Professional Email Validation Service

Validates user emails to ensure:
- Not from disposable/temporary email services
- Proper work email format
- Industry-standard validation

Provides natural, helpful feedback to users.
"""

import re
import os
from typing import Tuple, Optional, Set
from pathlib import Path


class EmailValidator:
    """
    Professional email validator with disposable email detection.

    Features:
    - Disposable email blocking (10,000+ domains)
    - Work email validation
    - Natural error messages
    - Fast lookup with Set data structure
    """

    # Common free email providers (acceptable but not ideal for B2B)
    FREE_EMAIL_PROVIDERS = {
        'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com',
        'aol.com', 'icloud.com', 'mail.com', 'protonmail.com',
        'zoho.com', 'yandex.com', 'gmx.com', 'mail.ru'
    }

    # Known work email patterns (large companies)
    KNOWN_BUSINESS_DOMAINS = {
        'microsoft.com', 'google.com', 'amazon.com', 'apple.com',
        'meta.com', 'facebook.com', 'ibm.com', 'oracle.com',
        'salesforce.com', 'adobe.com', 'cisco.com', 'intel.com',
        'hp.com', 'dell.com', 'accenture.com', 'deloitte.com',
        'pwc.com', 'kpmg.com', 'ey.com', 'mckinsey.com'
    }

    def __init__(self, blocklist_path: Optional[str] = None):
        """
        Initialize email validator.

        Args:
            blocklist_path: Path to disposable email blocklist file
        """
        self.disposable_domains: Set[str] = set()

        # Auto-detect blocklist path
        if blocklist_path is None:
            # Try common locations
            possible_paths = [
                "disposable_email_blocklist.conf",
                "../disposable_email_blocklist.conf",
                "../../disposable_email_blocklist.conf",
                os.path.join(os.path.dirname(__file__), "../../disposable_email_blocklist.conf")
            ]

            for path in possible_paths:
                if os.path.exists(path):
                    blocklist_path = path
                    break

        # Load blocklist
        if blocklist_path and os.path.exists(blocklist_path):
            self._load_blocklist(blocklist_path)
            print(f"[EmailValidator] Loaded {len(self.disposable_domains):,} disposable email domains")
        else:
            print(f"[EmailValidator] Warning: Disposable email blocklist not found")

    def _load_blocklist(self, path: str):
        """Load disposable email domains from file"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    domain = line.strip().lower()
                    if domain and not domain.startswith('#'):
                        self.disposable_domains.add(domain)
        except Exception as e:
            print(f"[EmailValidator] Error loading blocklist: {e}")

    def validate_email(self, email: str) -> Tuple[bool, Optional[str], str]:
        """
        Validate email address comprehensively.

        Args:
            email: Email address to validate

        Returns:
            Tuple of (is_valid, email_type, message)
            - is_valid: True if email is acceptable
            - email_type: "work", "personal", "disposable", "invalid"
            - message: User-friendly message
        """
        if not email:
            return False, "invalid", "Please provide an email address."

        email = email.strip().lower()

        # Step 1: Basic format validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return False, "invalid", "That doesn't look like a valid email address. Could you double-check it?"

        # Extract domain
        try:
            domain = email.split('@')[1]
        except IndexError:
            return False, "invalid", "Please provide a complete email address (e.g., name@company.com)."

        # Step 2: Check for disposable/temporary email
        if domain in self.disposable_domains:
            return False, "disposable", (
                "We noticed you used a temporary email address. "
                "For a better experience, please provide your work email instead. "
                "This helps us send you personalized information and support."
            )

        # Step 3: Check for common free email providers
        if domain in self.FREE_EMAIL_PROVIDERS:
            # Accept but note it's personal
            return True, "personal", (
                "Got it! For business inquiries, we recommend using your work email "
                "for faster support and personalized assistance."
            )

        # Step 4: Check for known business domains
        if domain in self.KNOWN_BUSINESS_DOMAINS:
            return True, "work", "Perfect! We'll send professional information to your work email."

        # Step 5: Heuristic check for work email
        # Work emails typically have: company domain (not free provider), proper TLD
        if self._looks_like_work_email(domain):
            return True, "work", "Thanks! We'll use your work email for professional communications."

        # Accept but encourage work email
        return True, "unknown", (
            "Email received! If you have a work email, feel free to share that instead "
            "for faster business support."
        )

    def _looks_like_work_email(self, domain: str) -> bool:
        """
        Heuristic to detect if domain looks like a work email.

        Indicators:
        - Not a free provider
        - Not disposable
        - Has proper TLD
        - Reasonable domain length
        """
        # Already checked disposable and free providers

        # Check TLD (work emails rarely use .tk, .ml, .ga, etc.)
        suspicious_tlds = {
            'tk', 'ml', 'ga', 'cf', 'gq',  # Free TLDs
            'xyz', 'top', 'work', 'click'   # Often used for temporary
        }

        parts = domain.split('.')
        if len(parts) < 2:
            return False

        tld = parts[-1]
        if tld in suspicious_tlds:
            return False

        # Work domains typically have 2-3 parts (company.com or company.co.uk)
        if len(parts) > 4:
            return False

        # Domain shouldn't be too short (likely disposable)
        domain_name = parts[-2] if len(parts) >= 2 else parts[0]
        if len(domain_name) < 3:
            return False

        return True

    def is_disposable(self, email: str) -> bool:
        """Quick check if email is from disposable provider"""
        try:
            domain = email.strip().lower().split('@')[1]
            return domain in self.disposable_domains
        except:
            return False

    def is_work_email(self, email: str) -> bool:
        """Check if email is likely a work email"""
        try:
            domain = email.strip().lower().split('@')[1]

            # Not free provider and not disposable
            if domain in self.FREE_EMAIL_PROVIDERS:
                return False
            if domain in self.disposable_domains:
                return False

            # Known business or looks like work email
            if domain in self.KNOWN_BUSINESS_DOMAINS:
                return True

            return self._looks_like_work_email(domain)
        except:
            return False

    def get_validation_message(self, email: str, context: str = "general") -> str:
        """
        Get natural validation message based on context.

        Args:
            email: Email to validate
            context: Context of request ("initial", "retry", "correction")

        Returns:
            Natural, helpful message
        """
        is_valid, email_type, message = self.validate_email(email)

        if not is_valid:
            if email_type == "disposable":
                if context == "retry":
                    return (
                        "I see you provided a temporary email again. "
                        "For the best experience, please use your professional work email. "
                        "It helps us provide better support and send you valuable insights."
                    )
                else:
                    return message
            else:
                return message

        # Valid email - positive reinforcement
        if email_type == "work":
            return "Excellent! I've got your work email."
        elif email_type == "personal":
            if context == "initial":
                return (
                    "Thanks! I've noted your email. "
                    "If you have a work email, that would help us provide business-specific information."
                )
            else:
                return "Got it! Email saved."

        return "Perfect, I've saved your email."


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_email_validator: Optional[EmailValidator] = None


def get_email_validator() -> EmailValidator:
    """Get or create email validator singleton"""
    global _email_validator

    if _email_validator is None:
        _email_validator = EmailValidator()

    return _email_validator


def validate_email(email: str) -> Tuple[bool, Optional[str], str]:
    """
    Convenient function to validate email.

    Returns:
        (is_valid, email_type, message)
    """
    validator = get_email_validator()
    return validator.validate_email(email)
