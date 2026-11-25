#!/usr/bin/env python3
"""Step 5: Verify orientation of terrain baked mask texture using test triangle."""

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

        print("Loading application for orientation test...")
        page.goto("http://localhost:8000/#radius=6")

        page.wait_for_selector("#loading-overlay.hidden", timeout=25000)
        page.wait_for_timeout(3500)

        # Look at NE corner of chunk (0, 0): x=1000, z=-1000
        # Target at (850, 930, -850)
        # Camera at (850, 1600, -849) looking almost top-down so North (-Z) is UP, East (+X) is RIGHT
        print("Capturing NE corner of chunk (0, 0)...")
        page.evaluate("""() => {
            const timeSlider = document.querySelector("#time");
            timeSlider.value = "38"; // 12:00 Day
            timeSlider.dispatchEvent(new Event("input"));

            const exaggSlider = document.querySelector("#vertical-exaggeration");
            exaggSlider.value = "1.0";
            exaggSlider.dispatchEvent(new Event("input"));

            camera.up.set(0, 0, -1); // North (-Z) is UP
            camera.position.set(850, 1600, -850.01);
            controls.target.set(850, 920, -850);
            controls.update();
        }""")
        page.wait_for_timeout(3000)
        shot = SCREENSHOT_DIR / "step5_orientation_test.png"
        page.screenshot(path=str(shot))
        print(f"Saved {shot}")

        fps_val = page.evaluate("() => document.querySelector('#fps')?.textContent")
        print(f"FPS: {fps_val}")
        print(f"Console errors ({len(errors)}): {errors}")
        print(f"Console warnings ({len(warnings)})")

        browser.close()


if __name__ == "__main__":
    verify()
