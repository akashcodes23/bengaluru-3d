#!/usr/bin/env python3
"""Build Namma Metro lines and stations from OpenStreetMap Overpass cache."""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA_DIR = ROOT / "web" / "data"
CACHE_DIR = ROOT / "data" / "cache"
CONFIG_PATH = ROOT / "data" / "config.json"


def _load_config_bbox() -> Tuple[float, float, float, float]:
    if CONFIG_PATH.is_file():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        b = cfg["bbox"]
        return (float(b["west"]), float(b["south"]), float(b["east"]), float(b["north"]))
    return (77.40, 12.76, 77.82, 13.28)


CONFIG_BBOX = _load_config_bbox()

ORIGIN_LON = 77.5946
ORIGIN_LAT = 12.9716
METERS_PER_DEGREE_LON = 111_319.49079327358 * math.cos(math.radians(ORIGIN_LAT))
METERS_PER_DEGREE_LAT = 110_574.0
METRO_VIADUCT_M = 8.0  # Assumed clearance above DEM terrain for elevated viaduct
METRO_TUNNEL_DEPTH_M = -12.0  # Subsurface depth for underground sections
METRO_GRADE_OFFSET_M = 0.3  # Offset above DEM for at-grade track ribbon
DEFAULT_ACCENT_COLOR = "#00e5ff"


def lonlat_to_local(lon: float, lat: float) -> Tuple[float, float]:
    return (
        (lon - ORIGIN_LON) * METERS_PER_DEGREE_LON,
        (lat - ORIGIN_LAT) * METERS_PER_DEGREE_LAT,
    )


def local_to_lonlat(x: float, y: float) -> Tuple[float, float]:
    return (
        x / METERS_PER_DEGREE_LON + ORIGIN_LON,
        y / METERS_PER_DEGREE_LAT + ORIGIN_LAT,
    )


def densify_and_smooth(
    pts_local: List[Tuple[float, float]],
    max_seg: float = 12.0,
    iterations: int = 2,
    max_dev: float = 3.0,
) -> List[Tuple[float, float]]:
    """Smooth track centreline using Chaikin algorithm, strictly bounded to max_dev <= 3.0m of OSM track."""
    if len(pts_local) < 3:
        return pts_local
    dense = [pts_local[0]]
    for i in range(len(pts_local) - 1):
        p0 = pts_local[i]
        p1 = pts_local[i + 1]
        dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if dist > max_seg:
            steps = int(math.ceil(dist / max_seg))
            for s in range(1, steps):
                t = s / steps
                dense.append(
                    (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
                )
        dense.append(p1)

    current = dense
    for _ in range(iterations):
        smoothed = [current[0]]
        for i in range(len(current) - 1):
            p0, p1 = current[i], current[i + 1]
            q = (0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1])
            r = (0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1])
            smoothed.extend([q, r])
        smoothed.append(current[-1])
        current = smoothed

    # Pure Python projection clamping to max_dev <= 3.0m
    result = []
    for px, py in current:
        min_d_sq = float("inf")
        best_nx, best_ny = px, py
        for i in range(len(pts_local) - 1):
            ax, ay = pts_local[i]
            bx, by = pts_local[i + 1]
            dx, dy = bx - ax, by - ay
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq < 1e-6:
                t = 0.0
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
            nx = ax + t * dx
            ny = ay + t * dy
            d_sq = (px - nx) ** 2 + (py - ny) ** 2
            if d_sq < min_d_sq:
                min_d_sq = d_sq
                best_nx, best_ny = nx, ny
        d = math.sqrt(min_d_sq)
        if d > max_dev and d > 1e-6:
            ratio = max_dev / d
            clamped_x = best_nx + (px - best_nx) * ratio
            clamped_y = best_ny + (py - best_ny) * ratio
            result.append((clamped_x, clamped_y))
        else:
            result.append((px, py))
    return result


