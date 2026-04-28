"""Map ERPNext Territory names to GeoJSON region codes."""

import frappe
from typing import Dict, List, Optional, Tuple

# ISO 3166-1 alpha-3 country codes for common territories
COUNTRY_CODE_MAP = {
    "india": "IND", "kenya": "KEN", "united states": "USA",
    "united kingdom": "GBR", "china": "CHN", "japan": "JPN",
    "germany": "DEU", "france": "FRA", "canada": "CAN",
    "australia": "AUS", "brazil": "BRA", "south africa": "ZAF",
    "nigeria": "NGA", "tanzania": "TZA", "uganda": "UGA",
    "ethiopia": "ETH", "ghana": "GHA", "egypt": "EGY",
    "uae": "ARE", "saudi arabia": "SAU", "singapore": "SGP",
    "malaysia": "MYS", "indonesia": "IDN", "thailand": "THA",
    "vietnam": "VNM", "pakistan": "PAK", "bangladesh": "BGD",
    "sri lanka": "LKA", "nepal": "NPL", "italy": "ITA",
    "spain": "ESP", "netherlands": "NLD", "russia": "RUS",
    "mexico": "MEX", "argentina": "ARG", "colombia": "COL",
}

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
    "delhi": "NCT of Delhi", "new delhi": "NCT of Delhi",
    "chandigarh": "Chandigarh", "puducherry": "Puducherry",
    "jammu and kashmir": "Jammu & Kashmir",
    "ladakh": "Ladakh", "lakshadweep": "Lakshadweep",
    "andaman and nicobar": "Andaman & Nicobar Island",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
}


def get_custom_mapping() -> Dict[str, str]:
    """Load user-defined territory-to-code overrides from Insights Settings."""
    settings = frappe.get_single("Insights Settings")
    mapping = {}
    if hasattr(settings, "territory_geo_mapping") and settings.territory_geo_mapping:
        for row in settings.territory_geo_mapping:
            if row.territory_name and row.geo_code:
                mapping[row.territory_name.strip().lower()] = row.geo_code.strip()
    return mapping


def map_territory_to_geo(
    territory_name: str,
    custom_mapping: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[str], str]:
    """
    Map an ERPNext territory name to a GeoJSON code.

    Returns:
        (geo_code, level) where level is 'country', 'state', or 'unmapped'
    """
    if custom_mapping is None:
        custom_mapping = get_custom_mapping()

    key = territory_name.strip().lower()

    # Priority 1: custom overrides
    if key in custom_mapping:
        code = custom_mapping[key]
        level = "state" if code in INDIA_STATE_MAP.values() else "country"
        return code, level

    # Priority 2: India state match
    if key in INDIA_STATE_MAP:
        return INDIA_STATE_MAP[key], "state"

    # Priority 3: country match
    if key in COUNTRY_CODE_MAP:
        return COUNTRY_CODE_MAP[key], "country"

    return None, "unmapped"


def map_territories_bulk(
    data: List[Dict],
    territory_field: str = "territory",
    value_field: str = "value",
) -> Dict:
    """
    Map a list of {territory, value} dicts to world and India geo data.

    Returns:
        {
            "world": [{"name": "IND", "value": 100}, ...],
            "india": [{"name": "Maharashtra", "value": 50}, ...],
            "unmapped": [{"territory": "Custom Region", "value": 10}, ...]
        }
    """
    custom_mapping = get_custom_mapping()
    world_data = {}
    india_data = {}
    unmapped = []

    for row in data:
        territory = row.get(territory_field, "")
        value = row.get(value_field, 0)
        if not territory:
            continue

        geo_code, level = map_territory_to_geo(territory, custom_mapping)

        if level == "country":
            world_data[geo_code] = world_data.get(geo_code, 0) + value
        elif level == "state":
            india_data[geo_code] = india_data.get(geo_code, 0) + value
            # Also aggregate India total for world map
            world_data["IND"] = world_data.get("IND", 0) + value
        else:
            unmapped.append({"territory": territory, "value": value})

    return {
        "world": [{"name": k, "value": v} for k, v in world_data.items()],
        "india": [{"name": k, "value": v} for k, v in india_data.items()],
        "unmapped": unmapped,
    }
