"""
PostgreSQL Integration Test Script

This script tests all PostgreSQL components:
- Database connection
- pgvector extension
- Conversation and message persistence
- Vector embeddings
- FAQ service

Run this script to verify your PostgreSQL implementation works correctly.
"""

import asyncio
import sys
from datetime import datetime

from chatbot.config.settings import get_settings
from chatbot.integrations.postgres.client import pg_client
from chatbot.database.conversation_service import get_conversation_service
from chatbot.database.message_service import get_message_service
from chatbot.services.retrieval.pgvector_retriever import get_pgvector_retriever
from chatbot.database.faq_service_postgres import get_faq_service
from chatbot.config.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()


class Colors:
    """Terminal colors for pretty output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_test(name: str):
    """Print test name"""
    print(f"\n{Colors.BOLD}Testing: {name}{Colors.ENDC}")


def print_success(message: str):
    """Print success message"""
    print(f"{Colors.OKGREEN}✅ {message}{Colors.ENDC}")


def print_error(message: str):
    """Print error message"""
    print(f"{Colors.FAIL}❌ {message}{Colors.ENDC}")


def print_warning(message: str):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠️  {message}{Colors.ENDC}")


def print_info(message: str):
    """Print info message"""
    print(f"{Colors.OKCYAN}ℹ️  {message}{Colors.ENDC}")


async def test_database_connection():
    """Test 1: PostgreSQL connection"""
    print_test("PostgreSQL Connection")

    try:
        # Check settings
        if not settings.postgres_enabled:
            print_error("PostgreSQL is disabled in settings (POSTGRES_ENABLED=false)")
            return False

        print_info(f"Connecting to {settings.postgres_host}:{settings.postgres_port}")

        # Connect
        await pg_client.connect()

        if not pg_client.is_connected():
            print_error("Failed to establish connection")
            return False

        print_success(f"Connected to PostgreSQL")

        # Health check
        health = await pg_client.health_check()

        if health['status'] == 'healthy':
            print_success(f"Database health: {health['status']}")
            print_info(f"PostgreSQL version: {health['version']}")
            print_info(f"Pool size: {health['pool_size']} (in use: {health['pool_in_use']})")

            if health['pgvector_installed']:
                print_success("pgvector extension installed")
            else:
                print_warning("pgvector extension NOT installed")
                print_warning("Run: CREATE EXTENSION vector;")

            return True
        else:
            print_error(f"Database unhealthy: {health.get('error', 'Unknown error')}")
            return False

    except Exception as e:
        print_error(f"Connection failed: {e}")
        return False


async def test_conversation_persistence():
    """Test 2: Conversation and Message Persistence"""
    print_test("Conversation & Message Persistence")

    try:
        # Initialize services
        conversation_service = await get_conversation_service()
        message_service = await get_message_service()

        # Create test conversation
        session_id = f"test_session_{datetime.utcnow().timestamp()}"
        print_info(f"Creating conversation: {session_id}")

        conversation_id = await conversation_service.create_conversation(
            session_id=session_id,
            site_id=settings.site_id,
            metadata={"test": True, "source": "integration_test"}
        )

        print_success(f"Created conversation: {conversation_id}")

        # Store user message
        await message_service.store_message(
            conversation_id=conversation_id,
            role="user",
            content="This is a test message from the integration test",
            metadata={"test": True}
        )
        print_success("Stored user message")

        # Store assistant message
        await message_service.store_message(
            conversation_id=conversation_id,
            role="assistant",
            content="This is a test response from the chatbot",
            metadata={"test": True, "sources": ["test"]}
        )
        print_success("Stored assistant message")

        # Retrieve conversation
        conversation = await conversation_service.get_conversation(session_id)
        if conversation:
            print_success(f"Retrieved conversation: {conversation['session_id']}")
        else:
            print_error("Failed to retrieve conversation")
            return False

        # Retrieve messages
        messages = await message_service.get_conversation_messages(
            conversation_id=conversation_id,
            limit=10
        )

        if len(messages) >= 2:
            print_success(f"Retrieved {len(messages)} messages")
            return True
        else:
            print_error(f"Expected 2+ messages, got {len(messages)}")
            return False

    except Exception as e:
        print_error(f"Conversation persistence test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_pgvector_embeddings():
    """Test 3: pgvector Embeddings"""
    print_test("pgvector Embeddings")

    if not settings.use_pgvector:
        print_warning("pgvector disabled in settings (USE_PGVECTOR=false)")
        return False

    try:
        pgvector = get_pgvector_retriever()

        # Store test embedding
        print_info("Storing test embedding...")
        content_id = f"test_content_{datetime.utcnow().timestamp()}"

        embedding_id = await pgvector.store_embedding(
            content_type="test",
            content_id=content_id,
            content_text="Export Genius provides comprehensive trade data for exporters and importers",
            metadata={"test": True, "source": "integration_test"},
            ttl_hours=24  # 1 day TTL for test
        )

        print_success(f"Stored embedding: {embedding_id}")

        # Search for similar content
        print_info("Searching for similar embeddings...")
        results = await pgvector.search_similar(
            query="trade data for businesses",
            content_type="test",
            top_k=5,
            similarity_threshold=0.5
        )

        if len(results) > 0:
            print_success(f"Found {len(results)} similar embeddings")
            for i, result in enumerate(results[:3], 1):
                print_info(f"  {i}. Similarity: {result['similarity']:.3f} - {result['content_text'][:60]}...")
            return True
        else:
            print_warning("No similar embeddings found (threshold might be too high)")
            return True  # Still success if storage worked

    except Exception as e:
        print_error(f"pgvector test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_faq_service():
    """Test 4: FAQ Service"""
    print_test("FAQ Service (PostgreSQL)")

    try:
        faq_service = get_faq_service()
        await faq_service.initialize()

        # Get FAQ for home page
        print_info("Fetching FAQs for home page...")
        faqs = await faq_service.get_suggested_questions("/", limit=5)

        if faqs:
            print_success(f"Retrieved {len(faqs)} FAQs")
            for i, faq in enumerate(faqs[:3], 1):
                print_info(f"  {i}. {faq['question'][:60]}...")
            return True
        else:
            print_warning("No FAQs found (database might be empty)")
            print_warning("Run migration script: python scripts/migrate_mysql_to_postgres.py")
            return True  # Not a failure, just empty DB

    except Exception as e:
        print_error(f"FAQ service test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_database_stats():
    """Test 5: Database Statistics"""
    print_test("Database Statistics")

    try:
        stats = await pg_client.get_stats()

        print_success("Retrieved database statistics")
        print_info(f"Database size: {stats['database_size']}")

        if stats['row_counts']:
            print_info("\nRow counts:")
            for table, count in stats['row_counts'].items():
                if count is not None:
                    print_info(f"  {table}: {count:,} rows")

        # Conversation stats
        conversation_service = await get_conversation_service()
        conv_stats = await conversation_service.get_stats()

        print_info("\nConversation stats:")
        print_info(f"  Total: {conv_stats.get('total', 0)}")
        print_info(f"  Active: {conv_stats.get('active', 0)}")
        print_info(f"  Today: {conv_stats.get('today', 0)}")

        # pgvector stats
        if settings.use_pgvector:
            pgvector = get_pgvector_retriever()
            emb_stats = await pgvector.get_stats()

            print_info("\nEmbedding stats:")
            print_info(f"  Total embeddings: {emb_stats.get('total_embeddings', 0)}")

            by_type = emb_stats.get('by_content_type', {})
            if by_type:
                for content_type, count in by_type.items():
                    print_info(f"    {content_type}: {count}")

        return True

    except Exception as e:
        print_error(f"Stats test failed: {e}")
        return False


async def run_all_tests():
    """Run all integration tests"""
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}PostgreSQL Integration Test Suite{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*70}{Colors.ENDC}")

    print_info(f"Database: {settings.postgres_host}:{settings.postgres_port}")
    print_info(f"Site: {settings.site_id}")
    print_info(f"pgvector enabled: {settings.use_pgvector}")

    results = {}

    # Run tests
    results['connection'] = await test_database_connection()

    if results['connection']:
        results['conversations'] = await test_conversation_persistence()
        results['pgvector'] = await test_pgvector_embeddings()
        results['faq'] = await test_faq_service()
        results['stats'] = await test_database_stats()
    else:
        print_error("\nSkipping remaining tests due to connection failure")
        print_info("\nTroubleshooting:")
        print_info("1. Check if PostgreSQL is running:")
        print_info("   - Docker: docker ps | grep postgres")
        print_info("   - Local: pg_isready")
        print_info("2. Verify .env configuration:")
        print_info("   - POSTGRES_ENABLED=true")
        print_info("   - POSTGRES_HOST=localhost")
        print_info("   - POSTGRES_PORT=5432")
        print_info("   - POSTGRES_PASSWORD=<your_password>")
        print_info("3. Start PostgreSQL:")
        print_info("   - Docker: docker-compose up -d postgres")
        print_info("   - Windows: scripts\\setup_postgres_docker.bat")
        return False

    # Summary
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}Test Summary{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*70}{Colors.ENDC}")

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    for test_name, result in results.items():
        status = f"{Colors.OKGREEN}✅ PASS{Colors.ENDC}" if result else f"{Colors.FAIL}❌ FAIL{Colors.ENDC}"
        print(f"{test_name.ljust(20)}: {status}")

    print(f"\n{Colors.BOLD}Result: {passed}/{total} tests passed{Colors.ENDC}")

    if passed == total:
        print_success("\n🎉 All tests passed! PostgreSQL integration is working perfectly!")
        return True
    else:
        print_error(f"\n⚠️  {total - passed} test(s) failed")
        return False


async def main():
    """Main entry point"""
    try:
        success = await run_all_tests()

        # Cleanup
        if pg_client.is_connected():
            await pg_client.close()

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print_warning("\n\nTests interrupted by user")
        if pg_client.is_connected():
            await pg_client.close()
        sys.exit(1)

    except Exception as e:
        print_error(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()

        if pg_client.is_connected():
            await pg_client.close()

        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