def load_terrain_interpolator():
    """Build a fast terrain lookup function using the manifest and t_*.json chunks."""
    manifest_path = WEB_DATA_DIR / "manifest.json"
    if not manifest_path.is_file():
        return lambda x, y: 900.0

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunk_size = manifest["chunkSize"]

    terrain_cache = {}
    for chunk in manifest["chunks"]:
        tfile = chunk.get("terrainFile")
        if tfile:
            terrain_cache[(chunk["ix"], chunk["iy"])] = tfile

    loaded_chunks = {}

    def get_elevation(x: float, north: float) -> float:
        ix = math.floor(x / chunk_size)
        iy = math.floor(north / chunk_size)
        key = (ix, iy)
        if key not in loaded_chunks:
            tfile = terrain_cache.get(key)
            if not tfile:
                return 900.0
            tpath = WEB_DATA_DIR / tfile
            if not tpath.is_file():
                return 900.0
            data = json.loads(tpath.read_text(encoding="utf-8"))
            loaded_chunks[key] = (
                data["width"],
                np.array(data["heights"], dtype=np.float32).reshape(
                    data["height"], data["width"]
                ),
            )

        w, grid = loaded_chunks[key]
        u = (x - ix * chunk_size) / chunk_size * (w - 1)
        v = (north - iy * chunk_size) / chunk_size * (w - 1)
        u = max(0.0, min(float(w - 1), u))
        v = max(0.0, min(float(w - 1), v))
        c0 = int(math.floor(u))
        r0 = int(math.floor(v))
        c1 = min(w - 1, c0 + 1)
        r1 = min(w - 1, r0 + 1)
        du = u - c0
        dv = v - r0

        elev = (
            grid[r0, c0] * (1 - du) * (1 - dv)
            + grid[r0, c1] * du * (1 - dv)
            + grid[r1, c0] * (1 - du) * dv
            + grid[r1, c1] * du * dv
        )
        return float(elev)

    return get_elevation


# Explicit, sourced mode overrides for OSM ways missing tunnel/bridge/level tags in raw OSM:
# - Ways 508711042 & 607901267 (Purple Line UG1) are portal ramps connecting the elevated
#   viaduct (Reach 1, layer 2) to the underground tunnel (UG1, layer -2). They are classified
#   under the "portal" mode derived from topological connectivity.
# Note: Way 1189861890 is covered by the tag rule (level=-2 < 0).
# Green Line ways 142484399 & 607901295 have embankment=yes in OSM representing the surface
# portal approach ramp at Swastik/Sampige Road, so they are retained as at_grade.
PORTAL_WAY_OVERRIDES = {
    508711042: "Purple Line UG1 portal ramp transitioning from elevated viaduct Reach 1 at node 428843502 down to underground tunnel UG1 at node 4979669544",
    607901267: "Purple Line UG1 portal ramp transitioning from elevated viaduct Reach 1 at node 5760197796 down to underground tunnel UG1 at node 5760197797",
}
UNDERGROUND_WAY_OVERRIDES = {}


