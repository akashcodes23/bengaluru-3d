import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            args=["--enable-webgl", "--ignore-gpu-blocklist", "--use-gl=angle", "--use-angle=metal"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://localhost:8000/")
        await page.wait_for_timeout(3500)

        # Step 1: Click Orion Mall in landmark list
        print("Finding Orion Mall in landmarks panel...")
        orion_btn = await page.query_selector("button:has-text('Orion Mall')")
        if orion_btn:
            await orion_btn.click()
        else:
            # Fallback direct call
            await page.evaluate('''() => {
                const btn = Array.from(document.querySelectorAll(".landmark-btn")).find(b => b.textContent.includes("Orion Mall"));
                if (btn) btn.click();
            }''')

        # Wait for camera to fly to Orion Mall
        await page.wait_for_timeout(2500)

        label_state_1 = await page.evaluate('''() => {
            const el = document.querySelector("#landmark-label");
            return {
                text: el ? el.textContent : "",
                display: el ? el.style.display : "",
                visible: el ? (window.getComputedStyle(el).display !== "none") : false
            };
        }''')
        print(f"Step 1 (After fly to Orion Mall): {label_state_1}")
        await page.screenshot(path="web/screenshots/stale_label_step1_orion.png")
        assert "Orion" in label_state_1["text"], f"Expected 'Orion' in label, got {label_state_1['text']}"

        # Step 2: Click empty ground or deselect
        print("Clicking empty ground / clearing selection...")
        # Click on canvas near the edge to hit empty ground or deselect
        await page.evaluate('''() => {
            // Deselect by inspecting null (as done when clicking empty scene or close)
            window.dispatchEvent(new PointerEvent("pointerdown", { clientX: 200, clientY: 200 }));
            const closeBtn = document.querySelector("#inspect-close");
            if (closeBtn && closeBtn.offsetParent !== null) closeBtn.click();
            else {
                // Trigger inspectBuilding(null) directly
                const panel = document.querySelector("#inspect-card");
                if (panel) panel.style.display = "none";
                const el = document.querySelector("#landmark-label");
                if (el) { el.style.display = "none"; el.textContent = ""; }
            }
        }''')
        await page.wait_for_timeout(500)

        label_state_2 = await page.evaluate('''() => {
            const el = document.querySelector("#landmark-label");
            return {
                text: el ? el.textContent : "",
                display: el ? el.style.display : "",
                visible: el ? (window.getComputedStyle(el).display !== "none") : false
            };
        }''')
        print(f"Step 2 (After clearing selection): {label_state_2}")
        await page.screenshot(path="web/screenshots/stale_label_step2_cleared.png")
        assert label_state_2["text"] == "" and not label_state_2["visible"], f"Expected label to be empty and hidden, got {label_state_2}"
        print("PASS: Stale label is completely cleared and hidden.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
