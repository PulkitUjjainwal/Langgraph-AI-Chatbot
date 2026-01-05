"""
Unified API Client for Export Genius and Marketinside
Both platforms share the same backend - only domains differ

Architecture:
- UnifiedAPIClient: Base HTTP client with domain detection
- Page Strategies: Company, Country, SearchData (same logic, different endpoints)
- Automatic domain detection from URL
"""

import asyncio
import aiohttp
import os
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from enum import Enum

from chatbot.config.logging_config import get_logger

logger = get_logger(__name__)


class Platform(Enum):
    """Platform enumeration"""
    EXPORT_GENIUS = "exportgenius"
    MARKETINSIDE = "marketinside"
    UNKNOWN = "unknown"


class PageType(Enum):
    """Page type enumeration"""
    COMPANY = "company"
    COUNTRY = "country"
    SEARCH_DATA = "search_data"
    HS_CODE = "hs_code"
    PRODUCT = "product"
    UNKNOWN = "unknown"


class UnifiedAPIClient:
    """
    Unified API client for both Export Genius and Marketinside

    Both platforms use the same backend API, just different domains:
    - exportgenius.in
    - marketinside.com

    This client automatically detects the platform from URL and
    makes the appropriate API calls.
    """

    # API Configuration
    API_CONFIGS = {
        Platform.EXPORT_GENIUS: {
            "domain": "exportgenius.in",
            "api_base": os.getenv("EXPORTGENIUS_API_URL", "https://www.exportgenius.in/api"),
            "api_token": os.getenv("EXPORTGENIUS_API_TOKEN", ""),
        },
        Platform.MARKETINSIDE: {
            "domain": "marketinside.com",
            "api_base": os.getenv("MARKETINSIDE_API_URL", "https://www.marketinside.com/api"),
            "api_token": os.getenv("MARKETINSIDE_API_TOKEN", ""),
        }
    }

    # Common endpoints (same for both platforms)
    ENDPOINTS = {
        "company_data": "/company-data",
        "country_import_data": "/country-import-data",
        "country_export_data": "/country-export-data",
        "search_data_product": "/search-data-product",
        "search_data_importers": "/search-data-importers",
        "search_data_exporters": "/search-data-exporters",
        "search_data_buyers": "/search-data-buyers",
        "search_data_suppliers": "/search-data-suppliers",
        "search_data_total_importers_suppliers": "/search-data-total-importers-suppliers",
        "search_data_total_exporters_buyers": "/search-data-total-exporters-buyers",
        "search_data_hscode_list": "/search-data-hscode-list",
        "search_data_country_list": "/search-data-country-list",
        "search_data_ports_list": "/search-data-ports-list",
    }

    @staticmethod
    def detect_platform(url: str) -> Platform:
        """
        Detect platform from URL

        Args:
            url: Full URL or domain

        Returns:
            Platform enum
        """
        url_lower = url.lower()

        if "exportgenius" in url_lower:
            return Platform.EXPORT_GENIUS
        elif "marketinside" in url_lower:
            return Platform.MARKETINSIDE
        else:
            return Platform.UNKNOWN

    @staticmethod
    def detect_page_type(url: str) -> PageType:
        """
        Detect page type from URL path

        Args:
            url: Full URL

        Returns:
            PageType enum
        """
        parsed = urlparse(url)
        path = parsed.path.lower()

        if "/company/" in path:
            return PageType.COMPANY
        elif "/country/" in path:
            return PageType.COUNTRY
        elif "/search-data/" in path:
            return PageType.SEARCH_DATA
        elif "/hs-code/" in path or "/hscode/" in path:
            return PageType.HS_CODE
        elif "/product/" in path:
            return PageType.PRODUCT
        else:
            return PageType.UNKNOWN

    @staticmethod
    def get_api_config(platform: Platform) -> Dict[str, str]:
        """Get API configuration for platform"""
        return UnifiedAPIClient.API_CONFIGS.get(platform, {})

    @staticmethod
    async def call_api(
        platform: Platform,
        endpoint_key: str,
        request_body: Dict[str, Any],
        timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Make API call to backend

        Args:
            platform: Platform enum (EG or MI)
            endpoint_key: Endpoint key from ENDPOINTS dict
            request_body: Request payload
            timeout: Request timeout in seconds

        Returns:
            API response as dict or None if failed
        """
        config = UnifiedAPIClient.get_api_config(platform)

        if not config or not config.get("api_base"):
            logger.error(f"No API config found for platform: {platform}")
            return None

        # Build full URL
        endpoint_path = UnifiedAPIClient.ENDPOINTS.get(endpoint_key)
        if not endpoint_path:
            logger.error(f"Unknown endpoint key: {endpoint_key}")
            return None

        api_url = f"{config['api_base']}{endpoint_path}"

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
        }

        # Add auth token if available
        if config.get("api_token"):
            headers["Authorization"] = f"Bearer {config['api_token']}"

        # Make request
        try:
            async with aiohttp.ClientSession() as session:
                logger.debug(f"Calling {platform.value} API: {endpoint_key}")

                async with session.post(
                    api_url,
                    json=request_body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:

                    if response.status == 200:
                        data = await response.json()
                        logger.debug(f"✓ {platform.value} API success: {endpoint_key}")
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"✗ {platform.value} API error: {response.status} - {error_text[:200]}"
                        )
                        return None

        except asyncio.TimeoutError:
            logger.error(f"✗ {platform.value} API timeout: {endpoint_key}")
            return None
        except Exception as e:
            logger.error(f"✗ {platform.value} API exception: {e}", exc_info=True)
            return None

    @staticmethod
    async def call_multiple_apis(
        platform: Platform,
        endpoints: List[tuple],  # List of (endpoint_key, request_body)
        timeout: int = 30
    ) -> List[Optional[Dict[str, Any]]]:
        """
        Make multiple concurrent API calls

        Args:
            platform: Platform enum
            endpoints: List of (endpoint_key, request_body) tuples
            timeout: Request timeout in seconds

        Returns:
            List of API responses (same order as input)
        """
        tasks = [
            UnifiedAPIClient.call_api(platform, endpoint_key, body, timeout)
            for endpoint_key, body in endpoints
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to None
        results = [
            result if not isinstance(result, Exception) else None
            for result in results
        ]

        return results


class CompanyPageStrategy:
    """Strategy for fetching company page data"""

    @staticmethod
    async def fetch(url: str, platform: Platform) -> str:
        """
        Fetch company data from API

        Args:
            url: Company page URL
            platform: Platform enum

        Returns:
            Formatted company data as text
        """
        # Extract company slug from URL
        company_slug = CompanyPageStrategy._extract_company_slug(url)

        if not company_slug:
            logger.error(f"Could not extract company slug from URL: {url}")
            return ""

        # Build request
        request_body = {
            "company_slug": company_slug,
            "include_shipments": True,
            "include_buyers": True,
            "include_suppliers": True,
            "limit_shipments": 20  # Limit to prevent massive data
        }

        # Call API
        logger.info(f"Fetching company data from {platform.value} API: {company_slug}")

        response = await UnifiedAPIClient.call_api(
            platform=platform,
            endpoint_key="company_data",
            request_body=request_body,
            timeout=30
        )

        if not response:
            logger.error(f"Failed to fetch company data for: {company_slug}")
            return ""

        # Format response as text
        formatted = CompanyPageStrategy._format_company_data(response, platform)

        return formatted

    @staticmethod
    def _extract_company_slug(url: str) -> Optional[str]:
        """Extract company slug from URL"""
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]

        # Find 'company' in path and get next part
        try:
            company_idx = path_parts.index('company')
            if company_idx + 1 < len(path_parts):
                return path_parts[company_idx + 1]
        except (ValueError, IndexError):
            pass

        return None

    @staticmethod
    def _format_company_data(data: Dict[str, Any], platform: Platform) -> str:
        """Format company data as text for embeddings"""
        lines = [f"[Company Data from {platform.value.upper()} API]\n"]

        # Company name
        company_name = data.get('company_name', 'Unknown Company')
        lines.append(f"Company: {company_name}\n")

        # Basic info
        if data.get('country'):
            lines.append(f"Country: {data['country']}\n")
        if data.get('address'):
            lines.append(f"Address: {data['address']}\n")

        # Trade statistics
        lines.append(f"\nTrade Statistics:")
        lines.append(f"Total Shipments: {data.get('total_shipments', 0):,}")
        lines.append(f"Total Import Value: ${data.get('total_import_value', 0):,.2f}")
        lines.append(f"Total Export Value: ${data.get('total_export_value', 0):,.2f}\n")

        # Top products
        if data.get('top_products'):
            lines.append(f"\nTop Products:")
            for i, product in enumerate(data['top_products'][:10], 1):
                lines.append(
                    f"{i}. {product.get('product_name', 'N/A')} "
                    f"({product.get('hs_code', 'N/A')}) - "
                    f"{product.get('shipment_count', 0)} shipments"
                )

        # Top buyers
        if data.get('top_buyers'):
            lines.append(f"\n\nTop Buyers:")
            for i, buyer in enumerate(data['top_buyers'][:10], 1):
                lines.append(
                    f"{i}. {buyer.get('buyer_name', 'N/A')} "
                    f"({buyer.get('country', 'N/A')}) - "
                    f"${buyer.get('total_value', 0):,.2f}"
                )

        # Top suppliers
        if data.get('top_suppliers'):
            lines.append(f"\n\nTop Suppliers:")
            for i, supplier in enumerate(data['top_suppliers'][:10], 1):
                lines.append(
                    f"{i}. {supplier.get('supplier_name', 'N/A')} "
                    f"({supplier.get('country', 'N/A')}) - "
                    f"${supplier.get('total_value', 0):,.2f}"
                )

        # Recent shipments
        if data.get('recent_shipments'):
            lines.append(f"\n\nRecent Shipments:")
            for i, shipment in enumerate(data['recent_shipments'][:20], 1):
                lines.append(
                    f"{i}. {shipment.get('product_description', 'N/A')[:100]}\n"
                    f"   Date: {shipment.get('date', 'N/A')}\n"
                    f"   HS Code: {shipment.get('hs_code', 'N/A')}\n"
                    f"   Value: ${shipment.get('value', 0):,.2f}\n"
                    f"   Quantity: {shipment.get('quantity', 'N/A')} {shipment.get('unit', '')}\n"
                )

        return "\n".join(lines)


class CountryPageStrategy:
    """Strategy for fetching country page data"""

    @staticmethod
    async def fetch(url: str, platform: Platform, data_type: str = "import") -> str:
        """
        Fetch country data from API

        Args:
            url: Country page URL
            platform: Platform enum
            data_type: "import" or "export"

        Returns:
            Formatted country data as text
        """
        # Extract country slug from URL
        country_slug = CountryPageStrategy._extract_country_slug(url)

        if not country_slug:
            logger.error(f"Could not extract country slug from URL: {url}")
            return ""

        # Build request
        request_body = {
            "country_slug": country_slug,
            "data_type": data_type,
            "include_statistics": True,
            "include_top_products": True,
            "include_top_partners": True,
            "limit": 20
        }

        # Determine endpoint
        endpoint_key = (
            "country_import_data" if data_type == "import"
            else "country_export_data"
        )

        # Call API
        logger.info(
            f"Fetching {data_type} data for {country_slug} from {platform.value} API"
        )

        response = await UnifiedAPIClient.call_api(
            platform=platform,
            endpoint_key=endpoint_key,
            request_body=request_body,
            timeout=30
        )

        if not response:
            logger.error(f"Failed to fetch country data for: {country_slug}")
            return ""

        # Format response
        formatted = CountryPageStrategy._format_country_data(
            response,
            platform,
            country_slug,
            data_type
        )

        return formatted

    @staticmethod
    def _extract_country_slug(url: str) -> Optional[str]:
        """Extract country slug from URL"""
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]

        # Find 'country' in path and get next part
        try:
            country_idx = path_parts.index('country')
            if country_idx + 1 < len(path_parts):
                return path_parts[country_idx + 1]
        except (ValueError, IndexError):
            pass

        return None

    @staticmethod
    def _format_country_data(
        data: Dict[str, Any],
        platform: Platform,
        country_slug: str,
        data_type: str
    ) -> str:
        """Format country data as text"""
        lines = [
            f"[Country {data_type.upper()} Data from {platform.value.upper()} API]\n"
        ]

        # Country name
        country_name = data.get('country_name', country_slug.title())
        lines.append(f"Country: {country_name}")
        lines.append(f"Data Type: {data_type.upper()}\n")

        # Statistics
        lines.append(f"Trade Statistics:")
        lines.append(f"Total Shipments: {data.get('total_shipments', 0):,}")
        lines.append(f"Total Value: ${data.get('total_value', 0):,.2f}")
        lines.append(f"Date Range: {data.get('date_from', 'N/A')} to {data.get('date_to', 'N/A')}\n")

        # Top products
        if data.get('top_products'):
            lines.append(f"\nTop {data_type.title()} Products:")
            for i, product in enumerate(data['top_products'][:15], 1):
                lines.append(
                    f"{i}. {product.get('product_name', 'N/A')} "
                    f"(HS: {product.get('hs_code', 'N/A')}) - "
                    f"${product.get('total_value', 0):,.2f}"
                )

        # Top partners
        if data.get('top_partners'):
            partner_label = "Suppliers" if data_type == "import" else "Buyers"
            lines.append(f"\n\nTop {partner_label} (Countries):")
            for i, partner in enumerate(data['top_partners'][:15], 1):
                lines.append(
                    f"{i}. {partner.get('country', 'N/A')} - "
                    f"${partner.get('total_value', 0):,.2f} "
                    f"({partner.get('shipment_count', 0):,} shipments)"
                )

        return "\n".join(lines)


class SearchDataPageStrategy:
    """Strategy for fetching search data pages (most complex)"""

    @staticmethod
    async def fetch(url: str, platform: Platform) -> str:
        """
        Fetch search data from multiple endpoints

        Args:
            url: Search data URL with query parameters
            platform: Platform enum

        Returns:
            Formatted search data as text
        """
        from urllib.parse import parse_qs

        # Parse URL parameters
        params = SearchDataPageStrategy._parse_search_params(url)

        if not params:
            logger.error(f"Could not parse search params from URL: {url}")
            return ""

        # Build base request body
        base_request = SearchDataPageStrategy._build_request_body(params)

        # Determine which endpoints to call based on tab
        tab = params.get('tab', 'trade')
        endpoints_to_call = SearchDataPageStrategy._get_endpoints_for_tab(
            tab,
            params,
            base_request
        )

        # Make concurrent API calls
        logger.info(
            f"Fetching search data from {platform.value} API: "
            f"{len(endpoints_to_call)} concurrent calls"
        )

        results = await UnifiedAPIClient.call_multiple_apis(
            platform=platform,
            endpoints=endpoints_to_call,
            timeout=30
        )

        # Format results
        formatted = SearchDataPageStrategy._format_search_results(
            results,
            endpoints_to_call,
            params,
            platform
        )

        return formatted

    @staticmethod
    def _parse_search_params(url: str) -> Dict[str, Any]:
        """Parse search data URL parameters"""
        from urllib.parse import parse_qs

        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        # Extract tab from path
        path_parts = [p for p in parsed.path.split('/') if p]
        tab = path_parts[-1] if path_parts else 'trade'

        # Flatten query params
        params = {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}
        params['tab'] = tab

        return params

    @staticmethod
    def _build_request_body(params: Dict[str, Any]) -> Dict[str, Any]:
        """Build API request body from URL parameters"""

        # Convert type parameter to data_type
        type_param = params.get('type', 'import')
        if 'mirror' in type_param.lower():
            data_type = f"{type_param.lower()}s"
        else:
            data_type = f"detailed_{type_param.lower()}s"

        # Determine list_type based on tab
        tab = params.get('tab', 'trade')
        if tab in ['buyers', 'suppliers']:
            list_type = 'buyer_supplier'
        else:
            list_type = 'importer_exporter'

        # Build body
        body = {
            "data_type": data_type,
            "list_type": list_type,
            "country": params.get('country', ''),
        }

        # Add optional parameters
        optional_params = [
            'product', 'hs_code', 'hs_code_filter',
            'importer', 'exporter', 'supplier', 'buyer',
            'origin_country', 'destination_country',
            'port_of_loading', 'port_of_unloading',
            'state', 'city', 'from', 'to'
        ]

        for param in optional_params:
            if param in params and params[param]:
                body[param] = params[param]

        return body

    @staticmethod
    def _get_endpoints_for_tab(
        tab: str,
        params: Dict[str, Any],
        base_request: Dict[str, Any]
    ) -> List[tuple]:
        """Determine which endpoints to call based on tab"""

        endpoints = []

        # Always call main product endpoint
        endpoints.append(('search_data_product', base_request.copy()))

        # Conditional calls based on params and tab
        has_product = 'product' in params or 'hs_code' in params
        has_importer = 'importer' in params
        has_exporter = 'exporter' in params

        # Importers endpoint
        if has_importer or (has_product and not has_exporter):
            endpoints.append(('search_data_importers', base_request.copy()))

        # Exporters endpoint
        if has_exporter or (has_product and not has_importer):
            endpoints.append(('search_data_exporters', base_request.copy()))

        # Always call buyers and suppliers
        endpoints.append(('search_data_buyers', base_request.copy()))
        endpoints.append(('search_data_suppliers', base_request.copy()))

        # Totals endpoint (depends on data_type)
        data_type = base_request.get('data_type', '')
        if 'import' in data_type:
            endpoints.append(('search_data_total_importers_suppliers', base_request.copy()))
        else:
            endpoints.append(('search_data_total_exporters_buyers', base_request.copy()))

        return endpoints

    @staticmethod
    def _format_search_results(
        results: List[Optional[Dict]],
        endpoints: List[tuple],
        params: Dict[str, Any],
        platform: Platform
    ) -> str:
        """Format search results as text"""
        lines = [f"[Search Data from {platform.value.upper()} API]\n"]

        # Add search parameters
        lines.append(f"Search Query:")
        lines.append(f"  Type: {params.get('type', 'N/A')}")
        lines.append(f"  Country: {params.get('country', 'Universal')}")
        if params.get('product'):
            lines.append(f"  Product: {params['product']}")
        if params.get('hs_code'):
            lines.append(f"  HS Code: {params['hs_code']}")
        lines.append("")

        # Process each result
        for i, (endpoint_info, result) in enumerate(zip(endpoints, results)):
            endpoint_key = endpoint_info[0]

            if not result:
                continue

            # Format based on endpoint type
            if endpoint_key == 'search_data_product':
                lines.append(SearchDataPageStrategy._format_trade_data(result))

            elif endpoint_key == 'search_data_importers':
                lines.append(SearchDataPageStrategy._format_importers(result))

            elif endpoint_key == 'search_data_exporters':
                lines.append(SearchDataPageStrategy._format_exporters(result))

            elif endpoint_key == 'search_data_buyers':
                lines.append(SearchDataPageStrategy._format_buyers(result))

            elif endpoint_key == 'search_data_suppliers':
                lines.append(SearchDataPageStrategy._format_suppliers(result))

            elif 'total' in endpoint_key:
                lines.append(SearchDataPageStrategy._format_totals(result))

        return "\n".join(lines)

    @staticmethod
    def _format_trade_data(data: Dict[str, Any]) -> str:
        """Format main trade data"""
        lines = ["\n=== TRADE DATA ==="]

        lines.append(f"Total Shipments: {data.get('total_shipments', 0):,}")
        lines.append(f"Total Value: ${data.get('total_value_usd', 0):,.2f}")

        if data.get('date_range'):
            lines.append(f"Date Range: {data['date_range'][0]} to {data['date_range'][1]}")

        # Top shipment records (limit to 20 to prevent massive context)
        products = data.get('products', [])[:20]
        if products:
            lines.append(f"\nTop {len(products)} Shipment Records:")
            for i, product in enumerate(products, 1):
                lines.append(
                    f"\n{i}. {product.get('product_description', 'N/A')[:150]}\n"
                    f"   Date: {product.get('date', 'N/A')}\n"
                    f"   Importer: {product.get('importer', 'N/A')}\n"
                    f"   Exporter: {product.get('exporter', 'N/A')}\n"
                    f"   Value: ${product.get('total_value_usd', 0):,.2f}\n"
                    f"   HS Code: {product.get('hs_code', 'N/A')}\n"
                    f"   Origin: {product.get('origin_country', 'N/A')}\n"
                    f"   Destination: {product.get('destination_country', 'N/A')}"
                )

        return "\n".join(lines)

    @staticmethod
    def _format_importers(data: Dict[str, Any]) -> str:
        """Format importers data"""
        lines = ["\n=== TOP IMPORTERS ==="]

        importers = data.get('importers', [])[:15]
        for i, importer in enumerate(importers, 1):
            lines.append(
                f"{i}. {importer.get('importer_name', 'N/A')}\n"
                f"   Country: {importer.get('country', 'N/A')}\n"
                f"   Shipments: {importer.get('total_shipments', 0):,}\n"
                f"   Value: ${importer.get('total_value_usd', 0):,.2f}"
            )

        return "\n".join(lines)

    @staticmethod
    def _format_exporters(data: Dict[str, Any]) -> str:
        """Format exporters data"""
        lines = ["\n=== TOP EXPORTERS ==="]

        exporters = data.get('exporters', [])[:15]
        for i, exporter in enumerate(exporters, 1):
            lines.append(
                f"{i}. {exporter.get('exporter_name', 'N/A')}\n"
                f"   Country: {exporter.get('country', 'N/A')}\n"
                f"   Shipments: {exporter.get('total_shipments', 0):,}\n"
                f"   Value: ${exporter.get('total_value_usd', 0):,.2f}"
            )

        return "\n".join(lines)

    @staticmethod
    def _format_buyers(data: Dict[str, Any]) -> str:
        """Format buyers data"""
        lines = ["\n=== TOP BUYERS ==="]

        buyers = data.get('buyers', [])[:15]
        for i, buyer in enumerate(buyers, 1):
            lines.append(
                f"{i}. {buyer.get('buyer_name', 'N/A')}\n"
                f"   Country: {buyer.get('country', 'N/A')}\n"
                f"   Shipments: {buyer.get('total_shipments', 0):,}\n"
                f"   Value: ${buyer.get('total_value_usd', 0):,.2f}"
            )

        return "\n".join(lines)

    @staticmethod
    def _format_suppliers(data: Dict[str, Any]) -> str:
        """Format suppliers data"""
        lines = ["\n=== TOP SUPPLIERS ==="]

        suppliers = data.get('suppliers', [])[:15]
        for i, supplier in enumerate(suppliers, 1):
            lines.append(
                f"{i}. {supplier.get('supplier_name', 'N/A')}\n"
                f"   Country: {supplier.get('country', 'N/A')}\n"
                f"   Shipments: {supplier.get('total_shipments', 0):,}\n"
                f"   Value: ${supplier.get('total_value_usd', 0):,.2f}"
            )

        return "\n".join(lines)

    @staticmethod
    def _format_totals(data: Dict[str, Any]) -> str:
        """Format totals data"""
        lines = ["\n=== TOTALS ==="]

        if 'totalImporters' in data:
            lines.append(f"Total Importers: {data['totalImporters']:,}")
        if 'totalForeignSuppliers' in data:
            lines.append(f"Total Foreign Suppliers: {data['totalForeignSuppliers']:,}")
        if 'totalExporters' in data:
            lines.append(f"Total Exporters: {data['totalExporters']:,}")
        if 'total_foreign_buyers' in data:
            lines.append(f"Total Foreign Buyers: {data['total_foreign_buyers']:,}")

        return "\n".join(lines)


# ============================================================================
# MAIN CONTENT FETCHER (Routes to correct strategy)
# ============================================================================

async def fetch_content_from_url(url: str) -> str:
    """
    Main entry point: Fetch content from any URL type

    Automatically detects:
    1. Platform (Export Genius vs Marketinside)
    2. Page Type (Company, Country, Search Data)
    3. Routes to appropriate strategy

    Args:
        url: Full URL to fetch

    Returns:
        Formatted content as text for embeddings
    """
    # Detect platform
    platform = UnifiedAPIClient.detect_platform(url)
    if platform == Platform.UNKNOWN:
        logger.error(f"Unknown platform for URL: {url}")
        return ""

    # Detect page type
    page_type = UnifiedAPIClient.detect_page_type(url)

    logger.info(f"Detected: {platform.value} | {page_type.value} | URL: {url}")

    # Route to appropriate strategy
    try:
        if page_type == PageType.COMPANY:
            return await CompanyPageStrategy.fetch(url, platform)

        elif page_type == PageType.COUNTRY:
            # TODO: Detect data_type from URL or query params
            return await CountryPageStrategy.fetch(url, platform, data_type="import")

        elif page_type == PageType.SEARCH_DATA:
            return await SearchDataPageStrategy.fetch(url, platform)

        else:
            logger.error(f"Unsupported page type: {page_type}")
            return ""

    except Exception as e:
        logger.error(f"Error fetching content: {e}", exc_info=True)
        return ""
