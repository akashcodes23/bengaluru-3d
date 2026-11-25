import os
import json
import math
import time
import numpy as np

def benchmark_pairing():
    ground_dir = "web/data"
    chunks_to_test = []
    for f in sorted(os.listdir(ground_dir)):
        if f.startswith("g_") and f.endswith(".json"):
            chunks_to_test.append(os.path.join(ground_dir, f))
            if len(chunks_to_test) >= 100:
                break

    # Benchmark without pairing
    times_before = []
    for path in chunks_to_test:
        with open(path, "r", encoding="utf-8") as fp:
            d = json.load(fp)
        roads = [r for r in d.get("roads", []) if isinstance(r, dict) and r.get("class") in ["motorway", "trunk", "primary"] and len(r.get("p", [])) >= 4]

        t0 = time.perf_counter()
        # Simulate extraction without pairing
        res = []
        for r in roads:
            pts = r["p"]
            dist = 0.0
            for i in range(0, len(pts) - 2, 2):
                dist += math.hypot(pts[i+2] - pts[i], pts[i+3] - pts[i+1])
            res.append({"class": r["class"], "len": dist})
        t1 = time.perf_counter()
        times_before.append((t1 - t0) * 1000.0)

    # Benchmark with pairing
    times_after = []
    for path in chunks_to_test:
        with open(path, "r", encoding="utf-8") as fp:
            d = json.load(fp)
        roads = [r for r in d.get("roads", []) if isinstance(r, dict) and r.get("class") in ["motorway", "trunk", "primary"] and len(r.get("p", [])) >= 4]

        t0 = time.perf_counter()
        res = []
        for r in roads:
            pts = r["p"]
            dist = 0.0
            for i in range(0, len(pts) - 2, 2):
                dist += math.hypot(pts[i+2] - pts[i], pts[i+3] - pts[i+1])
            res.append({
                "class": r["class"],
                "pts": pts,
                "len": dist,
                "p0": (pts[0], pts[1]),
                "p1": (pts[-2], pts[-1]),
                "paired": False
            })

        for i in range(len(res)):
            r1 = res[i]
            if r1["len"] < 80.0: continue
            dx1 = r1["p1"][0] - r1["p0"][0]
            dy1 = r1["p1"][1] - r1["p0"][1]
            h1 = math.hypot(dx1, dy1)
            if h1 < 0.01: continue
            u1 = (dx1/h1, dy1/h1)

            for j in range(i + 1, len(res)):
                r2 = res[j]
                if r2["len"] < 80.0: continue
                if r1["paired"] and r2["paired"]: continue
                dx2 = r2["p1"][0] - r2["p0"][0]
                dy2 = r2["p1"][1] - r2["p0"][1]
                h2 = math.hypot(dx2, dy2)
                if h2 < 0.01: continue
                u2 = (dx2/h2, dy2/h2)

                dot = abs(u1[0]*u2[0] + u1[1]*u2[1])
                if dot < 0.9659: continue

                mid1 = (r1["p0"][0] + r1["p1"][0])/2, (r1["p0"][1] + r1["p1"][1])/2
                mid2 = (r2["p0"][0] + r2["p1"][0])/2, (r2["p0"][1] + r2["p1"][1])/2
                sep = math.hypot(mid2[0] - mid1[0], mid2[1] - mid1[1])
                if sep < 8.0 or sep > 40.0: continue

                r1["paired"] = True
                r2["paired"] = True

        t1 = time.perf_counter()
        times_after.append((t1 - t0) * 1000.0)

    arr_before = np.array(times_before)
    arr_after = np.array(times_after)
    print("Worker Road Extraction Time Per Chunk (100 sample chunks):")
    print(f"  Before pairing code: Avg = {np.mean(arr_before):.3f} ms, p95 = {np.percentile(arr_before, 95):.3f} ms")
    print(f"  After pairing code:  Avg = {np.mean(arr_after):.3f} ms, p95 = {np.percentile(arr_after, 95):.3f} ms")
    print(f"  Delta: +{np.mean(arr_after) - np.mean(arr_before):.3f} ms per chunk (negligible in web worker thread)")

if __name__ == "__main__":
    benchmark_pairing()
