import json
import math
from collections import defaultdict
from shapely.geometry import LineString, Point

with open("data/cache/osm_metro.json") as f:
    data = json.load(f)

nodes = {el["id"]: el for el in data["elements"] if el["type"] == "node"}
ways = [el for el in data["elements"] if el["type"] == "way"]

# Find station nodes
station_nodes = []
for n in nodes.values():
    tags = n.get("tags", {})
    if tags.get("railway") == "station" or tags.get("station") == "subway":
        station_nodes.append(n)

print(f"Total station nodes: {len(station_nodes)}")

# Let's inspect the target 7 underground stations and the 1 at-grade station
target_stations = [
    "Cubbon Park",
    "Vidhana Soudha",
    "Sir M. Visveshwaraya Station, Central College",
    "Nadaprabhu Kempegowda Station, Majestic",
    "Krantivira Sangolli Rayanna Railway Station",
    "Chickpete",
    "Krishna Rajendra Market",
]

# Build ways
way_dict = {}
for w in ways:
    tags = w.get("tags", {})
    railway = tags.get("railway", "")
    service = tags.get("service")
    usage = tags.get("usage")
    if service in ("yard", "siding", "crossover", "spur") or usage in ("yard", "siding", "depot"):
        continue
    if railway not in ("subway", "light_rail", "construction", "proposed"):
        continue
    pts = [nodes[nid] for nid in w["nodes"] if nid in nodes]
    if len(pts) >= 2:
        line = LineString([(p["lon"], p["lat"]) for p in pts])
        tunnel = tags.get("tunnel")
        bridge = tags.get("bridge")
        layer_str = tags.get("layer")
        try:
            layer = int(layer_str) if layer_str is not None else 0
        except ValueError:
            layer = 0
        name = tags.get("name", "")
        desig = tags.get("designation", "")
        way_dict[w["id"]] = {
            "way": w,
            "line": line,
            "tags": tags,
            "pure_mode": "underground" if (tunnel == "yes" or layer < 0) else ("elevated" if (bridge in ("yes", "viaduct") or layer > 0) else "at_grade"),
            "name": name,
            "desig": desig
        }

print(f"Loaded {len(way_dict)} track ways.")

# Check all operational stations in web/data/metro_stations.json
with open("web/data/metro_stations.json") as f:
    stations = json.load(f)

print(f"\nTotal stations in web/data/metro_stations.json: {len(stations)}")
op_stations = [s for s in stations if not s.get("is_construction")]
print(f"Operational stations: {len(op_stations)}")

# Count modes of operational stations
modes_count = defaultdict(int)
for s in op_stations:
    modes_count[s.get("mode")] += 1
print(f"Operational station modes: {dict(modes_count)}")

# Check each operational station distance to nearest way and the mode of that nearest way
print("\n--- AUDIT OF OPERATIONAL STATIONS VS NEAREST TRACK WAYS ---")
for s in op_stations:
    pt = Point(s["lon"], s["lat"])
    # Find nearest way
    min_dist_m = 999999.0
    nearest_way = None
    for wid, wdata in way_dict.items():
        # distance in degrees roughly converted to meters
        d_deg = pt.distance(wdata["line"])
        d_m = d_deg * 111000.0
        if d_m < min_dist_m:
            min_dist_m = d_m
            nearest_way = wdata
    
    stn_mode = s.get("mode")
    w_mode = nearest_way["pure_mode"]
    w_name = nearest_way["name"]
    wid = nearest_way["way"]["id"]
    
    # Check if target station or at_grade station
    is_target_ug = any(t.lower() in s["name"].lower() for t in ["Cubbon", "Vidhana", "Visvesvaraya", "Visveshwaraya", "Majestic", "Sangolli", "Chickpete", "Krishna Rajendra"])
    is_at_grade = (stn_mode == "at_grade") or ("grade" in s.get("mode", ""))
    
    if is_target_ug or is_at_grade or stn_mode != w_mode:
        print(f"Station: {s['name']:<42} | Stn Mode: {stn_mode:<11} | Nearest Way {wid} ({min_dist_m:.1f}m away): pure_mode={w_mode:<11} (name='{w_name}')")

