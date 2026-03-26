"""
URL Validator - Intelligent edge case detection for trade data URLs

Only escalates to support when data is truly unavailable or URL would be broken.
Normal queries with valid data show URLs as expected.
"""

from typing import Dict, Any, Tuple, Optional
import re


class URLValidator:
    """Validates if URLs should be shown or if query needs dashboard/support"""

    CONTINENTS = {
        "africa", "asia", "europe", "north america", "south america",
        "oceania", "antarctica", "america", "asia pacific", "global"
    }

    # Countries with no bilateral trade data (embargo/sanctions)
    RESTRICTED_PAIRS = {
        ("north-korea", "*"),
        ("*", "north-korea"),
        ("iran", "usa"),
        ("usa", "iran"),
        # Add more as discovered
    }

    def __init__(self):
        self._mirror_cache = {}  # Cache for mirror/detailed checks

    def should_show_url(
        self,
        intent: str,
        params: Dict[str, Any],
        api_data: Optional[str] = None
    ) -> Tuple[bool, str, str]:
        """
        Determine if URL should be shown or redirect to support.

        Args:
            intent: Query intent
            params: Extracted parameters
            api_data: API response data (optional, for zero-value check)

        Returns:
            (show_url: bool, reason: str, message: str)
            - show_url: True = show URL normally, False = redirect to support
            - reason: Why URL wasn't shown (for logging)
            - message: User-friendly explanation
        """

        # Check 1: Continent queries (no specific country URL)
        if self._is_continent_query(params):
            return self._handle_continent_query(params)

        # Check 2: Country-to-continent mix
        if self._is_country_continent_mix(params):
            return self._handle_country_continent_mix(params)

        # Check 3: Mirror-to-mirror country queries (limited data)
        if intent == "country_to_country":
            result = self._check_mirror_to_mirror(params)
            if result is not None:
                return result

        # Check 4: Zero values (no actual trade data)
        if api_data and self._has_zero_values(api_data):
            return self._handle_zero_data(params)

        # Check 5: Would result in 404
        if self._would_be_404(intent, params):
            return self._handle_404(params)

        # All checks passed - show URL normally
        return True, "valid", ""

    def _is_continent_query(self, params: Dict[str, Any]) -> bool:
        """Check if query is about a continent (not a specific country)"""
        for key in ["country", "origin_country", "destination_country"]:
            value = params.get(key, "").lower().strip().replace("-", " ")
            if value in self.CONTINENTS:
                return True
        return False

    def _is_country_continent_mix(self, params: Dict[str, Any]) -> bool:
        """Check if query mixes country and continent"""
        origin = params.get("origin_country", "").lower().strip().replace("-", " ")
        dest = params.get("destination_country", "").lower().strip().replace("-", " ")

        if origin and dest:
            origin_is_continent = origin in self.CONTINENTS
            dest_is_continent = dest in self.CONTINENTS
            # Return true if one is continent and other is country
            return origin_is_continent != dest_is_continent

        return False

    def _check_mirror_to_mirror(self, params: Dict[str, Any]) -> Optional[Tuple[bool, str, str]]:
        """
        Check if both countries in bilateral query are mirror-only.

        Note: This is a simplified check. In production, you'd query the API
        to check if both countries are mirror-only.

        For now, we'll skip this check and let the URL show normally.
        The API client already handles mirror vs detailed internally.
        """
        # TODO: Implement if needed for specific business logic
        # For now, return None to continue normal flow
        return None

    def _has_zero_values(self, api_data: str) -> bool:
        """Check if API data shows no actual trade (all zeros/empty)"""
        if not api_data:
            return False

        # CRITICAL: Only check Total Shipments and Total Value, not N/A company names
        # Company names can be N/A but data still exists (shipment records, values, etc.)

        # Check for explicit zero indicators in totals
        zero_indicators = [
            "Total Shipments: 0",
            "Total Value: $0",
            "Total Value: $0.00",
            "Total Value: USD 0",
            "No shipments found",
            "No data available",
        ]

        for indicator in zero_indicators:
            if indicator in api_data:
                return True

        # DO NOT check for N/A in records - company names can be N/A but data exists
        # The shipment records, values, and trade data are what matter, not company names

        return False

    def _would_be_404(self, intent: str, params: Dict[str, Any]) -> bool:
        """Check if URL would result in 404"""
        if intent != "country_to_country":
            return False

        origin = params.get("origin_country", "").lower().replace(" ", "-")
        dest = params.get("destination_country", "").lower().replace(" ", "-")

        if not origin or not dest:
            return False

        # Check against restricted pairs
        for restricted_origin, restricted_dest in self.RESTRICTED_PAIRS:
            if restricted_origin == "*" or restricted_origin == origin:
                if restricted_dest == "*" or restricted_dest == dest:
                    return True

        return False

    def _handle_continent_query(self, params: Dict[str, Any]) -> Tuple[bool, str, str]:
        """Generate response for continent queries"""
        continent = self._extract_continent(params)

        message = (
            f"Great question about {continent} trade! Continental-level analysis requires "
            f"aggregating data across multiple countries. Our dashboard is perfect for this - "
            f"it provides multi-country comparisons, regional trends, and comprehensive trade flows. "
            f"Would you like to see specific country data first, or explore our dashboard for the full picture?"
        )

        return False, "continent_query", message

    def _handle_country_continent_mix(self, params: Dict[str, Any]) -> Tuple[bool, str, str]:
        """Generate response for country-continent mix"""
        message = (
            f"Trade analysis between a country and an entire continent requires "
            f"multi-country data aggregation. Our dashboard provides this comprehensive view. "
            f"For now, I can show you data for specific country pairs if you'd like to narrow it down?"
        )

        return False, "country_continent_mix", message

    def _handle_zero_data(self, params: Dict[str, Any]) -> Tuple[bool, str, str]:
        """Generate response when data shows zero values"""
        country = params.get("country", params.get("origin_country", "this query"))
        product = params.get("product", params.get("hs_code", "this product"))

        message = (
            f"I couldn't find recent trade data for {product} from {country}. This could mean:\n"
            f"• Limited or no recent shipments in this category\n"
            f"• Data might be available under a different product classification\n"
            f"• Try a broader product search or different time period\n\n"
            f"Our dashboard offers advanced search and historical data. "
            f"Or I can help you search for similar products?"
        )

        return False, "no_data", message

    def _handle_404(self, params: Dict[str, Any]) -> Tuple[bool, str, str]:
        """Generate response for queries that would 404"""
        origin = params.get("origin_country", "")
        dest = params.get("destination_country", "")

        message = (
            f"Trade data between {origin.title()} and {dest.title()} requires special access "
            f"due to data restrictions. Our dashboard team can provide custom data requests "
            f"for restricted country pairs. Would you like to try a different country combination?"
        )

        return False, "restricted_404", message

    def _extract_continent(self, params: Dict[str, Any]) -> str:
        """Extract continent name from params"""
        for key in ["country", "origin_country", "destination_country"]:
            value = params.get(key, "").strip().replace("-", " ")
            if value.lower() in self.CONTINENTS:
                return value.title()
        return "this region"


# Singleton instance
_validator_instance = None


def get_url_validator() -> URLValidator:
    """Get or create URL validator singleton"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = URLValidator()
    return _validator_instance
