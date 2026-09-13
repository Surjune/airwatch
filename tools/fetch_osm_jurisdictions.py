"""Build the authority registry from OpenStreetMap administrative boundaries.

Replaces hand-drawn bounding boxes with real district and state outlines, fetched
from the Overpass API and written to ``infra/seed/authorities.json``. Re-run it to
refresh the boundaries; the output is committed so seeding needs no network.

Which body answers a pollution complaint is a policy question OpenStreetMap
cannot answer. This script takes the boundary from OSM and the responsibility
from a short, explicit table below: the district administration first (tier 1),
then the state pollution control board or committee (tier 2). Contact addresses
stay on the reserved ``.invalid`` domain -- a seeded deployment contacts no one.

Boundary data (c) OpenStreetMap contributors, available under the Open Database
Licence (ODbL).

Run with: node scripts/py.mjs ../tools/fetch_osm_jurisdictions.py
"""

# This tool reports progress to a terminal for the person running it.
# ruff: noqa: T201

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import linemerge, polygonize, unary_union

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "infra" / "seed" / "authorities.json"

#: Public Overpass instances, tried in order. The main one times out under load.
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

#: Attempts per instance, and the wait between them, before moving on.
ATTEMPTS = 3
RETRY_WAIT_SECONDS = 20.0
USER_AGENT = "AirWatch/0.1 (+https://github.com/Surjune/airwatch)"
TIMEOUT_SECONDS = 180.0

#: Seconds between Overpass queries. The public instance asks callers to pace
#: themselves; this is a one-off tool, so waiting costs nothing.
PAUSE_SECONDS = 5.0

#: Simplification tolerance in degrees. A district outline at ~50 m keeps every
#: street-scale boundary a hotspot could fall on either side of; a state at
#: ~1 km is plenty for a tier-2 fallback and keeps the seed file small.
DISTRICT_TOLERANCE_DEG = 0.0005
STATE_TOLERANCE_DEG = 0.01

#: (display name, ISO 3166-2 state code, OSM district name, contact slug).
DISTRICTS: tuple[tuple[str, str, str, str], ...] = (
    *(
        (f"{name} district administration, Delhi", "IN-DL", name, name.lower().replace(" ", "-"))
        for name in (
            "Central Delhi",
            "Central North Delhi",
            "East Delhi",
            "New Delhi",
            "North Delhi",
            "North East Delhi",
            "North West Delhi",
            "Old Delhi",
            "Outer North Delhi",
            "South Delhi",
            "South East Delhi",
            "South West Delhi",
            "West Delhi",
        )
    ),
    (
        "Gautam Buddha Nagar district administration (Noida)",
        "IN-UP",
        "Gautam Buddha Nagar",
        "gautam-buddha-nagar",
    ),
    ("Ghaziabad district administration", "IN-UP", "Ghaziabad", "ghaziabad"),
    ("Gurugram district administration", "IN-HR", "Gurugram", "gurugram"),
    ("Faridabad district administration", "IN-HR", "Faridabad", "faridabad"),
    ("Kanpur Nagar district administration", "IN-UP", "Kanpur Nagar", "kanpur-nagar"),
    ("Coimbatore district administration", "IN-TN", "Coimbatore", "coimbatore"),
)

#: (display name, ISO 3166-2 code, contact slug) for the tier-2 regulators.
STATES: tuple[tuple[str, str, str], ...] = (
    ("Delhi Pollution Control Committee", "IN-DL", "dpcc"),
    ("Uttar Pradesh Pollution Control Board", "IN-UP", "uppcb"),
    ("Haryana State Environment Protection Council", "IN-HR", "haryana-epc"),
    ("Tamil Nadu Pollution Control Board", "IN-TN", "tnpcb"),
)


def overpass(query: str) -> list[dict[str, Any]]:
    """Run an Overpass query, retrying and falling back across instances."""
    last_error: Exception | None = None
    for url in OVERPASS_URLS:
        for attempt in range(1, ATTEMPTS + 1):
            try:
                response = httpx.post(
                    url,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT},
                    timeout=TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                elements = response.json().get("elements", [])
                time.sleep(PAUSE_SECONDS)
                return list(elements)
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                print(f"    {url} attempt {attempt} failed: {error}")
                time.sleep(RETRY_WAIT_SECONDS)
    raise RuntimeError(f"Every Overpass instance failed: {last_error}")


