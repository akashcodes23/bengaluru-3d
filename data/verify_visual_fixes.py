#!/usr/bin/env python3
"""Verify smooth terrain-conforming green spaces and properly elevated buildings in WebGL."""

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
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on(
            "console",
            lambda msg: (
                errors.append(msg.text)
                if msg.type == "error"
                else (
                    warnings.append(msg.text)
                    if msg.type == "warning"
                    else None
                )
            ),
        )

        print("Loading application...")
        page.goto("http://localhost:8000/#radius=6")

        # Wait for loading overlay to hide and city chunks to settle
        page.wait_for_selector("#loading-overlay.hidden", timeout=25000)
        page.wait_for_timeout(3500)

        # 1. Chinnaswamy Stadium & Cubbon Park (Daytime, 12:00, 1.0x exaggeration)
        print("1. Capturing Chinnaswamy Stadium & Cubbon Park (daytime 12:00)...")
        page.evaluate("""() => {
            const timeSlider = document.querySelector("#time");
            timeSlider.value = "38"; // 12:00 Day
            timeSlider.dispatchEvent(new Event("input"));

            const exaggSlider = document.querySelector("#vertical-exaggeration");
            exaggSlider.value = "1.0";
            exaggSlider.dispatchEvent(new Event("input"));

            window.flyToLocation(12.97882, 77.59959, "M. Chinnaswamy Stadium", false, 450);
        }""")
        page.wait_for_timeout(3500)
        shot1 = SCREENSHOT_DIR / "chinnaswamy_smooth_ground.png"
        page.screenshot(path=str(shot1))
        print(f"   Saved {shot1}")

        # 2. Chinnaswamy at 2.5x vertical exaggeration
        print("2. Capturing Chinnaswamy at 2.5x exaggeration...")
        page.evaluate("""() => {
            const exaggSlider = document.querySelector("#vertical-exaggeration");
            exaggSlider.value = "2.5";
            exaggSlider.dispatchEvent(new Event("input"));
        }""")
        page.wait_for_timeout(3500)
        shot2 = SCREENSHOT_DIR / "chinnaswamy_2_5x_exagg.png"
        page.screenshot(path=str(shot2))
        print(f"   Saved {shot2}")

        # 3. WTC Bangalore / Brigade Gateway (Golden hour, 1.0x exaggeration)
        print("3. Capturing WTC Bangalore / Brigade Gateway...")
        page.evaluate("""() => {
            const exaggSlider = document.querySelector("#vertical-exaggeration");
            exaggSlider.value = "1.0";
            exaggSlider.dispatchEvent(new Event("input"));

            const timeSlider = document.querySelector("#time");
            timeSlider.value = "72"; // Golden hour
            timeSlider.dispatchEvent(new Event("input"));

            window.flyToLocation(13.01231, 77.55621, "World Trade Center Bangalore", false, 550);
        }""")
        page.wait_for_timeout(3500)
        shot3 = SCREENSHOT_DIR / "wtc_brigade_gateway.png"
        page.screenshot(path=str(shot3))
        print(f"   Saved {shot3}")

        # 4. Vidhana Soudha & Cubbon Park (Aerial view)
        print("4. Capturing Vidhana Soudha & Cubbon Park...")
        page.evaluate("""() => {
            window.flyToLocation(12.9797, 77.5907, "Vidhana Soudha & Cubbon Park", true, 900);
        }""")
        page.wait_for_timeout(3500)
        shot4 = SCREENSHOT_DIR / "cubbon_park_wide.png"
        page.screenshot(path=str(shot4))
        print(f"   Saved {shot4}")

        # Check stats
        fps_val = page.evaluate("() => document.querySelector('#fps')?.textContent")
        chunks_val = page.evaluate("() => document.querySelector('#chunk-count')?.textContent")
        bldgs_val = page.evaluate("() => document.querySelector('#building-count')?.textContent")
        render_stats = page.evaluate("() => document.querySelector('#render-stats')?.textContent")

        print(f"\nReported Stats:")
        print(f"FPS: {fps_val}")
        print(f"Chunks loaded: {chunks_val}")
        print(f"Buildings in view: {bldgs_val}")
        print(f"Draw calls / triangles: {render_stats}")
        print(f"Console errors ({len(errors)}): {errors}")
        print(f"Console warnings ({len(warnings)})")

        browser.close()


if __name__ == "__main__":
    verify()
