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
    from shapely.geometry import LineString, Point

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

    orig_line = LineString(pts_local)
    result = []
    for p in current:
        pt = Point(p)
        d = orig_line.distance(pt)
        if d > max_dev:
            nearest = orig_line.interpolate(orig_line.project(pt))
            ratio = max_dev / d
            nx = nearest.x + (p[0] - nearest.x) * ratio
            ny = nearest.y + (p[1] - nearest.y) * ratio
            result.append((nx, ny))
        else:
            result.append(p)
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

        is_construction = (
            railway == "construction"
            or "construction" in tags
            or tags.get("proposed") is not None
        )

        # Mode
        tunnel = tags.get("tunnel")
        bridge = tags.get("bridge")
        layer_str = tags.get("layer")
        try:
            layer = int(layer_str) if layer_str is not None else 0
        except ValueError:
            layer = 0

        if tunnel == "yes" or layer < 0:
            mode = "underground"
        elif bridge in ("yes", "viaduct") or layer > 0:
            mode = "elevated"
        else:
            mode = "at_grade"

        # Line & Color from relation
        rels = way_rels.get(wid, [])
        if rels:
            # Pick first primary relation
            primary_rel = rels[0]
            line_ref = primary_rel["ref"]
            line_name = primary_rel["name"]
            line_color = primary_rel["color"]
        else:
            line_ref = "Metro"
            line_name = "Namma Metro"
            line_color = DEFAULT_ACCENT_COLOR

        # Note: Pink Line elevated section (Kalena Agrahara to Tavarekere) opened Nov 13, 2026.
        # In OSM, some ways may be tagged railway=subway or railway=construction.
        # If railway == subway, it is already marked operational.

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
                "length_m": round(way_len_m, 1),
                "points": pts_3d,
            }
        )

    # 3. Process Stations
    station_nodes_raw = {}
    # Nodes with station tags
    for nid, node in nodes.items():
        ntags = node.get("tags", {})
        if (
            ntags.get("railway") in ("station", "stop")
            or ntags.get("station") == "subway"
            or ntags.get("construction") == "station"
            or "metro" in ntags.get("name", "").lower()
        ):
            station_nodes_raw[nid] = node

    # Deduplicate stations by name and proximity
    stations_by_name = defaultdict(list)
    for nid, node in station_nodes_raw.items():
        name = node.get("tags", {}).get("name")
        if not name:
            continue
        # Clean clean name
        clean_name = name.replace(" (u/c)", "").replace(" (Proposed)", "").strip()
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

        # Construction status
        is_construction = any(
            "(u/c)" in n.get("tags", {}).get("name", "")
            or "(Proposed)" in n.get("tags", {}).get("name", "")
            or n.get("tags", {}).get("construction") is not None
            or n.get("tags", {}).get("railway") == "proposed"
            for n in node_group
        )

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

        # Known underground stations verification
        if clean_name in (
            "Nadaprabhu Kempegowda Station, Majestic",
            "Dr. B. R. Ambedkar Station, Vidhana Soudha",
            "Sir M. Visvesvaraya Stn., Central College",
            "Cubbon Park",
            "Krantivira Sangolli Rayanna Railway Station",
            "Chickpete",
            "Krishna Rajendra Market",
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

        # Pink Line Phase 2 elevated section check:
        # Kalena Agrahara, Hulimavu, IIMB, JP Nagar 4th Phase, Jayadeva Hospital / Interchange, Tavarekere
        # opened on 13 Nov 2026.
        if clean_name in (
            "Kalena Agrahara",
            "Hulimavu",
            "IIMB",
            "Bilekahalli",
            "JP Nagar 4th Phase",
            "Jayadeva Interchange",
            "Jayadeva Hospital",
            "Tavarekere",
        ):
            best_mode = "elevated"
            best_line = "Pink" if clean_name != "Jayadeva Hospital" else best_line
            best_color = "#ec4899" if clean_name != "Jayadeva Hospital" else best_color
            # These 6/7 stations are operational since 13 Nov 2026!
            is_construction = False

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

    print("\n--- UNDER CONSTRUCTION STATS (Track-km) ---")
    for mode, km in sorted(construction_km_by_mode.items()):
        print(f"  {mode}: {km:.2f} track-km (~{km/2:.2f} route-km)")
    print(f"Total Under Construction: {total_con_track_km:.2f} km")

    op_stations = [s for s in stations if not s["is_construction"]]
    con_stations = [s for s in stations if s["is_construction"]]
    print(f"\n--- STATIONS ---")
    print(f"Total Deduplicated Stations: {len(stations)}")
    print(
        f"Operational Stations: {len(op_stations)} (Elevated: {station_modes['elevated']}, Underground: {station_modes['underground']}, Grade: {station_modes['at_grade']})"
    )
    print(f"Under Construction Stations: {len(con_stations)}")

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
