"""
Production-Grade Unified API Client for Export Genius and Marketinside

Features:
- Single codebase for both platforms (same backend, different domains)
- Concurrent API calls with error handling
- Retry logic with exponential backoff
- Request/response logging
- Graceful degradation (partial failures handled)
- Type hints for better IDE support
- Configuration via environment variables
"""

import asyncio
import aiohttp
import os
import time
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse, parse_qs
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

from chatbot.config.logging_config import get_logger

logger = get_logger(__name__)


# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================

class Platform(Enum):
    """Platform enumeration"""
    EXPORT_GENIUS = "exportgenius"
    MARKETINSIDE = "marketinside"
    UNKNOWN = "unknown"


class PageType(Enum):
    """Page type enumeration"""
    COMPANY = "company"
    COUNTRY = "country"
    COUNTRY_TO_COUNTRY = "country_to_country"
    HS_CODE = "hs_code"
    SEARCH_DATA = "search_data"
    UNKNOWN = "unknown"


@dataclass
class APIConfig:
    """API configuration for a platform"""
    domain: str
    api_base_url: str
    bearer_token: str
    timeout: int = 30
    max_retries: int = 3


@dataclass
class APIResponse:
    """Standardized API response"""
    success: bool
    data: Optional[Dict[str, Any]]
    error: Optional[str]
    endpoint: str
    duration: float


# ============================================================================
# BASE API CLIENT (Handles HTTP, Retries, Errors)
# ============================================================================

