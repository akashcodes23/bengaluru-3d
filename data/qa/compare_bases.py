#!/usr/bin/env python3
import json
import math
import sys
import time
from pathlib import Path
import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1]))
from build_terrain import *

def main():
    manifest_path = WEB_DATA_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks = manifest.get("chunks", [])
    print(f"Loaded manifest with {len(chunks)} chunks.")
    
    # Load raster tiles
    west, south = local_to_lonlat(-15000, -16000)
    east, north = local_to_lonlat(20000, 18000)
    tile_keys = [
        'Copernicus_DSM_COG_10_N12_00_E077_00_DEM/Copernicus_DSM_COG_10_N12_00_E077_00_DEM.tif',
        'Copernicus_DSM_COG_10_N13_00_E077_00_DEM/Copernicus_DSM_COG_10_N13_00_E077_00_DEM.tif'
    ]
    t0 = time.time()
    tiles = [RasterTile(k, (west, south, east, north)) for k in tile_keys]
    sampler = TerrainSampler(tiles)
    print(f"Raster tiles loaded in {time.time() - t0:.1f}s.")
    
    total_buildings = 0
    changed_over_3m = 0
    max_change = 0.0
    hist_bins = [0, 1, 2, 3, 5, 10, 15, 20, 30, 50, 100]
    hist_counts = [0] * (len(hist_bins) - 1)
    
    t_start = time.time()
    for idx, chunk in enumerate(chunks):
        bfile = chunk.get("buildingFile")
        tfile = chunk.get("terrainFile")
        if not bfile or not tfile:
            continue
        
        bpath = WEB_DATA_DIR / bfile
        tpath = WEB_DATA_DIR / tfile
        if not bpath.is_file() or not tpath.is_file():
            continue
            
        b_records = json.loads(bpath.read_text(encoding="utf-8"))
        t_data = json.loads(tpath.read_text(encoding="utf-8"))
        stored_bases = t_data.get("buildingBases", [])
        
        if not b_records or not stored_bases:
            continue
            
        # For each building, compute centroid elevation and compare with stored base (which is min in bbox)
        for i, rec in enumerate(b_records):
            if i >= len(stored_bases):
                break
            coords = rec[1]
            cx, cnorth = polygon_centroid(coords)
            clon, clat = local_to_lonlat(cx, cnorth)
            cent_elev = float(sampler.sample(np.array([clon]), np.array([clat]))[0])
            min_base = stored_bases[i]
            diff = abs(min_base - cent_elev)
            
            total_buildings += 1
            if diff > 3.0:
                changed_over_3m += 1
            if diff > max_change:
                max_change = diff
                
            for b_idx in range(len(hist_bins) - 1):
                if hist_bins[b_idx] <= diff < hist_bins[b_idx + 1]:
                    hist_counts[b_idx] += 1
                    break
                    
        if (idx + 1) % 100 == 0 or (idx + 1) == len(chunks):
            elapsed = time.time() - t_start
            print(f"Processed {idx + 1}/{len(chunks)} chunks ({total_buildings:,} bldgs) in {elapsed:.1f}s. >3m: {changed_over_3m:,} ({100*changed_over_3m/total_buildings:.1f}%), max: {max_change:.2f}m", flush=True)

    print("--- FINAL BASE CHANGE REPORT ---")
    print(f"Total buildings evaluated: {total_buildings:,}")
    print(f"Buildings changed base by > 3 m: {changed_over_3m:,} ({100*changed_over_3m/total_buildings:.2f}%)")
    print(f"Maximum base change: {max_change:.2f} m")
    print("Histogram of |min_dem - centroid|:")
    for b_idx in range(len(hist_bins) - 1):
        print(f"  [{hist_bins[b_idx]}, {hist_bins[b_idx + 1]}) m: {hist_counts[b_idx]:,} ({100*hist_counts[b_idx]/total_buildings:.2f}%)")

if __name__ == "__main__":
    main()
