"""
Authentication Module

Provides JWT-based authentication for the feedback dashboard.
"""

from .password import hash_password, verify_password
from .jwt_handler import create_access_token, create_refresh_token, verify_token
from .dependencies import get_current_user, require_auth, require_super_admin
from .models import (
    LoginRequest,
    TokenResponse,
    CreateUserRequest,
    UpdateUserRequest,
    UserResponse,
)

__all__ = [
    # Password hashing
    "hash_password",
    "verify_password",
    # JWT handling
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    # Dependencies
    "get_current_user",
    "require_auth",
    "require_super_admin",
    # Models
    "LoginRequest",
    "TokenResponse",
    "CreateUserRequest",
    "UpdateUserRequest",
    "UserResponse",
]
