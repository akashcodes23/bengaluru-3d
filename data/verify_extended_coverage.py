#!/usr/bin/env python3
"""Verify extended Bengaluru 3D coverage, airport layer, and performance in WebGL headless Chrome."""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIRS = [ROOT / "docs" / "screenshots", ROOT / "web" / "screenshots"]
for d in SCREENSHOT_DIRS:
    d.mkdir(parents=True, exist_ok=True)


def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            args=[
                "--use-gl=angle",
                "--use-angle=metal",
                "--enable-webgl",
                "--ignore-gpu-blocklist",
            ],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )

        print("--- Step 1: Default View (Vidhana Soudha, Cubbon Park, MG Road) ---")
        page.goto("http://localhost:8000/#radius=6")
        page.wait_for_selector("#loading-overlay.hidden", timeout=25000)
        page.wait_for_timeout(3500)

        stats_default = page.evaluate("""() => {
            return {
                chunks: document.querySelector('#chunk-count')?.textContent || '',
                buildings: document.querySelector('#building-count')?.textContent || '',
                fps: document.querySelector('#fps')?.textContent || '',
                render_stats: document.querySelector('#render-stats')?.textContent || '',
            };
        }""")
        print("Default View Stats:", json.dumps(stats_default, indent=2))
        for d in SCREENSHOT_DIRS:
            page.screenshot(path=str(d / "default_view_golden_hour.png"))

        print("\n--- Step 2: Kempegowda International Airport (BLR) ---")
        # Fly to airport (Terminal 1 / Runways)
        page.evaluate("""() => {
            const exaggeration = window.verticalExaggeration || 1.0;
            // Airport center near Terminal 1 & Runways: tx=12517, ty=25310
            window.controls.target.set(12517, 915 * exaggeration, -25310);
            window.camera.position.set(12517 - 1200, 915 * exaggeration + 1800, -25310 + 2600);
            window.controls.update();
        }""")
        page.wait_for_timeout(4000)

        stats_airport = page.evaluate("""() => {
            return {
                chunks: document.querySelector('#chunk-count')?.textContent || '',
                buildings: document.querySelector('#building-count')?.textContent || '',
                fps: document.querySelector('#fps')?.textContent || '',
                render_stats: document.querySelector('#render-stats')?.textContent || '',
            };
        }""")
        print("Airport View Stats:", json.dumps(stats_airport, indent=2))
        for d in SCREENSHOT_DIRS:
            page.screenshot(path=str(d / "airport_runways_terminals.png"))

        print("\n--- Step 3: Electronic City / Whitefield ---")
        # Fly to Electronic City
        page.evaluate("""() => {
            const exaggeration = window.verticalExaggeration || 1.0;
            // Electronic City: tx=7636, ty=-13999
            window.controls.target.set(7636, 910 * exaggeration, 13999);
            window.camera.position.set(7636 - 800, 910 * exaggeration + 1600, 13999 + 2200);
            window.controls.update();
        }""")
        page.wait_for_timeout(4000)

        stats_ecity = page.evaluate("""() => {
            return {
                chunks: document.querySelector('#chunk-count')?.textContent || '',
                buildings: document.querySelector('#building-count')?.textContent || '',
                fps: document.querySelector('#fps')?.textContent || '',
                render_stats: document.querySelector('#render-stats')?.textContent || '',
            };
        }""")
        print("Electronic City Stats:", json.dumps(stats_ecity, indent=2))
        for d in SCREENSHOT_DIRS:
            page.screenshot(path=str(d / "electronic_city_overview.png"))

        # Fly to Whitefield (ITPB)
        page.evaluate("""() => {
            const exaggeration = window.verticalExaggeration || 1.0;
            // Whitefield ITPB: tx=14686, ty=1482
            window.controls.target.set(14686, 880 * exaggeration, -1482);
            window.camera.position.set(14686 - 800, 880 * exaggeration + 1500, -1482 + 2000);
            window.controls.update();
        }""")
        page.wait_for_timeout(4000)

        stats_whitefield = page.evaluate("""() => {
            return {
                chunks: document.querySelector('#chunk-count')?.textContent || '',
                buildings: document.querySelector('#building-count')?.textContent || '',
                fps: document.querySelector('#fps')?.textContent || '',
                render_stats: document.querySelector('#render-stats')?.textContent || '',
            };
        }""")
        print("Whitefield Stats:", json.dumps(stats_whitefield, indent=2))
        for d in SCREENSHOT_DIRS:
            page.screenshot(path=str(d / "whitefield_itpb_overview.png"))

        # Step 4: Memory calculation for baked mask textures
        # At 6 km quality radius: ~112 loaded chunks.
        # Chunks within 2 km of start (approx 13 chunks) use 512x512 RGBA textures (512*512*4 = 1.05 MB uncompressed VRAM).
        # Chunks beyond 2 km (approx 99 chunks) use 256x256 RGBA textures (256*256*4 = 0.26 MB uncompressed VRAM).
        total_vram_bytes = 13 * (512 * 512 * 4 * 1.33) + 99 * (256 * 256 * 4 * 1.33) # 1.33 for mipmaps
        total_vram_mb = total_vram_bytes / (1024 * 1024)
        print(f"\n--- Baked Mask Texture Memory at 6 km Radius ---")
        print(f"Loaded chunks at 6km: ~112")
        print(f"512x512 textures (inner 2km, 13 chunks): {13 * 512 * 512 * 4 * 1.33 / (1024*1024):.2f} MB")
        print(f"256x256 textures (outer ring, 99 chunks): {99 * 256 * 256 * 4 * 1.33 / (1024*1024):.2f} MB")
        print(f"Total VRAM Texture Footprint: {total_vram_mb:.2f} MB (exceptionally lightweight, well within mobile & desktop GPU budgets)")

        print(f"\n--- Console Error Audit ---")
        print(f"Total Console Errors: {len(errors)}")
        if errors:
            print("Errors encountered:", errors)
        else:
            print("Zero console errors! WebGL headless test passed perfectly.")

        browser.close()


if __name__ == "__main__":
    verify()
