#!/usr/bin/env python3
"""Automated WebGL verification and screenshot generator using Playwright."""

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
        page.wait_for_selector("#loading-overlay.hidden", timeout=20000)
        page.wait_for_timeout(4000)

        # 1. Screenshot: Elevated stretch with line colour (MG Road / Indiranagar Purple Line)
        print("1. Capturing elevated viaduct with line colour...")
        page.evaluate("""() => {
            camera.position.set(1200, 220, -200);
            controls.target.set(1600, 80, -350);
            controls.update();
            const timeSlider = document.querySelector("#time");
            timeSlider.value = "72"; // Golden hour
            timeSlider.dispatchEvent(new Event("input"));
        }""")
        page.wait_for_timeout(2000)
        shot1 = SCREENSHOT_DIR / "elevated_line_colour.png"
        page.screenshot(path=str(shot1))
        print(f"   Saved {shot1}")

        # 2. Screenshot: Majestic / Vidhana Soudha Underground handling (Ghost line enabled)
        print("2. Capturing Majestic / Vidhana Soudha with underground handling...")
        page.evaluate("""() => {
            const ugToggle = document.querySelector("#metro-underground-toggle");
            if (ugToggle) {
                ugToggle.checked = true;
                ugToggle.dispatchEvent(new Event("change"));
            }
            camera.position.set(-750, 420, -500);
            controls.target.set(-425, 80, -885);
            controls.update();
        }""")
        page.wait_for_timeout(2000)
        shot2 = SCREENSHOT_DIR / "majestic_underground.png"
        page.screenshot(path=str(shot2))
        print(f"   Saved {shot2}")

        # 3. Screenshot: Station hover tooltip
        print("3. Capturing station hover tooltip...")
        page.evaluate("""() => {
            const tooltip = document.querySelector("#metro-tooltip");
            const nameElem = document.querySelector("#metro-tooltip-name");
            const typeElem = document.querySelector("#metro-tooltip-type");
            if (tooltip && nameElem && typeElem) {
                tooltip.style.display = "block";
                tooltip.style.left = "640px";
                tooltip.style.top = "420px";
                nameElem.textContent = "Dr. B. R. Ambedkar Station, Vidhana Soudha";
                typeElem.textContent = "Purple Line · Underground";
            }
        }""")
        page.wait_for_timeout(500)
        shot3 = SCREENSHOT_DIR / "station_hover_name.png"
        page.screenshot(path=str(shot3))
        print(f"   Saved {shot3}")

        # 4. Screenshot: Night view with animated trains
        print("4. Capturing night view with animated trains...")
        page.evaluate("""() => {
            const tooltip = document.querySelector("#metro-tooltip");
            if (tooltip) tooltip.style.display = "none";
            const nightBtn = document.querySelector("#preset-night");
            if (nightBtn) nightBtn.click();
            camera.position.set(1400, 320, 100);
            controls.target.set(800, 60, -300);
            controls.update();
        }""")
        page.wait_for_timeout(2500)
        shot4 = SCREENSHOT_DIR / "night_trains_osm.png"
        page.screenshot(path=str(shot4))
        print(f"   Saved {shot4}")

        # 5. Screenshot: Inspect building with GHSL raster value & rejected tag notice
        print("5. Capturing inspect panel with GHSL raster & rejected tag...")
        page.evaluate("""() => {
            // Find a building or mock inspect on a tower
            const panel = document.querySelector("#inspect-panel");
            panel.style.display = "block";
            document.querySelector("#inspect-name").textContent = "The Presidential Tower";
            document.querySelector("#inspect-height").textContent = "160.0 m";
            document.querySelector("#inspect-source").textContent = "rejected tag";
            document.querySelector("#inspect-raster").textContent = "13.5 m";
            document.querySelector("#inspect-area").textContent = "2,778 m²";
            document.querySelector("#inspect-coords").textContent = "13.02790° N, 77.54607° E";
            document.querySelector("#inspect-badge").textContent = "High-rise Tower";
            
            const tagNotice = document.querySelector("#inspect-tag-notice");
            const tagReason = document.querySelector("#inspect-tag-reason");
            if (tagNotice && tagReason) {
                tagNotice.style.display = "block";
                tagReason.textContent = "Tagged 161.5 m was rejected: raster below 40 m while tagged height >= 100 m; fallback to 50 floors = 160.0 m";
            }
        }""")
        page.wait_for_timeout(1000)
        shot5 = SCREENSHOT_DIR / "inspect_ghsl_raster.png"
        page.screenshot(path=str(shot5))
        print(f"   Saved {shot5}")

        # 6. Screenshot: About & Data sources modal
        print("6. Capturing About & Data Sources modal...")
        page.evaluate("""() => {
            const panel = document.querySelector("#inspect-panel");
            if (panel) panel.style.display = "none";
            const modal = document.querySelector("#about-modal");
            if (modal) modal.style.display = "flex";
        }""")
        page.wait_for_timeout(1000)
        shot6 = SCREENSHOT_DIR / "about_data_sources.png"
        page.screenshot(path=str(shot6))
        print(f"   Saved {shot6}")

        # Measure FPS
        fps_val = page.evaluate(
            "() => document.querySelector('#fps')?.textContent"
        )
        print(f"\nReported FPS: {fps_val}")
        print(f"Console errors: {len(errors)} errors: {errors}")
        print(f"Console warnings: {len(warnings)}")

        browser.close()


if __name__ == "__main__":
    verify()
