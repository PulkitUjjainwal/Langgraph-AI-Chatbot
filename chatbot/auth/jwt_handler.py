"""
JWT Token Handler

Creates and verifies JWT access tokens and refresh tokens.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
import jwt
from chatbot.config.settings import get_settings

settings = get_settings()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload data to encode (must include user_id, email, role)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string

    Example:
        >>> token = create_access_token(
        ...     {"user_id": 1, "email": "user@example.com", "role": "admin"}
        ... )
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )

    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """
    Create a JWT refresh token (long-lived).

    Args:
        data: Payload data to encode (must include user_id)

    Returns:
        Encoded JWT refresh token string

    Example:
        >>> token = create_refresh_token({"user_id": 1})
    """
    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )

    return encoded_jwt


def verify_token(token: str, expected_type: str = "access") -> Optional[Dict]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string to verify
        expected_type: Expected token type ("access" or "refresh")

    Returns:
        Decoded token payload if valid, None if invalid

    Example:
        >>> payload = verify_token(token, "access")
        >>> if payload:
        ...     user_id = payload["user_id"]
        ...     role = payload["role"]
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        # Verify token type
        if payload.get("type") != expected_type:
            return None

        return payload

    except jwt.ExpiredSignatureError:
        # Token has expired
        return None
    except jwt.InvalidTokenError:
        # Invalid token
        return None
    except Exception:
        # Other errors
        return None
