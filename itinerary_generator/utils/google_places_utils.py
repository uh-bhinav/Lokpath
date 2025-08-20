# itinerary_generator/utils/google_places_utils.py
"""
Thin, safe wrapper(s) around the canonical Google Places fetchers in the
Itinerarybuilder package. This module:
- Avoids handling credentials (delegated to Itinerarybuilder).
- Is resilient to package name casing (Itinerarybuilder vs itinerarybuilder).
- Adds optional text-query search support for the /search-places route.
- Never raises on normal failures; returns [] and logs context instead.
"""

from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Try both casings to be robust across OS/filesystem setups
_fetch_places = None
_text_search = None

try:
    from Itinerarybuilder.fetch_places import fetch_places as _fetch_places  # type: ignore
    try:
        # If a dedicated text search exists, use it (optional)
        from Itinerarybuilder.fetch_places import text_search as _text_search  # type: ignore
    except Exception:
        _text_search = None
except Exception:
    try:
        from itinerarybuilder.fetch_places import fetch_places as _fetch_places  # type: ignore
        try:
            from itinerarybuilder.fetch_places import text_search as _text_search  # type: ignore
        except Exception:
            _text_search = None
    except Exception as e:
        # We will handle this at call-sites and return [].
        logger.error("Failed to import Itinerarybuilder.fetch_places: %s", e)


def fetch_google_places(
    location: str,
    max_results: int = 20,
    radius: int = 15000,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch POIs for a location using the project's canonical Google Places fetcher.

    Args:
        location: City/region name (e.g., "Coorg").
        max_results: Upper bound on returned POIs.
        radius: Search radius in meters (only used if supported by underlying fetcher).
        query: Optional text query for name-based search (e.g., "Raja", "waterfall").

    Returns:
        A list[dict] of POIs (raw, not normalized), or [] on failure.
    """
    if _fetch_places is None:
        logger.error("fetch_google_places called but _fetch_places is unavailable.")
        return []

    try:
        # If the Itinerarybuilder layer exposes a dedicated text search, prefer it.
        if query and _text_search:
            results = _text_search(location=location, query=query, max_results=max_results, radius=radius)
            return results or []

        # Otherwise, fetch broadly and (optionally) filter client-side by query
        results = _fetch_places(location=location, max_results=max_results, radius=radius) or []

        if query:
            q = query.casefold()
            # Lightweight name filter; proper filtering/ranking should still happen upstream.
            results = [p for p in results if (p.get("name") or "").casefold().find(q) != -1]

        # Enforce max_results cap after filtering
        if max_results and max_results > 0:
            results = results[:max_results]

        return results

    except Exception as e:
        logger.error(
            "Error in fetch_google_places(location=%r, query=%r, max_results=%r, radius=%r): %s",
            location, query, max_results, radius, e
        )
        return []
