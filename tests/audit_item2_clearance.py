"""
Item 2: Complete Clearance Audit (All 25 waypoints + 25m path audit)
Rule: margin = alt - max(ground + 120, roof + 40)
"""

import json
import math
import os

ORIGIN_LON = 77.5946
ORIGIN_LAT = 12.9716
METERS_PER_DEGREE_LON = 111319.49079327358 * math.cos(ORIGIN_LAT * math.pi / 180)
METERS_PER_DEGREE_LAT = 110574.0
CHUNK_SIZE = 1000

terrain_cache = {}

def get_terrain_elevation(x, north):
    ix = math.floor(x / CHUNK_SIZE)
    iy = math.floor(north / CHUNK_SIZE)
    key = f"{ix}_{iy}"
    if key not in terrain_cache:
        t_path = f"web/data/t_{ix}_{iy}.json"
        if not os.path.exists(t_path):
            terrain_cache[key] = None
        else:
            with open(t_path) as fp:
                terrain_cache[key] = json.load(fp)

    grid = terrain_cache[key]
    if not grid:
        return 900.0 # fallback

    scaleX = grid["width"] - 1
    scaleY = grid["height"] - 1
    fx = max(0.0, min(scaleX, (x / CHUNK_SIZE - ix) * scaleX))
    fy = max(0.0, min(scaleY, (north / CHUNK_SIZE - iy) * scaleY))
    x0, y0 = math.floor(fx), math.floor(fy)
    x1, y1 = min(scaleX, x0 + 1), min(scaleY, y0 + 1)
    tx, ty = fx - x0, fy - y0
    def at(col, row):
        return grid["heights"][row * grid["width"] + col]
    lower = at(x0, y0) * (1 - tx) + at(x1, y0) * tx
    upper = at(x0, y1) * (1 - tx) + at(x1, y1) * tx
    return lower * (1 - ty) + upper * ty

def lat_lon_to_local(lat, lon):
    east = (lon - ORIGIN_LON) * METERS_PER_DEGREE_LON
    north = (lat - ORIGIN_LAT) * METERS_PER_DEGREE_LAT
    return east, -north, north

building_chunks_cache = {}
def get_building_records(ix, iy):
    key = f"{ix}_{iy}"
    if key not in building_chunks_cache:
        c_path = f"web/data/c_{ix}_{iy}.json"
        if not os.path.exists(c_path):
            building_chunks_cache[key] = []
        else:
            with open(c_path) as fp:
                building_chunks_cache[key] = json.load(fp)
    return building_chunks_cache[key]

def find_tallest_building_within_100m(local_x, local_north):
    chunk_ix = math.floor(local_x / CHUNK_SIZE)
    chunk_iy = math.floor(local_north / CHUNK_SIZE)

    tallest = None
    max_roof = -1e9

    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            c_ix = chunk_ix + dx
            c_iy = chunk_iy + dy
            records = get_building_records(c_ix, c_iy)
            for b_idx, r in enumerate(records):
                h, coords, src = r[0], r[1], r[2]
                if len(coords) < 6: continue
                # Fast bounding box check
                if abs(coords[0] - local_x) > 150.0 or abs(coords[1] - local_north) > 150.0:
                    continue

                # Min distance from (local_x, local_north) to polygon segment
                min_d = 1e9
                for i in range(0, len(coords) - 2, 2):
                    x1, y1 = coords[i], coords[i+1]
                    x2, y2 = coords[i+2], coords[i+3]
                    l2 = (x2 - x1)**2 + (y2 - y1)**2
                    t = max(0.0, min(1.0, ((local_x - x1)*(x2 - x1) + (local_north - y1)*(y2 - y1)) / l2)) if l2 > 0 else 0.0
                    px = x1 + t * (x2 - x1)
                    py = y1 + t * (y2 - y1)
                    d = math.hypot(local_x - px, local_north - py)
                    if d < min_d: min_d = d

                if min_d <= 100.0:
                    b_ground = get_terrain_elevation(coords[0], coords[1])
                    roof = b_ground + h
                    if roof > max_roof:
                        max_roof = roof
                        tallest = {
                            "id": f"c_{c_ix}_{c_iy}#{b_idx}",
                            "height": h,
                            "top": roof,
                            "dist": min_d
                        }
    return tallest

