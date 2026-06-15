"""
Geo Resolver — reverse geocode GPS coordinates to addresses.

Since GPS is optional, this module only activates when coordinates are available.
Uses a local SQLite cache to avoid repeated API calls.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GeoCache

logger = logging.getLogger("geo_resolver")


async def resolve(
    db: Session,
    latitude: float,
    longitude: float,
) -> dict[str, str | None]:
    """Resolve a GPS coordinate to an address.

    Returns cached result if available. When the cache is cold and no
    external API is configured, returns an empty dict gracefully.

    Never raises — Geo is optional in TJOS.
    """
    # Check cache
    cached = db.scalar(
        select(GeoCache).where(
            GeoCache.latitude == round(latitude, 5),
            GeoCache.longitude == round(longitude, 5),
        )
    )
    if cached:
        return {
            "address": cached.address,
            "city": cached.city,
            "province": cached.province,
            "country": cached.country,
        }

    # No external API configured — just cache the miss
    # Users can plug in Nominatim, Google Maps, Amap (高德), etc.
    entry = GeoCache(
        latitude=round(latitude, 5),
        longitude=round(longitude, 5),
        address=None,
        city=None,
        province=None,
        country=None,
        resolved_at=datetime.now(),
    )
    db.add(entry)
    db.flush()

    return {"address": None, "city": None, "province": None, "country": None}


async def resolve_with_provider(
    db: Session,
    latitude: float,
    longitude: float,
    provider: str = "nominatim",
) -> dict[str, str | None]:
    """Resolve coordinates using an external geocoding provider.

    Supported providers:
      - nominatim: OpenStreetMap (free, rate-limited)
      - amap: 高德地图 (good for China)
    """
    result = await _call_provider(latitude, longitude, provider)

    # Cache the result
    cached = db.scalar(
        select(GeoCache).where(
            GeoCache.latitude == round(latitude, 5),
            GeoCache.longitude == round(longitude, 5),
        )
    )
    if cached:
        cached.address = result.get("address")
        cached.city = result.get("city")
        cached.province = result.get("province")
        cached.country = result.get("country")
        cached.resolved_at = datetime.now()
    else:
        entry = GeoCache(
            latitude=round(latitude, 5),
            longitude=round(longitude, 5),
            address=result.get("address"),
            city=result.get("city"),
            province=result.get("province"),
            country=result.get("country"),
            resolved_at=datetime.now(),
        )
        db.add(entry)

    db.flush()
    return result


async def _call_provider(
    latitude: float,
    longitude: float,
    provider: str,
) -> dict[str, str | None]:
    """Call an external geocoding API. Returns empty dict on failure."""
    try:
        import httpx

        if provider == "nominatim":
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://nominatim.openstreetmap.org/reverse",
                    params={"lat": latitude, "lon": longitude, "format": "json"},
                    headers={"User-Agent": "TeslaJourneyOS/1.0"},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    addr = data.get("address", {})
                    return {
                        "address": data.get("display_name"),
                        "city": addr.get("city") or addr.get("town") or addr.get("village"),
                        "province": addr.get("state") or addr.get("province"),
                        "country": addr.get("country"),
                    }

        elif provider == "amap":
            # 高德地图 reverse geocoding — requires API key in env
            import os
            api_key = os.environ.get("AMAP_API_KEY", "")
            if not api_key:
                logger.warning("AMAP_API_KEY not set")
                return {}
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://restapi.amap.com/v3/geocode/regeo",
                    params={
                        "location": f"{longitude},{latitude}",
                        "key": api_key,
                    },
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    regeo = data.get("regeocode", {})
                    comp = regeo.get("addressComponent", {})
                    return {
                        "address": regeo.get("formatted_address"),
                        "city": comp.get("city"),
                        "province": comp.get("province"),
                        "country": comp.get("country", "中国"),
                    }

    except Exception:
        logger.debug("Geocoding failed for %s provider", provider, exc_info=True)

    return {"address": None, "city": None, "province": None, "country": None}
