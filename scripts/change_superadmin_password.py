#!/usr/bin/env python3
"""
Change Superadmin Password Script

Usage:
    python change_superadmin_password.py

This script will:
1. Prompt you for the superadmin email
2. Prompt you for the new password
3. Hash the password securely using bcrypt
4. Update the database with the new password hash
"""

import sys
import os
from getpass import getpass

# Add the parent directory to the path so we can import from chatbot module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chatbot.auth.password import hash_password
from chatbot.config.settings import get_settings
import aiomysql
import asyncio


async def change_password(email: str, new_password: str):
    """Change password for a user"""
    settings = get_settings()

    # Connect to database
    print(f"\n[*] Connecting to database...")
    print(f"    Host: {settings.mysql_host}:{settings.mysql_port}")
    print(f"    Database: {settings.mysql_database}")
    print(f"    User: {settings.mysql_user}")

    try:
        conn = await aiomysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            db=settings.mysql_database,
            autocommit=True
        )
        print(f"[✓] Connected to database")

        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Check if user exists
            await cursor.execute(
                "SELECT id, email, role, is_active FROM users WHERE email = %s",
                (email,)
            )
            user = await cursor.fetchone()

            if not user:
                print(f"[✗] Error: User with email '{email}' not found!")
                return False

            print(f"\n[*] User found:")
            print(f"    ID: {user['id']}")
            print(f"    Email: {user['email']}")
            print(f"    Role: {user['role']}")
            print(f"    Active: {user['is_active']}")

            # Hash the new password
            print(f"\n[*] Hashing new password...")
            password_hash = hash_password(new_password)
            print(f"[✓] Password hashed successfully")

            # Update password in database
            print(f"\n[*] Updating password in database...")
            await cursor.execute(
                "UPDATE users SET password_hash = %s, updated_at = NOW() WHERE email = %s",
                (password_hash, email)
            )

            print(f"[✓] Password updated successfully!")
            print(f"\n{'='*60}")
            print(f"✓ Password changed for: {email}")
            print(f"✓ You can now login with your new password")
            print(f"{'='*60}\n")

            return True

    except Exception as e:
        print(f"\n[✗] Database error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()


async def main():
    """Main function"""
    print("="*60)
    print("  Superadmin Password Change Tool")
    print("="*60)

    settings = get_settings()

    print(f"\nConfigured superadmin emails:")
    for email in settings.super_admin_emails:
        print(f"  - {email}")

    # Get email
    print(f"\n[*] Enter the superadmin email:")
    email = input("    Email: ").strip()

    if not email:
        print("[✗] Error: Email cannot be empty")
        return

    # Validate email is in superadmin list
    if email not in settings.super_admin_emails:
        print(f"\n[!] Warning: '{email}' is not in the SUPER_ADMIN_EMAILS list")
        print(f"    Current list: {', '.join(settings.super_admin_emails)}")
        confirm = input("    Continue anyway? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("[*] Cancelled")
            return

    # Get new password
    print(f"\n[*] Enter new password:")
    print(f"    Requirements:")
    print(f"    - Minimum 8 characters")
    print(f"    - At least one uppercase letter")
    print(f"    - At least one lowercase letter")
    print(f"    - At least one number")
    print(f"    - At least one special character")

    new_password = getpass("    New Password: ")
    confirm_password = getpass("    Confirm Password: ")

    if not new_password:
        print("[✗] Error: Password cannot be empty")
        return

    if new_password != confirm_password:
        print("[✗] Error: Passwords do not match!")
        return

    # Validate password strength
    if len(new_password) < 8:
        print("[✗] Error: Password must be at least 8 characters")
        return

    if not any(c.isupper() for c in new_password):
        print("[✗] Error: Password must contain at least one uppercase letter")
        return

    if not any(c.islower() for c in new_password):
        print("[✗] Error: Password must contain at least one lowercase letter")
        return

    if not any(c.isdigit() for c in new_password):
        print("[✗] Error: Password must contain at least one number")
        return

    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in new_password):
        print("[✗] Error: Password must contain at least one special character")
        return

    print(f"[✓] Password validation passed")

    # Confirm change
    print(f"\n[!] You are about to change the password for: {email}")
    confirm = input("    Proceed? (yes/no): ").strip().lower()

    if confirm != 'yes':
        print("[*] Cancelled")
        return

    # Change password
    success = await change_password(email, new_password)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[*] Cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[✗] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