def relation_polygon(relation: dict[str, Any]) -> Polygon:
    """Stitch a boundary relation's outer ways into its largest polygon.

    Boundary relations are split into many ways; ``polygonize`` joins them into
    closed rings. A district can include small detached pieces, and the
    jurisdiction column holds one polygon, so the largest is kept.
    """
    lines = [
        LineString([(point["lon"], point["lat"]) for point in member["geometry"]])
        for member in relation.get("members", [])
        if member.get("type") == "way"
        and member.get("role") in {"outer", ""}
        and member.get("geometry")
    ]
    polygons = list(polygonize(linemerge(unary_union(lines))))
    if not polygons:
        raise ValueError(f"Relation {relation.get('id')} did not close into a polygon.")
    merged = unary_union(polygons)
    if isinstance(merged, MultiPolygon):
        return max(merged.geoms, key=lambda part: part.area)
    if isinstance(merged, Polygon):
        return merged
    raise ValueError(f"Relation {relation.get('id')} produced {merged.geom_type}.")


def ring(polygon: Polygon, tolerance: float) -> list[list[float]]:
    """Simplified exterior ring as ``[lon, lat]`` pairs, rounded to ~1 m."""
    simplified = polygon.simplify(tolerance, preserve_topology=True)
    assert isinstance(simplified, Polygon)
    return [[round(lon, 5), round(lat, 5)] for lon, lat in simplified.exterior.coords[:-1]]


def fetch_districts(state_code: str, names: list[str]) -> dict[str, dict[str, Any]]:
    """Every named district in one state, in a single query."""
    pattern = "|".join(names)
    elements = overpass(
        f'[out:json][timeout:170];area["ISO3166-2"="{state_code}"]->.s;'
        f'relation(area.s)["boundary"="administrative"]["admin_level"="5"]["name"~"^({pattern})$"];'
        "out geom;"
    )
    found = {element["tags"]["name"]: element for element in elements}
    missing = set(names) - set(found)
    if missing:
        raise LookupError(f"No district named {sorted(missing)} in {state_code}.")
    return found


def fetch_state(state_code: str) -> dict[str, Any]:
    elements = overpass(
        f'[out:json][timeout:170];relation["boundary"="administrative"]["ISO3166-2"="{state_code}"];'
        "out geom;"
    )
    if not elements:
        raise LookupError(f"No state boundary for {state_code}.")
    return elements[0]


def main() -> int:
    authorities: list[dict[str, Any]] = []

    relations: dict[tuple[str, str], dict[str, Any]] = {}
    for state_code in sorted({code for _, code, _, _ in DISTRICTS}):
        names = [name for _, code, name, _ in DISTRICTS if code == state_code]
        for name, relation in fetch_districts(state_code, names).items():
            relations[(state_code, name)] = relation

    for display, state_code, osm_name, slug in DISTRICTS:
        relation = relations[(state_code, osm_name)]
        vertices = ring(relation_polygon(relation), DISTRICT_TOLERANCE_DEG)
        authorities.append(
            {
                "name": display,
                "escalation_tier": 1,
                "contact_email": f"{slug}@authority.invalid",
                "osm_relation_id": relation["id"],
                "jurisdiction": vertices,
            }
        )
        print(f"  tier 1  {display:<56} relation {relation['id']:>8}  {len(vertices):>4} vertices")

    for display, state_code, slug in STATES:
        relation = fetch_state(state_code)
        vertices = ring(relation_polygon(relation), STATE_TOLERANCE_DEG)
        authorities.append(
            {
                "name": display,
                "escalation_tier": 2,
                "contact_email": f"{slug}@authority.invalid",
                "osm_relation_id": relation["id"],
                "jurisdiction": vertices,
            }
        )
        print(f"  tier 2  {display:<56} relation {relation['id']:>8}  {len(vertices):>4} vertices")

    document = {
        "_about": (
            "Jurisdictions built from OpenStreetMap administrative boundaries by "
            "tools/fetch_osm_jurisdictions.py. The boundaries are real; which body answers a "
            "pollution alert inside each is an explicit policy table in that script, and a "
            "deployment must confirm it with the bodies named before sending real alerts."
        ),
        "_licence": "Boundary data (c) OpenStreetMap contributors, ODbL 1.0. https://www.openstreetmap.org/copyright",
        "_coordinate_order": "[longitude, latitude], WGS84, matching GeoJSON and PostGIS",
        "_escalation_tier": (
            "The district administration (tier 1) is notified before the state pollution "
            "control body (tier 2), so both are not alerted for one event, each assuming the "
            "other is handling it."
        ),
        "_contact": (
            "Addresses are on the reserved .invalid domain. No real inbox is contacted by a "
            "seeded deployment."
        ),
        "authorities": authorities,
    }
    OUTPUT.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {len(authorities)} authorities to {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
