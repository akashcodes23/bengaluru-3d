import asyncio
from playwright.async_api import async_playwright

async def test_date(page, date_str, label):
    # Navigate with hash to set date, time=37.5 (which is 12:00 IST), radius=2, shadows=1
    url = f"http://localhost:8000/#date={date_str}&time=37.5&radius=2&shadows=1"
    await page.goto(url)
    await page.wait_for_timeout(3000)

    res = await page.evaluate('''() => {
        const sun = window.sunLight;
        const target = window.controls.target;
        const deltaX = sun.position.x - target.x;
        const deltaY = sun.position.y - target.y;
        const deltaZ = sun.position.z - target.z;
        const elev = document.querySelector("#sun-elev-val") ? document.querySelector("#sun-elev-val").textContent : "";
        const azim = document.querySelector("#sun-azim-val") ? document.querySelector("#sun-azim-val").textContent : "";
        const timeLabel = document.querySelector("#time-label") ? document.querySelector("#time-label").textContent : "";
        return {
            sunPos: { x: sun.position.x, y: sun.position.y, z: sun.position.z },
            target: { x: target.x, y: target.y, z: target.z },
            delta: { x: deltaX, y: deltaY, z: deltaZ },
            elev,
            azim,
            timeLabel
        };
    }''')
    print(f"\n--- {label} ({date_str} at {res['timeLabel']} IST) ---")
    print(f"Sun HUD: Elevation {res['elev']}, Azimuth {res['azim']}")
    print(f"Controls Target: x={res['target']['x']:.2f}, y={res['target']['y']:.2f}, z={res['target']['z']:.2f}")
    print(f"Sun Position:    x={res['sunPos']['x']:.2f}, y={res['sunPos']['y']:.2f}, z={res['sunPos']['z']:.2f}")
    z_dir = "South" if res['delta']['z'] >= 0 else "North"
    print(f"Delta (Sun - Target): dx={res['delta']['x']:.2f} (East), dy={res['delta']['y']:.2f} (Up), dz={res['delta']['z']:.2f} ({z_dir})")
    
    # Assertions
    # In scene coords: -Z is North, +Z is South
    if "Nov" in label or "2026-11-24" in date_str:
        assert res['delta']['z'] > 0, f"Expected light to be on SOUTH side (dz > 0), got dz={res['delta']['z']}"
        print(f"[ASSERT PASS] 2026-11-24 12:00 IST: deltaZ = +{res['delta']['z']:.2f} > 0 -> Light is on the SOUTH side of target.")
    elif "Jun" in label or "2026-06-21" in date_str:
        assert res['delta']['z'] < 0, f"Expected light to be on NORTH side (dz < 0), got dz={res['delta']['z']}"
        print(f"[ASSERT PASS] 2026-06-21 12:00 IST: deltaZ = {res['delta']['z']:.2f} < 0 -> Light is on the NORTH side of target.")
    return res

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            args=["--enable-webgl", "--ignore-gpu-blocklist", "--use-gl=angle", "--use-angle=metal"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await test_date(page, "2026-11-24", "Winter Noon (2026-11-24)")
        await test_date(page, "2026-06-21", "Summer Noon (2026-06-21)")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
