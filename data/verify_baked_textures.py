#!/usr/bin/env python3
"""Verification script for baked terrain mask textures, visual quality, and performance."""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = ROOT / "web" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


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
        warnings = []
        page.on("pageerror", lambda err: errors.append(f"PAGEERROR: {err}"))
        page.on(
            "console",
            lambda msg: (
                errors.append(f"CONSOLE ERROR: {msg.text}")
                if msg.type == "error"
                else (
                    warnings.append(f"CONSOLE WARN: {msg.text}")
                    if msg.type == "warning"
                    else None
                )
            ),
        )

        results = {}

        print("--- Step 1: Loading default view (radius=6) ---")
        page.goto("http://localhost:8000/#radius=6")
        page.wait_for_selector("#loading-overlay.hidden", timeout=30000)
        page.wait_for_timeout(3500)

        # Measure Default View Stats
        default_stats = page.evaluate("""() => {
            const statsText = document.querySelector("#render-stats")?.textContent || "";
            const fpsText = document.querySelector("#fps")?.textContent || "";
            const chunkCountText = document.querySelector("#chunk-count")?.textContent || "";
            const buildingCountText = document.querySelector("#building-count")?.textContent || "";

            let count512 = 0;
            let count256 = 0;
            let totalTextureBytes = 0;
            if (window.loadedChunks) {
                for (const chunk of window.loadedChunks.values()) {
                    if (chunk.maskTexture && chunk.maskTexture.image) {
                        const w = chunk.maskTexture.image.width;
                        const h = chunk.maskTexture.image.height;
                        if (w === 512) count512++;
                        else if (w === 256) count256++;
                        // RGBA8 with mipmaps = w * h * 4 * 1.3333 bytes
                        totalTextureBytes += Math.round(w * h * 4 * (4 / 3));
                    }
                }
            }

            return {
                statsText,
                fpsText,
                chunkCountText,
                buildingCountText,
                count512,
                count256,
                totalTextureBytes,
                textureMemoryMB: (totalTextureBytes / (1024 * 1024)).toFixed(2)
            };
        }""")
        results["radius_6km"] = default_stats
        print(f"Radius 6km Stats: {json.dumps(default_stats, indent=2)}")

        # Screenshot: Default view
        shot_default = SCREENSHOT_DIR / "default_view_baked.png"
        page.screenshot(path=str(shot_default))
        print(f"Saved {shot_default}")

        # Measure Radius = 4 km Stats
        print("\n--- Step 2: Switching to Quality Radius 4 km ---")
        page.evaluate("""() => {
            const radiusSelect = document.querySelector("#radius");
            if (radiusSelect) {
                radiusSelect.value = "4";
                radiusSelect.dispatchEvent(new Event("change"));
            }
        }""")
        page.wait_for_timeout(3500)
        radius_4km_stats = page.evaluate("""() => {
            const statsText = document.querySelector("#render-stats")?.textContent || "";
            const fpsText = document.querySelector("#fps")?.textContent || "";
            const chunkCountText = document.querySelector("#chunk-count")?.textContent || "";
            const buildingCountText = document.querySelector("#building-count")?.textContent || "";

            let count512 = 0;
            let count256 = 0;
            let totalTextureBytes = 0;
            if (window.loadedChunks) {
                for (const chunk of window.loadedChunks.values()) {
                    if (chunk.maskTexture && chunk.maskTexture.image) {
                        const w = chunk.maskTexture.image.width;
                        const h = chunk.maskTexture.image.height;
                        if (w === 512) count512++;
                        else if (w === 256) count256++;
                        totalTextureBytes += Math.round(w * h * 4 * (4 / 3));
                    }
                }
            }

            return {
                statsText,
                fpsText,
                chunkCountText,
                buildingCountText,
                count512,
                count256,
                totalTextureBytes,
                textureMemoryMB: (totalTextureBytes / (1024 * 1024)).toFixed(2)
            };
        }""")
        results["radius_4km"] = radius_4km_stats
        print(f"Radius 4km Stats: {json.dumps(radius_4km_stats, indent=2)}")

        # Switch back to radius 6km for screenshots
        page.evaluate("""() => {
            const radiusSelect = document.querySelector("#radius");
            if (radiusSelect) {
                radiusSelect.value = "6";
                radiusSelect.dispatchEvent(new Event("change"));
            }
        }""")
        page.wait_for_timeout(2000)

        # Screenshot 1: Cubbon Park 1.5 km Day (12:00)
        print("\n--- Step 3: Capturing Cubbon Park 1.5 km Day (12:00) ---")
        page.evaluate("""() => {
            document.querySelector("#preset-day")?.click();
            // Cubbon Park center at x = -150, north = 700
            // Look top-down oblique from 1500m altitude
            camera.position.set(-150, 1500, -700 + 400);
            controls.target.set(-150, 920, -700);
            controls.update();
        }""")
        page.wait_for_timeout(2500)
        shot_cubbon_day = SCREENSHOT_DIR / "cubbon_park_1500m_day.png"
        page.screenshot(path=str(shot_cubbon_day))
        print(f"Saved {shot_cubbon_day}")

        # Screenshot 2: Cubbon Park 1.5 km Night (22:00)
        print("\n--- Step 4: Capturing Cubbon Park 1.5 km Night (22:00) ---")
        page.evaluate("""() => {
            document.querySelector("#preset-night")?.click();
        }""")
        page.wait_for_timeout(2000)
        shot_cubbon_night = SCREENSHOT_DIR / "cubbon_park_1500m_night.png"
        page.screenshot(path=str(shot_cubbon_night))
        print(f"Saved {shot_cubbon_night}")

        # Screenshot 3: Lalbagh Botanical Garden (Day)
        print("\n--- Step 5: Capturing Lalbagh Botanical Garden ---")
        page.evaluate("""() => {
            document.querySelector("#preset-day")?.click();
            // Lalbagh Botanical Garden coords: lat 12.9507, lon 77.5848
            window.flyToLocation(12.9507, 77.5848, "Lalbagh Botanical Garden", true, 1100);
        }""")
        page.wait_for_timeout(3500)
        shot_lalbagh = SCREENSHOT_DIR / "lalbagh_baked.png"
        page.screenshot(path=str(shot_lalbagh))
        print(f"Saved {shot_lalbagh}")

        # Screenshot 4: Ulsoor Lake (Day)
        print("\n--- Step 6: Capturing Ulsoor Lake ---")
        page.evaluate("""() => {
            // Ulsoor Lake coords: lat 12.9822, lon 77.6200
            window.flyToLocation(12.9822, 77.6200, "Ulsoor Lake", true, 950);
        }""")
        page.wait_for_timeout(3500)
        shot_ulsoor = SCREENSHOT_DIR / "ulsoor_lake_baked.png"
        page.screenshot(path=str(shot_ulsoor))
        print(f"Saved {shot_ulsoor}")

        # Screenshot 5: Chunk boundary crossing at x = 0, north = 600
        print("\n--- Step 7: Capturing Chunk boundary crossing (Cubbon Park) ---")
        page.evaluate("""() => {
            // Chunk border between (-1, 0) and (0, 0) is x = 0.0
            // Cubbon Park extends through x = 0 around north = 600
            camera.position.set(0, 1150, -600 + 350);
            controls.target.set(0, 920, -600);
            controls.update();
        }""")
        page.wait_for_timeout(2500)
        shot_border = SCREENSHOT_DIR / "chunk_border_park.png"
        page.screenshot(path=str(shot_border))
        print(f"Saved {shot_border}")

        print("\n--- Console Errors Check ---")
        print(f"Total Console Errors: {len(errors)}")
        for err in errors:
            print(f"  {err}")

        browser.close()


if __name__ == "__main__":
    verify()
