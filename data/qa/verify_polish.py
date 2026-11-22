#!/usr/bin/env python3
"""Verify polish: Readable ground, Click to Inspect, Metro visual upgrades, Day/Golden/Night presets, and URL hash."""

import asyncio
import json
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

        print("Waiting for chunks and metro to stream...")
        for _ in range(40):
            status = await page.inner_text("#status")
            if "Loaded" in status or "nearby chunks" in status:
                break
            await asyncio.sleep(0.5)

        try:
            await page.wait_for_selector("#loading-overlay.hidden", timeout=10000)
        except Exception:
            await page.evaluate("() => document.querySelector('#loading-overlay').classList.add('hidden')")

        await asyncio.sleep(2.5)  # Let chunks and textures render

        fps = await page.inner_text("#fps")
        chunks = await page.inner_text("#chunk-count")
        buildings = await page.inner_text("#building-count")
        render_stats = await page.inner_text("#render-stats")
        print(f"HUD Status: {chunks} chunks, {buildings} bldgs, {fps}, Calls/Tris: {render_stats}")

        # 1. Day Aerial (12:00)
        print("1. Capturing Day Aerial (12:00)...")
        await page.click("#preset-day")
        await asyncio.sleep(1.5)
        await page.screenshot(path=str(OUTPUT_DIR / "day_aerial.png"))

        # 2. Golden Hour (17:30)
        print("2. Capturing Golden Hour (17:30)...")
        await page.click("#preset-golden")
        await asyncio.sleep(1.5)
        await page.screenshot(path=str(OUTPUT_DIR / "golden_hour.png"))

        # 3. Night Aerial with Windows Lit (21:00)
        print("3. Capturing Night Aerial (21:00)...")
        await page.click("#preset-night")
        await asyncio.sleep(1.5)
        await page.screenshot(path=str(OUTPUT_DIR / "night_aerial.png"))

        # 4. Close Street-Level View over MG Road / Cubbon Park at 12:00
        print("4. Capturing MG Road / Cubbon Park Street-Level View at 12:00...")
        await page.click("#preset-day")
        # MG Road coordinates: 12.9756, 77.6066
        await page.evaluate("""() => {
            flyToLocation(12.9756, 77.6066, "MG Road / Cubbon Park Corridor", false, 140);
        }""")
        await asyncio.sleep(2.5)
        await page.screenshot(path=str(OUTPUT_DIR / "mg_road_cubbon_day_1200.png"))

        # 5. Close Street-Level View over MG Road / Cubbon Park at 21:00 (Warm Emissive Roads)
        print("5. Capturing MG Road / Cubbon Park Street-Level View at 21:00...")
        await page.click("#preset-night")
        await asyncio.sleep(1.5)
        await page.screenshot(path=str(OUTPUT_DIR / "mg_road_cubbon_night_2100.png"))

        # 6. Inspect Panel on Verified Landmark: Vidhana Soudha
        print("6. Inspecting Verified Landmark: Vidhana Soudha...")
        await page.click("#preset-golden")
        # Fly to Vidhana Soudha: 12.9796, 77.5906
        await page.evaluate("""() => {
            flyToLocation(12.9796, 77.5906, "Vidhana Soudha", false, 160);
        }""")
        await asyncio.sleep(2.5)

        # Trigger inspection on Vidhana Soudha building
        inspection_result_vs = await page.evaluate("""() => {
            const chunks = window.loadedChunks || loadedChunks;
            let targetBldg = null;
            // Prefer Vidhana Soudha near 12.9796, 77.5906
            for (const [key, state] of chunks) {
                if (!state.parsedBuildings && state.buildingText) {
                    try { state.parsedBuildings = JSON.parse(state.buildingText); } catch(e){}
                }
                const bldgs = state.parsedBuildings || [];
                for (let i = 0; i < bldgs.length; i++) {
                    const b = bldgs[i];
                    if (b[2] === 4) { // verified landmark
                        const [cx, cNorth] = window.polygonCentroid(b[1]);
                        const lon = 77.5946 + cx / (111319.49079327358 * Math.cos(12.9716 * Math.PI / 180));
                        const lat = 12.9716 + cNorth / 110574;
                        if (Math.hypot(lat - 12.9796, lon - 77.5906) < 0.002) {
                            const cy = state.buildingBounds[i * 4 + 1];
                            const bHeight = Math.max(3, b[0]);
                            targetBldg = {
                                chunkKey: key,
                                index: i,
                                height: b[0],
                                coords: b[1],
                                source: b[2],
                                baseY: cy - bHeight / 2,
                                topY: cy + bHeight / 2,
                            };
                            break;
                        }
                    }
                }
                if (targetBldg) break;
            }
            if (targetBldg) {
                const [cx, cNorth] = window.polygonCentroid(targetBldg.coords);
                camera.position.set(cx + 80, targetBldg.topY + 60, -cNorth + 110);
                controls.target.set(cx, targetBldg.baseY + targetBldg.height / 2, -cNorth);
                controls.update();
                window.inspectBuilding(targetBldg);
                return {
                    name: document.querySelector("#inspect-name").textContent,
                    height: document.querySelector("#inspect-height").textContent,
                    source: document.querySelector("#inspect-source").textContent,
                    area: document.querySelector("#inspect-area").textContent,
                    coords: document.querySelector("#inspect-coords").textContent,
                };
            }
            return null;
        }""")
        print(f"Vidhana Soudha Inspection Data: {inspection_result_vs}")
        await asyncio.sleep(1.0)
        await page.screenshot(path=str(OUTPUT_DIR / "inspect_verified_landmark.png"))

        # 7. Inspect Panel on Tagged Tower (e.g. Public Utility Building or Comet)
        print("7. Inspecting Tagged Tower...")
        inspection_result_tower = await page.evaluate("""() => {
            const chunks = window.loadedChunks || loadedChunks;
            let bestTower = null;
            let maxHeight = 0;
            for (const [key, state] of chunks) {
                if (!state.parsedBuildings && state.buildingText) {
                    try { state.parsedBuildings = JSON.parse(state.buildingText); } catch(e){}
                }
                const bldgs = state.parsedBuildings || [];
                for (let i = 0; i < bldgs.length; i++) {
                    const b = bldgs[i];
                    if (b[2] === 0 && b[0] > maxHeight) { // tagged
                        maxHeight = b[0];
                        const cy = state.buildingBounds[i * 4 + 1];
                        const bHeight = Math.max(3, b[0]);
                        bestTower = {
                            chunkKey: key,
                            index: i,
                            height: b[0],
                            coords: b[1],
                            source: b[2],
                            baseY: cy - bHeight / 2,
                            topY: cy + bHeight / 2,
                        };
                    }
                }
            }
            if (bestTower) {
                const [cx, cNorth] = window.polygonCentroid(bestTower.coords);
                camera.position.set(cx + 120, bestTower.topY + 60, -cNorth + 140);
                controls.target.set(cx, bestTower.baseY + bestTower.height / 2, -cNorth);
                controls.update();
                window.inspectBuilding(bestTower);
                return {
                    name: document.querySelector("#inspect-name").textContent,
                    height: document.querySelector("#inspect-height").textContent,
                    source: document.querySelector("#inspect-source").textContent,
                    area: document.querySelector("#inspect-area").textContent,
                    coords: document.querySelector("#inspect-coords").textContent,
                };
            }
            return null;
        }""")
        print(f"Tagged Tower Inspection Data: {inspection_result_tower}")
        await asyncio.sleep(2.0)
        await page.screenshot(path=str(OUTPUT_DIR / "inspect_tagged_tower.png"))

        # 8. Metro Viaduct Deck Ribbon & Station Hover
        print("8. Inspecting Metro Viaduct Deck Ribbon & Station Hover Tooltip...")
        await page.evaluate("""() => {
            flyToLocation(12.9730, 77.6170, "Trinity Metro Station", false, 110);
        }""")
        await asyncio.sleep(2.5)

        hover_info = await page.evaluate("""() => {
            const stations = window.metroStationsData || [];
            const s = stations.find(st => st.name && st.name.includes("Trinity")) || stations[0];
            if (!s) return null;
            const platformY = (s.ground_z + 8.0) * (Number(document.querySelector("#vertical-exaggeration").value) || 1.0);
            const p = new THREE.Vector3(s.x, platformY, -s.y);
            p.project(camera);
            const sx = (p.x * 0.5 + 0.5) * window.innerWidth;
            const sy = (-(p.y * 0.5) + 0.5) * window.innerHeight;
            
            window.dispatchEvent(new PointerEvent("pointermove", { clientX: sx, clientY: sy }));
            return {
                station: s.name,
                tooltipVisible: document.querySelector("#metro-tooltip").style.display,
                tooltipText: document.querySelector("#metro-tooltip-name").textContent,
            };
        }""")
        print(f"Station Hover Tooltip: {hover_info}")
        await asyncio.sleep(1.0)
        await page.screenshot(path=str(OUTPUT_DIR / "metro_viaduct_ribbon.png"))

        # 9. Verify Shareable URL Hash
        current_hash = await page.evaluate("() => location.hash")
        print(f"9. Current Shareable URL Hash: {current_hash}")

        # Check console errors
        print("\n=== VERIFICATION RESULTS ===")
        print(f"Total Page Errors: {len(page_errors)}")
        for err in page_errors:
            print(f"  ERROR: {err}")
        print(f"Total Console Logs: {len(console_logs)}")
        for log in console_logs[-10:]:
            print(f"  {log}")

        final_fps = await page.inner_text("#fps")
        final_stats = await page.inner_text("#render-stats")
        print(f"\n=== FINAL PERFORMANCE ===")
        print(f"FPS: {final_fps} | Render Calls/Triangles: {final_stats}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_verification())
