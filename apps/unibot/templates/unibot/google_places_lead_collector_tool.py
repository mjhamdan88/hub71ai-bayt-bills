import time
import requests
from typing import List, Dict, Any, Optional
from unibot.services.credentials import get_credentials
from unibot.services.tool_exceptions import ToolHandlerError, ToolHandlerWarning

# Google Places API endpoints
PLACES_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Credential key used for this tool (long, specific to avoid conflicts)
CRED_KEY = "GOOGLE_PLACES_API_KEY_FOR_LEAD_COLLECTOR_TOOL"


def _fetch_place_details(place_id: str, api_key: str) -> Dict[str, Any]:
    """Fetch detailed information for a single place."""
    details_params = {
        "place_id": place_id,
        "fields": "name,formatted_address,international_phone_number,website,rating,reviews",
        "key": api_key,
    }
    resp = requests.get(PLACE_DETAILS_URL, params=details_params, timeout=10)
    data = resp.json()
    result = data.get("result", {})
    # Extract some reviews snippets if available (max 3)
    reviews_data = result.get("reviews", [])[:3]
    reviews = [r.get("text") for r in reviews_data]
    return {
        "name": result.get("name"),
        "address": result.get("formatted_address"),
        "phone": result.get("international_phone_number"),
        "website": result.get("website"),
        "rating": result.get("rating"),
        "reviews": reviews,
    }


def collect_google_places_leads(query: str, location: str, radius: int = 50000, num_leads: int = 50) -> Dict[str, Any]:
    """Collect business leads from Google Places based on a text search.

    Args:
        query: Search term, e.g., "plumber" or "coffee shop".
        location: Lat,lng string indicating search center.
        radius: Search radius in meters (max 50000).
        num_leads: Total number of leads to collect (pagination will continue until reached or no more results).
    Returns:
        Dict with a list under "leads" key.
    """

    creds = get_credentials([
        {"key": CRED_KEY, "label": "Google Places API Key for Lead Collector", "type": "password", "placeholder": "Enter your Google Places API key"}
    ])
    if creds is None:
        raise ToolHandlerError("API key is not set. A link to configure it has been sent to you.")
    api_key = creds[CRED_KEY]

    params = {
        "query": query,
        "location": location,
        "radius": radius,
        "key": api_key,
    }

    leads: List[Dict[str, Any]] = []
    next_page_token: Optional[str] = None

    while len(leads) < num_leads:
        if next_page_token:
            params["pagetoken"] = next_page_token
            # Google recommends waiting a short period before using next_page_token
            time.sleep(2)
        resp = requests.get(PLACES_SEARCH_URL, params=params, timeout=10)
        data = resp.json()
        results = data.get("results", [])
        for r in results:
            if len(leads) >= num_leads:
                break
            place_id = r.get("place_id")
            if not place_id:
                continue
            try:
                details = _fetch_place_details(place_id, api_key)
                leads.append(details)
            except Exception:
                # Skip place if details fetch fails
                continue
        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break  # No more pages

    if not leads:
        raise ToolHandlerWarning("No leads were collected from Google Places.", payload={"query": query})

    return {
        "query": query,
        "total_collected": len(leads),
        "leads": leads,
    }


tool_definition = {
    "name": "collect_google_places_leads",
    "description": (
        "Collect business leads from Google Places based on a search query, "
        "returning phone numbers, websites, addresses, ratings, and review snippets. "
        "Automatically paginates until the requested number of leads is gathered."
    ),
    "parameters": {
        "query": {
            "type": "string",
            "description": "Search term, e.g., 'coffee shop' or 'electrician'."
        },
        "location": {
            "type": "string",
            "description": "Latitude and longitude of the search center in 'lat,lng' format."
        },
        "radius": {
            "type": "integer",
            "description": "Search radius in meters (max 50000).",
            "default": 50000
        },
        "num_leads": {
            "type": "integer",
            "description": "Total number of leads to collect (may paginate multiple times).",
            "default": 50
        }
    },
    "run": collect_google_places_leads,
} 
