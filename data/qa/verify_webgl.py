#!/usr/bin/env python3
"""Verify WebGL city viewer, metro, trains, and landmarks in headless Chrome."""

import asyncio
import os
import sys
import time
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "web" / "screenshots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

async def run_verification():
    console_logs = []
    page_errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=True,
            args=[
                "--enable-webgl",
                "--ignore-gpu-blocklist",
                "--use-gl=angle",
                "--use-angle=metal",
                "--enable-features=Vulkan,DefaultANGLEMetal",
                "--disable-background-timer-throttling",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
        )
        page = await context.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        print("Navigating to http://localhost:8000 ...")
        await page.goto("http://localhost:8000", wait_until="networkidle")

        # Wait for scene to load chunks
        print("Waiting for city chunks and metro to load...")
        for _ in range(30):
            status = await page.inner_text("#status")
            if "Loaded" in status or "nearby chunks" in status:
                break
            await asyncio.sleep(0.5)

        await asyncio.sleep(2.0)  # Allow initial render frames to settle

        # Read HUD stats
        fps = await page.inner_text("#fps")
        chunks = await page.inner_text("#chunk-count")
        buildings = await page.inner_text("#building-count")
        render_stats = await page.inner_text("#render-stats")
        print(f"HUD Initial Status: {chunks} chunks, {buildings} bldgs, {fps}, Calls/Tris: {render_stats}")

        # 1. Screenshot: Landmark Panel
        print("Taking Screenshot 1: Landmark & Tech Park panel...")
        # Hover/scroll over landmark panel to show categories
        await page.screenshot(path=str(OUTPUT_DIR / "1_landmark_panel.png"))

        # 2. Screenshot: A metro station
        print("Focusing on a Metro Station (Vidhana Soudha / MG Road)...")
        # Click on Vidhana Soudha or MG Road in landmarks
        # Vidhana Soudha: 12.9796, 77.5906
        await page.evaluate("""() => {
            flyToLocation(12.9796, 77.5906, "Vidhana Soudha Metro Station", false, 180);
        }""")
        await asyncio.sleep(2.5)
        print("Taking Screenshot 2: Metro station marker and viaduct...")
        await page.screenshot(path=str(OUTPUT_DIR / "2_metro_station.png"))

        # 3. Screenshot: Elevated stretch of the metro
        print("Focusing on an elevated stretch of Namma Metro (Indiranagar / CMH Road)...")
        # Coordinates: 12.9780, 77.6380 (Indiranagar elevated corridor)
        await page.evaluate("""() => {
            flyToLocation(12.9780, 77.6380, "Indiranagar Elevated Metro Guideway", false, 140);
        }""")
        await asyncio.sleep(2.5)
        print("Taking Screenshot 3: Elevated metro viaduct...")
        await page.screenshot(path=str(OUTPUT_DIR / "3_elevated_viaduct.png"))

        # 4. Screenshot: Metro at ground level in dense area
        print("Focusing on metro in dense downtown / Majestic...")
        # Majestic / KSR Bengaluru: 12.9757, 77.5728
        await page.evaluate("""() => {
            flyToLocation(12.9757, 77.5728, "Kempegowda Majestic Interchange", false, 280);
        }""")
        await asyncio.sleep(2.5)
        print("Taking Screenshot 4: Metro in dense downtown area...")
        await page.screenshot(path=str(OUTPUT_DIR / "4_dense_area_metro.png"))

        # 5. Screenshot: Night view with moving trains
        print("Switching to night mode...")
        # Set time slider to 95 (night time)
        await page.evaluate("""() => {
            const slider = document.querySelector("#time");
            slider.value = 92;
            slider.dispatchEvent(new Event("input"));
            // Angle camera towards elevated track corridor
            camera.position.set(controls.target.x + 250, controls.target.y + 120, controls.target.z + 320);
            controls.update();
        }""")
        await asyncio.sleep(2.5)
        print("Taking Screenshot 5: Night view with illuminated metro trains...")
        await page.screenshot(path=str(OUTPUT_DIR / "5_night_view_trains.png"))

        # Read performance metrics with Metro ON vs Metro OFF
        fps_metro_on = await page.inner_text("#fps")
        stats_metro_on = await page.inner_text("#render-stats")

        # Toggle Metro OFF
        await page.evaluate("""() => {
            const toggle = document.querySelector("#metro-toggle");
            toggle.checked = false;
            toggle.dispatchEvent(new Event("change"));
        }""")
        await asyncio.sleep(1.5)
        fps_metro_off = await page.inner_text("#fps")
        stats_metro_off = await page.inner_text("#render-stats")

        print("=== VERIFICATION RESULTS ===")
        print(f"Page errors: {len(page_errors)}")
        if page_errors:
            for err in page_errors:
                print(f"  ERROR: {err}")
        print(f"Console logs ({len(console_logs)}):")
        for log in console_logs[-15:]:
            print(f"  {log}")

        print("\n=== PERFORMANCE REPORT ===")
        print(f"Metro ON:  {fps_metro_on} | Draw calls & Triangles: {stats_metro_on}")
        print(f"Metro OFF: {fps_metro_off} | Draw calls & Triangles: {stats_metro_off}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_verification())