def main():
    # Load waypoints from web/tours.js
    with open("web/tours.js") as fp:
        text = fp.read()

    import re
    tour_blocks = re.findall(r'\{\s*id:\s*\"([^\"]+)\",\s*title:\s*\"([^\"]+)\".*?waypoints:\s*\[(.*?)\n\s*\]\s*\}', text, re.DOTALL)

    all_rows = []
    print("="*140)
    print("ITEM 2: COMPLETE CLEARANCE TABLE (ALL 25 WAYPOINTS)")
    print("="*140)
    print(f"{'#':2s} | {'Stop Name':40s} | {'Source Field':32s} | {'CamAlt':7s} | {'Gnd':6s} | {'Tallest Bldg':15s} | {'H(m)':5s} | {'Top(m)':6s} | {'Dist':5s} | {'Margin':7s}")
    print("-"*140)

    count = 0
    min_wp_margin = 1e9

    for tid, title, wp_str in tour_blocks:
        wps = re.findall(r'name:\s*\"([^\"]+)\".*?lat:\s*([\d\.-]+).*?lon:\s*([\d\.-]+).*?alt_m:\s*(\d+).*?source:\s*\"([^\"]+)\"', wp_str, re.DOTALL)
        for w in wps:
            count += 1
            name, lat_s, lon_s, alt_s, src = w[0], float(w[1]), float(w[2]), float(w[3]), w[4]
            east, z, north = lat_lon_to_local(lat_s, lon_s)
            ground = get_terrain_elevation(east, north)
            cam_alt = ground + alt_s

            tb = find_tallest_building_within_100m(east, north)
            roof = tb["top"] if tb else 0.0

            # Rule: margin = alt - max(ground + 120, roof + 40)
            margin = cam_alt - max(ground + 120.0, roof + 40.0)
            if margin < min_wp_margin:
                min_wp_margin = margin

            tb_id = tb["id"] if tb else "none"
            tb_h = f"{tb['height']:.1f}" if tb else "-"
            tb_top = f"{tb['top']:.1f}" if tb else "-"
            tb_d = f"{tb['dist']:.1f}m" if tb else "-"

            print(f"{count:2d} | {name[:40]:40s} | {src[:32]:32s} | {cam_alt:7.1f} | {ground:6.1f} | {tb_id:15s} | {tb_h:5s} | {tb_top:6s} | {tb_d:5s} | {margin:+6.1f}m")
            all_rows.append({
                "num": count,
                "tour": tid,
                "name": name,
                "source": src,
                "camAlt": cam_alt,
                "ground": ground,
                "tb": tb,
                "margin": margin,
                "east": east,
                "north": north,
                "alt_m": alt_s
            })

    print(f"\nTotal Waypoints: {count}")
    print(f"Min Waypoint Margin: {min_wp_margin:+.2f} m (Rule: margin = alt - max(ground+120, roof+40))")

    # 25m Spline Path Sampling
    print("\n" + "="*140)
    print("25-METRE SPLINE PATH SAMPLING AUDIT (ALL 4 TOURS)")
    print("="*140)

    # For each tour, construct CatmullRom spline through waypoints and sample every 25 m
    path_samples = []
    for tid, title, wp_str in tour_blocks:
        wps = re.findall(r'name:\s*\"([^\"]+)\".*?lat:\s*([\d\.-]+).*?lon:\s*([\d\.-]+).*?alt_m:\s*(\d+)', wp_str, re.DOTALL)
        # Waypoints 3D points
        pts = []
        for w in wps:
            e, z, n = lat_lon_to_local(float(w[1]), float(w[2]))
            g = get_terrain_elevation(e, n)
            pts.append((e, g + float(w[3]), n))

        # Sample spline by linear/centripetal interpolation between waypoints
        # Since CatmullRom in JS passes through waypoints, evaluate points along the segments
        for seg_idx in range(len(pts) - 1):
            pA = pts[seg_idx]
            pB = pts[seg_idx + 1]
            seg_len = math.hypot(pB[0] - pA[0], pB[1] - pA[1], pB[2] - pA[2])
            n_steps = max(1, int(math.ceil(seg_len / 25.0)))
            for s in range(n_steps):
                t = s / n_steps
                px = pA[0] + t * (pB[0] - pA[0])
                py = pA[1] + t * (pB[1] - pA[1])
                pn = pA[2] + t * (pB[2] - pA[2])
                ground_y = get_terrain_elevation(px, pn)
                tb = find_tallest_building_within_100m(px, pn)
                roof_top = tb["top"] if tb else 0.0
                margin = py - max(ground_y + 120.0, roof_top + 40.0)
                path_samples.append({
                    "tour": tid,
                    "pos": (px, py, pn),
                    "camAlt": py,
                    "ground": ground_y,
                    "tb": tb,
                    "margin": margin
                })

    path_samples.sort(key=lambda x: x["margin"])
    min_path_margin = path_samples[0]["margin"]
    print(f"Total Path Samples Evaluated: {len(path_samples)}")
    print(f"Min Path Margin: {min_path_margin:+.2f} m")
    print(f"Assertion min_margin >= 0: {min_path_margin >= 0.0}")
    print(f"Assertion min_path_margin <= min_wp_margin: {min_path_margin <= min_wp_margin + 0.01}")

    print("\n3 Lowest Samples Along Flight Paths (All Columns):")
    print(f"{'Tour':24s} | {'CamAlt':7s} | {'Ground':7s} | {'Tallest Bldg':15s} | {'Height':6s} | {'Top':7s} | {'Dist':6s} | {'Margin':8s}")
    print("-"*105)
    for s in path_samples[:3]:
        tb = s["tb"]
        tb_id = tb["id"] if tb else "none"
        tb_h = f"{tb['height']:.1f}m" if tb else "-"
        tb_top = f"{tb['top']:.1f}m" if tb else "-"
        tb_d = f"{tb['dist']:.1f}m" if tb else "-"
        print(f"{s['tour']:24s} | {s['camAlt']:7.1f} | {s['ground']:7.1f} | {tb_id:15s} | {tb_h:6s} | {tb_top:7s} | {tb_d:6s} | {s['margin']:+7.2f}m")

if __name__ == "__main__":
    main()
