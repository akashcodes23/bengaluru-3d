import os, time, json
from PIL import Image
import numpy as np
from playwright.sync_api import sync_playwright

ARTIFACTS_DIR = "/Users/akashgpatil/.gemini/antigravity/brain/86fc38d5-d7fe-45d5-8c7f-3089d5a9f7c1"

def analyze_crop(img_path, crop_box=None):
    img = Image.open(img_path).convert("RGB")
    if crop_box:
        img = img.crop(crop_box)
    arr = np.array(img)
    R = arr[:, :, 0].astype(np.float32)
    G = arr[:, :, 1].astype(np.float32)
    B = arr[:, :, 2].astype(np.float32)

    # White: R>200, G>200, B>180
    white_mask = (R > 200) & (G > 200) & (B > 180)
    # Red: R>120, R>2.5*G, R>2.5*B
    red_mask = (R > 120) & (R > 2.5 * G) & (R > 2.5 * B)

    white_count = int(np.sum(white_mask))
    red_count = int(np.sum(red_mask))
    ratio = (red_count / white_count) if white_count > 0 else 0.0

    if red_count > 0:
        red_mean_rgb = (float(np.mean(R[red_mask])), float(np.mean(G[red_mask])), float(np.mean(B[red_mask])))
    else:
        red_mean_rgb = (0.0, 0.0, 0.0)

    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(img_path)))
    return {
        "path": img_path,
        "mtime": mtime,
        "white_count": white_count,
        "red_count": red_count,
        "ratio": ratio,
        "red_mean_rgb": red_mean_rgb
    }

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-angle=metal"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        
        # Load Manyata at 21:00 with traffic
        page.goto("http://localhost:8000/?focus=13.0475,77.6207&altitude=600#time=94&traffic=med&radius=4")
        page.wait_for_timeout(4000)

        # Wait until chunks loaded
        page.wait_for_function("() => window.loadedChunks && window.loadedChunks.size >= 10")
        page.wait_for_timeout(2000)

        # Ensure night time (21:00)
        page.evaluate("""() => {
            window.setTimeByClock(21, 0);
            const sel = document.querySelector('#traffic-density');
            if (sel) {
                sel.value = 'med';
                sel.dispatchEvent(new Event('change'));
            }
        }""")
        page.wait_for_timeout(1000)

        results = {}

        # 1. Amber Road - Normal view
        page.evaluate("() => window.setRoadTheme('amber')")
        page.wait_for_timeout(1000)
        amber_normal_path = os.path.join(ARTIFACTS_DIR, "taillights_amber_normal.png")
        page.screenshot(path=amber_normal_path)
        results["amber_normal"] = analyze_crop(amber_normal_path)

        # 2. Amber Road - Traffic-only black frame
        page.evaluate("""() => {
            window.terrainGroup.visible = false;
            window.buildingGroup.visible = false;
            window.groundGroup.visible = false;
            if (window.metroGroup) window.metroGroup.visible = false;
            window.forceBlackBackground = true;
            window.scene.background.set(0x000000);
        }""")
        page.wait_for_timeout(500)
        amber_traffic_only_path = os.path.join(ARTIFACTS_DIR, "taillights_amber_traffic_only.png")
        page.screenshot(path=amber_traffic_only_path)
        results["amber_traffic_only"] = analyze_crop(amber_traffic_only_path)

        # Restore visibility
        page.evaluate("""() => {
            window.terrainGroup.visible = true;
            window.buildingGroup.visible = true;
            window.groundGroup.visible = true;
            if (window.metroGroup) window.metroGroup.visible = true;
            window.forceBlackBackground = false;
        }""")

        # 3. Slate Road - Normal view
        page.evaluate("() => window.setRoadTheme('slate')")
        page.wait_for_timeout(1000)
        slate_normal_path = os.path.join(ARTIFACTS_DIR, "taillights_slate_normal.png")
        page.screenshot(path=slate_normal_path)
        results["slate_normal"] = analyze_crop(slate_normal_path)

        # 4. Slate Road - Traffic-only black frame
        page.evaluate("""() => {
            window.terrainGroup.visible = false;
            window.buildingGroup.visible = false;
            window.groundGroup.visible = false;
            if (window.metroGroup) window.metroGroup.visible = false;
            window.forceBlackBackground = true;
            window.scene.background.set(0x000000);
        }""")
        page.wait_for_timeout(500)
        slate_traffic_only_path = os.path.join(ARTIFACTS_DIR, "taillights_slate_traffic_only.png")
        page.screenshot(path=slate_traffic_only_path)
        results["slate_traffic_only"] = analyze_crop(slate_traffic_only_path)

        # Create Side-by-side comparison image
        im_amber = Image.open(amber_normal_path)
        im_slate = Image.open(slate_normal_path)
        w, h = im_amber.size
        side_by_side = Image.new("RGB", (w * 2, h))
        side_by_side.paste(im_amber, (0, 0))
        side_by_side.paste(im_slate, (w, 0))
        side_by_side_path = os.path.join(ARTIFACTS_DIR, "taillights_amber_vs_slate_comparison.png")
        side_by_side.save(side_by_side_path)

        browser.close()

    print("=== TAILLIGHT AUDIT RESULTS ===")
    for k, v in results.items():
        print(f"Condition: {k}")
        print(f"  File: {v['path']}")
        print(f"  mtime: {v['mtime']}")
        print(f"  White count: {v['white_count']}")
        print(f"  Red count: {v['red_count']}")
        print(f"  Ratio (red / white): {v['ratio']:.4f} ({v['ratio']*100:.2f}%)")
        print(f"  Red mean RGB: ({v['red_mean_rgb'][0]:.1f}, {v['red_mean_rgb'][1]:.1f}, {v['red_mean_rgb'][2]:.1f})")

    sbs_mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(side_by_side_path)))
    print(f"\nSide-by-side comparison: {side_by_side_path} (mtime: {sbs_mtime})")

if __name__ == "__main__":
    run()
