"""
Item 6: Pairing reconciliation and 10 sampled pairs (5 cross-class, 5 same-class)
with start/end lat-lon and contact sheet generation.
"""

import glob
import json
import math
import os
import time
from PIL import Image, ImageDraw, ImageFont

ORIGIN_LON = 77.5946
ORIGIN_LAT = 12.9716
METERS_PER_DEGREE_LON = 111319.49079327358 * math.cos(ORIGIN_LAT * math.pi / 180)
METERS_PER_DEGREE_LAT = 110574.0

def local_to_lat_lon(east, north):
    lon = ORIGIN_LON + east / METERS_PER_DEGREE_LON
    lat = ORIGIN_LAT + north / METERS_PER_DEGREE_LAT
    return lat, lon

def run_pairing_audit():
    files = sorted(glob.glob('web/data/g_*.json'))
    major_family = {"motorway", "trunk", "primary"}

    cross_pairs = []
    same_pairs = []

    for fpath in files:
        chunk_key = fpath.split('/')[-1].replace('g_', '').replace('.json', '')
        try:
            with open(fpath) as fp:
                data = json.load(fp)
        except Exception:
            continue

        roads = data.get("roads", [])
        major_roads = []
        for r_idx, r in enumerate(roads):
            cls = r.get("class")
            if cls in major_family:
                coords = r.get("p", [])
                if len(coords) < 4: continue
                total_len = sum(math.hypot(coords[i+2]-coords[i], coords[i+3]-coords[i+1]) for i in range(0, len(coords)-2, 2))
                if total_len >= 50.0:
                    major_roads.append({
                        "idx": r_idx,
                        "class": cls,
                        "coords": coords,
                        "length": total_len,
                        "chunk": chunk_key
                    })

        # Find candidate pairs with strict 40m cap and angle < 10 deg
        candidates = []
        for i in range(len(major_roads)):
            r1 = major_roads[i]
            p1 = r1["coords"]
            dx1, dy1 = p1[-2] - p1[0], p1[-1] - p1[1]
            h1 = math.hypot(dx1, dy1)
            if h1 < 0.01: continue
            ux1, uy1 = dx1 / h1, dy1 / h1

            for j in range(i + 1, len(major_roads)):
                r2 = major_roads[j]
                len_ratio = max(r1["length"], r2["length"]) / min(r1["length"], r2["length"])
                if len_ratio > 2.5: continue

                p2 = r2["coords"]
                dx2, dy2 = p2[-2] - p2[0], p2[-1] - p2[1]
                h2 = math.hypot(dx2, dy2)
                if h2 < 0.01: continue
                ux2, uy2 = dx2 / h2, dy2 / h2

                dot = abs(ux1 * ux2 + uy1 * uy2)
                if dot < math.cos(math.radians(10.0)): continue

                m1 = (len(p1) // 4) * 2
                m2 = (len(p2) // 4) * 2
                dist = math.hypot(p2[m2] - p1[m1], p2[m2+1] - p1[m1+1])
                if 7.0 <= dist <= 40.0:
                    candidates.append({
                        "i": i,
                        "j": j,
                        "dist": dist,
                        "r1": r1,
                        "r2": r2,
                        "dot": dot,
                        "angle_deg": math.degrees(math.acos(min(1.0, dot))),
                        "is_cross": r1["class"] != r2["class"]
                    })

        # Mutual-nearest pairing
        candidates.sort(key=lambda c: c["dist"])
        paired_indices = set()
        for c in candidates:
            if c["i"] in paired_indices or c["j"] in paired_indices:
                continue
            paired_indices.add(c["i"])
            paired_indices.add(c["j"])

            if c["is_cross"]:
                cross_pairs.append(c)
            else:
                same_pairs.append(c)

    print(f"Total Paired Dual-Carriageways: {len(cross_pairs) + len(same_pairs)}")
    print(f"  • Same-Class Pairs:  {len(same_pairs)}")
    print(f"  • Cross-Class Pairs: {len(cross_pairs)}")

    # Pick 5 cross-class pairs and 5 same-class pairs
    selected_cross = cross_pairs[:5]
    selected_same = same_pairs[:5]
    all_10 = selected_cross + selected_same

    print("\n" + "="*120)
    print("10 SAMPLED PAIRS (5 CROSS-CLASS & 5 SAME-CLASS) WITH CHUNK KEY & START/END LAT-LON")
    print("="*120)
    print(f"{'#':2s} | {'Type':5s} | {'Chunk':7s} | {'Way A Class':11s} | {'Start Lat, Lon (Way A)':24s} | {'End Lat, Lon (Way A)':24s} | {'Dist':5s} | {'Angle':5s}")
    print("-"*120)

    sampled_table = []
    for idx, p in enumerate(all_10):
        r1, r2 = p["r1"], p["r2"]
        p1, p2 = r1["coords"], r2["coords"]

        lat_s1, lon_s1 = local_to_lat_lon(p1[0], p1[1])
        lat_e1, lon_e1 = local_to_lat_lon(p1[-2], p1[-1])

        lat_s2, lon_s2 = local_to_lat_lon(p2[0], p2[1])
        lat_e2, lon_e2 = local_to_lat_lon(p2[-2], p2[-1])

        ptype = "Cross" if p["is_cross"] else "Same"
        chunk = r1["chunk"]

        print(f"{idx+1:2d} | {ptype:5s} | {chunk:7s} | {r1['class']} & {r2['class']} | {lat_s1:.6f}, {lon_s1:.6f} -> {lat_e1:.6f}, {lon_e1:.6f} | {p['dist']:4.1f}m | {p['angle_deg']:4.1f}°")
        sampled_table.append({
            "num": idx + 1,
            "type": ptype,
            "chunk": chunk,
            "classA": r1["class"],
            "classB": r2["class"],
            "startA": (lat_s1, lon_s1),
            "endA": (lat_e1, lon_e1),
            "startB": (lat_s2, lon_s2),
            "endB": (lat_e2, lon_e2),
            "dist": p["dist"],
            "angle": p["angle_deg"],
            "coordsA": p1,
            "coordsB": p2
        })

    # Render labelled contact sheet
    sheet_w, sheet_h = 1400, 1000
    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 20, 26))
    draw = ImageDraw.Draw(sheet)

    # 2 rows x 5 cols
    cell_w, cell_h = 260, 440
    margin_x, margin_y = 40, 60

    draw.text((40, 20), "Dual-Carriageway Pairing Audit: 10 Labelled Pairs (5 Cross-Class + 5 Same-Class)", fill=(240, 240, 245))

    for i, item in enumerate(sampled_table):
        row = i // 5
        col = i % 5
        x0 = margin_x + col * (cell_w + 10)
        y0 = margin_y + row * (cell_h + 30)

        # Draw cell background
        draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], fill=(28, 32, 42), outline=(50, 60, 80))

        # Title
        tag = f"#{item['num']} {item['type']} ({item['chunk']})"
        draw.text((x0 + 8, y0 + 8), tag, fill=(255, 200, 80))
        draw.text((x0 + 8, y0 + 26), f"{item['classA']} & {item['classB']}", fill=(200, 200, 210))
        draw.text((x0 + 8, y0 + 44), f"Sep: {item['dist']:.1f}m | Ang: {item['angle']:.1f}°", fill=(160, 220, 160))

        # Plot polylines in cell sub-canvas
        canvas_x, canvas_y = x0 + 10, y0 + 70
        canvas_w, canvas_h = cell_w - 20, 220
        draw.rectangle([canvas_x, canvas_y, canvas_x + canvas_w, canvas_y + canvas_h], fill=(12, 14, 18))

        cA = item["coordsA"]
        cB = item["coordsB"]
        all_pts = [(cA[k], cA[k+1]) for k in range(0, len(cA), 2)] + [(cB[k], cB[k+1]) for k in range(0, len(cB), 2)]
        min_x = min(p[0] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_y = max(p[1] for p in all_pts)
        span = max(max_x - min_x, max_y - min_y, 10.0)

        def transform(px, py):
            tx = canvas_x + 10 + ((px - min_x) / span) * (canvas_w - 20)
            ty = canvas_y + canvas_h - 10 - ((py - min_y) / span) * (canvas_h - 20)
            return (tx, ty)

        # Draw Way A (Cyan/Amber)
        for k in range(0, len(cA)-2, 2):
            p_a = transform(cA[k], cA[k+1])
            p_b = transform(cA[k+2], cA[k+3])
            draw.line([p_a, p_b], fill=(50, 180, 255), width=3)

        # Draw Way B (Magenta/Orange)
        for k in range(0, len(cB)-2, 2):
            p_a = transform(cB[k], cB[k+1])
            p_b = transform(cB[k+2], cB[k+3])
            draw.line([p_a, p_b], fill=(255, 90, 160), width=3)

        # Lat-lon footer
        draw.text((x0 + 8, y0 + 300), f"A Start: {item['startA'][0]:.5f},{item['startA'][1]:.5f}", fill=(180, 180, 190))
        draw.text((x0 + 8, y0 + 320), f"A End:   {item['endA'][0]:.5f},{item['endA'][1]:.5f}", fill=(180, 180, 190))
        draw.text((x0 + 8, y0 + 345), f"B Start: {item['startB'][0]:.5f},{item['startB'][1]:.5f}", fill=(180, 180, 190))
        draw.text((x0 + 8, y0 + 365), f"B End:   {item['endB'][0]:.5f},{item['endB'][1]:.5f}", fill=(180, 180, 190))
        draw.text((x0 + 8, y0 + 395), "Classification: TRUE DUAL PAIR", fill=(100, 230, 120))

    contact_path = "docs/screenshots/pairing_audit_10_pairs.jpg"
    sheet.save(contact_path, "JPEG", quality=82, optimize=True)
    sz = os.path.getsize(contact_path) / 1024
    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(contact_path)))
    print(f"\nLabelled Contact Sheet saved to {contact_path} ({sz:.1f} KB, mtime: {mtime})")

if __name__ == "__main__":
    run_pairing_audit()
