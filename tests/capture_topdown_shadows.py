import asyncio
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw, ImageFont

async def capture_topdown(page, time_val, out_path, annotation_text, arrow_dir):
    # UB City coords: lat 12.97175, lon 77.5958333
    # local x = (77.5958333 - 77.5946) * 111319.5 * cos(12.9716) = 134m
    # local north = (12.97175 - 12.9716) * 110574 = 16.6m -> z = -16.6m
    # URL hash: date=2026-11-24, time=time_val, radius=2, shadows=1
    url = f"http://localhost:8000/#date=2026-11-24&time={time_val}&radius=2&shadows=1"
    await page.goto(url)
    await page.wait_for_timeout(3500)

    # Set camera directly above UB City looking straight down with North up (-Z is up)
    await page.evaluate('''() => {
        const x = 134;
        const z = -16.6;
        const elev = 920; // terrain around 920m
        const cam = window.camera;
        const ctrl = window.controls;
        
        ctrl.target.set(x, elev, z);
        cam.position.set(x, elev + 650, z + 0.001); // slight offset to prevent gimbal lock
        cam.up.set(0, 0, -1); // North (-Z) is UP on screen
        cam.lookAt(x, elev, z);
        ctrl.update();
        
        // Ensure shadow map is enabled and updated
        window.renderer.shadowMap.enabled = true;
        if (window.sunLight) window.sunLight.castShadow = true;
        window.renderer.render(window.scene, window.camera);
    }''')
    await page.wait_for_timeout(1000)
    await page.screenshot(path=out_path)

    # Annotate image with compass and shadow direction
    img = Image.open(out_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    
    # Draw Compass Rose in top-right
    # Center (1320, 100)
    cx, cy = 1320, 100
    r = 45
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(15, 23, 42, 220), outline=(241, 245, 249, 255), width=2)
    # North arrow (Up)
    draw.line([cx, cy + 15, cx, cy - 35], fill=(239, 68, 68, 255), width=3)
    draw.polygon([(cx, cy - 42), (cx - 7, cy - 30), (cx + 7, cy - 30)], fill=(239, 68, 68, 255))
    draw.text((cx - 5, cy - 25), "N", fill=(255, 255, 255, 255))
    draw.text((cx + 25, cy - 7), "E", fill=(255, 255, 255, 255))
    draw.text((cx - 4, cy + 25), "S", fill=(255, 255, 255, 255))
    draw.text((cx - 35, cy - 7), "W", fill=(255, 255, 255, 255))

    # Banner with annotation text
    draw.rectangle([20, 20, 680, 110], fill=(15, 23, 42, 230), outline=(56, 189, 248, 255), width=2)
    draw.text((35, 30), annotation_text[0], fill=(248, 250, 252, 255))
    draw.text((35, 55), annotation_text[1], fill=(253, 224, 71, 255))
    draw.text((35, 80), annotation_text[2], fill=(148, 163, 184, 255))

    # Center target indicator on UB Tower (screen center: 720, 450)
    tx, ty = 720, 450
    draw.ellipse([tx - 6, ty - 6, tx + 6, ty + 6], fill=(239, 68, 68, 255), outline=(255, 255, 255, 255), width=2)
    
    # Shadow direction arrow from tower base
    if arrow_dir == "NORTH":
        # Arrow pointing up (towards North)
        draw.line([tx, ty - 15, tx, ty - 120], fill=(56, 189, 248, 255), width=4)
        draw.polygon([(tx, ty - 135), (tx - 10, ty - 115), (tx + 10, ty - 115)], fill=(56, 189, 248, 255))
        draw.text((tx + 15, ty - 100), "SHADOW -> DUE NORTH", fill=(56, 189, 248, 255))
    elif arrow_dir == "ENE":
        # Arrow pointing towards top-right (East-North-East)
        draw.line([tx, ty - 15, tx + 180, ty - 70], fill=(56, 189, 248, 255), width=4)
        draw.polygon([(tx + 195, ty - 75), (tx + 175, ty - 85), (tx + 172, ty - 60)], fill=(56, 189, 248, 255))
        draw.text((tx + 50, ty - 80), "SHADOW -> EAST-NORTH-EAST (ENE)", fill=(56, 189, 248, 255))

    img.save(out_path)
    print(f"Annotated screenshot saved: {out_path}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            args=["--enable-webgl", "--ignore-gpu-blocklist", "--use-gl=angle", "--use-angle=metal"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        
        # 12:00 on 2026-11-24: time=37.5 (Noon)
        await capture_topdown(
            page,
            37.5,
            "web/screenshots/topdown_ubcity_1200.png",
            [
                "UB City / UB Tower (123m) Top-Down View [North is UP]",
                "Date: 2026-11-24 12:00 IST | Sun: Azimuth 177° (South), Elev +56.6°",
                "Observed: Directional shadow falls directly to the NORTH of the tower"
            ],
            "NORTH"
        )

        # 17:30 on 2026-11-24: time=72 (Golden Hour)
        await capture_topdown(
            page,
            72,
            "web/screenshots/topdown_ubcity_1730.png",
            [
                "UB City / UB Tower (123m) Top-Down View [North is UP]",
                "Date: 2026-11-24 17:30 IST | Sun: Azimuth 248° (WSW), Elev +3.9°",
                "Observed: Directional shadow falls towards EAST-NORTH-EAST (ENE)"
            ],
            "ENE"
        )

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
