"""
Multi-agent pipeline — a direct Python port of the client-side logic in
project.html (parseWhatsappSurplus / runMatchingAgent / runDispatchAgent),
so the frontend's regex + haversine reasoning is now backed by a real
server instead of being reimplemented twice.
"""
import re
import math
from typing import List, Dict, Optional

EXTRACTION_PATTERN = re.compile(
    r"(\d+)\s*(plates|servings|serves|kg|boxes|portions|meals|containers|packets|trays)\s*(?:of\s+)?(.*?)"
    r"(?=\s+(?:remaining|left|ready|from|extra|now|need|urgent|please)|\.|,|;|$)",
    re.IGNORECASE,
)


def parse_whatsapp_surplus(message: str, lat: Optional[float], lon: Optional[float],
                            spoil_override: Optional[float] = None) -> Dict:
    text_lower = message.lower()
    quantity = 30
    food_type = "Unspecified Food"

    match = EXTRACTION_PATTERN.search(text_lower)
    if match:
        quantity = int(match.group(1))
        raw_food = match.group(3).strip()
        if raw_food:
            food_type = raw_food.title()

    spoil_hours = spoil_override or 4
    if not spoil_override:
        if "urgent" in text_lower:
            spoil_hours = 2
        elif "now" in text_lower or "tonight" in text_lower:
            spoil_hours = 3

    return {
        "food_type": food_type,
        "quantity_servings": quantity,
        "time_to_spoil_hours": spoil_hours,
        "location_lat": lat if lat is not None else 28.7041,
        "location_lon": lon if lon is not None else 77.1025,
    }


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def run_matching_agent(surplus: Dict, ngos: List[Dict]) -> Dict:
    eligible = [n for n in ngos if n["accepts_cooked"] and n["capacity_servings"] >= surplus["quantity_servings"]]
    pool = eligible if eligible else ngos

    best, best_dist = None, math.inf
    for n in pool:
        d = haversine_km(surplus["location_lat"], surplus["location_lon"], n["lat"], n["lon"])
        if d < best_dist:
            best_dist, best = d, n

    match_found = len(eligible) > 0
    urgency = "High" if surplus["time_to_spoil_hours"] <= 2 else "Medium" if surplus["time_to_spoil_hours"] <= 4 else "Low"
    margin_ratio = min(1, (best["capacity_servings"] - surplus["quantity_servings"]) / best["capacity_servings"]) if match_found and best else 0
    proximity_bonus = max(0, (5 - best_dist)) * 0.02 if match_found else 0
    confidence = min(0.98, 0.6 + margin_ratio * 0.3 + proximity_bonus) if match_found else 0.15

    reasoning = (
        f"{best['name']} accepts cooked meals and holds {best['capacity_servings']} servings of free capacity "
        f"against this {surplus['quantity_servings']}-serving payload, {best_dist:.2f} km from pickup."
        if match_found else
        f"No NGO node currently has enough free capacity (need {surplus['quantity_servings']} servings)."
    )

    return {
        "match_found": match_found,
        "best_ngo_id": best["ngo_id"] if match_found and best else None,
        "best_ngo_name": best["name"] if match_found and best else None,
        "confidence_score": round(confidence, 2),
        "reasoning": reasoning,
        "dispatch_urgency": urgency,
        "distance_km": round(best_dist, 2) if best else None,
    }


def run_dispatch_agent(surplus: Dict, urgency: str, volunteers: List[Dict]) -> Dict:
    eligible = [v for v in volunteers if v["capacity"] >= surplus["quantity_servings"]]
    pool = eligible if eligible else volunteers

    best, best_dist = None, math.inf
    for v in pool:
        d = haversine_km(surplus["location_lat"], surplus["location_lon"], v["lat"], v["lon"])
        if d < best_dist:
            best_dist, best = d, v

    padding = {"High": 0, "Medium": 2, "Low": 4}.get(urgency, 2)
    eta_mins = max(4, round((best_dist / best["speed_kmph"]) * 60) + padding)

    reasoning = (
        f"{best['name']}'s {best['vehicle']} can carry {best['capacity']} servings and is {best_dist:.2f} km away."
        if eligible else
        f"No vehicle has full capacity; assigning {best['name']} ({best['vehicle']}) for a partial pickup."
    )

    return {
        "assigned_volunteer_id": best["vol_id"],
        "assigned_volunteer_name": best["name"],
        "vehicle_type": best["vehicle"],
        "estimated_pickup_mins": eta_mins,
        "reasoning": reasoning,
        "distance_km": round(best_dist, 2),
    }
