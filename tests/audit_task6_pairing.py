import glob
import json
import math
import os
from collections import defaultdict

def distance_point_to_segment(px, py, x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)

def analyze_pairing():
    files = sorted(glob.glob('web/data/g_*.json'))
    print(f"Scanning {len(files)} ground chunks for major roads...")

    all_pairs_raw = [] # all pairs with separation 0-40m
    hosur_pairs = []
    pairs_near_boundary = 0
    total_valid_pairs = 0

    pairs_m_t_only = 0
    pairs_all_major = 0

    # Histogram in 1m bins (0 to 40)
    bins = [0] * 41

    for fpath in files:
        fname = os.path.basename(fpath)
        # Parse chunk coordinates
        parts = fname.replace("g_", "").replace(".json", "").split("_")
        ix, iy = int(parts[0]), int(parts[1])
        chunk_min_x = ix * 1000.0
        chunk_max_x = (ix + 1) * 1000.0
        chunk_min_y = iy * 1000.0
        chunk_max_y = (iy + 1) * 1000.0

        with open(fpath) as fp:
            try:
                data = json.load(fp)
            except Exception:
                continue

        roads = data.get("roads", [])
        major_roads = []
        for r in roads:
            cls = r.get("class")
            if cls in ("motorway", "trunk", "primary"):
                coords = r.get("p", [])
                if len(coords) < 4:
                    continue
                # Compute polyline length
                total_len = 0.0
                for i in range(0, len(coords) - 2, 2):
                    total_len += math.hypot(coords[i+2] - coords[i], coords[i+3] - coords[i+1])
                if total_len >= 15.0:
                    major_roads.append({
                        "class": cls,
                        "coords": coords,
                        "length": total_len,
                        "chunk": (ix, iy)
                    })

        # Test pairing within this chunk
        for i in range(len(major_roads)):
            r1 = major_roads[i]
            if r1["length"] < 80.0:
                continue
            p1 = r1["coords"]
            dx1 = p1[-2] - p1[0]
            dy1 = p1[-1] - p1[1]
            hyp1 = math.hypot(dx1, dy1)
            if hyp1 < 0.01:
                continue
            ux1, uy1 = dx1 / hyp1, dy1 / hyp1

            for j in range(i + 1, len(major_roads)):
                r2 = major_roads[j]
                if r2["length"] < 80.0:
                    continue
                p2 = r2["coords"]
                dx2 = p2[-2] - p2[0]
                dy2 = p2[-1] - p2[1]
                hyp2 = math.hypot(dx2, dy2)
                if hyp2 < 0.01:
                    continue
                ux2, uy2 = dx2 / hyp2, dy2 / hyp2

                dot = abs(ux1 * ux2 + uy1 * uy2)
                if dot < 0.9659: # angle > 15 deg
                    continue

                mid1_idx = (len(p1) // 4) * 2
                mid2_idx = (len(p2) // 4) * 2
                vx = p2[mid2_idx] - p1[mid1_idx]
                vy = p2[mid2_idx + 1] - p1[mid1_idx + 1]
                dist = math.hypot(vx, vy)

                if dist <= 40.0:
                    bin_idx = min(40, int(dist))
                    bins[bin_idx] += 1
                    all_pairs_raw.append((dist, r1, r2))

                    if r1["class"] in ("motorway", "trunk") and r2["class"] in ("motorway", "trunk"):
                        pairs_m_t_only += 1
                    pairs_all_major += 1

                    # Check if Hosur road (approx coords: x ~ 0 to 4000, y ~ -2000 to -12000)
                    mx = (p1[0] + p2[0]) / 2.0
                    my = (p1[1] + p2[1]) / 2.0
                    if 0 <= mx <= 4000 and -12000 <= my <= -2000:
                        hosur_pairs.append((dist, r1, r2, (ix, iy)))

                    # Check chunk boundary proximity (endpoints within 2m of boundary)
                    near_b = False
                    for pt in (p1[0], p1[-2], p2[0], p2[-2]):
                        if abs(pt - chunk_min_x) <= 2.0 or abs(pt - chunk_max_x) <= 2.0:
                            near_b = True
                            break
                    for pt in (p1[1], p1[-1], p2[1], p2[-1]):
                        if abs(pt - chunk_min_y) <= 2.0 or abs(pt - chunk_max_y) <= 2.0:
                            near_b = True
                            break
                    if near_b:
                        pairs_near_boundary += 1

    print("\n======================================================================")
    print("PAIRING AUDIT: RECONCILIATION & HISTOGRAM")
    print("======================================================================")
    print(f"Total candidate pairs with angle < 15° and length > 80m (0 to 40m): {len(all_pairs_raw)}")
    print(f"  Motorway & Trunk pairs only: {pairs_m_t_only}")
    print(f"  All Major (Motorway, Trunk, Primary): {pairs_all_major}")
    print(f"  Pairs with dist in [8m, 40m] (current threshold): {sum(bins[8:])}")
    print(f"  Pairs with dist < 8m: {sum(bins[:8])}")

    print("\n--- 1-METRE SEPARATION HISTOGRAM (0 to 40 m) ---")
    print(" Bin (m) | Count | Percentage | Cumulative")
    print("---------+-------+------------+-----------")
    cum = 0
    total = len(all_pairs_raw) if all_pairs_raw else 1
    for b in range(41):
        c = bins[b]
        cum += c
        pct = (c / total) * 100.0
        cum_pct = (cum / total) * 100.0
        marker = " <-- [Hosur Road elevated pair 7.3 - 8.8m]" if 7 <= b <= 8 else ""
        print(f" {b:2d} - {b+1:2d}m | {c:5d} | {pct:6.2f}%    | {cum_pct:6.2f}%{marker}")

    print("\n--- HOSUR ROAD AUDIT ---")
    print(f"Hosur Road corridor parallel pairs detected: {len(hosur_pairs)}")
    for dist, r1, r2, chunk in hosur_pairs[:8]:
        print(f"  Chunk {chunk}: dist={dist:.2f} m, classes=({r1['class']}, {r2['class']}), len1={r1['length']:.1f}m, len2={r2['length']:.1f}m")

    print("\n--- CHUNK BOUNDARY AUDIT ---")
    b_share = (pairs_near_boundary / total) * 100.0 if total else 0.0
    print(f"Pairs with at least one endpoint within 2m of chunk boundary: {pairs_near_boundary} / {total} ({b_share:.2f}%)")
    print("Handling: Polylines are chunk-clipped during tile ingestion. Pairing operates independently per chunk.")

if __name__ == "__main__":
    analyze_pairing()
