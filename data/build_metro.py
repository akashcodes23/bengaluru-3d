#!/usr/bin/env python3
"""Build Namma Metro lines and stations dataset from Overture Maps."""

import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import duckdb
import numpy as np
from shapely.geometry import shape, LineString, MultiLineString
from shapely.ops import linemerge, unary_union

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
METRO_VIADUCT_M = 8.0  # Assumed constant clearance above terrain for viaduct

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

def load_terrain_interpolator():
    """Build a fast terrain lookup function using the manifest and t_*.json chunks."""
    manifest_path = WEB_DATA_DIR / "manifest.json"
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
                return 900.0  # Bengaluru mean elevation fallback
            tpath = WEB_DATA_DIR / tfile
            if not tpath.is_file():
                return 900.0
            data = json.loads(tpath.read_text(encoding="utf-8"))
            loaded_chunks[key] = (data["width"], np.array(data["heights"], dtype=np.float32).reshape(data["height"], data["width"]))
            
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

def build_metro():
    print("Building Namma Metro lines and stations...")
    elev_func = load_terrain_interpolator()
    
    # 1. Load subway rail lines from transportation.parquet
    parquet_path = CACHE_DIR / "2026-10-21.0" / "transportation.parquet"
    if not parquet_path.is_file():
        raise FileNotFoundError(f"Missing {parquet_path}")
        
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    rows = con.execute(f"""
        SELECT id, geometry_json, class, subtype
        FROM '{parquet_path}'
        WHERE subtype = 'rail' AND class = 'subway'
    """).fetchall()
    print(f"Found {len(rows)} subway rail features in transportation.parquet.")
    
    raw_geoms = [shape(json.loads(r[1])) for r in rows]
    # Merge connected segments into continuous lines
    union_geom = unary_union(raw_geoms)
    merged = linemerge(union_geom)
    
    if isinstance(merged, LineString):
        lines = [merged]
    elif isinstance(merged, MultiLineString):
        lines = list(merged.geoms)
    else:
        lines = []
        
    print(f"Merged into {len(lines)} continuous track corridors.")
    
    # Sort by length descending, keep those of significant length (> 100m)
    lines = [l for l in lines if l.length * 111000 > 100]
    lines.sort(key=lambda l: l.length, reverse=True)
    
    # Convert to local coordinates and drape with viaduct clearance
    metro_tracks = []
    total_length_km = 0.0
    
    for idx, line in enumerate(lines):
        coords = list(line.coords)
        pts_3d = []
        line_len = 0.0
        for i, (lon, lat) in enumerate(coords):
            x, y = lonlat_to_local(lon, lat)
            ground_z = elev_func(x, y)
            # In 3D viewer: local X is East, local Y (Three.js Z) is South (-north), local Z (Three.js Y) is Up.
            # Elevation is relative to origin ground or absolute?
            # Let's check how index.html positions terrain!
            viaduct_elev = ground_z + METRO_VIADUCT_M
            pts_3d.append([round(x, 2), round(y, 2), round(viaduct_elev, 2), round(ground_z, 2)])
            if i > 0:
                prev_x, prev_y = pts_3d[i-1][0], pts_3d[i-1][1]
                line_len += math.hypot(x - prev_x, y - prev_y)
                
        total_length_km += line_len / 1000.0
        metro_tracks.append({
            "id": f"track_{idx+1}",
            "length_m": round(line_len, 1),
            "points": pts_3d,
        })
        
    print(f"Prepared {len(metro_tracks)} metro tracks, total length: {total_length_km:.1f} km.")
    
    # 2. Extract stations from places_full.parquet
    places_path = CACHE_DIR / "places_full.parquet"
    station_rows = con.execute(f"""
        SELECT names."primary" as name, 
               round(ST_X(geometry), 6) as lon, 
               round(ST_Y(geometry), 6) as lat
        FROM '{places_path}'
        WHERE (names."primary" ILIKE '%metro station%' 
           OR names."primary" ILIKE '%metro stn%'
           OR (basic_category IN ('travel_and_transportation', 'train_station') AND names."primary" ILIKE '%metro%'))
          AND names."primary" NOT ILIKE '%hotel%'
          AND names."primary" NOT ILIKE '%inn%'
          AND names."primary" NOT ILIKE '%townhouse%'
          AND names."primary" NOT ILIKE '%oyo%'
          AND names."primary" NOT ILIKE '%office%'
          AND names."primary" NOT ILIKE '%lab%'
          AND names."primary" NOT ILIKE '%hospital%'
          AND names."primary" NOT ILIKE '%bar%'
          AND names."primary" NOT ILIKE '%resort%'
          AND names."primary" NOT ILIKE '%shoe%'
          AND names."primary" NOT ILIKE '%deluxe%'
          AND names."primary" NOT ILIKE '%packers%'
          AND names."primary" NOT ILIKE '%bhive%'
          AND names."primary" NOT ILIKE '%chai%'
          AND names."primary" NOT ILIKE '%radical%'
          AND names."primary" NOT ILIKE '%distributor%'
          AND names."primary" NOT ILIKE '%corp%'
          AND names."primary" NOT ILIKE '%freight%'
          AND names."primary" NOT ILIKE '%parking%'
          AND names."primary" NOT ILIKE '%ticket counter%'
          AND names."primary" NOT ILIKE '%comforts%'
          AND names."primary" NOT ILIKE '%residency%'
          AND names."primary" NOT ILIKE '%santa maria%'
          AND names."primary" NOT ILIKE '%mr. pronto%'
          AND names."primary" NOT ILIKE '%zo rooms%'
          AND names."primary" NOT ILIKE '%collection o%'
        ORDER BY names."primary"
    """).fetchall()
    
    def dist_m(p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    stations = []
    for name, lon, lat in station_rows:
        x, y = lonlat_to_local(lon, lat)
        ground_z = elev_func(x, y)
        loc = (x, y)
        # Clean redundant suffixes/prefixes for neat HUD display if appropriate, but keep data name
        # Prompt: "show markers with names only where the name comes from the data."
        clean_name = name.strip()
        
        # Deduplicate stations within 200m
        dup = False
        for s in stations:
            if dist_m(loc, (s["x"], s["y"])) < 200:
                dup = True
                break
        if not dup:
            stations.append({
                "name": clean_name,
                "lon": lon,
                "lat": lat,
                "x": round(x, 2),
                "y": round(y, 2),
                "z": round(ground_z + METRO_VIADUCT_M, 2),
                "ground_z": round(ground_z, 2),
                "source": "Overture Places"
            })
            
    print(f"Extracted {len(stations)} deduplicated metro stations.")
    
    metro_payload = {
        "metadata": {
            "system": "Namma Metro (Bengaluru)",
            "source": "Overture Maps (transportation/segment & places/place)",
            "release": "2026-10-21.0",
            "viaductHeightMeters": METRO_VIADUCT_M,
            "assumptionViaductHeight": "8m standard elevated viaduct clearance above DEM terrain (assumed constant due to lack of per-segment vertical clearance in Overture schema)",
            "lineColor": "#00e5ff",
            "lineColorReason": "Neutral cyan accent chosen because Overture rail segments lack line names or ref tags in the saved dataset",
            "trackCount": len(metro_tracks),
            "stationCount": len(stations),
            "totalTrackLengthKm": round(total_length_km, 2),
            "trainsScheduleNotice": "illustrative, not live"
        },
        "tracks": metro_tracks,
        "stations": stations
    }
    
    metro_out = WEB_DATA_DIR / "metro.json"
    metro_out.write_text(json.dumps(metro_payload, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {metro_out} ({metro_out.stat().st_size / 1024:.1f} KB).")
    
    # Also write stations file
    stations_out = WEB_DATA_DIR / "metro_stations.json"
    stations_out.write_text(json.dumps(stations, indent=2), encoding="utf-8")
    print(f"Wrote {stations_out}.")

if __name__ == "__main__":
    build_metro()
