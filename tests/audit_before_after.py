import json
import math
from collections import defaultdict
from shapely.geometry import LineString

with open("data/cache/osm_metro.json") as f:
    data = json.load(f)

nodes = {el["id"]: el for el in data["elements"] if el["type"] == "node"}
ways = [el for el in data["elements"] if el["type"] == "way"]
rels = [el for el in data["elements"] if el["type"] == "relation"]

way_rels = defaultdict(list)
for r in rels:
    r_tags = r.get("tags", {})
    r_ref = r_tags.get("ref", "")
    r_name = r_tags.get("name", "")
    for m in r.get("members", []):
        if m["type"] == "way":
            way_rels[m["ref"]].append({"id": r["id"], "ref": r_ref, "name": r_name})

def get_way_line(wid, tags):
    for r in way_rels.get(wid, []):
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

def way_km(w):
    pts = [nodes[nid] for nid in w["nodes"] if nid in nodes]
    if len(pts) < 2:
        return 0.0
    km = 0.0
    for i in range(1, len(pts)):
        p1, p2 = pts[i-1], pts[i]
        dx = (p2["lon"] - p1["lon"]) * 111319.5 * math.cos(math.radians(12.9716))
        dy = (p2["lat"] - p1["lat"]) * 110574.0
        km += math.hypot(dx, dy) / 1000.0
    return km

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
    km = way_km(w)
    if km > 0:
        valid_ways.append((w, km))

# Pure tag mode (Before)
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

# New rule: Strict tags + Explicit sourced override list (NO "reach" rule)
UNDERGROUND_OVERRIDES = {
    508711042: "Purple Line UG1 Cubbon Park-Vidhana Soudha tunnel segment",
    607901267: "Purple Line UG1 Cubbon Park-Vidhana Soudha tunnel segment",
    142484399: "Green Line UG2 Sampige Road-Majestic tunnel segment",
    607901295: "Green Line UG2 Sampige Road-Majestic tunnel segment",
    1189861890: "Green Line UG2 Chickpete-KR Market tunnel segment",
}

def audited_mode(wid, tags):
    if wid in UNDERGROUND_OVERRIDES:
        return "underground"
    return pure_tag_mode(tags)

before_stats = defaultdict(lambda: defaultdict(lambda: {"count": 0, "km": 0.0}))
after_stats = defaultdict(lambda: defaultdict(lambda: {"count": 0, "km": 0.0}))

changed_ways = []

for w, km in valid_ways:
    wid = w["id"]
    tags = w.get("tags", {})
    line = get_way_line(wid, tags)
    m_before = pure_tag_mode(tags)
    m_after = audited_mode(wid, tags)

    before_stats[line][m_before]["count"] += 1
    before_stats[line][m_before]["km"] += km

    after_stats[line][m_after]["count"] += 1
    after_stats[line][m_after]["km"] += km

    if m_before != m_after:
        changed_ways.append({
            "wid": wid,
            "line": line,
            "km": km,
            "before": m_before,
            "after": m_after,
            "name": tags.get("name"),
            "designation": tags.get("designation"),
            "tags": tags,
            "reason": UNDERGROUND_OVERRIDES.get(wid, "N/A")
        })

print("=== BEFORE STATS (Pure OSM tags) ===")
for line in sorted(before_stats.keys()):
    print(f"Line {line}:")
    for m in ("underground", "elevated", "at_grade"):
        s = before_stats[line][m]
        print(f"  {m:<12}: {s['count']:>3} ways | {s['km']:>7.2f} track-km")

print("\n=== AFTER STATS (Pure OSM tags + Sourced Underground Overrides) ===")
for line in sorted(after_stats.keys()):
    print(f"Line {line}:")
    for m in ("underground", "elevated", "at_grade"):
        s = after_stats[line][m]
        print(f"  {m:<12}: {s['count']:>3} ways | {s['km']:>7.2f} track-km")

print("\n=== CHANGED WAYS AUDIT ===")
print(f"Total ways changed: {len(changed_ways)}")
for cw in changed_ways:
    print(f"\nWay ID: {cw['wid']} ({cw['line']})")
    print(f"  Length: {cw['km']:.3f} km ({cw['km']*1000:.1f} m)")
    print(f"  Mode Change: {cw['before']} -> {cw['after']}")
    print(f"  Name: {cw['name']!r}")
    print(f"  Designation: {cw['designation']!r}")
    print(f"  Reason: {cw['reason']}")
    print(f"  All OSM Tags: {cw['tags']}")

