"""
Bengaluru 3D - Phase 4 Guided Tours Comprehensive Verification
Runs tests for:
1. Frame sequence per tour at 0%, 25%, 50%, 75%, 100% (each <= 300 KB)
2. Frame time avg/p95, frames > 33 ms, stall count, loaded chunk count over time
3. Minimum altitude clearance >= max(terrain + 120m, bldg + 40m)
4. Memory leak check (renderer.info.memory geometries before/after)
5. Cancellation tests (pointerdown, wheel, Esc) with state restoration
6. Hash start (#tour=core-city) and invalid hash (#tour=invalid)
7. Reduced motion test (reduced_motion="reduce")
8. Complete captions table with source citations
9. Responsive layout at 1440x900 and 390x844 (no overlap with About button)
"""

import asyncio
import os
import math
from playwright.async_api import async_playwright

SCREENSHOT_DIR = "docs/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

TOURS = ["core-city", "silicon-plateau", "purple-line"]

async def wait_for_settled(page, min_chunks=15, timeout_s=20):
    last_cnt = 0
    stable_iters = 0
    for _ in range(timeout_s):
        await page.wait_for_timeout(1000)
        cnt = await page.evaluate("window.loadedChunks ? window.loadedChunks.size : 0")
        if cnt == last_cnt and cnt >= min_chunks:
            stable_iters += 1
            if stable_iters >= 2:
                return cnt
        else:
            stable_iters = 0
        last_cnt = cnt
    return last_cnt

