import asyncio
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import async_playwright

async def capture_views():
    os.makedirs("web/screenshots", exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            args=[
                "--enable-webgl",
                "--ignore-gpu-blocklist",
                "--use-gl=angle",
                "--use-angle=metal",
            ]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        errors = []
        page.on("pageerror", lambda err: errors.append(f"PageError: {err}"))
        page.on("console", lambda msg: errors.append(f"ConsoleError: {msg.text}") if msg.type == "error" else None)

        # 1. High aerial over Outer Ring Road near Manyata/Hebbal (?focus=13.0475,77.6207&altitude=1500)
        print("Capturing 1: Manyata/Hebbal ORR Aerial (21:00)...")
        await page.goto("http://localhost:8000/?focus=13.0475,77.6207&altitude=1500#time=94&radius=4&traffic=low")
        await page.wait_for_timeout(5000)
        await page.screenshot(path="web/screenshots/phase2_manyata_hebbal_orr.raw.png")

        # 2. Silk Board / Hosur Road area view (21:00)
        print("Capturing 2: Silk Board / Hosur Road Area View (21:00)...")
        await page.goto("http://localhost:8000/?focus=12.9176,77.6238&altitude=900#time=94&radius=4&traffic=low")
        await page.wait_for_timeout(5000)
        await page.screenshot(path="web/screenshots/phase2_silk_board_hosur_rd.raw.png")

        # 3. Close street-level view (21:00)
        print("Capturing 3: Close Street-Level View (21:00)...")
        await page.goto("http://localhost:8000/?focus=13.0358,77.5970&altitude=120#time=94&radius=2&traffic=low")
        await page.wait_for_timeout(3500)
        await page.evaluate("""() => {
            const controls = window.controls;
            const camera = window.camera;
            controls.target.set(260, 935, -7100);
            camera.position.set(220, 975, -6900);
            controls.update();
        }""")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="web/screenshots/phase2_close_street_view.raw.png")

        # 4. Midday view at 12:00 (traffic faint/off by day)
        print("Capturing 4: Midday 12:00 View...")
        await page.goto("http://localhost:8000/#time=37.5&radius=4&traffic=low")
        await page.wait_for_timeout(5000)
        await page.screenshot(path="web/screenshots/phase2_midday_1200.raw.png")

        # 5. Top-down view over Hosur Road dual-carriageway segment for zoomed annotation
        print("Capturing 5: Top-Down Carriageway for Annotation...")
        await page.goto("http://localhost:8000/?focus=12.9176,77.6238&altitude=500#time=94&radius=2&traffic=low")
        await page.wait_for_timeout(4500)
        await page.evaluate("""() => {
            const controls = window.controls;
            const camera = window.camera;
            controls.target.set(2950, 884, 5835);
            camera.position.set(2950, 1150, 5835);
            controls.update();
        }""")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="web/screenshots/phase2_topdown_carriageway.raw.png")

        print("\nTotal Console/Page Errors:", len(errors))
        for e in errors:
            print("  ", e)
        assert len(errors) == 0, f"Encountered {len(errors)} errors during screenshot capture!"

        await browser.close()

    # Post-process and compress all screenshots (<400 KB requirement via MEDIANCUT)
    print("\nCompressing screenshots (<400 KB budget)...")

    files = [
        ("web/screenshots/phase2_manyata_hebbal_orr.raw.png", "web/screenshots/phase2_manyata_hebbal_orr.png"),
        ("web/screenshots/phase2_silk_board_hosur_rd.raw.png", "web/screenshots/phase2_silk_board_hosur_rd.png"),
        ("web/screenshots/phase2_close_street_view.raw.png", "web/screenshots/phase2_close_street_view.png"),
        ("web/screenshots/phase2_midday_1200.raw.png", "web/screenshots/phase2_midday_1200.png"),
    ]

    for raw_p, out_p in files:
        img = Image.open(raw_p).convert("RGB")
        q = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        q.save(out_p, format="PNG", optimize=True)
        size_kb = os.path.getsize(out_p) / 1024
        print(f"  {out_p}: {size_kb:.1f} KB")
        if os.path.exists(raw_p):
            os.remove(raw_p)

    # Generate zoomed annotated crop
    print("\nGenerating phase2_traffic_streams_annotated.png...")
    topdown_img = Image.open("web/screenshots/phase2_topdown_carriageway.raw.png").convert("RGB")
    w, h = topdown_img.size
    crop_box = (w // 2 - 250, h // 2 - 250, w // 2 + 250, h // 2 + 250)
    cropped = topdown_img.crop(crop_box).copy()

    draw = ImageDraw.Draw(cropped)
    # Header badge
    draw.rectangle([(10, 10), (490, 85)], fill=(15, 23, 42), outline=(56, 189, 248), width=2)
    draw.text((20, 16), "INDIA LEFT-HAND DRIVE: DUAL-CARRIAGEWAY SEPARATION", fill=(248, 250, 252))
    draw.text((20, 36), "[LEFT LANE / FORWARD]: White headlights (+1.8 m offset)", fill=(254, 240, 138))
    draw.text((20, 52), "[LEFT LANE / REVERSE]: Red taillights (-1.8 m offset)", fill=(248, 113, 113))
    draw.text((20, 68), "Opposite sides of centerline: total separation = 3.6 m", fill=(148, 163, 184))

    # Lane callouts
    # Forward stream label near x=160, y=230
    draw.rectangle([(40, 210), (220, 245)], fill=(15, 23, 42), outline=(254, 240, 138), width=1)
    draw.text((45, 215), "Northbound lane (Left side)", fill=(254, 240, 138))
    draw.text((45, 229), "White headlights ->", fill=(255, 255, 255))
    draw.line([(130, 245), (150, 270)], fill=(254, 240, 138), width=2)

    # Reverse stream label near x=270, y=360
    draw.rectangle([(250, 370), (450, 405)], fill=(15, 23, 42), outline=(248, 113, 113), width=1)
    draw.text((255, 375), "Southbound lane (Left side)", fill=(248, 113, 113))
    draw.text((255, 389), "<- Red taillights", fill=(255, 120, 120))
    draw.line([(320, 370), (280, 320)], fill=(248, 113, 113), width=2)

    # Centerline indicator
    draw.line([(215, 180), (215, 420)], fill=(148, 163, 184), width=1)
    draw.text((180, 425), "Road Centerline", fill=(148, 163, 184))

    annotated_path = "web/screenshots/phase2_traffic_streams_annotated.png"
    q_ann = cropped.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    q_ann.save(annotated_path, format="PNG", optimize=True)
    size_kb = os.path.getsize(annotated_path) / 1024
    print(f"  {annotated_path}: {size_kb:.1f} KB")

    if os.path.exists("web/screenshots/phase2_topdown_carriageway.raw.png"):
        os.remove("web/screenshots/phase2_topdown_carriageway.raw.png")
    if os.path.exists("web/screenshots/topdown_test.png"):
        os.remove("web/screenshots/topdown_test.png")

if __name__ == "__main__":
    asyncio.run(capture_views())
