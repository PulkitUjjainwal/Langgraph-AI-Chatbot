"""
FastAPI Dependencies for Authentication

Provides dependency injection for route protection and user authentication.
"""

from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

from chatbot.auth.jwt_handler import verify_token
from chatbot.database.auth_service import AuthDatabaseService
from chatbot.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# HTTP Bearer token security scheme
security = HTTPBearer()

# Global database service instance
_auth_db_service: Optional[AuthDatabaseService] = None


def get_auth_db_service() -> AuthDatabaseService:
    """Get or create auth database service instance (singleton)"""
    global _auth_db_service

    if _auth_db_service is None:
        _auth_db_service = AuthDatabaseService(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            pool_size=settings.mysql_pool_size
        )

    return _auth_db_service


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AuthDatabaseService = Depends(get_auth_db_service)
) -> Dict[str, Any]:
    """
    Verify JWT token and return current authenticated user.

    This dependency can be used on any route that requires authentication.

    Usage:
        @app.get("/protected")
        async def protected_route(current_user = Depends(get_current_user)):
            return {"user": current_user}

    Raises:
        HTTPException: 401 if token is invalid or user not found
    """
    # Ensure database is initialized
    if not db._initialized:
        await db.initialize()

    # Extract token from credentials
    token = credentials.credentials

    # Verify JWT token
    payload = verify_token(token, expected_type="access")

    if not payload:
        logger.warning("[Auth] Invalid or expired access token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Extract user_id from payload
    user_id = payload.get("user_id")

    if not user_id:
        logger.error("[Auth] Token missing user_id")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Get user from database
    user = await db.get_user_by_id(user_id)

    if not user:
        logger.warning(f"[Auth] Token for non-existent user: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Check if user is active
    if not user["is_active"]:
        logger.warning(f"[Auth] Token for inactive user: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Remove password_hash from user object before returning
    user_safe = {k: v for k, v in user.items() if k != "password_hash"}

    logger.debug(f"[Auth] User authenticated: {user['email']}")
    return user_safe


async def require_auth(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Require any authenticated user (any role).

    This is an alias for get_current_user for better semantic clarity.

    Usage:
        @app.get("/feedback")
        async def get_feedback(current_user = Depends(require_auth)):
            # Any authenticated user can access
            return {"data": "..."}
    """
    return current_user


async def require_super_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Require super_admin role.

    Raises:
        HTTPException: 403 if user is not super_admin

    Usage:
        @app.post("/admin/users/create")
        async def create_user(user = Depends(require_super_admin)):
            # Only super_admin can access
            return {"message": "User created"}
    """
    if current_user.get("role") != "super_admin":
        logger.warning(
            f"[Auth] User {current_user.get('email')} attempted to access super_admin route"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )

    return current_user


async def require_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Require admin or super_admin role.

    Raises:
        HTTPException: 403 if user is not admin or super_admin

    Usage:
        @app.get("/admin/reports")
        async def get_reports(user = Depends(require_admin)):
            # Admin or super_admin can access
            return {"data": "..."}
    """
    if current_user.get("role") not in ["admin", "super_admin"]:
        logger.warning(
            f"[Auth] User {current_user.get('email')} attempted to access admin route"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return current_user


# Optional: Helper for optional authentication (user may or may not be logged in)
async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AuthDatabaseService = Depends(get_auth_db_service)
) -> Optional[Dict[str, Any]]:
    """
    Get current user if authenticated, None otherwise.

    This allows routes to optionally check authentication without requiring it.

    Usage:
        @app.get("/content")
        async def get_content(user = Depends(get_optional_user)):
            if user:
                # Show personalized content
                return {"content": "personalized"}
            else:
                # Show public content
                return {"content": "public"}
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
