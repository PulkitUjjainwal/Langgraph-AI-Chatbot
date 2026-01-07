"""
Unified API Integration Module

Main entry point for fetching and formatting content from any URL
Combines unified_api_client.py and unified_formatter.py

This is what DynamicContentManager should use
"""

from typing import Optional, Tuple
from chatbot.config.logging_config import get_logger
from chatbot.integrations.apis.unified_api_client import (
    UnifiedAPIClient,
    Platform,
    PageType,
    fetch_content_from_url as fetch_raw_data
)
from chatbot.integrations.apis.unified_formatter import UnifiedFormatter

logger = get_logger(__name__)


async def fetch_and_format_content(url: str) -> Tuple[str, Platform, PageType]:
    """
    Fetch content from URL and format as text for embeddings

    This is the main entry point that should be used by DynamicContentManager

    Args:
        url: Full URL to fetch (company, country, or search data)

    Returns:
        Tuple of (formatted_text, platform, page_type)

    Raises:
        Exception: If fetching or formatting fails
    """
    logger.info(f"Fetching and formatting content from: {url}")

    try:
        # Step 1: Fetch raw data from API
        data, platform, page_type = await fetch_raw_data(url)

        if "error" in data:
            logger.error(f"Failed to fetch data: {data['error']}")
            return f"Error: {data['error']}", platform, page_type

        logger.info(f"Successfully fetched {page_type.value} data from {platform.value}")

        # Step 2: Format based on page type
        if page_type == PageType.COMPANY:
            formatted_text = UnifiedFormatter.format_company_data(data)
        elif page_type == PageType.COUNTRY:
            formatted_text = UnifiedFormatter.format_country_data(data)
        elif page_type == PageType.COUNTRY_TO_COUNTRY:
            formatted_text = UnifiedFormatter.format_country_to_country_data(data)
        elif page_type == PageType.HS_CODE:
            formatted_text = UnifiedFormatter.format_hs_code_data(data)
        elif page_type == PageType.SEARCH_DATA:
            formatted_text = UnifiedFormatter.format_search_data(data)
        else:
            formatted_text = f"Error: Unsupported page type {page_type.value}"

        logger.info(f"Successfully formatted content ({len(formatted_text)} chars)")

        return formatted_text, platform, page_type

    except Exception as e:
        logger.error(f"Error in fetch_and_format_content: {e}", exc_info=True)
        raise


# Convenience functions for backward compatibility

async def is_company_url(url: str) -> bool:
    """Check if URL is a company page"""
    page_type = UnifiedAPIClient.detect_page_type(url)
    return page_type == PageType.COMPANY


async def is_country_url(url: str) -> bool:
    """Check if URL is a country page"""
    page_type = UnifiedAPIClient.detect_page_type(url)
    return page_type == PageType.COUNTRY


async def is_search_data_url(url: str) -> bool:
    """Check if URL is a search data page"""
    page_type = UnifiedAPIClient.detect_page_type(url)
    return page_type == PageType.SEARCH_DATA


async def is_country_to_country_url(url: str) -> bool:
    """Check if URL is a country-to-country bilateral trade page"""
    page_type = UnifiedAPIClient.detect_page_type(url)
    return page_type == PageType.COUNTRY_TO_COUNTRY


async def is_hs_code_url(url: str) -> bool:
    """Check if URL is an HS code chapter/hierarchy page"""
    page_type = UnifiedAPIClient.detect_page_type(url)
    return page_type == PageType.HS_CODE


async def get_platform(url: str) -> Platform:
    """Get platform from URL"""
    return UnifiedAPIClient.detect_platform(url)


async def get_page_type(url: str) -> PageType:
    """Get page type from URL"""
    return UnifiedAPIClient.detect_page_type(url)
