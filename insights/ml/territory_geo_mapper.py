"""Map ERPNext Territory names to GeoJSON region codes."""

import frappe
from typing import Any, Dict, List, Optional, Tuple

# The world GeoJSON (`src2/assets/maps_json/world_map.json`) keys its features on
# full country NAMES, not ISO codes. Emitting "IND"/"NPL"/"USA" matched no feature,
# so every "mapped" territory silently failed to paint. Resolution now goes through
# ERPNext's own Country list, which agrees with 156 of the map's 178 features.
#
# Only the names where ERPNext and the GeoJSON genuinely disagree are listed. Each
# was checked against the feature set individually; a normalised auto-match was
# tried first and rejected after it collided "United States" with "United Kingdom".
COUNTRY_NAME_ALIASES = {
    "united states": "United States of America",
    "tanzania": "United Republic of Tanzania",
    "serbia": "Republic of Serbia",
    "bahamas": "The Bahamas",
    "guinea-bissau": "Guinea Bissau",
    "congo, the democratic republic of the": "Democratic Republic of the Congo",
}

# The world map's name for India, used when rolling states up to the country view.
INDIA_MAP_NAME = "India"

# Indian state name to GeoJSON feature name mapping
INDIA_STATE_MAP = {
    "andhra pradesh": "Andhra Pradesh", "arunachal pradesh": "Arunachal Pradesh",
    "assam": "Assam", "bihar": "Bihar", "chhattisgarh": "Chhattisgarh",
    "goa": "Goa", "gujarat": "Gujarat", "haryana": "Haryana",
    "himachal pradesh": "Himachal Pradesh", "jharkhand": "Jharkhand",
    "karnataka": "Karnataka", "kerala": "Kerala",
    "madhya pradesh": "Madhya Pradesh", "maharashtra": "Maharashtra",
    "manipur": "Manipur", "meghalaya": "Meghalaya", "mizoram": "Mizoram",
    "nagaland": "Nagaland", "odisha": "Odisha", "punjab": "Punjab",
    "rajasthan": "Rajasthan", "sikkim": "Sikkim", "tamil nadu": "Tamil Nadu",
    "telangana": "Telangana", "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh", "uttarakhand": "Uttarakhand",
    "west bengal": "West Bengal",
    # Values below are verified against `india.json` feature names. Four were
    # wrong and painted nothing: "NCT of Delhi", "Jammu & Kashmir", "Andaman &
    # Nicobar Island" and a combined Dadra/Daman entry. The geojson spells them
    # out and keeps Dadra and Daman as separate features.
    "delhi": "Delhi", "new delhi": "Delhi",
    "chandigarh": "Chandigarh", "puducherry": "Puducherry",
    "jammu and kashmir": "Jammu and Kashmir",
    "ladakh": "Ladakh", "lakshadweep": "Lakshadweep",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "andaman and nicobar islands": "Andaman and Nicobar Islands",
    "dadra and nagar haveli": "Dadra and Nagar Haveli",
    "daman and diu": "Daman and Diu",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli",
}


def get_custom_mapping() -> Dict[str, str]:
    """Load user-defined territory-to-code overrides from Insights Settings."""
    try:
        settings = frappe.get_single("Insights Settings")
    except Exception:
        return {}
    mapping = {}
    if hasattr(settings, "territory_geo_mapping") and settings.territory_geo_mapping:
        for row in settings.territory_geo_mapping:
            if row.territory_name and row.geo_code:
                mapping[row.territory_name.strip().lower()] = row.geo_code.strip()
    return mapping


def get_country_names() -> Dict[str, str]:
    """
    Lowercased ERPNext country name -> the name the world GeoJSON uses.

    ERPNext's Country doctype is the authoritative list, so this replaces the
    36-entry hardcoded dict that silently failed for anything outside it,
    including "United Arab Emirates" (it only keyed "uae") and "Vanuatu".
    """
    try:
        rows = frappe.get_all("Country", fields=["name"])
    except Exception:
        return {}
    out = {}
    for row in rows:
        key = (row.get("name") or "").strip().lower()
        if key:
            out[key] = COUNTRY_NAME_ALIASES.get(key, (row.get("name") or "").strip())
    return out