class BaseAPIClient:
    """
    Base HTTP client with retry logic, error handling, and logging

    This is the foundation - all API calls go through this
    """

    def __init__(self, config: APIConfig):
        """
        Initialize base client

        Args:
            config: API configuration
        """
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication (matches browser exactly)"""
        return {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'authorization': f'Bearer {self.config.bearer_token}',
            'content-type': 'application/json',
            'origin': f'https://www.{self.config.domain}',
            'referer': f'https://www.{self.config.domain}/',
            'priority': 'u=1, i',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def call_endpoint(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        retry_count: int = 0
    ) -> APIResponse:
        """
        Make API call with retry logic and error handling

        Args:
            endpoint: API endpoint path (e.g., "/company-overview")
            payload: Request body
            retry_count: Current retry attempt

        Returns:
            APIResponse object with success/failure info
        """
        url = f"{self.config.api_base_url}{endpoint}"
        start_time = time.time()

        try:
            session = await self._get_session()

            async with session.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                duration = time.time() - start_time

                if response.status == 200:
                    data = await response.json()
                    logger.debug(
                        f"✓ {endpoint} - {response.status} - {duration:.2f}s"
                    )
                    return APIResponse(
                        success=True,
                        data=data,
                        error=None,
                        endpoint=endpoint,
                        duration=duration
                    )
                else:
                    error_text = await response.text()
                    logger.warning(
                        f"✗ {endpoint} - {response.status} - {error_text[:100]}"
                    )

                    # Retry on 5xx errors
                    if response.status >= 500 and retry_count < self.config.max_retries:
                        return await self._retry_request(endpoint, payload, retry_count)

                    return APIResponse(
                        success=False,
                        data=None,
                        error=f"HTTP {response.status}: {error_text[:200]}",
                        endpoint=endpoint,
                        duration=duration
                    )

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            logger.warning(f"✗ {endpoint} - Timeout after {duration:.1f}s")

            if retry_count < self.config.max_retries:
                return await self._retry_request(endpoint, payload, retry_count)

            return APIResponse(
                success=False,
                data=None,
                error=f"Timeout after {duration:.1f}s",
                endpoint=endpoint,
                duration=duration
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"✗ {endpoint} - Error: {e}", exc_info=True)

            if retry_count < self.config.max_retries:
                return await self._retry_request(endpoint, payload, retry_count)

            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                endpoint=endpoint,
                duration=duration
            )

    async def _retry_request(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        retry_count: int
    ) -> APIResponse:
        """Retry request with exponential backoff"""
        wait_time = 2 ** retry_count  # 2s, 4s, 8s
        logger.info(
            f"Retrying {endpoint} in {wait_time}s... "
            f"(attempt {retry_count + 1}/{self.config.max_retries})"
        )
        await asyncio.sleep(wait_time)
        return await self.call_endpoint(endpoint, payload, retry_count + 1)

    async def call_endpoints_parallel(
        self,
        endpoints: List[Tuple[str, Dict[str, Any]]]
    ) -> List[APIResponse]:
        """
        Call multiple endpoints in parallel

        Args:
            endpoints: List of (endpoint_path, payload) tuples

        Returns:
            List of APIResponse objects (same order as input)
        """
        tasks = [
            self.call_endpoint(endpoint, payload)
            for endpoint, payload in endpoints
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to APIResponse
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(APIResponse(
                    success=False,
                    data=None,
                    error=str(result),
                    endpoint=endpoints[i][0],
                    duration=0.0
                ))
            else:
                processed_results.append(result)

        return processed_results


# ============================================================================
# UNIFIED API CLIENT (Platform-Aware)
# ============================================================================

class UnifiedAPIClient:
    """
    Unified API client that works with both Export Genius and Marketinside

    Automatically detects platform from URL and routes to correct backend
    """

    # Country name to ISO code mapping (fallback - will be enriched from API)
    COUNTRY_NAME_TO_ISO = {
        "argentina": "AR", "vietnam": "VN", "china": "CN", "india": "IN",
        "usa": "US", "united-states": "US", "brazil": "BR", "mexico": "MX",
        "germany": "DE", "france": "FR", "italy": "IT", "spain": "ES",
        "united-kingdom": "GB", "uk": "GB", "japan": "JP", "south-korea": "KR",
        "korea": "KR", "australia": "AU", "canada": "CA", "russia": "RU",
        "turkey": "TR", "indonesia": "ID", "thailand": "TH", "malaysia": "MY",
        "singapore": "SG", "philippines": "PH", "pakistan": "PK", "bangladesh": "BD",
        "egypt": "EG", "south-africa": "ZA", "saudi-arabia": "SA", "uae": "AE",
        "united-arab-emirates": "AE", "netherlands": "NL", "belgium": "BE",
        "poland": "PL", "sweden": "SE", "norway": "NO", "denmark": "DK",
        "finland": "FI", "greece": "GR", "portugal": "PT", "chile": "CL",
        "colombia": "CO", "peru": "PE", "venezuela": "VE", "ecuador": "EC",
        "uruguay": "UY", "paraguay": "PY", "bolivia": "BO", "new-zealand": "NZ",
        "israel": "IL", "iran": "IR", "iraq": "IQ", "kuwait": "KW",
        "qatar": "QA", "oman": "OM", "bahrain": "BH", "jordan": "JO",
        "lebanon": "LB", "syria": "SY", "yemen": "YE", "morocco": "MA",
        "algeria": "DZ", "tunisia": "TN", "libya": "LY", "sudan": "SD",
        "ethiopia": "ET", "kenya": "KE", "nigeria": "NG", "ghana": "GH",
        "tanzania": "TZ", "uganda": "UG", "zimbabwe": "ZW", "zambia": "ZM",
        "mozambique": "MZ", "angola": "AO", "cameroon": "CM", "ivory-coast": "CI",
        "senegal": "SN", "botswana": "BW", "namibia": "NA", "mauritius": "MU",
        "madagascar": "MG", "kazakhstan": "KZ", "uzbekistan": "UZ", "ukraine": "UA",
        "belarus": "BY", "romania": "RO", "czech-republic": "CZ", "czechia": "CZ",
        "hungary": "HU", "austria": "AT", "switzerland": "CH", "ireland": "IE",
        "croatia": "HR", "serbia": "RS", "bulgaria": "BG", "slovakia": "SK",
        "slovenia": "SI", "lithuania": "LT", "latvia": "LV", "estonia": "EE",
        "iceland": "IS", "luxembourg": "LU", "malta": "MT", "cyprus": "CY",
        "albania": "AL", "macedonia": "MK", "north-macedonia": "MK", "bosnia": "BA",
        "bosnia-herzegovina": "BA", "montenegro": "ME", "moldova": "MD",
        "armenia": "AM", "georgia": "GE", "azerbaijan": "AZ", "turkmenistan": "TM",
        "kyrgyzstan": "KG", "tajikistan": "TJ", "mongolia": "MN", "nepal": "NP",
        "sri-lanka": "LK", "myanmar": "MM", "burma": "MM", "cambodia": "KH",
        "laos": "LA", "brunei": "BN", "maldives": "MV", "afghanistan": "AF",
        "bhutan": "BT", "taiwan": "TW", "hong-kong": "HK", "macau": "MO",
    }

    # Platform configurations
    PLATFORMS = {
        Platform.EXPORT_GENIUS: lambda: APIConfig(
            domain="exportgenius.in",
            api_base_url=os.getenv(
                "EXPORTGENIUS_API_URL",
                "https://api-dp.exportgenius.in/api/v1/users"
            ),
            # Try new name first, fallback to old name for backward compatibility
            bearer_token=(
                os.getenv("EXPORTGENIUS_API_TOKEN") or
                os.getenv("EXPORTGENIUS_BEARER_TOKEN") or
                ""
            ),
            timeout=30,
            max_retries=3
        ),
        Platform.MARKETINSIDE: lambda: APIConfig(
            domain="marketinsidedata.com",
            api_base_url=os.getenv(
                "MARKETINSIDE_API_URL",
                "https://api-dp.marketinsidedata.com/api/v1/users"
            ),
            # Try new name first, fallback to old name for backward compatibility
            bearer_token=(
                os.getenv("MARKETINSIDE_API_TOKEN") or
                os.getenv("MARKETINSIDE_BEARER_TOKEN") or
                ""
            ),
            timeout=30,
            max_retries=3
        )
    }

    # Endpoint definitions (same for both platforms)
    ENDPOINTS = {
        # Company endpoints
        "company_overview": "/company-overview",
        "company_countries": "/company-countries",
        "company_turnover": "/company-turnover",
        "company_commodities": "/company-commodities",
        "company_competitors": "/company-competitors",
        "company_ports": "/company-top-ports",
        "company_shipments": "/company-shipments",
        "company_faqs": "/company-faqs",

        # Country endpoints
        "country_stats": "/country-stats",
        "country_importers": "/country-importer-exporter",
        "country_partners": "/country-top-partners",
        "country_ports": "/country-ports",
        "country_chapters": "/country-chapters",
        "country_commodities": "/country-commodities",
        "country_faqs": "/country-faqs",
        "country_buyer_supplier": "/country-buyer-supplier",
        "country_monthly": "/country-monthly",

        # Country-to-Country endpoints
        "c2c_stats": "/country-to-country-stats",
        "c2c_chapters": "/country-to-country-chapters",
        "c2c_companies": "/country-to-country-importers-exporters",
        "c2c_shipments": "/country-to-country-shipments",
        "c2c_ports": "/country-to-country-ports",
        "c2c_monthly": "/country-to-country-monthly-trends",
        "c2c_countries_list": "/detailed-countries-list",
        "c2c_origin_dest_list": "/origin-destination-country-list",

        # HS Code hierarchy endpoints
        "hs_chapter_details": "/chapter-details",
        "hs_heading_details": "/heading-details",
        "hs_subheading_details": "/sub-heading-details",
        "hs_code_details": "/hs-code-details",
        "hs_heading_list": "/heading-lists",
        "hs_subheading_list": "/sub-heading-lists",
        "hs_code_list": "/hs-code-lists",

        # Search data endpoints
        "search_product": "/search-data-product",
        "search_importers": "/search-data-importers",
        "search_exporters": "/search-data-exporters",
        "search_buyers": "/search-data-buyers",
        "search_suppliers": "/search-data-suppliers",
        "search_total_imp_sup": "/search-data-total-importers-suppliers",
        "search_total_exp_buy": "/search-data-total-exporters-buyers",
        "search_hscode_list": "/search-data-hscode-list",
        "search_country_list": "/search-data-country-list",
        "search_ports_list": "/search-data-ports-list",
    }

    def __init__(self):
        """Initialize unified client"""
        self._clients: Dict[Platform, BaseAPIClient] = {}
        self._country_mapping_loaded = False  # Track if we loaded from API

    def _get_client(self, platform: Platform) -> BaseAPIClient:
        """Get or create client for platform"""
        if platform not in self._clients:
            config = self.PLATFORMS[platform]()
            self._clients[platform] = BaseAPIClient(config)
        return self._clients[platform]

    async def close_all(self):
        """Close all platform clients"""
        for client in self._clients.values():
            await client.close()

    @staticmethod
    def detect_platform(url: str) -> Platform:
        """Detect platform from URL"""
        url_lower = url.lower()
        if "exportgenius" in url_lower:
            return Platform.EXPORT_GENIUS
        elif "marketinside" in url_lower:
            return Platform.MARKETINSIDE
        return Platform.UNKNOWN

    @staticmethod
    def detect_page_type(url: str) -> PageType:
        """Detect page type from URL"""
        parsed = urlparse(url)
        path = parsed.path.lower()

        if "/company/" in path or "/company-data/" in path:
            return PageType.COMPANY
        elif "/cntry/" in path:
            return PageType.COUNTRY_TO_COUNTRY
        elif "/chapter/" in path:
            return PageType.HS_CODE
        elif "/country/" in path or "/country-data/" in path:
            return PageType.COUNTRY
        elif "/search-data/" in path:
            return PageType.SEARCH_DATA
        return PageType.UNKNOWN

    async def fetch_company_data(
        self,
        url: str,
        platform: Platform
    ) -> Dict[str, Any]:
        """
        Fetch all company data (8 endpoints: 1 sequential + 7 parallel)

        Args:
            url: Company URL
            platform: Platform enum

        Returns:
            Combined data from all endpoints
        """
        # Extract company code from URL
        company_code = self._extract_company_code(url)
        if not company_code:
            return {"error": "Could not extract company code from URL"}

        logger.info(
            f"Fetching company data from {platform.value}: {company_code[:12]}..."
        )

        client = self._get_client(platform)

        # Step 1: Fetch overview first (needed for i_e_code and country_code)
        overview_response = await client.call_endpoint(
            self.ENDPOINTS["company_overview"],
            {"company_code": company_code}
        )

        if not overview_response.success:
            return {
                "error": "Failed to fetch company overview",
                "details": overview_response.error
            }

        overview = overview_response.data
        ie_code = overview.get("i_e_code")
        country_code = overview.get("country_code", [])

        # Ensure country_code is a list
        if isinstance(country_code, str):
            country_code = [country_code]

        logger.info(f"  ✓ Overview fetched - IE: {ie_code}, Countries: {country_code}")

        # Step 2: Fetch remaining 7 endpoints in parallel
        base_payload = {
            "company_code": company_code,
            "country_code": country_code,
            "i_e_code": ie_code
        }

        parallel_endpoints = [
            (self.ENDPOINTS["company_countries"], base_payload),
            (self.ENDPOINTS["company_turnover"], base_payload),
            (self.ENDPOINTS["company_commodities"], base_payload),
            (self.ENDPOINTS["company_competitors"], base_payload),
            (self.ENDPOINTS["company_ports"], base_payload),
            (self.ENDPOINTS["company_shipments"], base_payload),
            (self.ENDPOINTS["company_faqs"], base_payload),
        ]

        logger.info("  📡 Fetching 7 endpoints in parallel...")
        start = time.time()
        results = await client.call_endpoints_parallel(parallel_endpoints)
        elapsed = time.time() - start

        # Count successes
        successes = sum(1 for r in results if r.success)
        logger.info(
            f"  ✓ Completed: {successes}/7 successful in {elapsed:.2f}s"
        )

        # Combine all data
        return {
            "company_code": company_code,
            "platform": platform.value,
            "fetched_at": datetime.now().isoformat(),
            "overview": overview,
            "countries": results[0].data if results[0].success else {"error": results[0].error},
            "turnover": results[1].data if results[1].success else {"error": results[1].error},
            "commodities": results[2].data if results[2].success else {"error": results[2].error},
            "competitors": results[3].data if results[3].success else {"error": results[3].error},
            "ports": results[4].data if results[4].success else {"error": results[4].error},
            "shipments": results[5].data if results[5].success else {"error": results[5].error},
            "faqs": results[6].data if results[6].success else {"error": results[6].error},
        }

    async def fetch_country_data(
        self,
        url: str,
        platform: Platform,
        data_type: str = "import"
    ) -> Dict[str, Any]:
        """
        Fetch all country data (9 endpoints in parallel)

        Args:
            url: Country URL
            platform: Platform enum
            data_type: "import" or "export"

        Returns:
            Combined data from all endpoints
        """
        # Extract country code from URL
        country_code = await self._extract_country_code(url, platform)
        if not country_code:
            return {"error": "Could not extract country code from URL"}

        logger.info(
            f"Fetching {data_type} data for {country_code} from {platform.value}"
        )

        client = self._get_client(platform)

        # All 9 endpoints in parallel
        base_payload = {
            "country_code": country_code,
            "data_type": data_type
        }

        parallel_endpoints = [
            (self.ENDPOINTS["country_stats"], base_payload),
            (self.ENDPOINTS["country_importers"], base_payload),
            (self.ENDPOINTS["country_partners"], base_payload),
            (self.ENDPOINTS["country_ports"], base_payload),
            (self.ENDPOINTS["country_chapters"], base_payload),
            (self.ENDPOINTS["country_commodities"], base_payload),
            (self.ENDPOINTS["country_faqs"], base_payload),
            (self.ENDPOINTS["country_buyer_supplier"], base_payload),
            (self.ENDPOINTS["country_monthly"], base_payload),
        ]

        logger.info("  📡 Fetching 9 endpoints in parallel...")
        start = time.time()
        results = await client.call_endpoints_parallel(parallel_endpoints)
        elapsed = time.time() - start

        successes = sum(1 for r in results if r.success)
        logger.info(
            f"  ✓ Completed: {successes}/9 successful in {elapsed:.2f}s"
        )

        # Combine all data
        return {
            "country_code": country_code,
            "data_type": data_type,
            "platform": platform.value,
            "fetched_at": datetime.now().isoformat(),
            "stats": results[0].data if results[0].success else {"error": results[0].error},
            "importers": results[1].data if results[1].success else {"error": results[1].error},
            "partners": results[2].data if results[2].success else {"error": results[2].error},
            "ports": results[3].data if results[3].success else {"error": results[3].error},
            "chapters": results[4].data if results[4].success else {"error": results[4].error},
            "commodities": results[5].data if results[5].success else {"error": results[5].error},
            "faqs": results[6].data if results[6].success else {"error": results[6].error},
            "buyer_supplier": results[7].data if results[7].success else {"error": results[7].error},
            "monthly": results[8].data if results[8].success else {"error": results[8].error},
        }

    async def fetch_search_data(
        self,
        url: str,
        platform: Platform
    ) -> Dict[str, Any]:
        """
        Fetch search data (6+ endpoints in parallel)

        Args:
            url: Search data URL with query parameters
            platform: Platform enum

        Returns:
            Combined data from all endpoints
        """
        # Parse URL parameters
        params = self._parse_search_params(url)

        logger.info(
            f"Fetching search data from {platform.value}: "
            f"{params.get('type')}/{params.get('country')}/{params.get('product', 'N/A')}"
        )

        client = self._get_client(platform)

        # Build request body
        request_body = self._build_search_request(params)

        # Determine which endpoints to call
        endpoints_to_call = self._get_search_endpoints(params, request_body)

        logger.info(f"  📡 Fetching {len(endpoints_to_call)} endpoints in parallel...")
        start = time.time()
        results = await client.call_endpoints_parallel(endpoints_to_call)
        elapsed = time.time() - start

        successes = sum(1 for r in results if r.success)
        logger.info(
            f"  ✓ Completed: {successes}/{len(endpoints_to_call)} successful in {elapsed:.2f}s"
        )

        # Map results to named fields
        result_map = {}
        for i, (endpoint, _) in enumerate(endpoints_to_call):
            # Extract endpoint name from path
            endpoint_name = endpoint.split('/')[-1].replace('-', '_')
            result_map[endpoint_name] = results[i].data if results[i].success else {"error": results[i].error}

        return {
            "search_params": params,
            "platform": platform.value,
            "fetched_at": datetime.now().isoformat(),
            **result_map
        }

    async def fetch_country_to_country_data(
        self,
        url: str,
        platform: Platform
    ) -> Dict[str, Any]:
        """
        Fetch country-to-country bilateral trade data (6 endpoints in parallel)

        Args:
            url: Country-to-country URL (e.g., /en/cntry/Belgium-export-France)
            platform: Platform enum

        Returns:
            Combined data from all endpoints
        """
        # Parse URL to extract countries and direction
        params = self._parse_c2c_url(url)

        if "error" in params:
            return params

        origin_country = params["origin_country"]
        destination_country = params["destination_country"]
        data_type = params["data_type"]

        logger.info(
            f"Fetching {data_type} data: {origin_country} → {destination_country} "
            f"from {platform.value}"
        )

        client = self._get_client(platform)

        # Build request body (conditional field assignment based on data_type)
        base_payload = {
            "data_type": data_type,
            "country_name": origin_country,
        }

        # Add origin_country for import, destination_country for export
        if data_type == "import":
            base_payload["origin_country"] = destination_country
        else:  # export
            base_payload["destination_country"] = destination_country

        # All 6 endpoints in parallel
        parallel_endpoints = [
            (self.ENDPOINTS["c2c_stats"], base_payload),
            (self.ENDPOINTS["c2c_chapters"], base_payload),
            (self.ENDPOINTS["c2c_companies"], base_payload),
            (self.ENDPOINTS["c2c_shipments"], base_payload),
            (self.ENDPOINTS["c2c_ports"], base_payload),
            (self.ENDPOINTS["c2c_monthly"], base_payload),
        ]

        logger.info("  📡 Fetching 6 endpoints in parallel...")
        start = time.time()
        results = await client.call_endpoints_parallel(parallel_endpoints)
        elapsed = time.time() - start

        successes = sum(1 for r in results if r.success)
        logger.info(
            f"  ✓ Completed: {successes}/6 successful in {elapsed:.2f}s"
        )

        # Combine all data
        return {
            "origin_country": origin_country,
            "destination_country": destination_country,
            "data_type": data_type,
            "platform": platform.value,
            "fetched_at": datetime.now().isoformat(),
            "stats": results[0].data if results[0].success else {"error": results[0].error},
            "chapters": results[1].data if results[1].success else {"error": results[1].error},
            "companies": results[2].data if results[2].success else {"error": results[2].error},
            "shipments": results[3].data if results[3].success else {"error": results[3].error},
            "ports": results[4].data if results[4].success else {"error": results[4].error},
            "monthly_trends": results[5].data if results[5].success else {"error": results[5].error},
        }

    async def fetch_hs_code_data(
        self,
        url: str,
        platform: Platform
    ) -> Dict[str, Any]:
        """
        Fetch HS code hierarchy data (automatic endpoint selection based on code length)

        Args:
            url: HS code chapter URL (e.g., /en/chapter/botswana-import-hs-code-27)
            platform: Platform enum

        Returns:
            Combined data from all relevant endpoints
        """
        # Parse URL to extract country, direction, and HS code
        params = self._parse_hs_code_url(url)

        if "error" in params:
            return params

        country_name = params["country_name"]
        data_type = params["data_type"]
        hs_code = params["hs_code"]
        hierarchy_level = params["hierarchy_level"]

        logger.info(
            f"Fetching HS code data: {country_name} {data_type} - "
            f"Code {hs_code} ({hierarchy_level}) from {platform.value}"
        )

        client = self._get_client(platform)

        # Convert country name to ISO code for Marketinside API
        # The API requires 2-letter ISO codes (e.g., "AR" not "argentina")
        country_code_iso = self.COUNTRY_NAME_TO_ISO.get(
            country_name.lower().replace(" ", "-"),
            country_name.upper()  # Fallback: use uppercase if not in mapping
        )

        logger.info(f"  📍 Country mapping: '{country_name}' → '{country_code_iso}'")

        # Build request body - field name varies by hierarchy level
        # Chapter uses "chapter", Heading uses "heading", Subheading uses "sub_heading", HS Code uses "hs_code"
        base_payload = {
            "data_type": "custom_data",
            "direction": data_type,
            "country_code": country_code_iso,  # Use ISO code, not full name
        }

        # Determine which endpoints to call and add the correct field name
        # Chapter (2 digits): chapter-details + heading-list
        # Heading (4 digits): heading-details + sub-heading-list
        # Subheading (6 digits): sub-heading-details + hs-code-list
        # HS Code (8+ digits): hs-code-details only

        parallel_endpoints = []

        if hierarchy_level == "chapter":
            payload = {**base_payload, "chapter": hs_code}
            parallel_endpoints = [
                (self.ENDPOINTS["hs_chapter_details"], payload),
                (self.ENDPOINTS["hs_heading_list"], payload),
            ]
        elif hierarchy_level == "heading":
            payload = {**base_payload, "heading": hs_code}
            parallel_endpoints = [
                (self.ENDPOINTS["hs_heading_details"], payload),
                (self.ENDPOINTS["hs_subheading_list"], payload),
            ]
        elif hierarchy_level == "subheading":
            payload = {**base_payload, "sub_heading": hs_code}
            parallel_endpoints = [
                (self.ENDPOINTS["hs_subheading_details"], payload),
                (self.ENDPOINTS["hs_code_list"], payload),
            ]
        elif hierarchy_level == "hs_code":
            payload = {**base_payload, "hs_code": hs_code}
            parallel_endpoints = [
                (self.ENDPOINTS["hs_code_details"], payload),
            ]

        logger.info(f"  📡 Fetching {len(parallel_endpoints)} endpoint(s) in parallel...")
        start = time.time()
        results = await client.call_endpoints_parallel(parallel_endpoints)
        elapsed = time.time() - start

        successes = sum(1 for r in results if r.success)
        logger.info(
            f"  ✓ Completed: {successes}/{len(parallel_endpoints)} successful in {elapsed:.2f}s"
        )

        # Build response based on hierarchy level
        response = {
            "country_name": country_name,
            "data_type": data_type,
            "hs_code": hs_code,
            "hierarchy_level": hierarchy_level,
            "platform": platform.value,
            "fetched_at": datetime.now().isoformat(),
        }

        # Add data based on hierarchy level
        if hierarchy_level == "chapter":
            response["chapter_details"] = results[0].data if results[0].success else {"error": results[0].error}
            response["heading_list"] = results[1].data if results[1].success else {"error": results[1].error}
        elif hierarchy_level == "heading":
            response["heading_details"] = results[0].data if results[0].success else {"error": results[0].error}
            response["subheading_list"] = results[1].data if results[1].success else {"error": results[1].error}
        elif hierarchy_level == "subheading":
            response["subheading_details"] = results[0].data if results[0].success else {"error": results[0].error}
            response["hs_code_list"] = results[1].data if results[1].success else {"error": results[1].error}
        elif hierarchy_level == "hs_code":
            response["hs_code_details"] = results[0].data if results[0].success else {"error": results[0].error}

        return response

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    @staticmethod
    def _extract_company_code(url: str) -> Optional[str]:
        """Extract company code from URL"""
        import re
        # Pattern: /company/[name]/[hash]
        pattern = r'/company/[^/]+/([a-f0-9]{32,64})/?'
        match = re.search(pattern, url)
        return match.group(1) if match else None

    async def _ensure_country_mapping(self, platform: Platform):
        """
        Ensure country name to ISO code mapping is populated from API

        Fetches country list from API and merges with fallback mapping.
        Called automatically before country code extraction.

        Args:
            platform: Platform to fetch from
        """
        # Only fetch once
        if self._country_mapping_loaded:
            return

        self._country_mapping_loaded = True
        initial_count = len(self.COUNTRY_NAME_TO_ISO)

        logger.info(
            f"Loading country mapping from {platform.value} API "
            f"(fallback has {initial_count} countries)"
        )

        try:
            client = self._get_client(platform)

            # Call country list endpoint (GET request)
            url = f"{client.config.api_base_url}/detailed-mirror-countries-list"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=client._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:

                    if response.status != 200:
                        logger.warning(
                            f"Failed to fetch country list: HTTP {response.status}"
                        )
                        return

                    data = await response.json()

            # Extract countries from response
            # Format: [{"country_name": "Argentina", "country_code": "AR", ...}, ...]
            countries = data.get("data", data) if isinstance(data, dict) else data

            if not isinstance(countries, list):
                logger.warning(f"Unexpected country list format: {type(countries)}")
                return

            # Merge with existing mapping
            api_count = 0
            for country in countries:
                country_name = country.get("country_name", "")
                country_code = country.get("country_code", "")

                if country_name and country_code:
                    # Store both normal and URL-friendly versions
                    name_lower = country_name.lower()
                    name_url = name_lower.replace(" ", "-")

                    self.COUNTRY_NAME_TO_ISO[name_lower] = country_code
                    self.COUNTRY_NAME_TO_ISO[name_url] = country_code
                    api_count += 1

            logger.info(
                f"✓ Loaded {api_count} countries from API "
                f"(total: {len(self.COUNTRY_NAME_TO_ISO)})"
            )

        except Exception as e:
            logger.warning(
                f"Failed to load country mapping from API: {e}. "
                f"Using fallback with {initial_count} countries"
            )

    async def _extract_country_code(
        self,
        url: str,
        platform: Platform
    ) -> Optional[str]:
        """
        Extract ISO country code from URL

        Args:
            url: Country URL (e.g., /en/country/bangladesh/imports)
            platform: Platform enum

        Returns:
            ISO country code (e.g., "BD") or None
        """
        import re

        # Ensure country mapping is loaded
        await self._ensure_country_mapping(platform)

        # Pattern: /country/[country-name] or /country-data/[country-name]
        pattern = r'/country(?:-data)?/([a-z\-]+)/?'
        match = re.search(pattern, url.lower())

        if not match:
            return None

        country_name = match.group(1)

        # Look up ISO code
        iso_code = self.COUNTRY_NAME_TO_ISO.get(country_name.lower())

        if iso_code:
            logger.debug(f"Mapped '{country_name}' → ISO code '{iso_code}'")
            return iso_code
        else:
            logger.warning(
                f"No ISO mapping for '{country_name}', using as-is "
                f"(API may fail)"
            )
            return country_name

    @staticmethod
    def _parse_search_params(url: str) -> Dict[str, Any]:
        """Parse search data URL parameters"""
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
    def _build_search_request(params: Dict[str, Any]) -> Dict[str, Any]:
        """Build search request body from URL parameters"""
        from datetime import datetime, timedelta

        # Convert type to data_type
        type_param = params.get('type', 'import').lower()
        if 'mirror' in type_param:
            data_type = f"{type_param}s"
        else:
            data_type = f"detailed_{type_param}s"

        # Determine list_type
        tab = params.get('tab', 'trade')
        list_type = 'buyer_supplier' if tab in ['buyers', 'suppliers'] else 'importer_exporter'

        # Handle country (convert "universal" to empty string)
        country = params.get('country', '')
        if country.lower() == 'universal':
            country = ''

        # Calculate date range if not provided (last 12 months)
        if 'from' not in params or 'to' not in params:
            to_date = datetime.now()
            from_date = to_date - timedelta(days=365)  # 12 months
            date_from = from_date.strftime('%Y-%m-%d')
            date_to = to_date.strftime('%Y-%m-%d')
        else:
            date_from = params['from']
            date_to = params['to']

        # Build body with required fields
        body = {
            "data_type": data_type,
            "list_type": list_type,
            "from": date_from,
            "to": date_to,
            "country": country,
        }

        # Add optional params
        optional = [
            'product', 'hs_code', 'hs_code_filter',
            'importer', 'exporter', 'supplier', 'buyer',
            'origin_country', 'destination_country',
            'port_of_loading', 'port_of_unloading',
            'state', 'city'
        ]

        for param in optional:
            if param in params and params[param]:
                # Capitalize first letter for proper nouns (China → China, not china)
                if param in ['origin_country', 'destination_country'] and isinstance(params[param], str):
                    body[param] = params[param].capitalize()
                else:
                    body[param] = params[param]

        return body

    def _get_search_endpoints(
        self,
        params: Dict[str, Any],
        request_body: Dict[str, Any]
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Determine which search endpoints to call with correct parameters

        Key insight: Different endpoints need different data_type values:
        - For IMPORT searches: importers/suppliers use detailed_imports
        - For IMPORT searches: exporters/buyers use detailed_exports (they're on the export side)
        """
        endpoints = []

        type_param = params.get('type', 'import').lower()
        is_import_search = 'import' in type_param
        is_export_search = 'export' in type_param

        # ====================================================================
        # 1. Main Product Endpoint (always call)
        # ====================================================================
        endpoints.append((self.ENDPOINTS["search_product"], request_body.copy()))

        # ====================================================================
        # 2. Importers Endpoint
        # ====================================================================
        # For import searches: Get companies importing the product
        if is_import_search:
            importers_body = request_body.copy()
            importers_body['data_type'] = 'detailed_imports'  # Must be imports
            endpoints.append((self.ENDPOINTS["search_importers"], importers_body))

        # ====================================================================
        # 3. Exporters Endpoint
        # ====================================================================
        # For import searches: Get companies exporting FROM origin_country
        # Need to flip parameters: origin becomes the country, country becomes destination
        if is_import_search and 'origin_country' in params:
            exporters_body = {
                'data_type': 'detailed_exports',  # Must be exports (they're exporting)
                'list_type': 'importer_exporter',
                'country': params['origin_country'],  # They're exporting FROM this country
            }

            # Add destination if we had a country filter
            if params.get('country') and params['country'] != 'universal':
                exporters_body['destination_country'] = params['country']

            # Add product filters
            if 'product' in params:
                exporters_body['product'] = params['product']
            if 'hs_code' in params:
                exporters_body['hs_code'] = params['hs_code']

            endpoints.append((self.ENDPOINTS["search_exporters"], exporters_body))
        elif is_export_search:
            exporters_body = request_body.copy()
            exporters_body['data_type'] = 'detailed_exports'
            endpoints.append((self.ENDPOINTS["search_exporters"], exporters_body))

        # ====================================================================
        # 4. Buyers Endpoint
        # ====================================================================
        # Buyers are companies buying (from exporter perspective)
        buyers_body = request_body.copy()
        buyers_body['data_type'] = 'detailed_exports'  # Buyers from export perspective
        buyers_body['list_type'] = 'buyer_supplier'

        # Remove origin_country if present (not valid for buyers endpoint)
        buyers_body.pop('origin_country', None)

        endpoints.append((self.ENDPOINTS["search_buyers"], buyers_body))

        # ====================================================================
        # 5. Suppliers Endpoint
        # ====================================================================
        # Suppliers are companies supplying (from import perspective)
        suppliers_body = request_body.copy()
        if is_import_search:
            suppliers_body['data_type'] = 'detailed_imports'  # Suppliers from import perspective
        else:
            suppliers_body['data_type'] = 'detailed_exports'
        suppliers_body['list_type'] = 'buyer_supplier'

        endpoints.append((self.ENDPOINTS["search_suppliers"], suppliers_body))

        # ====================================================================
        # 6. Totals Endpoint
        # ====================================================================
        if is_import_search:
            totals_body = request_body.copy()
            totals_body['data_type'] = 'detailed_imports'
            endpoints.append((self.ENDPOINTS["search_total_imp_sup"], totals_body))
        else:
            totals_body = request_body.copy()
            totals_body['data_type'] = 'detailed_exports'
            endpoints.append((self.ENDPOINTS["search_total_exp_buy"], totals_body))

        return endpoints

    @staticmethod
    def _parse_c2c_url(url: str) -> Dict[str, Any]:
        """
        Parse country-to-country URL to extract countries and direction

        URL Pattern: /[language]/cntry/[origin]-[direction]-[destination]
        Examples:
            - /en/cntry/Belgium-export-France
            - /en/cntry/United%20States-import-India

        Args:
            url: Country-to-country URL

        Returns:
            Dict with origin_country, destination_country, and data_type
        """
        import re
        from urllib.parse import unquote

        # Extract the last segment from path
        parsed = urlparse(url)
        path_segments = [p for p in parsed.path.split('/') if p]

        if not path_segments:
            return {"error": "Could not parse URL path"}

        last_segment = path_segments[-1]

        # Split by hyphen: [origin]-[direction]-[destination]
        parts = last_segment.split('-')

        if len(parts) < 3:
            return {"error": f"Invalid URL format: expected [origin]-[direction]-[destination], got {last_segment}"}

        # Handle cases where country names have hyphens (e.g., "united-states-import-india")
        # Find the direction keyword (import or export)
        direction_index = -1
        direction = None

        for i, part in enumerate(parts):
            if part.lower() in ['import', 'export']:
                direction_index = i
                direction = part.lower()
                break

        if direction_index == -1:
            return {"error": f"Could not find 'import' or 'export' in URL: {last_segment}"}

        # Everything before direction is origin country
        origin_parts = parts[:direction_index]
        # Everything after direction is destination country
        destination_parts = parts[direction_index + 1:]

        if not origin_parts or not destination_parts:
            return {"error": f"Missing origin or destination country in URL: {last_segment}"}

        # Join parts with hyphens and decode URL encoding
        origin_country = unquote('-'.join(origin_parts))
        destination_country = unquote('-'.join(destination_parts))

        # Keep country names lowercase and replace hyphens with spaces
        # API expects lowercase country names (e.g., "south africa", "argentina")
        origin_country = origin_country.replace('-', ' ').lower()
        destination_country = destination_country.replace('-', ' ').lower()

        return {
            "origin_country": origin_country,
            "destination_country": destination_country,
            "data_type": direction
        }

    @staticmethod
    def _parse_hs_code_url(url: str) -> Dict[str, Any]:
        """
        Parse HS code URL to extract country, direction, and HS code

        URL Pattern: /[language]/chapter/[country]-[direction]-hs-code-[code]
        Examples:
            - /en/chapter/botswana-import-hs-code-27 (Chapter - 2 digits)
            - /en/chapter/botswana-import-hs-code-2710 (Heading - 4 digits)
            - /en/chapter/botswana-import-hs-code-271012 (Subheading - 6 digits)
            - /en/chapter/botswana-import-hs-code-27101230 (HS Code - 8+ digits)

        Args:
            url: HS code chapter URL

        Returns:
            Dict with country_name, data_type, hs_code, and hierarchy_level
        """
        from urllib.parse import unquote

        # Extract the last segment from path
        parsed = urlparse(url)
        path_segments = [p for p in parsed.path.split('/') if p]

        if not path_segments:
            return {"error": "Could not parse URL path"}

        last_segment = path_segments[-1]

        # Split by hyphen: [country]-[direction]-hs-code-[code]
        parts = last_segment.split('-')

        if len(parts) < 4:
            return {"error": f"Invalid URL format: expected [country]-[direction]-hs-code-[code], got {last_segment}"}

        # Find "hs" and "code" keywords
        hs_index = -1
        for i, part in enumerate(parts):
            if part.lower() == 'hs' and i + 1 < len(parts) and parts[i + 1].lower() == 'code':
                hs_index = i
                break

        if hs_index == -1:
            return {"error": f"Could not find 'hs-code' in URL: {last_segment}"}

        # Find direction keyword before "hs-code"
        direction_index = -1
        direction = None

        for i in range(hs_index):
            if parts[i].lower() in ['import', 'export']:
                direction_index = i
                direction = parts[i].lower()
                break

        if direction_index == -1:
            return {"error": f"Could not find 'import' or 'export' in URL: {last_segment}"}

        # Everything before direction is country name
        country_parts = parts[:direction_index]

        # Everything after "code" is the HS code
        code_parts = parts[hs_index + 2:]  # Skip "hs" and "code"

        if not country_parts or not code_parts:
            return {"error": f"Missing country or HS code in URL: {last_segment}"}

        # Join parts and decode URL encoding
        country_name = unquote('-'.join(country_parts))
        hs_code = ''.join(code_parts)  # Join without separator for HS code

        # Keep country name lowercase (API expects lowercase)
        country_name = country_name.replace('-', ' ').lower()

        # Determine hierarchy level based on code length
        code_length = len(hs_code)
        if code_length == 2:
            hierarchy_level = "chapter"
        elif code_length == 4:
            hierarchy_level = "heading"
        elif code_length == 6:
            hierarchy_level = "subheading"
        elif code_length >= 8:
            hierarchy_level = "hs_code"
        else:
            return {"error": f"Invalid HS code length: {code_length} (expected 2, 4, 6, or 8+ digits)"}

        return {
            "country_name": country_name,
            "data_type": direction,
            "hs_code": hs_code,
            "hierarchy_level": hierarchy_level
        }


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def fetch_content_from_url(url: str) -> Tuple[Dict[str, Any], Platform, PageType]:
    """
    Main entry point: Fetch content from any URL

    Automatically detects platform and page type, then fetches data

    Args:
        url: Full URL to fetch

    Returns:
        Tuple of (data_dict, platform, page_type)
    """
    client = UnifiedAPIClient()

    try:
        # Detect platform and page type
        platform = UnifiedAPIClient.detect_platform(url)
        page_type = UnifiedAPIClient.detect_page_type(url)

        if platform == Platform.UNKNOWN:
            return {"error": "Unknown platform"}, platform, page_type

        if page_type == PageType.UNKNOWN:
            return {"error": "Unknown page type"}, platform, page_type

        # Fetch data based on page type
        if page_type == PageType.COMPANY:
            data = await client.fetch_company_data(url, platform)
        elif page_type == PageType.COUNTRY:
            data = await client.fetch_country_data(url, platform)
        elif page_type == PageType.COUNTRY_TO_COUNTRY:
            data = await client.fetch_country_to_country_data(url, platform)
        elif page_type == PageType.HS_CODE:
            data = await client.fetch_hs_code_data(url, platform)
        elif page_type == PageType.SEARCH_DATA:
            data = await client.fetch_search_data(url, platform)
        else:
            data = {"error": f"Unsupported page type: {page_type}"}

        return data, platform, page_type

    finally:
        await client.close_all()
