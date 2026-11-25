import argparse
import asyncio
import numpy as np
from playwright.async_api import async_playwright

async def measure_scenario(page, label, url, num_frames=300):
    await page.goto(url)
    # Wait for chunks, terrain, meshes, and traffic to settle
    await page.wait_for_timeout(5000)

    data = await page.evaluate('''async (numFrames) => {
        const r = window.renderer;
        const s = window.scene;
        const c = window.camera;
        const sun = window.sunLight;

        // Measure frame durations
        const deltas = [];
        let prev = await new Promise(requestAnimationFrame);
        for (let i = 0; i < numFrames; i++) {
            const cur = await new Promise(requestAnimationFrame);
            deltas.push(cur - prev);
            prev = cur;
        }

        const baseCalls = r.info.render.calls;
        const baseTris = r.info.render.triangles;
        const totalVehicles = window.getTotalTrafficVehicles ? window.getTotalTrafficVehicles() : 0;
        const badge = document.querySelector("#traffic-count-badge") ? document.querySelector("#traffic-count-badge").textContent : "";

        return {
            deltas,
            calls: baseCalls,
            triangles: baseTris,
            totalVehicles,
            badge
        };
    }''', num_frames)

    arr = np.array(data["deltas"])
    avg_ms = float(np.mean(arr))
    p95_ms = float(np.percentile(arr, 95))
    p50_ms = float(np.percentile(arr, 50))
    min_ms = float(np.min(arr))
    max_ms = float(np.max(arr))
    fps = 1000.0 / avg_ms if avg_ms > 0 else 0

    return {
        "label": label,
        "url": url,
        "avg_ms": avg_ms,
        "p95_ms": p95_ms,
        "p50_ms": p50_ms,
        "min_ms": min_ms,
        "max_ms": max_ms,
        "fps": fps,
        "calls": data["calls"],
        "triangles": data["triangles"],
        "vehicles": data["totalVehicles"],
        "badge": data["badge"],
    }

async def run_traffic_benchmark():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            args=[
                "--enable-webgl",
                "--ignore-gpu-blocklist",
                "--use-gl=angle",
                "--use-angle=metal",
                "--disable-frame-rate-limit",
                "--disable-gpu-vsync"
            ]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        scenarios = [
            ("Default view, Night (21:00), Traffic OFF", "http://localhost:8000/#time=94&radius=4&traffic=off"),
            ("Default view, Night (21:00), Traffic LOW", "http://localhost:8000/#time=94&radius=4&traffic=low"),
            ("Default view, Night (21:00), Traffic MEDIUM", "http://localhost:8000/#time=94&radius=4&traffic=med"),
            ("Major Junction (Silk Board 2km, Night), Traffic LOW", "http://localhost:8000/?focus=12.9176,77.6238&altitude=1200#radius=2&time=94&traffic=low"),
        ]

        results = []
        for label, url in scenarios:
            res = await measure_scenario(page, label, url)
            results.append(res)

        print("\n" + "=" * 110)
        print("PHASE 2 PERFORMANCE BENCHMARK (VSync Disabled)")
        print("=" * 110)
        header = f"{'Scenario':<42} | {'Avg (ms)':<9} | {'p95 (ms)':<9} | {'FPS':<6} | {'Draw Calls':<10} | {'Triangles':<11} | {'Instances':<10}"
        print(header)
        print("-" * 110)
        for r in results:
            print(f"{r['label']:<42} | {r['avg_ms']:>6.2f} ms | {r['p95_ms']:>6.2f} ms | {r['fps']:>5.0f} | {r['calls']:>10,} | {r['triangles']:>11,} | {r['vehicles']:>10,}")
        print("=" * 110)

        # Delta analysis
        off_time = results[0]["avg_ms"]
        low_time = results[1]["avg_ms"]
        med_time = results[2]["avg_ms"]
        delta_low_pct = ((low_time - off_time) / off_time) * 100
        delta_med_pct = ((med_time - off_time) / off_time) * 100
        print(f"\nDelta vs Traffic OFF:")
        print(f"  Traffic LOW:    {delta_low_pct:+.2f}% avg frame time ({low_time:.2f} ms vs {off_time:.2f} ms)")
        print(f"  Traffic MEDIUM: {delta_med_pct:+.2f}% avg frame time ({med_time:.2f} ms vs {off_time:.2f} ms)")
        if delta_med_pct > 15.0:
            print(f"  WARNING: Medium density exceeds 15% frame time budget ({delta_med_pct:.1f}% > 15%).")
        else:
            print(f"  PASS: Both Low and Medium traffic stay comfortably within the 15% performance budget.")

        await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bengaluru 3D Performance Benchmark")
    parser.add_argument("--mode", default="traffic", choices=["traffic", "solar"], help="Benchmark suite to run")
    args = parser.parse_args()
    if args.mode == "traffic":
        asyncio.run(run_traffic_benchmark())
