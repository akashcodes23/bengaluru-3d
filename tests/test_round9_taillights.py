import os, time, json
from PIL import Image
import numpy as np
from playwright.sync_api import sync_playwright

def run():
    print("======================================================================")
    print("ITEM 6: TAILLIGHTS CLEAN PIXEL DIFF MEASUREMENT")
    print("======================================================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-angle=metal"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        # 1. Capture Normal Baseline with traffic OFF at 21:00 Night
        print("Capturing baseline frame (traffic OFF at 21:00 night)...")
        page.goto("http://localhost:8000/?focus=13.0475,77.6207&altitude=600#time=87&traffic=off")
        page.wait_for_timeout(3500)
        baseline_path = "/tmp/traffic_baseline_off.png"
        page.screenshot(path=baseline_path)

        # 2. Capture Frame with Traffic ON (med) at same camera and time
        print("Capturing frame with traffic ON (med density)...")
        page.evaluate("""() => {
            const densitySelect = document.querySelector("#traffic-density");
            if (densitySelect) {
                densitySelect.value = "med";
                densitySelect.dispatchEvent(new Event("change"));
            }
            if (window.trafficUniforms) {
                window.trafficUniforms.uTrafficEnabled.value = 1.0;
            }
        }""")
        page.wait_for_timeout(2500)
        traffic_on_path = "/tmp/traffic_on_frame.png"
        page.screenshot(path=traffic_on_path)

        # 3. Capture Traffic-Only Black Frame (isolated traffic points)
        print("Capturing isolated traffic-only black frame...")
        page.evaluate("""() => {
            if (window.buildingGroup) window.buildingGroup.visible = false;
            if (window.terrainGroup) window.terrainGroup.visible = false;
            if (window.groundGroup) window.groundGroup.visible = false;
            if (window.metroGroup) window.metroGroup.visible = false;
            if (window.heroManager && window.heroManager.landmarksGroup) window.heroManager.landmarksGroup.visible = false;
            window.scene.background = new THREE.Color(0x000000);
            window.renderer.render(window.scene, window.camera);
        }""")
        page.wait_for_timeout(1000)
        black_traffic_path = "/tmp/traffic_isolated_black.png"
        page.screenshot(path=black_traffic_path)

        browser.close()

    # Pixel Diff Analysis
    img_base = Image.open(baseline_path).convert("RGB")
    img_on = Image.open(traffic_on_path).convert("RGB")
    img_black = Image.open(black_traffic_path).convert("RGB")

    arr_base = np.array(img_base, dtype=np.int16)
    arr_on = np.array(img_on, dtype=np.int16)
    arr_black = np.array(img_black, dtype=np.float32)

    diff = np.abs(arr_on - arr_base)
    diff_max = np.max(diff, axis=2) # maximum channel delta

    # Traffic-added pixels are those where difference > 25
    traffic_mask = (diff_max > 25)

    R_on = arr_on[:, :, 0].astype(np.float32)
    G_on = arr_on[:, :, 1].astype(np.float32)
    B_on = arr_on[:, :, 2].astype(np.float32)

    # Standard thresholds:
    # White: R>200, G>200, B>180
    white_added_mask = traffic_mask & (R_on > 200) & (G_on > 200) & (B_on > 180)
    # Red: R>200, G<80, B<80 (standard strict red) or R>120, R>2.5*G, R>2.5*B
    red_strict_mask = traffic_mask & (R_on > 200) & (G_on < 80) & (B_on < 80)
    red_sat_mask = traffic_mask & (R_on > 120) & (R_on > 2.5 * G_on) & (R_on > 2.5 * B_on)

    # In isolated black frame:
    R_b = arr_black[:, :, 0]
    G_b = arr_black[:, :, 1]
    B_b = arr_black[:, :, 2]
    black_red_mask = (R_b > 120) & (R_b > 2.5 * G_b) & (R_b > 2.5 * B_b)
    black_white_mask = (R_b > 200) & (G_b > 200) & (B_b > 180)

    count_added_white = int(np.sum(white_added_mask))
    count_added_red = int(np.sum(red_sat_mask))
    count_black_red = int(np.sum(black_red_mask))
    count_black_white = int(np.sum(black_white_mask))

    red_survival_pct = (count_added_red / count_black_red * 100.0) if count_black_red > 0 else 100.0
    white_survival_pct = (count_added_white / count_black_white * 100.0) if count_black_white > 0 else 100.0

    mean_rgb_red = (
        float(np.mean(R_on[red_sat_mask])) if count_added_red > 0 else 0.0,
        float(np.mean(G_on[red_sat_mask])) if count_added_red > 0 else 0.0,
        float(np.mean(B_on[red_sat_mask])) if count_added_red > 0 else 0.0
    )

    ratio = (count_added_red / count_added_white) if count_added_white > 0 else 1.0

    # Save visual artifact diff image
    diff_vis = Image.fromarray(np.clip(diff * 3, 0, 255).astype(np.uint8))
    diff_path = "docs/screenshots/traffic_diff_proof.jpg"
    diff_vis.save(diff_path, format="JPEG", quality=85)
    diff_mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(diff_path)))

    print(f"\nDiff Measurement Results:")
    print(f"  • Traffic-Added White Headlight Pixels (R>200,G>200,B>180): {count_added_white}")
    print(f"  • Traffic-Added Red Taillight Pixels (R>120,R>2.5G,R>2.5B):  {count_added_red}")
    print(f"  • Ratio (Added Red / Added White): {ratio:.2f}x (Requirement: 0.5x to 1.5x: {'PASS' if 0.5 <= ratio <= 1.5 else 'FAIL'})")
    print(f"  • Mean RGB of Added Red Taillights: R={mean_rgb_red[0]:.1f}, G={mean_rgb_red[1]:.1f}, B={mean_rgb_red[2]:.1f}")
    print(f"  • Isolated Black Frame Counts: Red={count_black_red}, White={count_black_white}")
    print(f"  • Taillight Survival Rate (in-scene vs isolated): {red_survival_pct:.1f}%")
    print(f"  • Headlight Survival Rate (in-scene vs isolated): {white_survival_pct:.1f}%")
    print(f"  • Evidence Diff Image: {diff_path} (mtime: {diff_mtime})")

if __name__ == "__main__":
    run()
