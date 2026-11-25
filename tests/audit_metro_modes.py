import json
import math
from collections import defaultdict
from shapely.geometry import LineString, Point

with open("data/cache/osm_metro.json") as f:
    data = json.load(f)

nodes = {el["id"]: el for el in data["elements"] if el["type"] == "node"}
ways = [el for el in data["elements"] if el["type"] == "way"]
rels = [el for el in data["elements"] if el["type"] == "relation"]

# Build way to relations mapping
way_rels = defaultdict(list)
for r in rels:
    r_tags = r.get("tags", {})
    r_ref = r_tags.get("ref", "")
    r_name = r_tags.get("name", "")
    for m in r.get("members", []):
        if m["type"] == "way":
            way_rels[m["ref"]].append({"id": r["id"], "ref": r_ref, "name": r_name})

def get_way_line(wid, tags):
    r_list = way_rels.get(wid, [])
    for r in r_list:
        ref = r["ref"]
        if ref in ("Purple", "Green", "Yellow", "Pink", "Blue", "Orange", "Red"):
            return ref
        for cand in ("Purple", "Green", "Yellow", "Pink", "Blue", "Orange", "Red"):
            if cand.lower() in r["name"].lower():
                return cand
    for cand in ("Purple", "Green", "Yellow", "Pink", "Blue", "Orange", "Red"):
        if cand.lower() in tags.get("name", "").lower():
            return cand
    return "Unknown"

# Calculate way length
def way_geom(w):
    pts = [nodes[nid] for nid in w["nodes"] if nid in nodes]
    if len(pts) < 2:
        return 0.0, None
    line = LineString([(p["lon"], p["lat"]) for p in pts])
    # approximate meters: lon * 111320 * cos(lat), lat * 110574
    km = 0.0
    for i in range(1, len(pts)):
        p1, p2 = pts[i-1], pts[i]
        dx = (p2["lon"] - p1["lon"]) * 111319.5 * math.cos(math.radians(12.9716))
        dy = (p2["lat"] - p1["lat"]) * 110574.0
        km += math.hypot(dx, dy) / 1000.0
    return km, line

print("=== AUDIT OF ALL METRO TRACK WAYS ===")
valid_ways = []
for w in ways:
    tags = w.get("tags", {})
    railway = tags.get("railway", "")
    service = tags.get("service")
    usage = tags.get("usage")
    if service in ("yard", "siding", "crossover", "spur") or usage in ("yard", "siding", "depot"):
        continue
    if railway not in ("subway", "light_rail", "construction", "proposed"):
        continue
    km, line = way_geom(w)
    if km > 0:
        valid_ways.append((w, km, line))

print(f"Total valid passenger track ways: {len(valid_ways)}")

# Pure tag-based mode
def pure_tag_mode(tags):
    tunnel = tags.get("tunnel")
    bridge = tags.get("bridge")
    layer_str = tags.get("layer")
    try:
        layer = int(layer_str) if layer_str is not None else 0
    except ValueError:
        layer = 0
    if tunnel == "yes" or layer < 0:
        return "underground"
    elif bridge in ("yes", "viaduct") or layer > 0:
        return "elevated"
    else:
        return "at_grade"

# Print modes under pure tags
before_stats = defaultdict(lambda: defaultdict(lambda: {"count": 0, "km": 0.0}))
for w, km, line in valid_ways:
    tags = w.get("tags", {})
    line_name = get_way_line(w["id"], tags)
    m = pure_tag_mode(tags)
    before_stats[line_name][m]["count"] += 1
    before_stats[line_name][m]["km"] += km

print("\n--- BEFORE (Pure OSM Tags Only: tunnel=yes/layer<0 or bridge=yes/viaduct/layer>0) ---")
for line in sorted(before_stats.keys()):
    print(f"Line {line}:")
    for m in ("underground", "elevated", "at_grade"):
        st = before_stats[line][m]
        print(f"  {m:<12}: {st['count']:>3} ways, {st['km']:>7.2f} track-km")

# Identify every way where pure tag mode is at_grade or changed
print("\n--- WAYS CLASSIFIED AS at_grade UNDER PURE TAGS ---")
at_grade_ways = []
for w, km, line in valid_ways:
    tags = w.get("tags", {})
    m = pure_tag_mode(tags)
    if m == "at_grade":
        line_name = get_way_line(w["id"], tags)
        at_grade_ways.append((w, km, line_name))
        print(f"Way ID {w['id']} ({line_name}): {km:.3f} km | name={tags.get('name')!r} | desig={tags.get('designation')!r} | railway={tags.get('railway')!r} | bridge={tags.get('bridge')!r} | tunnel={tags.get('tunnel')!r} | layer={tags.get('layer')!r}")

