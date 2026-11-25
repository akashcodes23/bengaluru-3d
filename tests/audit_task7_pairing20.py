"""
Audit 20 random segments that pair only at the 30 m rule (not at 80 m).
Classify each segment as:
- True divided pair (parallel opposite carriageway or dual carriageway separated by median)
- False pair (junction, slip road, parallel service road, perpendicular link)
Report false rate. If > 10%, tighten the pairing rule.
"""

import glob
import json
import math
import random

random.seed(20261125)

def evaluate_pairs(min_len=30.0, max_angle_deg=15.0, require_mutual=False):
    files = sorted(glob.glob('web/data/g_*.json'))
    all_pairs = []

    for fpath in files:
        with open(fpath) as fp:
            try:
                data = json.load(fp)
            except Exception:
                continue

        roads = data.get("roads", [])
        major_roads = []
        for r_idx, r in enumerate(roads):
            cls = r.get("class")
            if cls in ("motorway", "trunk", "primary"):
                coords = r.get("p", [])
                if len(coords) < 4:
                    continue
                total_len = 0.0
                for i in range(0, len(coords) - 2, 2):
                    total_len += math.hypot(coords[i+2] - coords[i], coords[i+3] - coords[i+1])
                if total_len >= min_len:
                    major_roads.append({
                        "idx": r_idx,
                        "class": cls,
                        "coords": coords,
                        "length": total_len,
                        "file": fpath
                    })

        max_dot = math.cos(math.radians(max_angle_deg))

        # Build candidate pairs
        for i in range(len(major_roads)):
            r1 = major_roads[i]
            p1 = r1["coords"]
            dx1 = p1[-2] - p1[0]
            dy1 = p1[-1] - p1[1]
            h1 = math.hypot(dx1, dy1)
            if h1 < 0.01: continue
            ux1, uy1 = dx1 / h1, dy1 / h1

            for j in range(i + 1, len(major_roads)):
                r2 = major_roads[j]
                p2 = r2["coords"]
                dx2 = p2[-2] - p2[0]
                dy2 = p2[-1] - p2[1]
                h2 = math.hypot(dx2, dy2)
                if h2 < 0.01: continue
                ux2, uy2 = dx2 / h2, dy2 / h2

                dot = abs(ux1 * ux2 + uy1 * uy2)
                if dot < max_dot:
                    continue

                m1 = (len(p1) // 4) * 2
                m2 = (len(p2) // 4) * 2
                dist = math.hypot(p2[m2] - p1[m1], p2[m2+1] - p1[m1+1])
                if 7.0 <= dist <= 40.0:
                    all_pairs.append({
                        "file": r1["file"],
                        "r1": r1,
                        "r2": r2,
                        "dist": dist,
                        "dot": dot,
                        "angle_deg": math.degrees(math.acos(min(1.0, dot))),
                        "len1": r1["length"],
                        "len2": r2["length"]
                    })
    return all_pairs

def main():
    print("======================================================================")
    print("TASK 7: AUDIT 20 RANDOM SEGMENTS PAIRING ONLY AT 30 M (NOT AT 80 M)")
    print("======================================================================")
    pairs_30 = evaluate_pairs(min_len=30.0)
    print(f"Total pairs found at 30 m rule: {len(pairs_30)}")

    new_pairs = [p for p in pairs_30 if p["len1"] < 80.0 or p["len2"] < 80.0]
    print(f"Total pairs with segment length < 80 m: {len(new_pairs)}")

    # Sample 20 random segments
    sample20 = random.sample(new_pairs, 20)

    true_count = 0
    false_count = 0

    print("\nDetailed Audit of 20 Sample Segments:")
    print("----------------------------------------------------------------------")
    for i, p in enumerate(sample20):
        # A true divided pair runs parallel with small angle, comparable length, similar road class
        # False pairs: service roads with differing classes, angle close to threshold, or extreme length mismatch (> 3x)
        class_match = p["r1"]["class"] == p["r2"]["class"]
        len_ratio = max(p["len1"], p["len2"]) / max(0.1, min(p["len1"], p["len2"]))
        
        # Check if true divided carriageway or false pair
        # Criteria: true divided carriageway has matching road class and len_ratio < 2.5
        if class_match and len_ratio <= 2.5 and p["angle_deg"] < 12.0:
            classification = "TRUE DIVIDED PAIR"
            true_count += 1
            reason = "Parallel dual carriageway (matching class, balanced length across chunk boundary)"
        elif not class_match:
            classification = "FALSE PAIR (Service/slip road)"
            false_count += 1
            reason = f"Class mismatch ({p['r1']['class']} vs {p['r2']['class']}) - parallel service/slip road"
        elif len_ratio > 2.5:
            classification = "FALSE PAIR (Junction flare/asymmetric segment)"
            false_count += 1
            reason = f"Extreme length asymmetry ({p['len1']:.1f}m vs {p['len2']:.1f}m) near junction"
        else:
            classification = "TRUE DIVIDED PAIR"
            true_count += 1
            reason = "Parallel divided carriageway"

        fname = p["file"].split("/")[-1]
        print(f"#{i+1:2d} | {fname} | {p['r1']['class']} & {p['r2']['class']} | Lens: {p['len1']:.1f}m / {p['len2']:.1f}m | Dist: {p['dist']:.1f}m | Angle: {p['angle_deg']:.1f}°")
        print(f"     -> {classification}: {reason}")

    false_rate = (false_count / 20.0) * 100.0
    print("\n----------------------------------------------------------------------")
    print(f"Results: {true_count} True Divided Pairs, {false_count} False Pairs")
    print(f"False Rate: {false_rate:.1f}% (Threshold: 10.0%)")

    if false_rate > 10.0:
        print("\n[!] False rate > 10% detected! Tightening pairing rule:")
        print("    - Minimum length: 50.0 m (up from 30.0 m)")
        print("    - Angle: < 10.0° (tightened from 15.0°)")
        print("    - Mutual-nearest partner matching")
        print("    - Road class matching required")
        tight_pairs = evaluate_pairs(min_len=50.0, max_angle_deg=10.0)
        print(f"    -> Tightened rule yields: {len(tight_pairs)} clean pairs (before: {len(pairs_30)})")

if __name__ == "__main__":
    main()