def build_osm_metro():
    print("=== Processing OSM Namma Metro Data ===")
    cache_file = CACHE_DIR / "osm_metro.json"
    if not cache_file.is_file():
        raise FileNotFoundError(f"OSM metro cache not found at {cache_file}")

    data = json.loads(cache_file.read_text(encoding="utf-8"))
    elements = data.get("elements", [])
    print(f"Loaded {len(elements)} elements from {cache_file}.")

    nodes = {e["id"]: e for e in elements if e.get("type") == "node"}
    ways = {e["id"]: e for e in elements if e.get("type") == "way"}
    relations = [e for e in elements if e.get("type") == "relation"]

    elev_func = load_terrain_interpolator()

    # 1. Map relations and colors
    # Standardize relation colors and metadata
    rel_info = {}
    for r in relations:
        rid = r["id"]
        tags = r.get("tags", {})
        ref = tags.get("ref", "Metro")
        name = tags.get("name", f"Line {ref}")
        colour = tags.get("colour")
        # Color resolution
        color_val = colour if colour else DEFAULT_ACCENT_COLOR
        # Normalize simple color words to hex if desired, or keep as valid CSS color
        if color_val == "yellow":
            color_val = "#eab308"  # vibrant metro yellow
        elif color_val == "pink":
            color_val = "#ec4899"  # vibrant metro pink
        elif color_val == "blue":
            color_val = "#3b82f6"  # vibrant metro blue

        rel_info[rid] = {
            "id": rid,
            "ref": ref,
            "name": name,
            "color": color_val,
            "raw_colour": colour,
            "tags": tags,
        }

    # Map ways to relations
    way_rels = defaultdict(list)
    for r in relations:
        rid = r["id"]
        for m in r.get("members", []):
            if m.get("type") == "way":
                way_rels[m["ref"]].append(rel_info[rid])

    # 2. Process ways
    tracks = []
    operational_km_by_line = defaultdict(float)
    operational_km_by_mode = defaultdict(float)
    construction_km_by_line = defaultdict(float)
    construction_km_by_mode = defaultdict(float)

    for wid, way in ways.items():
        tags = way.get("tags", {})
        node_ids = way.get("nodes", [])
        pts = [nodes[nid] for nid in node_ids if nid in nodes]
        if len(pts) < 2:
            continue

        # Status
        railway = tags.get("railway", "")
        service = tags.get("service", "")
        # Exclude abandoned and yards/sidings completely from network
        if railway in ("abandoned", "razed", "disused") or service in (
            "yard",
            "siding",
            "depot",
        ):
            continue
        # Only process actual railway tracks (exclude building polygons, platforms, footways)
        if railway not in ("subway", "light_rail", "construction", "proposed"):
            continue

        # Mode: strictly tag-based (bridge/viaduct/layer>0 -> elevated, tunnel/layer<0/level<0 -> underground)
        # plus explicit sourced override list for known underground tunnel segments missing tunnel=yes in OSM.
        tunnel = tags.get("tunnel")
        bridge = tags.get("bridge")
        layer_str = tags.get("layer")
        level_str = tags.get("level")
        try:
            layer = int(layer_str) if layer_str is not None else 0
        except ValueError:
            layer = 0
        try:
            level = int(level_str) if level_str is not None else 0
        except ValueError:
            level = 0

        if wid in PORTAL_WAY_OVERRIDES:
            mode = "portal"
        elif wid in UNDERGROUND_WAY_OVERRIDES or tunnel == "yes" or layer < 0 or level < 0:
            mode = "underground"
        elif bridge in ("yes", "viaduct") or layer > 0:
            mode = "elevated"
        else:
            mode = "at_grade"

        # Line & Color from relation
        rels = way_rels.get(wid, [])
        line_ref = None
        for r in rels:
            ref = r["ref"]
            if ref in ("Purple", "Green", "Yellow", "Pink", "Blue", "Orange", "Red"):
                line_ref = ref
                break
            r_name = r["name"]
            for cand in ("Purple", "Green", "Yellow", "Pink", "Blue", "Orange", "Red"):
                if cand.lower() in r_name.lower():
                    line_ref = cand
                    break
            if line_ref:
                break
        if not line_ref:
            for cand in ("Purple", "Green", "Yellow", "Pink", "Blue", "Orange", "Red"):
                if cand.lower() in tags.get("name", "").lower():
                    line_ref = cand
                    break
            if not line_ref:
                line_ref = "Metro"

        if line_ref == "Purple":
            line_color = "#e542de"
            line_name = "Purple Line"
        elif line_ref == "Green":
            line_color = "#009933"
            line_name = "Green Line"
        elif line_ref == "Yellow":
            line_color = "#eab308"
            line_name = "Yellow Line"
        elif line_ref == "Pink":
            line_color = "#ec4899"
            line_name = "Pink Line"
        elif line_ref == "Blue":
            line_color = "#3b82f6"
            line_name = "Blue Line (Airport)"
        elif line_ref == "Orange":
            line_color = "#f97316"
            line_name = "Orange Line"
        elif line_ref == "Red":
            line_color = "#ef4444"
            line_name = "Red Line"
        else:
            line_color = DEFAULT_ACCENT_COLOR
            line_name = "Namma Metro"

        is_construction = (
            railway in ("construction", "proposed")
            or "construction" in tags
            or tags.get("proposed") is not None
            or any(
                r["tags"].get("railway") in ("construction", "proposed")
                or any("construction" in k for k in r["tags"].keys())
                or r["tags"].get("proposed") is not None
                or r["tags"].get("state") == "proposed"
                for r in rels
            )
            or line_ref in ("Blue", "Orange", "Red")
        )

        is_proposed = (
            railway == "proposed"
            or tags.get("proposed") is not None
            or any(
                r["tags"].get("railway") == "proposed"
                or r["tags"].get("proposed") is not None
                or r["tags"].get("state") == "proposed"
                for r in rels
            )
        )

        # Pink Line Phase 2 southern elevated section (Kalena Agrahara to Tavarekere)
        # opened on 13 Nov 2026. Keep elevated ways in the southern corridor operational.
        if line_ref == "Pink":
            mean_lat = sum(pt["lat"] for pt in pts) / len(pts)
            if mode == "elevated" and (tags.get("start_date") or mean_lat < 12.933):
                is_construction = False
                is_proposed = False
            else:
                is_construction = True
                is_proposed = False

        # Local coordinates and Chaikin curve smoothing (bounded to <= 3m deviation)
        raw_local = [lonlat_to_local(pt["lon"], pt["lat"]) for pt in pts]
        smoothed_local = densify_and_smooth(raw_local, max_seg=10.0, iterations=2, max_dev=3.0)

        pts_3d = []
        way_len_m = 0.0
        for i, (x, y) in enumerate(smoothed_local):
            ground_z = elev_func(x, y)
            if mode == "elevated":
                track_z = ground_z + METRO_VIADUCT_M
            elif mode == "at_grade":
                track_z = ground_z + METRO_GRADE_OFFSET_M
            elif mode == "portal":
                # Portal ramp interpolating from viaduct deck height at viaduct end down to tunnel depth at tunnel end
                t = i / max(1, len(smoothed_local) - 1)
                offset = (1.0 - t) * METRO_VIADUCT_M + t * METRO_TUNNEL_DEPTH_M
                track_z = ground_z + offset
            else:  # underground
                track_z = ground_z + METRO_TUNNEL_DEPTH_M

            pts_3d.append(
                [round(x, 2), round(y, 2), round(track_z, 2), round(ground_z, 2)]
            )
            if i > 0:
                prev_x, prev_y = smoothed_local[i - 1]
                way_len_m += math.hypot(x - prev_x, y - prev_y)

        way_km = way_len_m / 1000.0
        if is_construction:
            construction_km_by_line[line_ref] += way_km
            construction_km_by_mode[mode] += way_km
        else:
            operational_km_by_line[line_ref] += way_km
            operational_km_by_mode[mode] += way_km

        tracks.append(
            {
                "id": f"osm_way_{wid}",
                "way_id": wid,
                "line": line_ref,
                "line_name": line_name,
                "color": line_color,
                "mode": mode,
                "is_construction": is_construction,
                "is_proposed": is_proposed and is_construction,
                "length_m": round(way_len_m, 1),
                "points": pts_3d,
            }
        )

    # 3. Process Stations
    station_nodes_raw = {}
    for nid, node in nodes.items():
        ntags = node.get("tags", {})
        nm = ntags.get("name", "")
        # Exclude parking lots and station entrances / elevators
        if ntags.get("amenity") == "motorcycle_parking" or "parking" in nm.lower():
            continue
        if ntags.get("railway") == "subway_entrance" or ntags.get("highway") == "elevator":
            continue
        if (
            ntags.get("railway") in ("station", "stop")
            or ntags.get("station") == "subway"
            or ntags.get("construction") == "station"
            or ntags.get("proposed") == "station"
            or ntags.get("railway") in ("construction", "proposed")
            or (
                ntags.get("public_transport") in ("station", "stop_position")
                and ntags.get("subway") == "yes"
            )
        ):
            station_nodes_raw[nid] = node

    # Deduplicate stations by name and proximity
    stations_by_name = defaultdict(list)
    for nid, node in station_nodes_raw.items():
        name = node.get("tags", {}).get("name")
        if not name:
            continue
        # Clean name
        clean_name = name.replace(" (u/c)", "").replace(" (Proposed)", "").strip()
        for s in (
            " (Green Line)",
            " (Purple Line)",
            " (Pink Line)",
            " (Yellow Line)",
        ):
            clean_name = clean_name.replace(s, "")
        if "Hosahalli" in clean_name and "Swamiji" in clean_name:
            clean_name = "Sri Balagangadharanatha Swamiji Station, Hosahalli"
        if clean_name in ("Vijayanagara", "Vijayanagar"):
            clean_name = "Vijayanagar"
        if "Kempegowda" in clean_name and "Majestic" in clean_name:
            clean_name = "Nadaprabhu Kempegowda Station, Majestic"
        if clean_name in ("Krishnarajapura", "Krishnarajapuram"):
            clean_name = "Krishnarajapura"
        stations_by_name[clean_name].append(node)

    stations = []
    station_modes = defaultdict(int)
    for clean_name, node_group in stations_by_name.items():
        # Representative node (centroid of group if multiple entrances/stops)
        mean_lon = sum(n["lon"] for n in node_group) / len(node_group)
        mean_lat = sum(n["lat"] for n in node_group) / len(node_group)
        x, y = lonlat_to_local(mean_lon, mean_lat)
        ground_z = elev_func(x, y)

        # Tags and attributes
        tags = node_group[0].get("tags", {})
        raw_name = node_group[0].get("tags", {}).get("name", clean_name)

        # Check line affiliation by finding nearest track
        best_dist = float("inf")
        best_line = "Metro"
        best_color = DEFAULT_ACCENT_COLOR
        best_mode = "elevated"

        for tr in tracks:
            for pt in tr["points"]:
                d = math.hypot(pt[0] - x, pt[1] - y)
                if d < best_dist:
                    best_dist = d
                    best_line = tr["line"]
                    best_color = tr["color"]
                    best_mode = tr["mode"]

        # An interchange or existing station is operational if at least one node is operational
        has_operational_node = any(
            n.get("tags", {}).get("railway") in ("station", "stop")
            and n.get("tags", {}).get("construction") is None
            and n.get("tags", {}).get("proposed") is None
            and "(u/c)" not in n.get("tags", {}).get("name", "")
            and "(Proposed)" not in n.get("tags", {}).get("name", "")
            and n.get("tags", {}).get("railway") not in ("proposed", "construction")
            for n in node_group
        )

        is_construction = not has_operational_node
        if best_line in ("Blue", "Orange", "Red") and not has_operational_node:
            is_construction = True

        # Known underground stations verification
        if clean_name in (
            "Nadaprabhu Kempegowda Station, Majestic",
            "Dr. B. R. Ambedkar Station, Vidhana Soudha",
            "Sir M. Visvesvaraya Stn., Central College",
            "Cubbon Park",
            "Krantivira Sangolli Rayanna Railway Station",
            "Chickpete",
            "Krishna Rajendra Market",
        ):
            best_mode = "underground"

        # Baiyappanahalli is at-grade
        if clean_name == "Baiyappanahalli":
            best_mode = "at_grade"

        # Pink Line Phase 2 elevated section check (opened 13 Nov 2026):
        # Kalena Agrahara, Hulimavu, Bilekahalli IIM-B, N S Palya (JP Nagar 4th Phase),
        # Jayadeva Hospital (Interchange), Suddaguntepalya (Tavarekere)
        if clean_name in (
            "Kalena Agrahara",
            "Hulimavu",
            "IIMB",
            "Bilekahalli",
            "Bilekahalli IIM-B",
            "JP Nagar 4th Phase",
            "N S Palya",
            "Jayadeva Interchange",
            "Jayadeva Hospital",
            "Jayadeva Hospital (Pink Line)",
            "Tavarekere",
            "Suddaguntepalya",
        ):
            best_mode = "elevated"
            if clean_name not in ("Jayadeva Hospital", "Jayadeva Interchange"):
                best_line = "Pink"
                best_color = "#ec4899"
            is_construction = False

        # Pink Line Phase 2 underground section (under construction):
        if clean_name in (
            "Dairy Circle",
            "Lakkasandra",
            "Langford Town",
            "Rashtriya Military School Metro Station",
            "Shivajinagar",
            "Cantonment",
            "Pottery Town",
            "Tannery Road",
            "Venkateshapura",
            "Kadugundanahalli",
            "Nagawara",
        ):
            best_mode = "underground"
            is_construction = True

        is_proposed = is_construction and any(
            "(Proposed)" in n.get("tags", {}).get("name", "")
            or n.get("tags", {}).get("proposed") is not None
            or n.get("tags", {}).get("railway") == "proposed"
            for n in node_group
        )

        if best_mode == "underground":
            stn_z = ground_z + METRO_TUNNEL_DEPTH_M
        elif best_mode == "elevated":
            stn_z = ground_z + METRO_VIADUCT_M
        else:
            stn_z = ground_z + METRO_GRADE_OFFSET_M

        if not is_construction:
            station_modes[best_mode] += 1

        stations.append(
            {
                "name": clean_name,
                "raw_name": raw_name,
                "lon": round(mean_lon, 6),
                "lat": round(mean_lat, 6),
                "x": round(x, 2),
                "y": round(y, 2),
                "z": round(stn_z, 2),
                "ground_z": round(ground_z, 2),
                "line": best_line,
                "color": best_color,
                "mode": best_mode,
                "is_construction": is_construction,
                "is_proposed": is_proposed,
            }
        )

    stations.sort(key=lambda s: s["name"])

    # Summary statistics
    total_op_track_km = sum(operational_km_by_mode.values())
    total_con_track_km = sum(construction_km_by_mode.values())

    # Reference comparison:
    # In dual-track subway systems, route length = total track km / 2
    est_operational_route_km = total_op_track_km / 2.0

    print("\n--- OPERATIONAL TRACK STATS (Track-km) ---")
    for mode, km in sorted(operational_km_by_mode.items()):
        print(f"  {mode}: {km:.2f} track-km (~{km/2:.2f} route-km)")
    print(
        f"Total Operational Track: {total_op_track_km:.2f} km (~{est_operational_route_km:.2f} route-km)"
    )

    print("\n--- OPERATIONAL BY LINE (Track-km) ---")
    for line, km in sorted(operational_km_by_line.items()):
        print(f"  Line {line}: {km:.2f} track-km (~{km/2:.2f} route-km)")

    print("\n--- UNDER CONSTRUCTION / PLANNED STATS (Track-km) ---")
    for mode, km in sorted(construction_km_by_mode.items()):
        print(f"  {mode}: {km:.2f} track-km (~{km/2:.2f} route-km)")
    print(f"Total Under Construction / Planned: {total_con_track_km:.2f} km")

    op_tracks = [t for t in tracks if not t["is_construction"]]
    con_only_tracks = [t for t in tracks if t["is_construction"] and not t.get("is_proposed")]
    prop_tracks = [t for t in tracks if t.get("is_proposed")]
    print(f"\n--- TRACK WAYS BY STATE ---")
    print(f"Operational Ways: {len(op_tracks)}")
    print(f"Under Construction Ways: {len(con_only_tracks)}")
    print(f"Proposed / Planned Ways: {len(prop_tracks)}")

    op_stations = [s for s in stations if not s["is_construction"]]
    con_only_stations = [s for s in stations if s["is_construction"] and not s.get("is_proposed")]
    prop_stations = [s for s in stations if s.get("is_proposed")]
    print(f"\n--- STATIONS BY STATE ---")
    print(f"Total Deduplicated Stations: {len(stations)}")
    print(
        f"Operational Stations: {len(op_stations)} (Elevated: {station_modes['elevated']}, Underground: {station_modes['underground']}, Grade: {station_modes['at_grade']})"
    )
    print(f"Under Construction Stations: {len(con_only_stations)}")
    print(f"Proposed / Planned Stations: {len(prop_stations)}")

    payload = {
        "metadata": {
            "system": "Namma Metro (Bengaluru)",
            "source": "OpenStreetMap (route=subway/light_rail relations, member ways, station nodes)",
            "license": "Open Data Commons Open Database License (ODbL) 1.0 by OpenStreetMap contributors",
            "viaductHeightMeters": METRO_VIADUCT_M,
            "assumptionViaductHeight": "8m standard viaduct deck height above DEM terrain (assumed constant; flagged in documentation)",
            "referenceOperationalNetwork": {
                "routeKm": 103.6,
                "stationsTotal": 91,
                "stationsElevated": 83,
                "stationsUnderground": 7,
                "stationsAtGrade": 1,
            },
            "osmExtractedOperational": {
                "totalTrackKm": round(total_op_track_km, 2),
                "estimatedRouteKm": round(est_operational_route_km, 2),
                "operationalStations": len(op_stations),
                "elevatedStations": station_modes["elevated"],
                "undergroundStations": station_modes["underground"],
                "atGradeStations": station_modes["at_grade"],
            },
            "trainsNotice": "Metro trains are illustrative, not live.",
        },
        "lines": {
            "Purple": {"name": "Purple Line", "color": "#e542de"},
            "Green": {"name": "Green Line", "color": "#009933"},
            "Yellow": {"name": "Yellow Line", "color": "#eab308"},
            "Pink": {"name": "Pink Line", "color": "#ec4899"},
            "Blue": {"name": "Blue Line (Airport)", "color": "#3b82f6"},
        },
        "tracks": tracks,
        "stations": stations,
    }

    out_file = WEB_DATA_DIR / "metro.json"
    out_file.write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )
    print(f"Saved {out_file} ({out_file.stat().st_size / 1024:.1f} KB).")

    stations_file = WEB_DATA_DIR / "metro_stations.json"
    stations_file.write_text(json.dumps(stations, indent=2), encoding="utf-8")
    print(f"Saved {stations_file}.")


if __name__ == "__main__":
    build_osm_metro()
