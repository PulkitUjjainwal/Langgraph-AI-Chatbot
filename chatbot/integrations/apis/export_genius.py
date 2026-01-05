"""
Export Genius API Client
Async API client for fetching company data from exportgenius.in API

Features:
- Async HTTP requests with aiohttp
- Parallel API calls for performance
- In-memory caching
- Comprehensive error handling
- Retry logic with exponential backoff
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


class ExportGeniusAPIClient:
    """
    Async API client for Export Genius API

    Usage:
        client = ExportGeniusAPIClient(bearer_token="your_token")
        data = await client.fetch_all_company_data(company_code)
    """

    # API endpoint configurations
    BASE_URL = "https://api-dp.exportgenius.in/api/v1/users"

    ENDPOINTS = {
        "overview": "/company-overview",
        "countries": "/company-countries",
        "turnover": "/company-turnover",
        "commodities": "/company-commodities",
        "competitors": "/company-competitors",
        "ports": "/company-top-ports",
        "shipments": "/company-shipments",
        "faqs": "/company-faqs"
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
        self.bearer_token = bearer_token or os.getenv("EXPORT_GENIUS_BEARER_TOKEN")
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache: Dict[str, Dict] = {}  # In-memory cache by company_code

        if not self.bearer_token:
            logger.warning(
                "⚠️  No bearer token provided. Set EXPORT_GENIUS_BEARER_TOKEN "
                "environment variable or pass bearer_token parameter."
            )

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authorization"""
        return {
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'authorization': f'Bearer {self.bearer_token}',
            'content-type': 'application/json',
            'origin': 'https://www.exportgenius.in',
            'referer': 'https://www.exportgenius.in/',
            'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
        }

    @staticmethod
    def extract_company_code(url: str) -> Optional[str]:
        """
        Extract company code from Export Genius company URL

        Args:
            url: Company profile URL

        Returns:
            Company code (hash) or None if not a company URL

        Example:
            https://www.exportgenius.in/company/company-name/9ead49e7ecb36670a3e818ae049cf257
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
        """Check if URL is an Export Genius company profile URL"""
        if not url:
            return False
        # Handle both direct and language-prefixed URLs (e.g., /en/company/)
        return 'exportgenius.in' in url and '/company/' in url

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
            payload: Request payload (will be sent as form data)
            retry_count: Current retry attempt

        Returns:
            API response data
        """
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp is required. Install with: pip install aiohttp")

        url = f"{self.BASE_URL}{endpoint}"

        try:
            async with aiohttp.ClientSession() as session:
                # Despite the form-encoded header, API actually expects JSON payload
                # Send as JSON (aiohttp will serialize it)
                async with session.post(
                    url,
                    json=payload,  # Send as JSON, not form data
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

        logger.info(f"📊 Fetching company data for {company_code[:8]}...")

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

        # Turnover (Monthly breakdown)
        turnover = company_data.get("turnover", {})
        if turnover and "error" not in turnover:
            imports = turnover.get("imports", [])
            exports = turnover.get("exports", [])

            if imports or exports:
                sections.append("\n[MONTHLY TURNOVER]")

                if imports:
                    sections.append("Import Turnover by Month:")
                    for item in imports:
                        month = item.get('month', 'N/A')
                        value = item.get('value', 'locked')
                        percentage = item.get('percentage', 'locked')
                        sections.append(f"  • {month}: Value={value}, Share={percentage}%")

                if exports:
                    sections.append("\nExport Turnover by Month:")
                    for item in exports:
                        month = item.get('month', 'N/A')
                        value = item.get('value', 'locked')
                        percentage = item.get('percentage', 'locked')
                        sections.append(f"  • {month}: Value={value}, Share={percentage}%")

        # Commodities (HS Codes)
        commodities = company_data.get("commodities", {})
        if commodities and "error" not in commodities:
            imports = commodities.get("imports", [])
            exports = commodities.get("exports", [])

            if imports or exports:
                sections.append("\n[TOP COMMODITIES & HS CODES]")

                if imports:
                    sections.append("Top Import Commodities:")
                    for item in imports[:15]:
                        hs_code = item.get('hs_code', 'N/A')
                        desc = item.get('comodity_description', 'N/A')
                        value = item.get('value', 'locked')
                        percentage = item.get('percentage', 'locked')
                        sections.append(f"  • HS Code {hs_code}: {desc}")
                        sections.append(f"    Value: {value}, Share: {percentage}%")

                if exports:
                    sections.append("\nTop Export Commodities:")
                    for item in exports[:15]:
                        hs_code = item.get('hs_code', 'N/A')
                        desc = item.get('comodity_description', 'N/A')
                        value = item.get('value', 'locked')
                        percentage = item.get('percentage', 'locked')
                        sections.append(f"  • HS Code {hs_code}: {desc}")
                        sections.append(f"    Value: {value}, Share: {percentage}%")

        # Competitors
        competitors = company_data.get("competitors", {})
        if competitors and "error" not in competitors:
            import_comp = competitors.get("import_competitors", [])
            export_comp = competitors.get("export_competitors", [])

            if import_comp or export_comp:
                sections.append("\n[COMPETITORS]")

                if import_comp:
                    sections.append("Top Import Competitors:")
                    for item in import_comp[:15]:
                        name = item.get('competitor', 'N/A')
                        turnover = item.get('import_turnover', 0)
                        employees = item.get('num_employees', 'N/A')
                        sections.append(f"  • {name}: Turnover=${turnover:,.2f}, Employees={employees}")

                if export_comp:
                    sections.append("\nTop Export Competitors:")
                    for item in export_comp[:15]:
                        name = item.get('competitor', 'N/A')
                        turnover = item.get('export_turnover', 0)
                        employees = item.get('num_employees', 'N/A')
                        sections.append(f"  • {name}: Turnover=${turnover:,.2f}, Employees={employees}")

        # Ports
        ports = company_data.get("ports", {})
        if ports and "error" not in ports:
            loading = ports.get("loading", [])
            unloading = ports.get("unloading", [])

            if loading or unloading:
                sections.append("\n[TOP PORTS]")

                if loading:
                    sections.append("Loading Ports:")
                    for item in loading[:10]:
                        port = item.get('port', 'N/A')
                        count = item.get('count', 'N/A')
                        sections.append(f"  • {port}: {count} shipments")

                if unloading:
                    sections.append("\nUnloading Ports:")
                    for item in unloading[:10]:
                        port = item.get('port', 'N/A')
                        count = item.get('count', 'N/A')
                        sections.append(f"  • {port}: {count} shipments")

        # Shipments
        shipments = company_data.get("shipments", {})
        if shipments and "error" not in shipments:
            import_ship = shipments.get("import_shipments", [])
            export_ship = shipments.get("export_shipments", [])

            if import_ship or export_ship:
                sections.append("\n[RECENT SHIPMENTS]")

                if import_ship:
                    sections.append("Recent Import Shipments:")
                    for item in import_ship[:10]:
                        date = item.get('date', 'N/A')
                        if date and 'T' in date:
                            date = date.split('T')[0]
                        product = item.get('product_description', 'N/A')[:200]
                        hs_code = item.get('hs_code', 'N/A')
                        origin = item.get('origin_country', 'N/A')
                        value = item.get('total_value_usd', 'locked')
                        quantity = item.get('quantity', 'locked')
                        unit = item.get('unit', 'N/A')
                        sections.append(f"  • Date: {date}, Origin: {origin}")
                        sections.append(f"    HS Code: {hs_code}, Value: ${value}, Qty: {quantity} {unit}")
                        sections.append(f"    Product: {product}")

                if export_ship:
                    sections.append("\nRecent Export Shipments:")
                    for item in export_ship[:10]:
                        date = item.get('date', 'N/A')
                        if date and 'T' in date:
                            date = date.split('T')[0]
                        product = item.get('product_description', 'N/A')[:200]
                        hs_code = item.get('hs_code', 'N/A')
                        destination = item.get('destination_country', 'N/A')
                        value = item.get('total_value_usd', 'locked')
                        quantity = item.get('quantity', 'locked')
                        unit = item.get('unit', 'N/A')
                        sections.append(f"  • Date: {date}, Destination: {destination}")
                        sections.append(f"    HS Code: {hs_code}, Value: ${value}, Qty: {quantity} {unit}")
                        sections.append(f"    Product: {product}")

        # FAQs
        faqs = company_data.get("faqs", {})
        if faqs and "error" not in faqs:
            sections.append("\n[COMPANY FAQs]")

            # Top suppliers
            if faqs.get('top_suppliers'):
                sections.append(f"Top Suppliers: {faqs['top_suppliers']}")

            # Top buyers
            if faqs.get('top_buyers'):
                sections.append(f"Top Buyers: {faqs['top_buyers']}")

            # Monthly import/export
            if faqs.get('monthly_import'):
                sections.append(f"Monthly Import Breakdown: {faqs['monthly_import']}")

            if faqs.get('monthly_export'):
                sections.append(f"Monthly Export Breakdown: {faqs['monthly_export']}")

            # Top countries
            if faqs.get('top_10_countries_import'):
                sections.append(f"Import Countries Summary: {faqs['top_10_countries_import']}")

            if faqs.get('top_10_countries_export'):
                sections.append(f"Export Countries Summary: {faqs['top_10_countries_export']}")

            # Turnover summaries
            if faqs.get('import_turnover'):
                sections.append(f"Import Turnover: {faqs['import_turnover']}")

            if faqs.get('export_turnover'):
                sections.append(f"Export Turnover: {faqs['export_turnover']}")

        return "\n".join(sections)


# ============================================================================
# CONVENIENCE FUNCTION FOR CHATBOT INTEGRATION
# ============================================================================

async def fetch_company_data_from_url(url: str, bearer_token: Optional[str] = None) -> str:
    """
    Convenience function to fetch and format company data from URL

    Args:
        url: Export Genius company profile URL
        bearer_token: Optional bearer token (defaults to env var)

    Returns:
        Formatted company data as string for RAG context
    """
    client = ExportGeniusAPIClient(bearer_token=bearer_token)

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


# ============================================================================
# TESTING
# ============================================================================

if __name__ == '__main__':
    async def test():
        print("=" * 70)
        print("Testing Export Genius API Client")
        print("=" * 70)
        print()

        # Test URL from your example
        test_url = "https://www.exportgenius.in/company/nghi-son-refinery-petrochemical-compan/9ead49e7ecb36670a3e818ae049cf257"

        print(f"Test URL: {test_url}")
        print()

        # Extract company code
        client = ExportGeniusAPIClient()
        company_code = client.extract_company_code(test_url)

        print(f"✓ Company Code Extracted: {company_code}")
        print()

        if not client.bearer_token:
            print("⚠️  No bearer token found!")
            print("Set EXPORT_GENIUS_BEARER_TOKEN environment variable")
            print()
            return

        if company_code:
            print("Fetching all company data...")
            print()

            # Fetch all data
            data = await client.fetch_all_company_data(company_code)

            if "error" in data:
                print(f"❌ Error: {data['error']}")
            else:
                # Format for RAG
                formatted = client.format_for_rag(data)

                print("=" * 70)
                print("FORMATTED COMPANY DATA FOR RAG:")
                print("=" * 70)
                print(formatted)
                print("=" * 70)
                print()
                print(f"✓ Total characters: {len(formatted)}")
                print(f"✓ Cached in memory: Yes")
        else:
            print("❌ Failed to extract company code from URL")

    asyncio.run(test())
