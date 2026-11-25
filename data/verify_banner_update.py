#!/usr/bin/env python3
"""Verify the new banner, logo, and favicon in WebGL headless Chrome."""

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
        page.on("pageerror", lambda err: errors.append(f"PAGEERROR: {err}"))
        page.on(
            "console",
            lambda msg: (
                errors.append(f"CONSOLE ERROR: {msg.text}")
                if msg.type == "error"
                else None
            ),
        )

        print("Loading application...")
        page.goto("http://localhost:8000/#radius=6")

        # Check favicon link tag
        favicon_href = page.evaluate("""() => {
            const link = document.querySelector('link[rel~="icon"]');
            return link ? link.getAttribute('href') : null;
        }""")
        print(f"Favicon href: {favicon_href}")

        # Wait for scene to load
        page.wait_for_selector("#loading-overlay.hidden", timeout=30000)
        page.wait_for_timeout(2500)

        # Check banner visibility and attributes
        banner_info = page.evaluate("""() => {
            const banner = document.querySelector('#brand-banner');
            if (!banner) return null;
            const rect = banner.getBoundingClientRect();
            return {
                src: banner.getAttribute('src'),
                naturalWidth: banner.naturalWidth,
                naturalHeight: banner.naturalHeight,
                renderedWidth: rect.width,
                renderedHeight: rect.height,
                top: rect.top,
                left: rect.left
            };
        }""")
        print(f"Banner info: {banner_info}")

        # Screenshot: full default view showing the new topbar banner
        shot_view = SCREENSHOT_DIR / "banner_update_view.png"
        page.screenshot(path=str(shot_view))
        print(f"Saved full view screenshot to {shot_view}")

        # Screenshot: close up of topbar
        topbar = page.query_selector(".topbar")
        if topbar:
            shot_topbar = SCREENSHOT_DIR / "banner_closeup.png"
            topbar.screenshot(path=str(shot_topbar))
            print(f"Saved banner close-up screenshot to {shot_topbar}")

        # Open About modal and screenshot
        page.evaluate("""() => {
            document.querySelector('#about-open-btn')?.click();
        }""")
        page.wait_for_timeout(1000)
        shot_about = SCREENSHOT_DIR / "about_modal_banner.png"
        page.screenshot(path=str(shot_about))
        print(f"Saved About modal screenshot to {shot_about}")

        print(f"\nTotal console errors: {len(errors)}")
        for err in errors:
            print(f"  {err}")

        browser.close()


if __name__ == "__main__":
    verify()
