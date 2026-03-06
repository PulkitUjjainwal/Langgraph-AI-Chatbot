"""
PostgreSQL Integration Module

Provides async PostgreSQL client with connection pooling and pgvector support.
"""

from chatbot.integrations.postgres.client import (
    PostgreSQLClient,
    pg_client,
    get_postgres_client
)

__all__ = [
    "PostgreSQLClient",
    "pg_client",
    "get_postgres_client"
]