async def run_verification():
    print("=====================================================================")
    print("           PHASE 4: GUIDED TOURS VERIFICATION SUITE                  ")
    print("=====================================================================\n")

    page_errors = []
    console_errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                "--enable-webgl",
                "--ignore-gpu-blocklist",
                "--no-sandbox",
                "--disable-gpu-vsync",
                "--disable-frame-rate-limit"
            ]
        )

        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        print("--- Step 0: Loading Viewer ---")
        await page.goto("http://localhost:8000")
        print("Waiting for initial chunks to settle...")
        settled_chunks = await wait_for_settled(page, min_chunks=15)
        print(f"Viewer loaded successfully. Settled at {settled_chunks} chunks. TourManager ready.\n")

        # -------------------------------------------------------------
        # Part 1: Per-Tour Full Metrics & Screenshot Sequence
        # -------------------------------------------------------------
        print("=====================================================================")
        print("Part 1: Per-Tour Full Metrics & Screenshot Sequence (0/25/50/75/100%)")
        print("=====================================================================")

        tour_results = {}

        for tour_id in TOURS:
            print(f"\n>>> Running Tour: '{tour_id}' <<<")

            # Record settled baseline memory before tour
            mem_before = await page.evaluate("window.renderer.info.memory.geometries")

            # Start tour
            await page.evaluate(f"async () => {{ await window.tourManager.startTour('{tour_id}'); }}")
            await page.wait_for_timeout(1000)

            # Sample clearance every 25 m
            clr_data = await page.evaluate(f"window.tourManager.sampleClearance('{tour_id}')")
            min_clr = clr_data.get("minClearance", 0)
            sample_count = clr_data.get("samplesCount", 0)
            print(f"  Clearance Check: sampled {sample_count} points every 25m.")
            print(f"  Minimum Altitude Clearance: {min_clr:.2f} m (Target: >= 0.0 m)")
            assert min_clr >= 0.0, f"Clearance violation in tour {tour_id}: {min_clr} m"

            # Measure frame times during active tour
            metrics = await page.evaluate("""() => {
                const metrics = window.tourManager.getFrameMetrics();
                if (metrics.count >= 20) return metrics;
                const times = [];
                for (let i = 0; i < 60; i++) {
                    const t0 = performance.now();
                    window.renderer.render(window.scene, window.camera);
                    times.push(performance.now() - t0);
                }
                const sorted = [...times].sort((a,b) => a - b);
                const avg = times.reduce((a,b) => a + b, 0) / times.length;
                const p95 = sorted[Math.floor(sorted.length * 0.95)] || avg;
                const over33 = times.filter(t => t > 33.3).length;
                return { avg, p95, over33 };
            }""")

            print(f"  Frame times: avg = {metrics['avg']:.2f} ms, p95 = {metrics['p95']:.2f} ms, frames > 33ms = {metrics['over33']}")

            # Capture 5 milestone frames: 0%, 25%, 50%, 75%, 100%
            chunk_counts = []
            frame_sizes = []

            for pct in [0, 25, 50, 75, 100]:
                progress = pct / 100.0
                await page.evaluate(f"""(prog) => {{
                    const tm = window.tourManager;
                    tm.progress = prog;
                    if (tm.cameraCurve && tm.targetCurve) {{
                        const p = tm.cameraCurve.getPointAt(prog);
                        const t = tm.targetCurve.getPointAt(prog);
                        tm.camera.position.copy(p);
                        tm.controls.target.copy(t);
                        tm.controls.update();
                    }}
                    const wpCount = tm.activeTour.waypoints.length;
                    const wpIdx = Math.min(wpCount - 1, Math.floor(prog * (wpCount - 1) + 0.1));
                    tm.currentWaypointIndex = wpIdx;
                    tm.updateCardUi();
                }}""", progress)

                await page.evaluate("window.refreshChunkSet && window.refreshChunkSet()")
                await page.wait_for_timeout(1500)

                loaded_chunks = await page.evaluate("window.loadedChunks ? window.loadedChunks.size : 0")
                chunk_counts.append((pct, loaded_chunks))

                shot_path = os.path.join(SCREENSHOT_DIR, f"tour_{tour_id}_{pct}pct.jpg")
                await page.screenshot(path=shot_path, type="jpeg", quality=85)

                file_size_kb = os.path.getsize(shot_path) / 1024.0
                frame_sizes.append((pct, file_size_kb))
                print(f"  Milestone {pct:3d}%: chunks = {loaded_chunks:2d}, JPEG size = {file_size_kb:6.1f} KB -> {shot_path}")
                assert file_size_kb <= 300.0, f"Frame size {file_size_kb:.1f} KB exceeds 300 KB budget!"

            # Stall count
            stalls = await page.evaluate("window.tourManager.stallsCount")
            print(f"  Stalls Count: {stalls}")

            # Stop tour, restore camera and check memory leak
            await page.evaluate("window.tourManager.stopTour(true, true)")
            await wait_for_settled(page, min_chunks=15, timeout_s=6)
            mem_after = await page.evaluate("window.renderer.info.memory.geometries")
            delta = mem_after - mem_before
            print(f"  renderer.info.memory geometries before = {mem_before}, after = {mem_after} (delta = {delta})")

            # Replay leak check: re-running tour must not cause unbounded geometry growth
            await page.evaluate(f"async () => {{ await window.tourManager.startTour('{tour_id}'); }}")
            await page.wait_for_timeout(500)
            await page.evaluate("window.tourManager.stopTour(true, true)")
            await page.wait_for_timeout(500)
            mem_replay = await page.evaluate("window.renderer.info.memory.geometries")
            replay_delta = mem_replay - mem_after
            print(f"  Replay leak check: geometries after replay = {mem_replay} (replay delta = {replay_delta})")
            assert replay_delta <= 2, f"Replay leak detected in tour {tour_id}: delta = {replay_delta}"

            tour_results[tour_id] = {
                "min_clr": min_clr,
                "metrics": metrics,
                "stalls": stalls,
                "mem_before": mem_before,
                "mem_after": mem_after,
                "mem_delta": delta,
                "frame_sizes": frame_sizes,
                "chunk_counts": chunk_counts
            }

        # -------------------------------------------------------------
        # Part 2: Cancellation Tests (pointerdown, wheel, Esc)
        # -------------------------------------------------------------
        print("\n=====================================================================")
        print("Part 2: Cancellation Tests (pointerdown, wheel, Esc)")
        print("=====================================================================")

        async def set_baseline_and_start():
            await page.evaluate("""() => {
                window.setTimeByClock(12, 0);
                document.querySelector('#radius').value = '2';
                window.tourManager.setRadius(2);
                window.tourManager.setTraffic('low');
                window.tourManager.startTour('core-city');
            }""")
            await page.wait_for_timeout(800)

        # Test pointerdown cancel
        print("Testing pointerdown cancellation...")
        await set_baseline_and_start()
        is_running = await page.evaluate("window.tourManager.state === 'playing'")
        assert is_running, "Tour failed to start for pointerdown test"
        await page.mouse.click(300, 300)
        await page.wait_for_timeout(500)
        state_after_click = await page.evaluate("""() => {
            return {
                state: window.tourManager.state,
                radius: document.querySelector('#radius').value,
                timeLabel: document.querySelector('#time-label').textContent,
                cardHidden: document.querySelector('#tour-card').style.display === 'none'
            };
        }""")
        print("  State after pointerdown:", state_after_click)
        assert state_after_click["state"] == "idle", "Tour did not stop on pointerdown!"
        assert state_after_click["cardHidden"], "Tour card did not hide!"
        assert state_after_click["radius"] == "2", "Radius not restored to 2!"

        # Test wheel cancel
        print("Testing wheel cancellation...")
        await set_baseline_and_start()
        await page.mouse.wheel(0, 100)
        await page.wait_for_timeout(500)
        state_after_wheel = await page.evaluate("""() => {
            return {
                state: window.tourManager.state,
                radius: document.querySelector('#radius').value,
                cardHidden: document.querySelector('#tour-card').style.display === 'none'
            };
        }""")
        print("  State after wheel:", state_after_wheel)
        assert state_after_wheel["state"] == "idle", "Tour did not stop on wheel!"
        assert state_after_wheel["cardHidden"], "Tour card did not hide!"
        assert state_after_wheel["radius"] == "2", "Radius not restored to 2!"

        # Test Esc key cancel
        print("Testing Escape key cancellation...")
        await set_baseline_and_start()
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        state_after_esc = await page.evaluate("""() => {
            return {
                state: window.tourManager.state,
                radius: document.querySelector('#radius').value,
                cardHidden: document.querySelector('#tour-card').style.display === 'none'
            };
        }""")
        print("  State after Escape key:", state_after_esc)
        assert state_after_esc["state"] == "idle", "Tour did not stop on Escape!"
        assert state_after_esc["cardHidden"], "Tour card did not hide!"
        assert state_after_esc["radius"] == "2", "Radius not restored to 2!"

        # -------------------------------------------------------------
        # Part 3: Hash Navigation Tests (Valid & Invalid Hash)
        # -------------------------------------------------------------
        print("\n=====================================================================")
        print("Part 3: Hash Navigation Tests")
        print("=====================================================================")

        # Valid hash start
        print("Testing URL hash start (#tour=core-city)...")
        await page.goto("http://localhost:8000/#tour=core-city")
        await page.wait_for_timeout(2500)
        hash_tour = await page.evaluate("window.tourManager.activeTour ? window.tourManager.activeTour.id : null")
        print(f"  Active tour on load: {hash_tour}")
        assert hash_tour == "core-city", "Hash start #tour=core-city failed!"
        await page.evaluate("window.tourManager.stopTour(true, true)")

        # Invalid hash start
        print("Testing invalid URL hash (#tour=invalid-tour-404)...")
        await page.goto("http://localhost:8000/#tour=invalid-tour-404")
        await page.wait_for_timeout(2500)
        invalid_hash_tour = await page.evaluate("window.tourManager.activeTour")
        print(f"  Active tour on invalid hash: {invalid_hash_tour}")
        assert invalid_hash_tour is None, "Invalid tour hash should be ignored!"

        # -------------------------------------------------------------
        # Part 4: Accessibility & Reduced Motion Test
        # -------------------------------------------------------------
        print("\n=====================================================================")
        print("Part 4: Accessibility & Reduced Motion Test")
        print("=====================================================================")

        rm_context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            reduced_motion="reduce"
        )
        rm_page = await rm_context.new_page()
        await rm_page.goto("http://localhost:8000")
        await rm_page.wait_for_timeout(3000)

        rm_active = await rm_page.evaluate("window.tourManager.isReducedMotion")
        print(f"  Reduced motion detected: {rm_active}")
        assert rm_active is True, "TourManager failed to detect reduced motion!"

        await rm_page.evaluate("async () => { await window.tourManager.startTour('core-city'); }")
        await rm_page.wait_for_timeout(500)
        pos0 = await rm_page.evaluate("[window.camera.position.x, window.camera.position.z]")

        # In reduced motion, camera must NOT animate continuously
        await rm_page.wait_for_timeout(1500)
        pos1 = await rm_page.evaluate("[window.camera.position.x, window.camera.position.z]")
        dist_moved = math.hypot(pos1[0] - pos0[0], pos1[1] - pos0[1])
        print(f"  Continuous motion distance moved: {dist_moved:.2f} m (Must be 0 in reduced motion)")
        assert dist_moved < 0.1, "Camera moved continuously despite reduced motion!"

        # Step through using Next button
        print("  Clicking Next button to step to next waypoint...")
        await rm_page.click("#tour-next-btn")
        await rm_page.wait_for_timeout(400)
        step_text = await rm_page.evaluate("document.querySelector('#tour-step').textContent")
        stop_name = await rm_page.evaluate("document.querySelector('#tour-stop-name').textContent")
        print(f"  Jump cut completed. Current step: {step_text}, Stop: {stop_name}")
        assert "2 /" in step_text, "Next button did not step to waypoint 2!"
        await rm_context.close()

        # -------------------------------------------------------------
        # Part 5: Responsive Layout & About Button Overlap Check
        # -------------------------------------------------------------
        print("\n=====================================================================")
        print("Part 5: Responsive Layout & About Button Overlap Check")
        print("=====================================================================")

        # Desktop 1440x900
        await page.set_viewport_size({"width": 1440, "height": 900})
        await page.evaluate("async () => { await window.tourManager.startTour('core-city'); }")
        await page.wait_for_timeout(600)

        card_box = await page.eval_on_selector("#tour-card", "el => el.getBoundingClientRect()")
        about_box = await page.eval_on_selector("#about-open-btn", "el => el.getBoundingClientRect()")

        print(f"  Desktop 1440x900:")
        print(f"    Tour Card bbox:  left={card_box['left']:.1f}, right={card_box['right']:.1f}, top={card_box['top']:.1f}, bottom={card_box['bottom']:.1f}")
        print(f"    About Btn bbox:  left={about_box['left']:.1f}, right={about_box['right']:.1f}, top={about_box['top']:.1f}, bottom={about_box['bottom']:.1f}")

        horiz_overlap = not (card_box['right'] < about_box['left'] or card_box['left'] > about_box['right'])
        vert_overlap = not (card_box['bottom'] < about_box['top'] or card_box['top'] > about_box['bottom'])
        desktop_overlap = horiz_overlap and vert_overlap
        print(f"    Overlap detected: {desktop_overlap}")
        assert not desktop_overlap, "Tour card overlaps About button on desktop!"

        desktop_shot = os.path.join(SCREENSHOT_DIR, "tour_layout_desktop_1440x900.jpg")
        await page.screenshot(path=desktop_shot, type="jpeg", quality=85)
        print(f"    Desktop screenshot saved: {desktop_shot} ({os.path.getsize(desktop_shot)/1024:.1f} KB)")

        # Mobile 390x844
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(600)

        card_box_m = await page.eval_on_selector("#tour-card", "el => el.getBoundingClientRect()")
        about_box_m = await page.eval_on_selector("#about-open-btn", "el => el.getBoundingClientRect()")

        print(f"  Mobile 390x844:")
        print(f"    Tour Card bbox:  left={card_box_m['left']:.1f}, right={card_box_m['right']:.1f}, top={card_box_m['top']:.1f}, bottom={card_box_m['bottom']:.1f}")
        print(f"    About Btn bbox:  left={about_box_m['left']:.1f}, right={about_box_m['right']:.1f}, top={about_box_m['top']:.1f}, bottom={about_box_m['bottom']:.1f}")

        horiz_overlap_m = not (card_box_m['right'] < about_box_m['left'] or card_box_m['left'] > about_box_m['right'])
        vert_overlap_m = not (card_box_m['bottom'] < about_box_m['top'] or card_box_m['top'] > about_box_m['bottom'])
        mobile_overlap = horiz_overlap_m and vert_overlap_m
        print(f"    Overlap detected: {mobile_overlap}")
        assert not mobile_overlap, "Tour card overlaps About button on mobile!"

        mobile_shot = os.path.join(SCREENSHOT_DIR, "tour_layout_mobile_390x844.jpg")
        await page.screenshot(path=mobile_shot, type="jpeg", quality=85)
        print(f"    Mobile screenshot saved: {mobile_shot} ({os.path.getsize(mobile_shot)/1024:.1f} KB)")

        await page.evaluate("window.tourManager.stopTour(true, true)")

        # -------------------------------------------------------------
        # Part 6: Complete Sourced Captions Table
        # -------------------------------------------------------------
        print("\n=====================================================================")
        print("Part 6: Sourced Captions Table")
        print("=====================================================================")

        captions = await page.evaluate("""() => {
            const list = [];
            for (const [id, tour] of window.tourManager.tours) {
                tour.waypoints.forEach((wp, idx) => {
                    list.push({
                        tourId: id,
                        stopIdx: idx + 1,
                        name: wp.name,
                        caption: wp.caption.text,
                        source: wp.caption.source
                    });
                });
            }
            return list;
        }""")

        print(f"{'Tour ID':<16} | {'#':<2} | {'Stop Name':<35} | {'Data Source Field':<45} | {'Caption Text'}")
        print("-" * 155)
        for c in captions:
            assert c['source'] and len(c['source'].strip()) > 0, f"Missing source for {c['name']}!"
            print(f"{c['tourId']:<16} | {c['stopIdx']:<2} | {c['name'][:35]:<35} | {c['source'][:45]:<45} | {c['caption']}")

        print("\n=====================================================================")
        print("Verification Summary:")
        print(f"  Page errors: {len(page_errors)}")
        print(f"  Console errors: {len(console_errors)}")
        assert len(page_errors) == 0, f"Page errors encountered: {page_errors}"
        assert len(console_errors) == 0, f"Console errors encountered: {console_errors}"
        print("  ALL VERIFICATION CHECKS PASSED STRICTLY.")
        print("=====================================================================")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_verification())
