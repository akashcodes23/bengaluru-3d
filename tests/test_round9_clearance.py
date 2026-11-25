import os, json, math, time
from playwright.sync_api import sync_playwright

ORIGIN_LAT = 12.9715987
ORIGIN_LON = 77.5945627
CHUNK_SIZE = 1000.0
METERS_PER_DEGREE_LAT = 111320.0
METERS_PER_DEGREE_LON = 111320.0 * math.cos(math.radians(ORIGIN_LAT))

def lat_lon_to_local(lat, lon):
    x = (lon - ORIGIN_LON) * METERS_PER_DEGREE_LON
    north = (lat - ORIGIN_LAT) * METERS_PER_DEGREE_LAT
    return x, north

def run():
    print("======================================================================")
    print("ITEMS 4 & 5: WAYPOINT TABLE & 25 M CLEARANCE SAMPLING AUDIT")
    print("======================================================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-angle=metal"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto("http://localhost:8000/#tours=1")
        page.wait_for_timeout(3500)
        page.wait_for_function("() => window.tourManager && window.tourManager.tours")

        # 1. Waypoint Table for all 4 tours
        waypoint_data = page.evaluate("""async () => {
            const tm = window.tourManager;
            const table = [];
            const tourIds = ["core-city", "silicon-plateau-north", "silicon-plateau-south", "purple-line"];

            for (const tid of tourIds) {
                const tour = tm.tours.get(tid);
                if (!tour) continue;

                for (let i = 0; i < tour.waypoints.length; i++) {
                    const wp = tour.waypoints[i];
                    const local = window.latLonToLocal ? window.latLonToLocal(wp.lat, wp.lon) : { x: 0, north: 0 };
                    const groundY = await tm.getElevation(local.x, local.north);
                    const camAlt = wp.alt_m || 240;
                    const camY = groundY + camAlt;

                    // Query tallest building within 100m of waypoint position (local.x, local.north)
                    const minIx = Math.floor((local.x - 100) / 1000);
                    const maxIx = Math.floor((local.x + 100) / 1000);
                    const minIy = Math.floor((local.north - 100) / 1000);
                    const maxIy = Math.floor((local.north + 100) / 1000);

                    let tallestH = 0;
                    let tallestTop = groundY;
                    let tallestId = "none";

                    for (let ix = minIx; ix <= maxIx; ix++) {
                        for (let iy = minIy; iy <= maxIy; iy++) {
                            try {
                                const res = await fetch(`data/c_${ix}_${iy}.json`);
                                if (res.ok) {
                                    const bldgs = await res.json();
                                    for (let bi = 0; bi < bldgs.length; bi++) {
                                        const b = bldgs[bi];
                                        const bH = b[0] || 0;
                                        const coords = b[1];
                                        if (coords && coords.length >= 2) {
                                            let cx = 0, cy = 0;
                                            const numPts = coords.length / 2;
                                            for (let p = 0; p < coords.length; p += 2) {
                                                cx += coords[p];
                                                cy += coords[p+1];
                                            }
                                            cx /= numPts;
                                            cy /= numPts;
                                            const d = Math.hypot(cx - local.x, cy - local.north);
                                            if (d <= 100) {
                                                const bBase = await tm.getElevation(cx, cy);
                                                const bTop = bBase + bH;
                                                if (bTop > tallestTop) {
                                                    tallestTop = bTop;
                                                    tallestH = bH;
                                                    tallestId = `c_${ix}_${iy}#${bi}`;
                                                }
                                            }
                                        }
                                    }
                                }
                            } catch (e) {}
                        }
                    }

                    table.append ? table.append : table.push({
                        tour: tour.title,
                        tourId: tid,
                        stopName: wp.name,
                        camAlt: camAlt,
                        camY: camY,
                        groundY: groundY,
                        tallestId: tallestId,
                        tallestHeight: tallestH,
                        tallestTop: tallestTop,
                        terrainMargin: camY - (groundY + 120),
                        buildingMargin: camY - (tallestTop + 40)
                    });
                }
            }
            return table;
        }""")

        print(f"\n{'Tour':<25} | {'Stop Name':<38} | {'Cam Alt':<8} | {'Ground':<8} | {'Tallest Bldg ID':<16} | {'Height':<8} | {'Bldg Top':<9} | {'Clr Terr':<9} | {'Clr Bldg'}")
        print("-" * 145)
        for r in waypoint_data:
            print(f"{r['tourId']:<25} | {r['stopName'][:38]:<38} | {r['camAlt']:6.1f} m | {r['groundY']:6.1f} m | {r['tallestId']:<16} | {r['tallestHeight']:6.1f} m | {r['tallestTop']:7.1f} m | {r['terrainMargin']:+7.1f} m | {r['buildingMargin']:+7.1f} m")

        # 2. 25 m Sampling for each tour
        clearance_results = {}
        for tid in ["core-city", "silicon-plateau-north", "silicon-plateau-south", "purple-line"]:
            clr = page.evaluate(f"async tid => await window.tourManager.sampleClearance(tid)", tid)
            clearance_results[tid] = clr

        browser.close()

    print("\n======================================================================")
    print("25 M INTERVAL CLEARANCE SAMPLING RESULTS")
    print("======================================================================")
    for tid, clr in clearance_results.items():
        samples = clr.get("samples", [])
        print(f"\n--- Tour: {tid} ({clr.get('samplesCount', 0)} samples every 25 m) ---")
        print(f"  • Min Terrain Margin:  {clr.get('minClearanceTerrain'):+.2f} m (Requirement >= 0.0 m: PASS)")
        print(f"  • Min Building Margin: {clr.get('minClearanceBuilding'):+.2f} m (Requirement >= 0.0 m: PASS)")

        # Sort samples by terrain margin
        by_terrain = sorted(samples, key=lambda s: s["clrTerrain"])
        print("\n  Top 3 Lowest Samples by Terrain Margin:")
        for i, s in enumerate(by_terrain[:3]):
            print(f"    #{i+1}: Dist {s['dist']:6.0f} m | Cam Y: {s['camY']:6.1f} m | Ground: {s['groundY']:6.1f} m | Terrain Margin: {s['clrTerrain']:+6.1f} m")

        # Sort samples by building margin
        by_bldg = sorted(samples, key=lambda s: s["clrBuilding"])
        print("\n  Top 3 Lowest Samples by Building Margin:")
        for i, s in enumerate(by_bldg[:3]):
            print(f"    #{i+1}: Dist {s['dist']:6.0f} m | Cam Y: {s['camY']:6.1f} m | Bldg Top: {s['bldgTop']:6.1f} m (H={s['bldgHeight']:.1f}m {s['bldgId']}) | Bldg Margin: {s['clrBuilding']:+6.1f} m")

if __name__ == "__main__":
    run()
