"""
IP Geolocation Utility

Uses IP address to determine user's location (country, region, city).
Supports multiple geolocation services with fallback.
"""

import asyncio
import aiohttp
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class GeolocationService:
    """
    Service to get location information from IP address.

    Uses multiple providers with fallback:
    1. ip-api.com (free, no key required, 45 req/min)
    2. ipapi.co (free, 1000 req/day, no key for basic)
    """

    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    async def get_location_from_ip(self, ip_address: str) -> Dict[str, Optional[str]]:
        """
        Get location information from IP address.

        Args:
            ip_address: IPv4 or IPv6 address

        Returns:
            Dict with country, region, city, timezone
        """
        # Skip private/local IPs
        if self._is_private_ip(ip_address):
            logger.info(f"[Geolocation] Private IP detected: {ip_address}")
            return {
                'country': 'Local',
                'region': 'Local',
                'city': 'Local',
                'timezone': None
            }

        # Try primary service: ip-api.com
        result = await self._try_ipapi_com(ip_address)
        if result:
            return result

        # Try fallback service: ipapi.co
        result = await self._try_ipapi_co(ip_address)
        if result:
            return result

        # All services failed
        logger.warning(f"[Geolocation] All services failed for IP: {ip_address}")
        return {
            'country': None,
            'region': None,
            'city': None,
            'timezone': None
        }

    async def _try_ipapi_com(self, ip_address: str) -> Optional[Dict[str, Optional[str]]]:
        """
        Try ip-api.com service.
        Free tier: 45 requests per minute, no API key required.
        """
        try:
            url = f"http://ip-api.com/json/{ip_address}?fields=status,country,regionName,city,timezone"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status == 200:
                        data = await response.json()

                        if data.get('status') == 'success':
                            return {
                                'country': data.get('country'),
                                'region': data.get('regionName'),
                                'city': data.get('city'),
                                'timezone': data.get('timezone')
                            }

            logger.warning(f"[Geolocation] ip-api.com returned unsuccessful status for {ip_address}")
            return None

        except asyncio.TimeoutError:
            logger.warning(f"[Geolocation] ip-api.com timeout for {ip_address}")
            return None
        except Exception as e:
            logger.warning(f"[Geolocation] ip-api.com error for {ip_address}: {e}")
            return None

    async def _try_ipapi_co(self, ip_address: str) -> Optional[Dict[str, Optional[str]]]:
        """
        Try ipapi.co service.
        Free tier: 1000 requests per day, no API key required.
        """
        try:
            url = f"https://ipapi.co/{ip_address}/json/"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Check if error field exists (rate limit or invalid IP)
                        if 'error' in data:
                            logger.warning(f"[Geolocation] ipapi.co error: {data.get('reason', 'Unknown')}")
                            return None

                        return {
                            'country': data.get('country_name'),
                            'region': data.get('region'),
                            'city': data.get('city'),
                            'timezone': data.get('timezone')
                        }

            logger.warning(f"[Geolocation] ipapi.co returned status {response.status} for {ip_address}")
            return None

        except asyncio.TimeoutError:
            logger.warning(f"[Geolocation] ipapi.co timeout for {ip_address}")
            return None
        except Exception as e:
            logger.warning(f"[Geolocation] ipapi.co error for {ip_address}: {e}")
            return None

    def _is_private_ip(self, ip_address: str) -> bool:
        """
        Check if IP address is private/local.

        Returns True for:
        - localhost (127.0.0.1, ::1)
        - private networks (10.x.x.x, 192.168.x.x, 172.16-31.x.x)
        - link-local (169.254.x.x)
        """
        if not ip_address:
            return True

        # Localhost
        if ip_address in ['127.0.0.1', '::1', 'localhost']:
            return True

        # IPv4 private ranges
        parts = ip_address.split('.')
        if len(parts) == 4:
            try:
                first = int(parts[0])
                second = int(parts[1])

                # 10.0.0.0/8
                if first == 10:
                    return True

                # 172.16.0.0/12
                if first == 172 and 16 <= second <= 31:
                    return True

                # 192.168.0.0/16
                if first == 192 and second == 168:
                    return True

                # 169.254.0.0/16 (link-local)
                if first == 169 and second == 254:
                    return True

            except ValueError:
                pass

        # IPv6 private/local
        if ip_address.startswith('fe80:') or ip_address.startswith('fc00:') or ip_address.startswith('fd00:'):
            return True

        return False


# Singleton instance
_geolocation_service: Optional[GeolocationService] = None


def get_geolocation_service() -> GeolocationService:
    """Get or create geolocation service singleton"""
    global _geolocation_service

    if _geolocation_service is None:
        _geolocation_service = GeolocationService()

    return _geolocation_service


async def get_location_from_ip(ip_address: str) -> Dict[str, Optional[str]]:
    """
    Convenience function to get location from IP.

    Args:
        ip_address: IP address to lookup

    Returns:
        Dict with country, region, city, timezone
    """
    service = get_geolocation_service()
    return await service.get_location_from_ip(ip_address)
