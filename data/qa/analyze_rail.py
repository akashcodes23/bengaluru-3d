#!/usr/bin/env python3
"""Inspect full rail schema from Overture raw segment download and report statistics."""

import json
import math
import sys
from pathlib import Path
import duckdb

PARQUET_PATH = Path("data/cache/rail_all_seg.parquet")
if not PARQUET_PATH.is_file():
    print(f"File {PARQUET_PATH} does not exist yet.")
    sys.exit(1)

con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial;")

print("=== 1. FULL COLUMN LIST & NON-NULL COUNTS (RAIL ONLY) ===")
cols_desc = con.execute(f"DESCRIBE SELECT * FROM '{PARQUET_PATH}'").fetchall()
col_names = [c[0] for c in cols_desc]

rail_total = con.execute(f"SELECT COUNT(*) FROM '{PARQUET_PATH}' WHERE subtype = 'rail'").fetchone()[0]
print(f"Total rail rows: {rail_total}")

for col in col_names:
    nn = con.execute(f"SELECT COUNT({col}) FROM '{PARQUET_PATH}' WHERE subtype = 'rail' AND {col} IS NOT NULL").fetchone()[0]
    pct = (nn / rail_total * 100) if rail_total > 0 else 0
    print(f"  {col:25s}: {nn:6d} / {rail_total:6d} ({pct:5.1f}%) non-null")

print("\n=== 2. RAIL ROWS BY CLASS ===")
rows = con.execute(f"""
    SELECT class, COUNT(*) as cnt
    FROM '{PARQUET_PATH}'
    WHERE subtype = 'rail'
    GROUP BY class
    ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  class = {r[0]!r:20s}: {r[1]} rows")

print("\n=== 3. DETAILED RAIL FLAGS & MODES ===")
# Let's inspect rail_flags values
rows = con.execute(f"""
    SELECT id, class, subtype, rail_flags, level_rules, names.primary as name,
           ST_Length(ST_Transform(geometry, 'OGC:CRS84', 'EPSG:3857')) as len_m
    FROM '{PARQUET_PATH}'
    WHERE subtype = 'rail'
""").fetchall()

flag_stats = {}
for r in rows:
    fid, r_class, r_sub, r_flags, r_levels, r_name, r_len_m = r
    # parse flags
    flags_list = []
    if r_flags:
        for rf in r_flags:
            if isinstance(rf, dict) and 'values' in rf and rf['values']:
                flags_list.extend(rf['values'])
            elif isinstance(rf, list):
                flags_list.extend(rf)
    flags_set = set(flags_list)
    
    is_tunnel = 'is_tunnel' in flags_set
    is_bridge = 'is_bridge' in flags_set
    is_u_c = 'is_under_construction' in flags_set
    is_abandoned = 'is_abandoned' in flags_set
    is_electrified = 'is_electrified' in flags_set
    
    mode = "ground"
    if is_tunnel:
        mode = "tunnel"
    elif is_bridge:
        mode = "bridge"
    
    key = (r_class, mode, is_u_c, is_abandoned)
    if key not in flag_stats:
        flag_stats[key] = {"count": 0, "len_m": 0.0}
    flag_stats[key]["count"] += 1
    flag_stats[key]["len_m"] += (r_len_m or 0.0)

print(f"{'Class':15s} | {'Mode':10s} | {'Under Constr':12s} | {'Abandoned':10s} | {'Count':6s} | {'Total km':10s}")
print("-" * 75)
for (r_class, mode, is_u_c, is_abandoned), data in sorted(flag_stats.items()):
    km = data["len_m"] / 1000.0
    print(f"{r_class:15s} | {mode:10s} | {str(is_u_c):12s} | {str(is_abandoned):10s} | {data['count']:6d} | {km:8.2f} km")
