"""
Password Hashing and Verification

BACKWARD COMPATIBLE implementation that supports both:
- Old passlib/bcrypt hashes (for existing users)
- New direct bcrypt hashes (for new users)

This ensures original passwords continue to work!
"""

import hashlib
import bcrypt

# Try to import passlib for backward compatibility
try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    PASSLIB_AVAILABLE = True
except:
    PASSLIB_AVAILABLE = False


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt directly.

    Truncates to 72 bytes if needed (bcrypt limitation).

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    try:
        # Truncate to 72 bytes if needed (bcrypt limitation)
        password_bytes = password.encode('utf-8')[:72]

        # Hash with bcrypt (12 rounds)
        hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12))

        # Return as string
        return hashed.decode('utf-8')
    except Exception as e:
        print(f"[Auth] Password hashing error: {e}")
        # Fallback: truncate password manually
        password_truncated = password[:72]
        password_bytes = password_truncated.encode('utf-8')
        hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12))
        return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    BACKWARD COMPATIBLE - supports both old (passlib) and new (direct bcrypt) hashes!

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password from database

    Returns:
        True if password matches, False otherwise
    """
    try:
        # Method 1: Try direct bcrypt verification (new format)
        try:
            password_bytes = plain_password.encode('utf-8')[:72]
            hashed_bytes = hashed_password.encode('utf-8') if isinstance(hashed_password, str) else hashed_password

            if bcrypt.checkpw(password_bytes, hashed_bytes):
                return True
        except Exception as e:
            pass  # Try next method

        # Method 2: Try passlib verification (old format) for backward compatibility
        if PASSLIB_AVAILABLE:
            try:
                if pwd_context.verify(plain_password, hashed_password):
                    return True
            except Exception as e:
                pass  # Continue to next method

        # Method 3: If password is very long, try truncating differently
        if len(plain_password) > 72:
            try:
                password_bytes = plain_password[:72].encode('utf-8')
                hashed_bytes = hashed_password.encode('utf-8') if isinstance(hashed_password, str) else hashed_password

                if bcrypt.checkpw(password_bytes, hashed_bytes):
                    return True
            except Exception:
                pass

        return False

    except Exception as e:
        print(f"[Auth] Password verification error: {e}")
        return False