def map_territory_to_geo(
    territory_name: str,
    custom_mapping: Optional[Dict[str, str]] = None,
    country_names: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[str], str]:
    """
    Map one ERPNext territory name to a GeoJSON feature name.

    Returns:
        (feature_name, level) where level is 'country', 'state', or 'unmapped'.
        The value is a map feature NAME, not an ISO code; see COUNTRY_NAME_ALIASES.
    """
    if custom_mapping is None:
        custom_mapping = get_custom_mapping()
    if country_names is None:
        country_names = get_country_names()

    key = territory_name.strip().lower()
    if not key:
        return None, "unmapped"

    # Priority 1: custom overrides
    if key in custom_mapping:
        code = custom_mapping[key]
        level = "state" if code in INDIA_STATE_MAP.values() else "country"
        return code, level

    # Priority 2: India state match
    if key in INDIA_STATE_MAP:
        return INDIA_STATE_MAP[key], "state"

    # Priority 3: country match, against ERPNext's own country list
    if key in country_names:
        return country_names[key], "country"

    return None, "unmapped"


def get_territory_parents() -> Dict[str, Optional[str]]:
    """Territory name -> parent territory, for the whole tree in one query."""
    try:
        rows = frappe.get_all("Territory", fields=["name", "parent_territory"])
    except Exception:
        return {}
    return {row.get("name"): row.get("parent_territory") for row in rows}


def map_territories_bulk(
    data: List[Dict[str, Any]],
    territory_field: str = "territory",
    value_field: str = "value",
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Map a list of {territory, value} dicts to world and India geo data.

    A territory that does not resolve on its own name is resolved through its
    ERPNext parent chain, because territories are a tree and the leaves are
    usually cities: "Surat" is a child of "Gujarat", "Kurnool" of "Andhra
    Pradesh". Matching leaf names alone left 98 of 110 territories and 373 of 385
    customers off the map; walking the tree resolves all but the ones whose
    parentage is genuinely wrong or absent.

    Returns:
        {
            "world": [{"name": "India", "value": 100}, ...],
            "india": [{"name": "Maharashtra", "value": 50}, ...],
            "unmapped": [{"territory": "Custom Region", "value": 10}, ...]
        }
    """
    custom_mapping = get_custom_mapping()
    country_names = get_country_names()
    parents = get_territory_parents()
    world_data: Dict[str, float] = {}
    india_data: Dict[str, float] = {}
    unmapped: List[Dict[str, Any]] = []

    # Depth guard: a mis-parented tree can cycle, and Territory is user-editable.
    MAX_ANCESTOR_HOPS = 8

    for row in data:
        territory = row.get(territory_field, "")
        value = row.get(value_field, 0)
        if not isinstance(value, (int, float)):
            value = 0
        if not territory:
            continue

        geo_code, level = None, "unmapped"
        current, hops, seen = territory, 0, set()
        while current and hops <= MAX_ANCESTOR_HOPS and current not in seen:
            seen.add(current)
            geo_code, level = map_territory_to_geo(current, custom_mapping, country_names)
            if level != "unmapped":
                break
            current = parents.get(current)
            hops += 1

        if level == "country" and geo_code:
            world_data[geo_code] = world_data.get(geo_code, 0) + value
        elif level == "state" and geo_code:
            india_data[geo_code] = india_data.get(geo_code, 0) + value
            # A state also counts toward India on the world view.
            world_data[INDIA_MAP_NAME] = world_data.get(INDIA_MAP_NAME, 0) + value
        else:
            unmapped.append({"territory": territory, "value": value})

    return {
        "world": [{"name": k, "value": v} for k, v in world_data.items()],
        "india": [{"name": k, "value": v} for k, v in india_data.items()],
        "unmapped": unmapped,
    }
