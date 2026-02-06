"""
Authentication Service

Business logic for user authentication and management.
"""

from typing import Optional, Dict, Any
import logging

from chatbot.auth.password import hash_password, verify_password
from chatbot.auth.jwt_handler import create_access_token, create_refresh_token, verify_token
from chatbot.database.auth_service import AuthDatabaseService
from chatbot.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthService:
    """
    Authentication service that combines password hashing, JWT handling,
    and database operations.
    """

    def __init__(self, db_service: AuthDatabaseService):
        self.db = db_service

    async def authenticate_user(
        self,
        email: str,
        password: str
    ) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with email and password.

        Args:
            email: User email
            password: Plain text password

        Returns:
            User dict if authentication successful, None otherwise
        """
        # Get user from database
        user = await self.db.get_user_by_email(email)

        if not user:
            logger.warning(f"[Auth] Login attempt for non-existent user: {email}")
            return None

        # Check if user is active
        if not user["is_active"]:
            logger.warning(f"[Auth] Login attempt for inactive user: {email}")
            return None

        # Verify password
        if not verify_password(password, user["password_hash"]):
            logger.warning(f"[Auth] Invalid password for user: {email}")
            return None

        # Update last login timestamp
        await self.db.update_last_login(user["id"])

        logger.info(f"[Auth] User authenticated successfully: {email}")
        return user

    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str,
        role: str,
        creator_role: str
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new user.

        Args:
            username: Username
            email: Email address
            password: Plain text password (will be hashed)
            full_name: Full name
            role: User role (admin or user)
            creator_role: Role of the user creating this user

        Returns:
            Created user dict if successful, None otherwise
        """
        # Only super_admin can create users
        if creator_role != "super_admin":
            logger.warning(f"[Auth] Non-super-admin attempted to create user")
            return None

        # Cannot create super_admin via API (whitelist only)
        if role == "super_admin":
            logger.warning(f"[Auth] Attempted to create super_admin via API")
            return None

        # Check if email already exists
        existing_user = await self.db.get_user_by_email(email)
        if existing_user:
            logger.warning(f"[Auth] Attempted to create user with existing email: {email}")
            return None

        # Hash password
        password_hash = hash_password(password)

        # Create user in database
        user_id = await self.db.create_user(
            username=username,
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            role=role
        )

        if not user_id:
            logger.error(f"[Auth] Failed to create user: {email}")
            return None

        # Fetch and return created user
        user = await self.db.get_user_by_id(user_id)
        logger.info(f"[Auth] User created: {email} (role: {role})")
        return user

    async def update_user(
        self,
        user_id: int,
        full_name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        updater_role: str = "user"
    ) -> bool:
        """
        Update user information.

        Args:
            user_id: ID of user to update
            full_name: New full name
            role: New role
            is_active: New active status
            updater_role: Role of user performing the update

        Returns:
            True if successful, False otherwise
        """
        # Only super_admin can update users
        if updater_role != "super_admin":
            logger.warning(f"[Auth] Non-super-admin attempted to update user")
            return False

        # Get existing user
        user = await self.db.get_user_by_id(user_id)
        if not user:
            logger.warning(f"[Auth] Attempted to update non-existent user: {user_id}")
            return False

        # Cannot modify super_admin role or deactivate super_admin
        if user["role"] == "super_admin":
            if role and role != "super_admin":
                logger.warning(f"[Auth] Attempted to change super_admin role")
                return False
            if is_active is False:
                logger.warning(f"[Auth] Attempted to deactivate super_admin")
                return False

        # Cannot set role to super_admin
        if role == "super_admin":
            logger.warning(f"[Auth] Attempted to set role to super_admin")
            return False

        # Update user
        success = await self.db.update_user(
            user_id=user_id,
            full_name=full_name,
            role=role,
            is_active=is_active
        )

        if success:
            logger.info(f"[Auth] User updated: {user_id}")

        return success

    async def delete_user(self, user_id: int, deleter_role: str) -> bool:
        """
        Delete (deactivate) a user.

        Args:
            user_id: ID of user to delete
            deleter_role: Role of user performing the deletion

        Returns:
            True if successful, False otherwise
        """
        # Only super_admin can delete users
        if deleter_role != "super_admin":
            logger.warning(f"[Auth] Non-super-admin attempted to delete user")
            return False

        # Get user
        user = await self.db.get_user_by_id(user_id)
        if not user:
            logger.warning(f"[Auth] Attempted to delete non-existent user: {user_id}")
            return False

        # Cannot delete super_admin
        if user["role"] == "super_admin":
            logger.warning(f"[Auth] Attempted to delete super_admin user")
            return False

        # Soft delete
        success = await self.db.delete_user(user_id)

        if success:
            logger.info(f"[Auth] User deleted: {user_id}")

        return success

    async def generate_tokens(self, user: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate access and refresh tokens for a user.

        Args:
            user: User dict from database

        Returns:
            Dict with access_token and refresh_token
        """
        # Create token payload
        token_data = {
            "user_id": user["id"],
            "email": user["email"],
            "role": user["role"]
        }

        # Generate tokens
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token({"user_id": user["id"]})

        # Store refresh token in database
        await self.db.store_refresh_token(
            user_id=user["id"],
            token=refresh_token,
            expires_days=settings.jwt_refresh_token_expire_days
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token
        }

    async def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """
        Generate new access token from refresh token.

        Args:
            refresh_token: Refresh token

        Returns:
            New access token if successful, None otherwise
        """
        # Verify refresh token in database
        user_id = await self.db.verify_refresh_token(refresh_token)

        if not user_id:
            logger.warning("[Auth] Invalid or expired refresh token")
            return None

        # Get user
        user = await self.db.get_user_by_id(user_id)

        if not user or not user["is_active"]:
            logger.warning(f"[Auth] Refresh token for inactive user: {user_id}")
            return None

        # Create new access token
        token_data = {
            "user_id": user["id"],
            "email": user["email"],
            "role": user["role"]
        }

        access_token = create_access_token(token_data)
        logger.info(f"[Auth] Access token refreshed for user: {user['email']}")

        return access_token

    async def logout(self, refresh_token: str) -> bool:
        """
        Logout user by revoking refresh token.

        Args:
            refresh_token: Refresh token to revoke

        Returns:
            True if successful, False otherwise
        """
        success = await self.db.revoke_refresh_token(refresh_token)

        if success:
            logger.info("[Auth] User logged out successfully")

        return success

    def is_super_admin_email(self, email: str) -> bool:
        """
        Check if email is in super admin whitelist.

        Args:
            email: Email to check

        Returns:
            True if email is in whitelist, False otherwise
        """
        return email in settings.super_admin_emails
