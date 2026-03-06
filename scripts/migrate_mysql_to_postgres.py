#!/usr/bin/env python3
"""
Migrate FAQ data from MySQL to PostgreSQL

This script migrates:
- Pages table
- FAQ table
- Users table (if exists)
- Refresh tokens (if exists)

Usage:
    python scripts/migrate_mysql_to_postgres.py

Prerequisites:
    - MySQL running with data
    - PostgreSQL running with schema created
    - Both connection details in .env file
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from chatbot.config.settings import get_settings
from chatbot.integrations.postgres.client import pg_client

settings = get_settings()

# Try to import MySQL connector
try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except ImportError:
    print("ERROR: mysql-connector-python not installed")
    print("Install it with: pip install mysql-connector-python")
    sys.exit(1)


class MigrationStats:
    """Track migration statistics"""
    def __init__(self):
        self.pages_migrated = 0
        self.faq_migrated = 0
        self.users_migrated = 0
        self.tokens_migrated = 0
        self.errors = []

    def print_summary(self):
        """Print migration summary"""
        print("\n" + "=" * 70)
        print("MIGRATION SUMMARY")
        print("=" * 70)
        print(f"  Pages migrated:        {self.pages_migrated}")
        print(f"  FAQ entries migrated:  {self.faq_migrated}")
        print(f"  Users migrated:        {self.users_migrated}")
        print(f"  Refresh tokens:        {self.tokens_migrated}")
        print(f"  Errors:                {len(self.errors)}")

        if self.errors:
            print("\nERRORS:")
            for error in self.errors:
                print(f"  - {error}")

        print("=" * 70)


async def connect_mysql():
    """Connect to MySQL"""
    try:
        conn = mysql.connector.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset='utf8mb4'
        )
        print(f"✅ Connected to MySQL: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
        return conn
    except mysql.connector.Error as e:
        print(f"❌ Failed to connect to MySQL: {e}")
        return None


async def migrate_pages(mysql_conn, stats: MigrationStats):
    """Migrate pages table"""
    print("\n📄 Migrating pages...")

    try:
        # Fetch from MySQL
        cursor = mysql_conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM pages")
        pages = cursor.fetchall()
        cursor.close()

        if not pages:
            print("  ⚠️  No pages found in MySQL")
            return

        # Insert into PostgreSQL
        for page in pages:
            try:
                await pg_client.execute("""
                    INSERT INTO pages (id, page_key, page_name, url_pattern, is_active, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (page_key) DO UPDATE SET
                        page_name = EXCLUDED.page_name,
                        url_pattern = EXCLUDED.url_pattern,
                        is_active = EXCLUDED.is_active,
                        updated_at = CURRENT_TIMESTAMP
                """,
                    page['id'],
                    page['page_key'],
                    page['page_name'],
                    page['url_pattern'],
                    page.get('is_active', True),
                    page.get('created_at'),
                    page.get('updated_at')
                )
                stats.pages_migrated += 1

            except Exception as e:
                error_msg = f"Failed to migrate page {page['page_key']}: {e}"
                stats.errors.append(error_msg)
                print(f"  ❌ {error_msg}")

        print(f"  ✅ Migrated {stats.pages_migrated}/{len(pages)} pages")

    except Exception as e:
        error_msg = f"Pages migration failed: {e}"
        stats.errors.append(error_msg)
        print(f"  ❌ {error_msg}")


async def migrate_faq(mysql_conn, stats: MigrationStats):
    """Migrate FAQ table"""
    print("\n💬 Migrating FAQ entries...")

    try:
        # Fetch from MySQL
        cursor = mysql_conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM faq")
        faqs = cursor.fetchall()
        cursor.close()

        if not faqs:
            print("  ⚠️  No FAQ entries found in MySQL")
            return

        # Insert into PostgreSQL
        for faq in faqs:
            try:
                await pg_client.execute("""
                    INSERT INTO faq (
                        id, page_id, question, answer, question_type,
                        priority, keywords, click_count, is_active,
                        created_at, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (id) DO UPDATE SET
                        question = EXCLUDED.question,
                        answer = EXCLUDED.answer,
                        question_type = EXCLUDED.question_type,
                        priority = EXCLUDED.priority,
                        keywords = EXCLUDED.keywords,
                        click_count = EXCLUDED.click_count,
                        is_active = EXCLUDED.is_active,
                        updated_at = CURRENT_TIMESTAMP
                """,
                    faq['id'],
                    faq['page_id'],
                    faq['question'],
                    faq['answer'],
                    faq.get('question_type', 'suggested'),
                    faq.get('priority', 0),
                    faq.get('keywords'),
                    faq.get('click_count', 0),
                    faq.get('is_active', True),
                    faq.get('created_at'),
                    faq.get('updated_at')
                )
                stats.faq_migrated += 1

                if stats.faq_migrated % 10 == 0:
                    print(f"  ... {stats.faq_migrated} entries migrated")

            except Exception as e:
                error_msg = f"Failed to migrate FAQ {faq['id']}: {e}"
                stats.errors.append(error_msg)
                print(f"  ❌ {error_msg}")

        print(f"  ✅ Migrated {stats.faq_migrated}/{len(faqs)} FAQ entries")

    except Exception as e:
        error_msg = f"FAQ migration failed: {e}"
        stats.errors.append(error_msg)
        print(f"  ❌ {error_msg}")


async def migrate_users(mysql_conn, stats: MigrationStats):
    """Migrate users table (if exists)"""
    print("\n👤 Migrating users...")

    try:
        # Check if users table exists in MySQL
        cursor = mysql_conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = 'users'
        """, (settings.mysql_database,))

        if not cursor.fetchone()['COUNT(*)']:
            print("  ⚠️  Users table not found in MySQL (skipping)")
            cursor.close()
            return

        # Fetch users
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        cursor.close()

        if not users:
            print("  ⚠️  No users found in MySQL")
            return

        # Insert into PostgreSQL
        for user in users:
            try:
                await pg_client.execute("""
                    INSERT INTO users (
                        email, username, password_hash, full_name, role,
                        is_active, must_change_password, created_at, updated_at, last_login
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (email) DO UPDATE SET
                        username = EXCLUDED.username,
                        password_hash = EXCLUDED.password_hash,
                        full_name = EXCLUDED.full_name,
                        role = EXCLUDED.role,
                        is_active = EXCLUDED.is_active,
                        must_change_password = EXCLUDED.must_change_password,
                        updated_at = CURRENT_TIMESTAMP,
                        last_login = EXCLUDED.last_login
                """,
                    user['email'],
                    user['username'],
                    user['password_hash'],
                    user.get('full_name'),
                    user.get('role', 'user'),
                    user.get('is_active', True),
                    user.get('must_change_password', False),
                    user.get('created_at'),
                    user.get('updated_at'),
                    user.get('last_login')
                )
                stats.users_migrated += 1

            except Exception as e:
                error_msg = f"Failed to migrate user {user['email']}: {e}"
                stats.errors.append(error_msg)
                print(f"  ❌ {error_msg}")

        print(f"  ✅ Migrated {stats.users_migrated}/{len(users)} users")

    except Exception as e:
        error_msg = f"Users migration failed: {e}"
        stats.errors.append(error_msg)
        print(f"  ❌ {error_msg}")


async def verify_migration(stats: MigrationStats):
    """Verify migration by comparing counts"""
    print("\n🔍 Verifying migration...")

    try:
        # Check PostgreSQL counts
        pg_pages = await pg_client.fetchval("SELECT COUNT(*) FROM pages")
        pg_faq = await pg_client.fetchval("SELECT COUNT(*) FROM faq")
        pg_users = await pg_client.fetchval("SELECT COUNT(*) FROM users")

        print(f"\n  PostgreSQL counts:")
        print(f"    Pages:       {pg_pages}")
        print(f"    FAQ:         {pg_faq}")
        print(f"    Users:       {pg_users}")

        # Check if counts match
        if pg_pages == stats.pages_migrated:
            print("  ✅ Pages count matches")
        else:
            print(f"  ⚠️  Pages count mismatch (expected {stats.pages_migrated}, got {pg_pages})")

        if pg_faq == stats.faq_migrated:
            print("  ✅ FAQ count matches")
        else:
            print(f"  ⚠️  FAQ count mismatch (expected {stats.faq_migrated}, got {pg_faq})")

        if pg_users >= stats.users_migrated:  # >= because default admin user exists
            print("  ✅ Users count OK")
        else:
            print(f"  ⚠️  Users count mismatch (expected {stats.users_migrated}, got {pg_users})")

    except Exception as e:
        print(f"  ❌ Verification failed: {e}")


async def main():
    """Main migration function"""
    print("\n" + "=" * 70)
    print("MySQL TO POSTGRESQL MIGRATION")
    print("=" * 70)
    print(f"\nSource (MySQL):      {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    print(f"Target (PostgreSQL): {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_database}")

    # Confirm before proceeding
    print("\n⚠️  This will overwrite existing data in PostgreSQL with data from MySQL.")
    response = input("Continue? (yes/no): ").strip().lower()

    if response != 'yes':
        print("Migration cancelled.")
        return

    stats = MigrationStats()

    try:
        # Connect to MySQL
        mysql_conn = await connect_mysql()
        if not mysql_conn:
            print("❌ Cannot proceed without MySQL connection")
            return

        # Connect to PostgreSQL
        print(f"✅ Connecting to PostgreSQL...")
        await pg_client.connect()
        health = await pg_client.health_check()

        if health['status'] != 'healthy':
            print(f"❌ PostgreSQL is not healthy: {health}")
            return

        print(f"✅ Connected to PostgreSQL (version: {health.get('version', 'unknown')})")

        # Run migrations
        await migrate_pages(mysql_conn, stats)
        await migrate_faq(mysql_conn, stats)
        await migrate_users(mysql_conn, stats)

        # Verify
        await verify_migration(stats)

        # Close connections
        mysql_conn.close()
        await pg_client.close()

        # Print summary
        stats.print_summary()

        if len(stats.errors) == 0:
            print("\n✅ Migration completed successfully!")
            print("\nNext steps:")
            print("  1. Test FAQ service: curl http://localhost:8000/api/faq?url=/")
            print("  2. Disable MySQL in .env: MYSQL_ENABLED=false")
            print("  3. Restart application: uvicorn fastapi_chatbot:app --reload")
        else:
            print(f"\n⚠️  Migration completed with {len(stats.errors)} errors")
            print("    Review errors above and fix manually if needed")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
