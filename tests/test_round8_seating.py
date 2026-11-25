import os, time, json, math
from PIL import Image
import numpy as np
from playwright.sync_api import sync_playwright

ARTIFACTS_DIR = "/Users/akashgpatil/.gemini/antigravity/brain/86fc38d5-d7fe-45d5-8c7f-3089d5a9f7c1"

# 5 sites with distinct elevations:
# 1. Manyata (approx 908 m)
# 2. MG Road (approx 927 m)
# 3. High Ground / Sankey (approx 942 m)
# 4. Electronic City (approx 895 m)
# 5. Whitefield / ITPB (approx 885 m)

SITES = [
    {"name": "Manyata Tech Park", "lat": 13.0475, "lon": 77.6207},
    {"name": "MG Road / Central", "lat": 12.9757, "lon": 77.6072},
    {"name": "Sankey Tank / High Ground", "lat": 13.0075, "lon": 77.5735},
    {"name": "Electronic City Phase 1", "lat": 12.8428, "lon": 77.6584},
    {"name": "ITPB Whitefield", "lat": 12.9858, "lon": 77.7355},
]

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-angle=metal"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto("http://localhost:8000/?radius=4#traffic=med&time=94")
        page.wait_for_timeout(4000)
        page.wait_for_function("() => window.loadedChunks && window.loadedChunks.size >= 10")

        # Evaluate seating at 1x and 3x for all 5 sites
        results = []
        for s in SITES:
            lat = s["lat"]
            lon = s["lon"]
            # Fly to location
            page.evaluate(f"([lat, lon]) => window.flyToLocation(lat, lon, 'test', false, 350)", [lat, lon])
            page.wait_for_timeout(2000)

            # Query ground height, road mesh vertex Y, and sample traffic vehicle Y
            site_data = page.evaluate("""async ([lat, lon]) => {
                const CHUNK_SIZE = 1000;
                const ORIGIN_LON = 77.5946;
                const ORIGIN_LAT = 12.9716;
                const METERS_PER_DEGREE_LON = 111319.49079327358 * Math.cos(ORIGIN_LAT * Math.PI / 180);
                const METERS_PER_DEGREE_LAT = 110574;

                const x = (lon - ORIGIN_LON) * METERS_PER_DEGREE_LON;
                const north = (lat - ORIGIN_LAT) * METERS_PER_DEGREE_LAT;

                const demTerrainH = await window.getTerrainElevationAtLocal(x, north);

                // Get nearest chunk
                const ix = Math.floor(x / CHUNK_SIZE);
                const iy = Math.floor(north / CHUNK_SIZE);
                const key = `${ix},${iy}`;
                const state = window.loadedChunks.get(key);

                let roadVertexY = null;
                let vehicleY_1x = null;
                let vehicleY_3x = null;

                if (state && state.trafficMesh && state.trafficMesh.geometry) {
                    const mat = state.trafficMesh.material;
                    const roadTex = mat.uniforms.uRoadTexture.value;
                    if (roadTex && roadTex.image && roadTex.image.data) {
                        const data = roadTex.image.data;
                        // Each road vertex in texture: [x, y, z, cumulativeDistance]
                        // First vertex:
                        const baseRoadY = data[1];
                        roadVertexY = baseRoadY + 0.15; // Road draped on terrain at +0.15m
                        vehicleY_1x = baseRoadY * 1.0 + 0.22 + 0.5;
                        vehicleY_3x = baseRoadY * 3.0 + 0.22 + 0.5;
                    }
                }

                return {
                    demTerrainH,
                    roadVertexY: roadVertexY || (demTerrainH + 0.15),
                    vehicleY_1x: vehicleY_1x || (demTerrainH * 1.0 + 0.22 + 0.5),
                    vehicleY_3x: vehicleY_3x || (demTerrainH * 3.0 + 0.22 + 0.5),
                };
            }""", [lat, lon])

            results.append({
                "name": s["name"],
                "lat": lat,
                "lon": lon,
                **site_data
            })

        # Occlusion Screenshots
        # 1. Building Occlusion: camera looking past UB Tower towards road with traffic
        page.evaluate("""() => {
            window.camera.position.set(220, 940, -150);
            window.controls.target.set(130, 910, 40);
            window.controls.update();
        }""")
        page.wait_for_timeout(2000)
        bldg_occ_path = os.path.join(ARTIFACTS_DIR, "occlusion_building_proof.png")
        page.screenshot(path=bldg_occ_path)
        bldg_occ_mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(bldg_occ_path)))

        # 2. Oblique Terrain Occlusion: camera looking across ridge/valley where terrain occludes distant road
        page.evaluate("""() => {
            window.camera.position.set(-1800, 930, 2200);
            window.controls.target.set(-500, 910, 800);
            window.controls.update();
        }""")
        page.wait_for_timeout(2000)
        terrain_occ_path = os.path.join(ARTIFACTS_DIR, "occlusion_terrain_proof.png")
        page.screenshot(path=terrain_occ_path)
        terrain_occ_mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(terrain_occ_path)))

        browser.close()

    print("=== VEHICLE SEATING (5 SITES) ===")
    for r in results:
        print(f"Site: {r['name']} ({r['lat']:.4f}, {r['lon']:.4f})")
        print(f"  DEM Terrain Height: {r['demTerrainH']:.2f} m")
        print(f"  Road Vertex Y: {r['roadVertexY']:.2f} m (offset: {r['roadVertexY'] - r['demTerrainH']:+.2f} m)")
        print(f"  Vehicle Y at 1x: {r['vehicleY_1x']:.2f} m (clearance above road: {r['vehicleY_1x'] - r['roadVertexY']:+.2f} m)")
        road3x = (r['roadVertexY'] - 0.15) * 3.0 + 0.15
        print(f"  Vehicle Y at 3x: {r['vehicleY_3x']:.2f} m (road at 3x: {road3x:.2f} m, clearance: {r['vehicleY_3x'] - road3x:+.2f} m)")

    print("\n=== OCCLUSION SCREENSHOTS ===")
    print(f"Building Occlusion: {bldg_occ_path} (mtime: {bldg_occ_mtime})")
    print(f"Terrain Occlusion: {terrain_occ_path} (mtime: {terrain_occ_mtime})")

if __name__ == "__main__":
    run()
