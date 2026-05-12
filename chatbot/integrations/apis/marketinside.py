"""
Marketinside API Client
Async API client for fetching company data from marketinsidedata.com API

Features:
- Async HTTP requests with aiohttp
- Parallel API calls for performance
- In-memory caching
- Comprehensive error handling
- Retry logic with exponential backoff
- Same API structure as Export Genius
"""

import asyncio
import re
from typing import Dict, Optional, List
import logging
import os
from datetime import datetime

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("⚠️  Warning: aiohttp not installed. Install with: pip install aiohttp")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  Warning: python-dotenv not installed. Install with: pip install python-dotenv")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MarketinsideAPIClient:
    """
    Async API client for Marketinside API

    Usage:
        client = MarketinsideAPIClient(bearer_token="your_token")
        data = await client.fetch_all_company_data(company_code)
    """

    # API endpoint configurations
    BASE_URL = "https://api-dp.marketinsidedata.com/api/v1/users"

    ENDPOINTS = {
        # Company endpoints
        "overview": "/company-overview",
        "countries": "/company-countries",
        "turnover": "/company-turnover",
        "commodities": "/company-commodities",
        "competitors": "/company-competitors",
        "ports": "/company-top-ports",
        "shipments": "/company-shipments",
        "faqs": "/company-faqs",

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

        # Country list mapping
        "country_list": "/detailed-mirror-countries-list"
    }

    # Country name to ISO code mapping (populated on initialization)
    # Fallback mapping for common countries (used if API call fails)
    COUNTRY_NAME_TO_ISO: Dict[str, str] = {
        "argentina": "AR",
        "vietnam": "VN",
        "china": "CN",
        "united-kingdom": "GB",
        "usa": "US",
        "united-states": "US",
        "brazil": "BR",
        "mexico": "MX",
        "germany": "DE",
        "france": "FR",
        "italy": "IT",
        "spain": "ES",
        "united-kingdom": "GB",
        "uk": "GB",
        "japan": "JP",
        "south-korea": "KR",
        "korea": "KR",
        "australia": "AU",
        "canada": "CA",
        "russia": "RU",
        "turkey": "TR",
        "indonesia": "ID",
        "thailand": "TH",
        "malaysia": "MY",
        "singapore": "SG",
        "philippines": "PH",
        "pakistan": "PK",
        "bangladesh": "BD",
        "egypt": "EG",
        "south-africa": "ZA",
        "saudi-arabia": "SA",
        "uae": "AE",
        "united-arab-emirates": "AE",
        "netherlands": "NL",
        "belgium": "BE",
        "poland": "PL",
        "sweden": "SE",
        "norway": "NO",
        "denmark": "DK",
        "finland": "FI",
        "greece": "GR",
        "portugal": "PT",
        "chile": "CL",
        "colombia": "CO",
        "peru": "PE",
        "venezuela": "VE",
        "ecuador": "EC",
        "uruguay": "UY",
        "paraguay": "PY",
        "bolivia": "BO",
        "new-zealand": "NZ",
        "israel": "IL",
        "iran": "IR",
        "iraq": "IQ",
        "kuwait": "KW",
        "qatar": "QA",
        "oman": "OM",
        "bahrain": "BH",
        "jordan": "JO",
        "lebanon": "LB",
        "syria": "SY",
        "yemen": "YE",
        "morocco": "MA",
        "algeria": "DZ",
        "tunisia": "TN",
        "libya": "LY",
        "sudan": "SD",
        "ethiopia": "ET",
        "kenya": "KE",
        "nigeria": "NG",
        "ghana": "GH",
        "tanzania": "TZ",
        "uganda": "UG",
        "zimbabwe": "ZW",
        "zambia": "ZM",
        "mozambique": "MZ",
        "angola": "AO",
        "cameroon": "CM",
        "ivory-coast": "CI",
        "senegal": "SN",
        "botswana": "BW",
        "namibia": "NA",
        "mauritius": "MU",
        "madagascar": "MG",
        "kazakhstan": "KZ",
        "uzbekistan": "UZ",
        "ukraine": "UA",
        "belarus": "BY",
        "romania": "RO",
        "czech-republic": "CZ",
        "czechia": "CZ",
        "hungary": "HU",
        "austria": "AT",
        "switzerland": "CH",
        "ireland": "IE",
        "croatia": "HR",
        "serbia": "RS",
        "bulgaria": "BG",
        "slovakia": "SK",
        "slovenia": "SI",
        "lithuania": "LT",
        "latvia": "LV",
        "estonia": "EE",
        "iceland": "IS",
        "luxembourg": "LU",
        "malta": "MT",
        "cyprus": "CY",
        "albania": "AL",
        "macedonia": "MK",
        "north-macedonia": "MK",
        "bosnia": "BA",
        "bosnia-herzegovina": "BA",
        "montenegro": "ME",
        "moldova": "MD",
        "armenia": "AM",
        "georgia": "GE",
        "azerbaijan": "AZ",
        "turkmenistan": "TM",
        "kyrgyzstan": "KG",
        "tajikistan": "TJ",
        "mongolia": "MN",
        "nepal": "NP",
        "sri-lanka": "LK",
        "myanmar": "MM",
        "burma": "MM",
        "cambodia": "KH",
        "laos": "LA",
        "brunei": "BN",
        "maldives": "MV",
        "afghanistan": "AF",
        "bhutan": "BT",
        "taiwan": "TW",
        "hong-kong": "HK",
        "macau": "MO",
        "puerto-rico": "PR",
        "dominican-republic": "DO",
        "cuba": "CU",
        "jamaica": "JM",
        "trinidad": "TT",
        "trinidad-tobago": "TT",
        "barbados": "BB",
        "bahamas": "BS",
        "haiti": "HT",
        "honduras": "HN",
        "nicaragua": "NI",
        "costa-rica": "CR",
        "panama": "PA",
        "guatemala": "GT",
        "el-salvador": "SV",
        "belize": "BZ",
        "guyana": "GY",
        "suriname": "SR",
        "french-guiana": "GF",
        "fiji": "FJ",
        "papua-new-guinea": "PG",
        "samoa": "WS",
        "tonga": "TO",
        "vanuatu": "VU",
        "solomon-islands": "SB"
    }

    def __init__(
        self,
        bearer_token: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize API client

        Args:
            bearer_token: Bearer token for API authentication (defaults to env var)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.bearer_token = bearer_token or os.getenv("MARKETINSIDE_BEARER_TOKEN")
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache: Dict[str, Dict] = {}  # In-memory cache by company_code

        if not self.bearer_token:
            logger.warning(
                "⚠️  No bearer token provided. Set MARKETINSIDE_BEARER_TOKEN "
                "environment variable or pass bearer_token parameter."
            )

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authorization"""
        return {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'authorization': f'Bearer {self.bearer_token}',
            'content-type': 'application/json',
            'origin': 'https://www.marketinsidedata.com',
            'referer': 'https://www.marketinsidedata.com/',
            'priority': 'u=1, i',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }

    @staticmethod
    def extract_company_code(url: str) -> Optional[str]:
        """
        Extract company code from Marketinside company URL

        Args:
            url: Company profile URL

        Returns:
            Company code (hash) or None if not a company URL

        Example:
            https://www.marketinsidedata.com/company/company-name/9ead49e7ecb36670a3e818ae049cf257
            Returns: 9ead49e7ecb36670a3e818ae049cf257
        """
        # Pattern: /company/[company-name]/[hash]
        # The hash can be 32 or 64 characters (hex)
        pattern = r'/company/[^/]+/([a-f0-9]{32,64})/?'
        match = re.search(pattern, url)

        if match:
            return match.group(1)
        return None

    @staticmethod
    def is_company_url(url: str) -> bool:
        """Check if URL is a Marketinside company profile URL"""
        if not url:
            return False
        # Handle both direct and language-prefixed URLs (e.g., /en/company/, /fr/company/)
        return 'marketinsidedata.com' in url and '/company/' in url

    async def extract_country_code(self, url: str) -> Optional[str]:
        """
        Extract ISO country code from Marketinside country URL

        Args:
            url: Country profile URL

        Returns:
            ISO country code (e.g., "AR" for Argentina) or None if not found

        Example:
            https://www.marketinsidedata.com/en/country/argentina
            Returns: AR (ISO code for Argentina)
        """
        # Ensure country mapping is loaded
        await self._ensure_country_mapping()

        # Pattern: /country/[country-name]
        pattern = r'/country/([a-z\-]+)/?'
        match = re.search(pattern, url.lower())

        if not match:
            return None

        country_name = match.group(1)

        # Look up ISO code from mapping
        iso_code = self.COUNTRY_NAME_TO_ISO.get(country_name.lower())

        if iso_code:
            logger.info(f"Mapped country '{country_name}' -> ISO code '{iso_code}'")
            return iso_code
        else:
            logger.warning(f"No ISO code mapping found for '{country_name}', using name as fallback")
            return country_name  # Fallback to country name if mapping not found

    @staticmethod
    def is_country_url(url: str) -> bool:
        """Check if URL is a Marketinside country profile URL"""
        if not url:
            return False
        # Handle both direct and language-prefixed URLs (e.g., /en/country/, /fr/country/)
        return 'marketinsidedata.com' in url and '/country/' in url

    async def _make_request(
        self,
        endpoint: str,
        payload: Dict,
        retry_count: int = 0
    ) -> Dict:
        """
        Make async API request with retry logic

        Args:
            endpoint: API endpoint path
            payload: Request payload (will be sent as JSON)
            retry_count: Current retry attempt

        Returns:
            API response data
        """
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp is required. Install with: pip install aiohttp")

        url = f"{self.BASE_URL}{endpoint}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data

        except aiohttp.ClientError as e:
            if retry_count < self.max_retries:
                wait_time = 2 ** retry_count  # Exponential backoff
                logger.warning(f"Request failed, retrying in {wait_time}s... ({retry_count + 1}/{self.max_retries})")
                await asyncio.sleep(wait_time)
                return await self._make_request(endpoint, payload, retry_count + 1)
            else:
                logger.error(f"Request failed after {self.max_retries} retries: {e}")
                return {"error": str(e)}

        except Exception as e:
            logger.error(f"Unexpected error in API request: {e}")
            return {"error": str(e)}

    async def _make_get_request(
        self,
        endpoint: str,
        retry_count: int = 0
    ) -> Dict:
        """
        Make async GET API request with retry logic

        Args:
            endpoint: API endpoint path
            retry_count: Current retry attempt

        Returns:
            API response data
        """
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp is required. Install with: pip install aiohttp")

        url = f"{self.BASE_URL}{endpoint}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data

        except aiohttp.ClientError as e:
            if retry_count < self.max_retries:
                wait_time = 2 ** retry_count  # Exponential backoff
                logger.warning(f"GET request failed, retrying in {wait_time}s... ({retry_count + 1}/{self.max_retries})")
                await asyncio.sleep(wait_time)
                return await self._make_get_request(endpoint, retry_count + 1)
            else:
                logger.error(f"GET request failed after {self.max_retries} retries: {e}")
                return {"error": str(e)}

        except Exception as e:
            logger.error(f"Unexpected error in GET API request: {e}")
            return {"error": str(e)}

    async def _ensure_country_mapping(self) -> None:
        """
        Ensure country name to ISO code mapping is populated.
        Fetches country list from API and merges with fallback mapping.
        This is called automatically before any country code extraction.
        """
        # Check if we already tried to fetch from API (to avoid repeated failed attempts)
        if hasattr(self, '_country_mapping_loaded'):
            return

        self._country_mapping_loaded = True
        initial_count = len(self.COUNTRY_NAME_TO_ISO)
        logger.info(f"Starting with {initial_count} countries in fallback mapping")

        try:
            logger.info("Fetching country list from Marketinside API...")
            response = await self._make_get_request(self.ENDPOINTS["country_list"])

            if "error" in response:
                logger.warning(f"Failed to fetch country list from API: {response['error']}")
                logger.info(f"Using fallback mapping with {initial_count} countries")
                return

            # Extract country mapping from response
            # Response format: [{"country_name": "Argentina", "country_code": "AR", "data_type": [...]}, ...]
            countries = response.get("data", response)  # Handle both {"data": [...]} and direct array

            if not isinstance(countries, list):
                logger.warning(f"Unexpected country list format: {type(countries)}")
                logger.info(f"Using fallback mapping with {initial_count} countries")
                return

            # Merge API results with existing fallback mapping
            api_count = 0
            for country in countries:
                country_name = country.get("country_name", "")
                country_code = country.get("country_code", "")

                if country_name and country_code:
                    # Store with lowercase key for case-insensitive matching
                    # Also store URL-friendly version (with hyphens instead of spaces)
                    name_lower = country_name.lower()
                    name_url = name_lower.replace(" ", "-")

                    self.COUNTRY_NAME_TO_ISO[name_lower] = country_code
                    self.COUNTRY_NAME_TO_ISO[name_url] = country_code
                    api_count += 1

            logger.info(f"Successfully loaded {api_count} countries from API")
            logger.info(f"Total countries in mapping: {len(self.COUNTRY_NAME_TO_ISO)}")

        except Exception as e:
            logger.warning(f"Error loading country mapping from API: {e}")
            logger.info(f"Using fallback mapping with {initial_count} countries")

    async def fetch_company_overview(self, company_code: str) -> Dict:
        """
        Fetch company overview data

        Args:
            company_code: Company code (hash from URL)

        Returns:
            Overview data with i_e_code and country_code
        """
        payload = {"company_code": company_code}
        return await self._make_request(self.ENDPOINTS["overview"], payload)

    async def fetch_company_countries(
        self,
        company_code: str,
        country_code: List[str],
        ie_code: str
    ) -> Dict:
        """Fetch company countries data"""
        payload = {
            "company_code": company_code,
            "country_code": country_code,
            "i_e_code": ie_code
        }
        return await self._make_request(self.ENDPOINTS["countries"], payload)

    async def fetch_company_turnover(
        self,
        company_code: str,
        country_code: List[str],
        ie_code: str
    ) -> Dict:
        """Fetch company turnover data"""
        payload = {
            "company_code": company_code,
            "country_code": country_code,
            "i_e_code": ie_code
        }
        return await self._make_request(self.ENDPOINTS["turnover"], payload)

    async def fetch_company_commodities(
        self,
        company_code: str,
        country_code: List[str],
        ie_code: str
    ) -> Dict:
        """Fetch company commodities data"""
        payload = {
            "company_code": company_code,
            "country_code": country_code,
            "i_e_code": ie_code
        }
        return await self._make_request(self.ENDPOINTS["commodities"], payload)

    async def fetch_company_competitors(
        self,
        company_code: str,
        country_code: List[str],
        ie_code: str
    ) -> Dict:
        """Fetch company competitors data"""
        payload = {
            "company_code": company_code,
            "country_code": country_code,
            "i_e_code": ie_code
        }
        return await self._make_request(self.ENDPOINTS["competitors"], payload)

    async def fetch_company_ports(
        self,
        company_code: str,
        country_code: List[str],
        ie_code: str
    ) -> Dict:
        """Fetch company top ports data"""
        payload = {
            "company_code": company_code,
            "country_code": country_code,
            "i_e_code": ie_code
        }
        return await self._make_request(self.ENDPOINTS["ports"], payload)

    async def fetch_company_shipments(
        self,
        company_code: str,
        country_code: List[str],
        ie_code: str
    ) -> Dict:
        """Fetch company shipments data"""
        payload = {
            "company_code": company_code,
            "country_code": country_code,
            "i_e_code": ie_code
        }
        return await self._make_request(self.ENDPOINTS["shipments"], payload)

    async def fetch_company_faqs(
        self,
        company_code: str,
        country_code: List[str],
        ie_code: str
    ) -> Dict:
        """Fetch company FAQs data"""
        payload = {
            "company_code": company_code,
            "country_code": country_code,
            "i_e_code": ie_code
        }
        return await self._make_request(self.ENDPOINTS["faqs"], payload)

    # ========================================================================
    # COUNTRY DATA METHODS
    # ========================================================================

    async def fetch_country_stats(self, country_code: str, data_type: str = "import") -> Dict:
        """
        Fetch country statistics

        Args:
            country_code: Country code (e.g., 'argentina')
            data_type: 'import' or 'export'

        Returns:
            Country statistics data
        """
        payload = {
            "country_code": country_code,
            "data_type": data_type
        }
        return await self._make_request(self.ENDPOINTS["country_stats"], payload)

    async def fetch_country_importers(self, country_code: str, data_type: str = "import") -> Dict:
        """Fetch top importers/exporters for country"""
        payload = {
            "country_code": country_code,
            "data_type": data_type
        }
        return await self._make_request(self.ENDPOINTS["country_importers"], payload)

    async def fetch_country_partners(self, country_code: str, data_type: str = "import") -> Dict:
        """Fetch top trading partners for country"""
        payload = {
            "country_code": country_code,
            "data_type": data_type
        }
        return await self._make_request(self.ENDPOINTS["country_partners"], payload)

    async def fetch_country_ports(self, country_code: str, data_type: str = "import") -> Dict:
        """Fetch top ports for country"""
        payload = {
            "country_code": country_code,
            "data_type": data_type
        }
        return await self._make_request(self.ENDPOINTS["country_ports"], payload)

    async def fetch_country_chapters(self, country_code: str, data_type: str = "import") -> Dict:
        """Fetch HS code chapters for country"""
        payload = {
            "country_code": country_code,
            "data_type": data_type
        }
        return await self._make_request(self.ENDPOINTS["country_chapters"], payload)

    async def fetch_country_commodities(self, country_code: str, data_type: str = "import") -> Dict:
        """Fetch top commodities for country"""
        payload = {
            "country_code": country_code,
            "data_type": data_type
        }
        return await self._make_request(self.ENDPOINTS["country_commodities"], payload)

    async def fetch_country_faqs(self, country_code: str, data_type: str = "import") -> Dict:
        """Fetch FAQs for country"""
        payload = {
            "country_code": country_code,
            "data_type": data_type
        }
        return await self._make_request(self.ENDPOINTS["country_faqs"], payload)

    async def fetch_country_buyer_supplier(self, country_code: str, data_type: str = "import") -> Dict:
        """Fetch buyer/supplier data for country"""
        payload = {
            "country_code": country_code,
            "data_type": data_type
        }
        return await self._make_request(self.ENDPOINTS["country_buyer_supplier"], payload)

    async def fetch_country_monthly(self, country_code: str, data_type: str = "import") -> Dict:
        """Fetch monthly import/export trends for country"""
        payload = {
            "country_code": country_code,
            "data_type": data_type
        }
        return await self._make_request(self.ENDPOINTS["country_monthly"], payload)

    async def fetch_all_country_data(self, country_code: str, data_type: str = "import") -> Dict:
        """
        Fetch all country data (9 endpoints in parallel)

        Args:
            country_code: Country code (e.g., 'argentina')
            data_type: 'import' or 'export'

        Returns:
            Dictionary with all country data
        """
        # Check cache first
        cache_key = f"country_{country_code}_{data_type}"
        if cache_key in self.cache:
            logger.info(f"⚡ Using cached data for country {country_code} ({data_type})")
            return self.cache[cache_key]

        logger.info(f"📊 Fetching Marketinside country data for {country_code} ({data_type})...")

        # Fetch all endpoints in parallel
        tasks = [
            self.fetch_country_stats(country_code, data_type),
            self.fetch_country_importers(country_code, data_type),
            self.fetch_country_partners(country_code, data_type),
            self.fetch_country_ports(country_code, data_type),
            self.fetch_country_chapters(country_code, data_type),
            self.fetch_country_commodities(country_code, data_type),
            self.fetch_country_faqs(country_code, data_type),
            self.fetch_country_buyer_supplier(country_code, data_type),
            self.fetch_country_monthly(country_code, data_type)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine all data
        all_data = {
            "country_code": country_code,
            "data_type": data_type,
            "platform": "marketinside",
            "fetched_at": datetime.now().isoformat(),
            "stats": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
            "importers": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
            "partners": results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])},
            "ports": results[3] if not isinstance(results[3], Exception) else {"error": str(results[3])},
            "chapters": results[4] if not isinstance(results[4], Exception) else {"error": str(results[4])},
            "commodities": results[5] if not isinstance(results[5], Exception) else {"error": str(results[5])},
            "faqs": results[6] if not isinstance(results[6], Exception) else {"error": str(results[6])},
            "buyer_supplier": results[7] if not isinstance(results[7], Exception) else {"error": str(results[7])},
            "monthly": results[8] if not isinstance(results[8], Exception) else {"error": str(results[8])}
        }

        logger.info(f"  ✓ All 9 country endpoints fetched successfully")

        # Cache the result
        self.cache[cache_key] = all_data

        return all_data

    async def fetch_all_company_data(self, company_code: str) -> Dict:
        """
        Fetch all company data (overview + 7 other endpoints in parallel)

        This is the main method to use. It:
        1. Fetches company overview first (to get i_e_code and country_code)
        2. Fetches all other endpoints in parallel
        3. Caches the result in memory

        Args:
            company_code: Company code from URL

        Returns:
            Dictionary with all company data
        """
        # Check cache first
        if company_code in self.cache:
            logger.info(f"⚡ Using cached data for company {company_code[:8]}...")
            return self.cache[company_code]

        logger.info(f"📊 Fetching Marketinside company data for {company_code[:8]}...")

        # Step 1: Fetch overview to get i_e_code and country_code
        overview = await self.fetch_company_overview(company_code)

        if "error" in overview:
            logger.error(f"Failed to fetch company overview: {overview['error']}")
            return {"error": "Failed to fetch company overview", "details": overview}

        # Extract i_e_code and country_code from overview
        ie_code = overview.get("i_e_code")
        country_code = overview.get("country_code", [])

        if not ie_code:
            logger.error("Missing i_e_code in overview response")
            return {
                "error": "Missing required field i_e_code in overview",
                "overview": overview
            }

        # Handle country_code - ensure it's a list
        if not country_code:
            country_code = []
        elif isinstance(country_code, str):
            country_code = [country_code]

        logger.info(f"  ✓ Overview fetched - IE Code: {ie_code}, Countries: {country_code}")

        # Step 2: Fetch all other endpoints in parallel
        logger.info("  📡 Fetching remaining 7 endpoints in parallel...")

        tasks = [
            self.fetch_company_countries(company_code, country_code, ie_code),
            self.fetch_company_turnover(company_code, country_code, ie_code),
            self.fetch_company_commodities(company_code, country_code, ie_code),
            self.fetch_company_competitors(company_code, country_code, ie_code),
            self.fetch_company_ports(company_code, country_code, ie_code),
            self.fetch_company_shipments(company_code, country_code, ie_code),
            self.fetch_company_faqs(company_code, country_code, ie_code)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine all data
        all_data = {
            "company_code": company_code,
            "platform": "marketinside",
            "fetched_at": datetime.now().isoformat(),
            "overview": overview,
            "countries": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
            "turnover": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
            "commodities": results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])},
            "competitors": results[3] if not isinstance(results[3], Exception) else {"error": str(results[3])},
            "ports": results[4] if not isinstance(results[4], Exception) else {"error": str(results[4])},
            "shipments": results[5] if not isinstance(results[5], Exception) else {"error": str(results[5])},
            "faqs": results[6] if not isinstance(results[6], Exception) else {"error": str(results[6])}
        }

        logger.info(f"  ✓ All 8 endpoints fetched successfully")

        # Cache the result
        self.cache[company_code] = all_data

        return all_data

    @staticmethod
    def format_for_rag(company_data: Dict) -> str:
        """
        Format company data for RAG context (LLM consumption)

        Args:
            company_data: Complete company data from fetch_all_company_data()

        Returns:
            Formatted string ready for LLM context
        """
        if "error" in company_data:
            return f"Error fetching company data: {company_data.get('error')}"

        sections = []

        # Company Overview
        overview = company_data.get("overview", {})
        if overview and "error" not in overview:
            sections.append(f"""[COMPANY OVERVIEW]
Company Name: {overview.get('company_name', 'N/A')}
Address: {overview.get('address', 'N/A')}
Country: {overview.get('country_name', 'N/A')}
Headquarter: {overview.get('headquarter', 'N/A')}
Date Range: {overview.get('date_from', 'N/A')} to {overview.get('date_to', 'N/A')}
Import Turnover: ${overview.get('import_turnover', 0):,.2f}
Export Turnover: ${overview.get('export_turnover', 0):,.2f}
Import Shipments: {overview.get('import_shipments', 0):,}
Export Shipments: {overview.get('export_shipments', 0):,}
Website: {overview.get('websiteurl') or 'N/A'}
Phone: {overview.get('phone') or 'N/A'}
Industry: {overview.get('industry') or 'N/A'}""")

        # Countries
        countries = company_data.get("countries", {})
        if countries and "error" not in countries:
            imports = countries.get("imports", [])
            exports = countries.get("exports", [])

            if imports or exports:
                sections.append("\n[TOP TRADING COUNTRIES]")

                if imports:
                    sections.append("Import Countries:")
                    for item in imports[:10]:
                        country = item.get('country', 'N/A')
                        value = item.get('value', 'locked')
                        percentage = item.get('percentage', 'locked')
                        sections.append(f"  • {country}: Value={value}, Share={percentage}%")

                if exports:
                    sections.append("\nExport Countries:")
                    for item in exports[:10]:
                        country = item.get('country', 'N/A')
                        value = item.get('value', 'locked')
                        percentage = item.get('percentage', 'locked')
                        sections.append(f"  • {country}: Value={value}, Share={percentage}%")

        # Turnover (Monthly Import/Export Trends)
        turnover = company_data.get("turnover", {})
        if turnover and "error" not in turnover:
            date_range = turnover.get("date_range", [])
            imports = turnover.get("imports", [])
            exports = turnover.get("exports", [])

            if imports or exports:
                sections.append("\n[MONTHLY TURNOVER TRENDS]")
                if date_range:
                    sections.append(f"Date Range: {date_range[0]} to {date_range[1]}")

                if imports:
                    sections.append("\nImport Trends:")
                    for month_data in imports:
                        month = month_data.get('month', 'N/A')
                        value = month_data.get('value', 'locked')
                        percentage = month_data.get('percentage', 'locked')
                        sections.append(f"  • {month}: Value={value}, Percentage={percentage}%")

                if exports:
                    sections.append("\nExport Trends:")
                    for month_data in exports:
                        month = month_data.get('month', 'N/A')
                        value = month_data.get('value', 'locked')
                        percentage = month_data.get('percentage', 'locked')
                        sections.append(f"  • {month}: Value={value}, Percentage={percentage}%")

        # Commodities (Top Products)
        commodities = company_data.get("commodities", {})
        if commodities and "error" not in commodities:
            imports = commodities.get("imports", [])
            exports = commodities.get("exports", [])

            if imports or exports:
                sections.append("\n[TOP COMMODITIES]")

                if imports:
                    sections.append("\nTop Import Products:")
                    for idx, item in enumerate(imports[:10], 1):
                        product = item.get('comodity_description', 'N/A')  # Fixed field name
                        hs_code = item.get('hs_code', 'N/A')
                        value = item.get('value', 'locked')
                        percentage = item.get('percentage', 'locked')
                        sections.append(f"  {idx}. HS {hs_code}: {product[:80]}")
                        sections.append(f"     Value={value}, Share={percentage}%")

                if exports:
                    sections.append("\nTop Export Products:")
                    for idx, item in enumerate(exports[:10], 1):
                        product = item.get('comodity_description', 'N/A')  # Fixed field name
                        hs_code = item.get('hs_code', 'N/A')
                        value = item.get('value', 'locked')
                        percentage = item.get('percentage', 'locked')
                        sections.append(f"  {idx}. HS {hs_code}: {product[:80]}")
                        sections.append(f"     Value={value}, Share={percentage}%")

        # Competitors
        competitors = company_data.get("competitors", {})
        if competitors and "error" not in competitors:
            import_comps = competitors.get("import_competitors", [])  # Fixed field name
            export_comps = competitors.get("export_competitors", [])  # Fixed field name

            if import_comps or export_comps:
                sections.append("\n[COMPETITORS]")

                if import_comps:
                    sections.append("\nImport Competitors:")
                    for idx, comp in enumerate(import_comps[:10], 1):
                        name = comp.get('competitor', 'N/A')  # Fixed field name
                        turnover = comp.get('import_turnover', 'N/A')
                        employees = comp.get('num_employees', 'N/A')
                        sections.append(f"  {idx}. {name}")
                        sections.append(f"     Import Turnover: ${turnover:,}, Employees: {employees}")

                if export_comps:
                    sections.append("\nExport Competitors:")
                    for idx, comp in enumerate(export_comps[:10], 1):
                        name = comp.get('competitor', 'N/A')  # Fixed field name
                        turnover = comp.get('export_turnover', 'N/A')
                        employees = comp.get('num_employees', 'N/A')
                        sections.append(f"  {idx}. {name}")
                        sections.append(f"     Export Turnover: ${turnover:,}, Employees: {employees}")

        # Ports
        ports = company_data.get("ports", {})
        if ports and "error" not in ports:
            loading = ports.get("loading", [])  # Fixed field name
            unloading = ports.get("unloading", [])  # Fixed field name

            if loading or unloading:
                sections.append("\n[TOP PORTS]")

                if loading:
                    sections.append("\nLoading Ports (Export):")
                    for idx, port in enumerate(loading[:10], 1):
                        port_name = port.get('port_of_loading', 'N/A')  # Fixed field name
                        country = port.get('port_country', 'N/A')
                        value = port.get('value', 'locked')
                        percentage = port.get('percentage', 'locked')
                        sections.append(f"  {idx}. {port_name} ({country}): Value={value}, Share={percentage}%")

                if unloading:
                    sections.append("\nUnloading Ports (Import):")
                    for idx, port in enumerate(unloading[:10], 1):
                        port_name = port.get('port_of_unloading', 'N/A')  # Fixed field name
                        country = port.get('port_country', 'N/A')
                        value = port.get('value', 'locked')
                        percentage = port.get('percentage', 'locked')
                        sections.append(f"  {idx}. {port_name} ({country}): Value={value}, Share={percentage}%")

        # Shipments (Sample Shipment Records)
        shipments = company_data.get("shipments", {})
        if shipments and "error" not in shipments:
            import_shipments = shipments.get("import_shipments", [])  # Fixed field name
            export_shipments = shipments.get("export_shipments", [])  # Fixed field name

            if import_shipments or export_shipments:
                sections.append("\n[RECENT SHIPMENTS]")

                if import_shipments:
                    sections.append("\nRecent Import Shipments:")
                    for idx, shipment in enumerate(import_shipments[:5], 1):
                        date = shipment.get('date', 'N/A')[:10]  # Extract date only
                        product = shipment.get('product_description', 'N/A')  # Fixed field name
                        origin = shipment.get('origin_country', 'N/A')
                        quantity = shipment.get('quantity', 'N/A')
                        hs_code = shipment.get('hs_code', 'N/A')
                        sections.append(f"  {idx}. {date} - HS {hs_code}")
                        sections.append(f"     {product[:100]}")
                        sections.append(f"     Origin: {origin}, Qty: {quantity}")

                if export_shipments:
                    sections.append("\nRecent Export Shipments:")
                    for idx, shipment in enumerate(export_shipments[:5], 1):
                        date = shipment.get('date', 'N/A')[:10]  # Extract date only
                        product = shipment.get('product_description', 'N/A')  # Fixed field name
                        destination = shipment.get('destination_country', 'N/A')
                        quantity = shipment.get('quantity', 'N/A')
                        hs_code = shipment.get('hs_code', 'N/A')
                        sections.append(f"  {idx}. {date} - HS {hs_code}")
                        sections.append(f"     {product[:100]}")
                        sections.append(f"     Destination: {destination}, Qty: {quantity}")

        # FAQs (Pre-formatted strings from API)
        faqs = company_data.get("faqs", {})
        if faqs and "error" not in faqs:
            # FAQs are returned as direct string values, not an array
            if any(v for k, v in faqs.items() if k != "error"):
                sections.append("\n[FREQUENTLY ASKED QUESTIONS]")

                # Top Suppliers
                if faqs.get("top_suppliers"):
                    sections.append(f"\nTop Suppliers:")
                    sections.append(f"  {faqs['top_suppliers']}")

                # Top Buyers
                if faqs.get("top_buyers"):
                    sections.append(f"\nTop Buyers:")
                    sections.append(f"  {faqs['top_buyers']}")

                # Import Turnover
                if faqs.get("import_turnover"):
                    sections.append(f"\nImport Turnover:")
                    sections.append(f"  {faqs['import_turnover']}")

                # Export Turnover
                if faqs.get("export_turnover"):
                    sections.append(f"\nExport Turnover:")
                    sections.append(f"  {faqs['export_turnover']}")

                # Monthly Import Trends
                if faqs.get("monthly_import"):
                    sections.append(f"\nMonthly Import Pattern:")
                    sections.append(f"  {faqs['monthly_import']}")

                # Monthly Export Trends
                if faqs.get("monthly_export"):
                    sections.append(f"\nMonthly Export Pattern:")
                    sections.append(f"  {faqs['monthly_export']}")

                # Top Import Countries
                if faqs.get("top_10_countries_import"):
                    sections.append(f"\nTop Import Countries Summary:")
                    sections.append(f"  {faqs['top_10_countries_import']}")

                # Top Export Countries
                if faqs.get("top_10_countries_export"):
                    sections.append(f"\nTop Export Countries Summary:")
                    sections.append(f"  {faqs['top_10_countries_export']}")

        return "\n".join(sections)

    @staticmethod
    def format_country_for_rag(country_data: Dict) -> str:
        """
        Format country data for RAG context (LLM consumption)

        Args:
            country_data: Complete country data from fetch_all_country_data()

        Returns:
            Formatted string ready for LLM context
        """
        if "error" in country_data:
            return f"Error fetching country data: {country_data.get('error')}"

        sections = []
        country_code = country_data.get("country_code", "Unknown")
        data_type = country_data.get("data_type", "import")

        # Country Statistics (use ACTUAL field names from API)
        stats = country_data.get("stats", {})
        if stats and "error" not in stats:
            date_range = stats.get('date_range', [])
            date_from = date_range[0] if len(date_range) > 0 else 'N/A'
            date_to = date_range[1] if len(date_range) > 1 else 'N/A'

            total_value = stats.get('total_shipment_value', 0)
            shipment_count = stats.get('shipment_records', 0)
            importers_count = stats.get('importers', 0)
            suppliers_count = stats.get('suppliers', 0)

            # Only add section if there's actual data
            if total_value > 0 or shipment_count > 0:
                sections.append(f"""[COUNTRY STATISTICS - {country_code.upper()} {data_type.upper()}]
Country: {country_code.title()}
Data Type: {data_type.title()}
Total Shipment Value: ${total_value:,.2f}
Total Shipment Records: {shipment_count:,}
Number of Importers: {importers_count:,}
Number of Suppliers: {suppliers_count:,}
Date Range: {date_from} to {date_to}""")

        # Top Importers/Exporters (use ACTUAL field names)
        importers = country_data.get("importers", {})
        if importers and "error" not in importers:
            # API returns portImportData array
            top_companies = importers.get("portImportData", [])
            if top_companies:
                sections.append(f"\n[TOP {data_type.upper()}ERS]")
                for idx, company in enumerate(top_companies[:10], 1):
                    # Adjust field names based on actual API response
                    name = company.get('importer', company.get('exporter', company.get('company_name', 'N/A')))
                    value = company.get('import_value', company.get('export_value', company.get('value', 'N/A')))
                    shipments = company.get('shipment_count', company.get('shipments', 'N/A'))
                    sections.append(f"  {idx}. {name}: Value={value}, Shipments={shipments}")

        # Top Trading Partners (use monthlyImportData from partners endpoint)
        partners = country_data.get("partners", {})
        if partners and "error" not in partners:
            partner_list = partners.get("monthlyImportData", [])
            if partner_list:
                sections.append(f"\n[TOP TRADING PARTNERS]")
                for idx, partner in enumerate(partner_list[:10], 1):
                    country_name = partner.get('partner_country', partner.get('country', 'N/A'))
                    value = partner.get('trade_value', partner.get('value', 'N/A'))
                    percentage = partner.get('share', partner.get('percentage', 'N/A'))
                    sections.append(f"  {idx}. {country_name}: Value={value}, Share={percentage}%")

        # Top Ports (use portImportData from ports endpoint)
        ports = country_data.get("ports", {})
        if ports and "error" not in ports:
            port_list = ports.get("portImportData", [])
            if port_list:
                sections.append(f"\n[TOP PORTS]")
                for idx, port in enumerate(port_list[:10], 1):
                    port_name = port.get('port_name', port.get('port', 'N/A'))
                    value = port.get('port_value', port.get('value', 'N/A'))
                    shipments = port.get('shipment_count', port.get('shipments', 'N/A'))
                    sections.append(f"  {idx}. {port_name}: Value={value}, Shipments={shipments}")

        # Top HS Chapters
        chapters = country_data.get("chapters", {})
        if chapters and "error" not in chapters:
            # Handle both list and dict responses
            chapter_list = chapters if isinstance(chapters, list) else chapters.get("data", [])
            if chapter_list:
                sections.append(f"\n[TOP HS CODE CHAPTERS]")
                for idx, chapter in enumerate(chapter_list[:10], 1):
                    hs_code = chapter.get('hs_code', 'N/A')
                    description = chapter.get('description', 'N/A')
                    value = chapter.get('value', 'N/A')
                    sections.append(f"  {idx}. HS {hs_code} - {description}: Value={value}")

        # Top Commodities
        commodities = country_data.get("commodities", {})
        if commodities and "error" not in commodities:
            # Handle both list and dict responses
            commodity_list = commodities if isinstance(commodities, list) else commodities.get("data", [])
            if commodity_list:
                sections.append(f"\n[TOP COMMODITIES]")
                for idx, commodity in enumerate(commodity_list[:10], 1):
                    name = commodity.get('commodity', 'N/A')
                    value = commodity.get('value', 'N/A')
                    shipments = commodity.get('shipments', 'N/A')
                    sections.append(f"  {idx}. {name}: Value={value}, Shipments={shipments}")

        # Monthly Trends (use monthlyImportData)
        monthly = country_data.get("monthly", {})
        if monthly and "error" not in monthly:
            trends = monthly.get("monthlyImportData", [])
            if trends:
                sections.append(f"\n[MONTHLY TRENDS]")
                for trend in trends[-6:]:  # Last 6 months
                    month = trend.get('month', trend.get('period', 'N/A'))
                    value = trend.get('monthly_value', trend.get('value', 'N/A'))
                    shipments = trend.get('shipment_count', trend.get('shipments', 'N/A'))
                    sections.append(f"  • {month}: Value={value}, Shipments={shipments}")

        # FAQs
        faqs = country_data.get("faqs", {})
        if faqs and "error" not in faqs:
            # Handle both list and dict responses
            faq_list = faqs if isinstance(faqs, list) else faqs.get("data", [])
            if faq_list:
                sections.append(f"\n[FREQUENTLY ASKED QUESTIONS]")
                for faq in faq_list[:5]:
                    question = faq.get('question', 'N/A')
                    answer = faq.get('answer', 'N/A')
                    sections.append(f"  Q: {question}")
                    sections.append(f"  A: {answer}\n")

        # If no sections were added, provide helpful message
        if not sections:
            return f"""[NO DATA AVAILABLE - {country_code.upper()}]

The Marketinside API did not return any {data_type} data for {country_code.title()}.

This could mean:
- Country data is not available in the current subscription tier
- Data for this country is not yet available in the database
- The country code or data type may not be supported

To get accurate trade data for {country_code.title()}, you may need to:
1. Verify the country is supported by Marketinside
2. Check if a premium subscription is required for this data
3. Try searching for specific companies from {country_code.title()} instead"""

        return "\n".join(sections)


# ============================================================================
# CONVENIENCE FUNCTION FOR CHATBOT INTEGRATION
# ============================================================================

async def fetch_company_data_from_url(url: str, bearer_token: Optional[str] = None) -> str:
    """
    Convenience function to fetch and format company data from Marketinside URL

    Args:
        url: Marketinside company profile URL
        bearer_token: Optional bearer token (defaults to env var)

    Returns:
        Formatted company data as string for RAG context
    """
    client = MarketinsideAPIClient(bearer_token=bearer_token)

    # Check if it's a company URL
    if not client.is_company_url(url):
        return ""

    # Extract company code
    company_code = client.extract_company_code(url)

    if not company_code:
        logger.warning(f"Could not extract company code from URL: {url}")
        return ""

    # Fetch all data
    data = await client.fetch_all_company_data(company_code)

    # Format for RAG
    formatted = client.format_for_rag(data)

    return formatted


async def fetch_country_data_from_url(
    url: str,
    bearer_token: Optional[str] = None,
    data_type: str = "import"
) -> str:
    """
    Convenience function to fetch and format country data from Marketinside URL

    Args:
        url: Marketinside country profile URL
        bearer_token: Optional bearer token (defaults to env var)
        data_type: 'import' or 'export'

    Returns:
        Formatted country data as string for RAG context
    """
    client = MarketinsideAPIClient(bearer_token=bearer_token)

    # Check if it's a country URL
    if not client.is_country_url(url):
        return ""

    # Extract country code (now returns ISO code like "AR" instead of "argentina")
    country_code = await client.extract_country_code(url)

    if not country_code:
        logger.warning(f"Could not extract country code from URL: {url}")
        return ""

    # Fetch all data
    data = await client.fetch_all_country_data(country_code, data_type)

    # Format for RAG
    formatted = client.format_country_for_rag(data)

    return formatted
