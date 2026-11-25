#!/usr/bin/env python3
"""Build 3D airport geometry (runways, taxiways, aprons) for Kempegowda International Airport from OSM."""

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import triangulate

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA_DIR = ROOT / "web" / "data"
CACHE_DIR = ROOT / "data" / "cache"

ORIGIN_LON = 77.5946
ORIGIN_LAT = 12.9716
METERS_PER_DEGREE_LON = 111_319.49079327358 * math.cos(math.radians(ORIGIN_LAT))
METERS_PER_DEGREE_LAT = 110_574.0

DEFAULT_RUNWAY_WIDTH_M = 45.0
DEFAULT_TAXIWAY_WIDTH_M = 20.0
AIRPORT_GROUND_OFFSET_M = 0.35
APRON_GROUND_OFFSET_M = 0.28


def lonlat_to_local(lon: float, lat: float) -> Tuple[float, float]:
    return (
        (lon - ORIGIN_LON) * METERS_PER_DEGREE_LON,
        (lat - ORIGIN_LAT) * METERS_PER_DEGREE_LAT,
    )


def load_terrain_interpolator():
    manifest_path = WEB_DATA_DIR / "manifest.json"
    if not manifest_path.is_file():
        return lambda x, y: 910.0

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
                return 910.0
            tpath = WEB_DATA_DIR / tfile
            if not tpath.is_file():
                return 910.0
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


def build_airport():
    print("=== Processing OSM Airport Data ===")
    cache_file = CACHE_DIR / "osm_airport.json"
    if not cache_file.is_file():
        raise FileNotFoundError(f"OSM airport cache not found at {cache_file}")

    data = json.loads(cache_file.read_text(encoding="utf-8"))
    elements = data.get("elements", [])
    print(f"Loaded {len(elements)} elements from {cache_file}.")

    elev_func = load_terrain_interpolator()

    runways = []
    taxiways = []
    apron_polygons = []

    total_runway_len_m = 0.0
    total_taxiway_len_m = 0.0

    for e in elements:
        etype = e.get("type")
        tags = e.get("tags", {})
        aw = tags.get("aeroway")

        if etype == "way" and aw == "runway":
            geom = e.get("geometry", [])
            if len(geom) < 2:
                continue
            try:
                width = float(tags.get("width", DEFAULT_RUNWAY_WIDTH_M))
            except ValueError:
                width = DEFAULT_RUNWAY_WIDTH_M

            ref = tags.get("ref", "")
            name = tags.get("name", f"Runway {ref}".strip())
            pts_3d = []
            way_len = 0.0
            for i, pt in enumerate(geom):
                x, y = lonlat_to_local(pt["lon"], pt["lat"])
                z = elev_func(x, y) + AIRPORT_GROUND_OFFSET_M
                pts_3d.append([round(x, 2), round(y, 2), round(z, 2)])
                if i > 0:
                    px, py, _ = pts_3d[i - 1]
                    way_len += math.hypot(x - px, y - py)

            total_runway_len_m += way_len
            runways.append({
                "id": f"runway_{e['id']}",
                "ref": ref,
                "name": name,
                "width": width,
                "length_m": round(way_len, 1),
                "points": pts_3d,
            })

        elif etype == "way" and aw == "taxiway":
            geom = e.get("geometry", [])
            if len(geom) < 2:
                continue
            try:
                width = float(tags.get("width", DEFAULT_TAXIWAY_WIDTH_M))
            except ValueError:
                width = DEFAULT_TAXIWAY_WIDTH_M

            ref = tags.get("ref", "")
            pts_3d = []
            way_len = 0.0
            for i, pt in enumerate(geom):
                x, y = lonlat_to_local(pt["lon"], pt["lat"])
                z = elev_func(x, y) + AIRPORT_GROUND_OFFSET_M
                pts_3d.append([round(x, 2), round(y, 2), round(z, 2)])
                if i > 0:
                    px, py, _ = pts_3d[i - 1]
                    way_len += math.hypot(x - px, y - py)

            total_taxiway_len_m += way_len
            taxiways.append({
                "id": f"taxiway_{e['id']}",
                "ref": ref,
                "width": width,
                "length_m": round(way_len, 1),
                "points": pts_3d,
            })

        elif etype == "way" and aw == "apron":
            geom = e.get("geometry", [])
            if len(geom) >= 3:
                poly_pts = [lonlat_to_local(pt["lon"], pt["lat"]) for pt in geom]
                if poly_pts[0] != poly_pts[-1]:
                    poly_pts.append(poly_pts[0])
                try:
                    p = Polygon(poly_pts)
                    if p.is_valid and p.area > 10.0:
                        apron_polygons.append(p)
                except Exception:
                    pass

        elif etype == "relation" and aw == "apron":
            members = e.get("members", [])
            outers = [m["geometry"] for m in members if m.get("role") == "outer" and m.get("geometry")]
            inners = [m["geometry"] for m in members if m.get("role") == "inner" and m.get("geometry")]
            for out in outers:
                if len(out) >= 3:
                    out_pts = [lonlat_to_local(pt["lon"], pt["lat"]) for pt in out]
                    if out_pts[0] != out_pts[-1]:
                        out_pts.append(out_pts[0])
                    inner_rings = []
                    for inn in inners:
                        if len(inn) >= 3:
                            inn_pts = [lonlat_to_local(pt["lon"], pt["lat"]) for pt in inn]
                            if inn_pts[0] != inn_pts[-1]:
                                inn_pts.append(inn_pts[0])
                            inner_rings.append(inn_pts)
                    try:
                        p = Polygon(out_pts, inner_rings)
                        if p.is_valid and p.area > 10.0:
                            apron_polygons.append(p)
                    except Exception:
                        pass

    # Triangulate aprons for 3D flat mesh
    apron_triangles = []
    total_apron_area_m2 = 0.0
    for poly in apron_polygons:
        total_apron_area_m2 += poly.area
        triangles = triangulate(poly)
        for tri in triangles:
            if poly.contains(tri.centroid):
                pts = list(tri.exterior.coords)[:3]
                tri_pts = []
                for x, y in pts:
                    z = elev_func(x, y) + APRON_GROUND_OFFSET_M
                    tri_pts.extend([round(x, 2), round(y, 2), round(z, 2)])
                apron_triangles.extend(tri_pts)

    print(f"\n--- AIRPORT STATS ---")
    print(f"Runways: {len(runways)} ({total_runway_len_m/1000.0:.2f} km)")
    for rw in runways:
        print(f"  {rw['name']} (ref {rw['ref']}): length {rw['length_m']} m, width {rw['width']} m")
    print(f"Taxiways: {len(taxiways)} ({total_taxiway_len_m/1000.0:.2f} km)")
    print(f"Aprons: {len(apron_polygons)} polygons, {len(apron_triangles)//9} triangles ({total_apron_area_m2/1e6:.3f} km²)")

    out = {
        "metadata": {
            "airport": "Kempegowda International Airport (BLR / VOBL)",
            "source": "OpenStreetMap aeroway features",
            "license": "ODbL 1.0 by OpenStreetMap contributors",
            "defaultRunwayWidthM": DEFAULT_RUNWAY_WIDTH_M,
            "defaultTaxiwayWidthM": DEFAULT_TAXIWAY_WIDTH_M,
        },
        "runways": runways,
        "taxiways": taxiways,
        "apronTriangles": apron_triangles,
    }

    out_path = WEB_DATA_DIR / "airport.json"
    out_path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {out_path} ({out_path.stat().st_size / 1024:.1f} KB).")


if __name__ == "__main__":
    build_airport()
