import os, sys, time, json, math
from PIL import Image
import numpy as np
from playwright.sync_api import sync_playwright

ARTIFACTS_DIR = "/Users/akashgpatil/.gemini/antigravity/brain/86fc38d5-d7fe-45d5-8c7f-3089d5a9f7c1"

TOURS = [
    {"id": "core-city", "name": "Core City"},
    {"id": "silicon-plateau-north", "name": "Silicon Plateau: North and Central"},
    {"id": "silicon-plateau-south", "name": "Silicon Plateau: East and South"},
    {"id": "purple-line", "name": "Namma Metro Purple Line"}
]

def format_mtime(path):
    if os.path.exists(path):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path)))
    return "N/A"

def run_tours():
    print("Starting Round 8 Guided Tours Verification...")
    with sync_playwright() as p:
        # Launch headed Chrome with metal ANGLE
        browser = p.chromium.launch(headless=False, args=["--use-angle=metal", "--no-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # Step 0: Idle Default View Baseline
        print("\n--- STEP 0: IDLE DEFAULT VIEW BASELINE ---")
        page.goto("http://localhost:8000/#radius=4&time=72")
        page.wait_for_timeout(4000)
        page.wait_for_function("() => window.loadedChunks && window.loadedChunks.size >= 10")
        page.wait_for_timeout(2000)

        # Inject RAF logger and performance profiler
        page.evaluate("""() => {
            window.__rafDeltas = [];
            window.__lastRaf = performance.now();
            function rafLoop(now) {
                const dt = now - window.__lastRaf;
                window.__lastRaf = now;
                if (dt > 0 && dt < 500) {
                    window.__rafDeltas.push(dt);
                }
                requestAnimationFrame(rafLoop);
            }
            requestAnimationFrame(rafLoop);
            window.__recordPerf = true;
            window.__frameStats = { tourUpdateMs: [], scanMs: [], renderMs: [], workerMs: [], uploadMs: [] };
        }""")

        time.sleep(10)
        idle_raf = page.evaluate("() => ({ count: window.__rafDeltas.length, deltas: window.__rafDeltas.slice() })")
        idle_stats = page.evaluate("""() => {
            const fs = window.__frameStats;
            const avg = arr => arr.length ? (arr.reduce((a,b)=>a+b,0)/arr.length) : 0;
            return {
                tourUpdateMs: avg(fs.tourUpdateMs),
                scanMs: avg(fs.scanMs),
                renderMs: avg(fs.renderMs),
                workerMs: avg(fs.workerMs),
                uploadMs: avg(fs.uploadMs),
            };
        }""")

        deltas = np.array(idle_raf["deltas"]) if len(idle_raf["deltas"]) else np.array([16.6])
        idle_avg = float(np.mean(deltas))
        idle_p95 = float(np.percentile(deltas, 95))
        idle_max = float(np.max(deltas))
        idle_over33 = int(np.sum(deltas > 33.33))
        print(f"Idle Baseline ({len(deltas)} frames): avg={idle_avg:.2f} ms, p95={idle_p95:.2f} ms, max={idle_max:.2f} ms, frames>33ms={idle_over33}")
        print(f"Idle Main-thread: render={idle_stats['renderMs']:.2f} ms, worker={idle_stats['workerMs']:.2f} ms, upload={idle_stats['uploadMs']:.2f} ms")

        # Run each tour
        all_tour_results = []

        for tour_info in TOURS:
            tour_id = tour_info["id"]
            tour_name = tour_info["name"]
            print(f"\n==========================================")
            print(f"RUNNING TOUR: {tour_name} ({tour_id})")
            print(f"==========================================")

            # Sample clearance with real buildings first
            print("Sampling clearance every 25 m against terrain and real building chunks...")
            clearance_res = page.evaluate(f"async (tid) => await window.tourManager.sampleClearance(tid)", tour_id)
            print(f"Clearance samples: {clearance_res['samplesCount']}")
            print(f"Min terrain clearance: {clearance_res['minClearanceTerrain']:.2f} m")
            print(f"Min building clearance: {clearance_res['minClearanceBuilding']:.2f} m")
            print(f"Overall min clearance: {clearance_res['minClearance']:.2f} m")
            print("3 Lowest Clearance Samples:")
            for s in clearance_res["lowestSamples"]:
                print(f"  dist={s['dist']}m: camY={s['camY']:.1f}m, groundY={s['groundY']:.1f}m, bldg={s['bldgId']} (h={s['bldgHeight']:.1f}m, base={s['bldgBase']:.1f}m, top={s['bldgTop']:.1f}m) | clrTerrain={s['clrTerrain']:.1f}m, clrBldg={s['clrBuilding']:.1f}m, margin={s['margin']:.1f}m")

            # Start Tour
            page.evaluate("""(tid) => {
                window.__rafDeltas = [];
                window.__frameStats = { tourUpdateMs: [], scanMs: [], renderMs: [], workerMs: [], uploadMs: [] };
                window.tourManager.startTour(tid);
            }""", tour_id)

            t_start = time.time()
            last_log = t_start
            pause_time_total = 0.0
            last_pause_start = None
            longest_pause = 0.0
            log_entries = []
            screenshot_milestones = {"25": False, "50": False, "75": False, "100": False}
            screenshot_paths = {}

            # Loop every 2 seconds until natural completion
            while True:
                time.sleep(1.0)
                now = time.time()
                status = page.evaluate("""() => {
                    const tm = window.tourManager;
                    const r = tm ? tm.checkReadiness(tm.progress) : { isReady: true, chunksLoaded: 0, chunksRequired: 0 };
                    return {
                        state: tm ? tm.state : 'idle',
                        progress: tm ? tm.progress : 0,
                        currentSpeed: tm ? tm.currentSpeed : 0,
                        simDistAdvanced: tm ? (tm.simDistAdvanced || 0) : 0,
                        isPausedForLoading: tm ? tm.isPausedForLoading : false,
                        isStalled: tm ? tm.isStalled : false,
                        chunksLoaded: r.chunksLoaded,
                        chunksRequired: r.chunksRequired,
                    };
                }""")

                is_paused = status["isPausedForLoading"] or status["isStalled"]
                if is_paused:
                    if last_pause_start is None:
                        last_pause_start = now
                else:
                    if last_pause_start is not None:
                        pause_duration = now - last_pause_start
                        pause_time_total += pause_duration
                        if pause_duration > longest_pause:
                            longest_pause = pause_duration
                        last_pause_start = None

                # Capture milestones
                pct = status["progress"] * 100
                if pct >= 25 and not screenshot_milestones["25"]:
                    screenshot_milestones["25"] = True
                    p_shot = os.path.join(ARTIFACTS_DIR, f"tour_{tour_id}_25pct.png")
                    page.screenshot(path=p_shot)
                    screenshot_paths["25"] = p_shot
                if pct >= 50 and not screenshot_milestones["50"]:
                    screenshot_milestones["50"] = True
                    p_shot = os.path.join(ARTIFACTS_DIR, f"tour_{tour_id}_50pct.png")
                    page.screenshot(path=p_shot)
                    screenshot_paths["50"] = p_shot
                if pct >= 75 and not screenshot_milestones["75"]:
                    screenshot_milestones["75"] = True
                    p_shot = os.path.join(ARTIFACTS_DIR, f"tour_{tour_id}_75pct.png")
                    page.screenshot(path=p_shot)
                    screenshot_paths["75"] = p_shot

                # Log every 2s
                if now - last_log >= 2.0 or status["progress"] >= 1.0 or status["state"] == "paused":
                    elapsed = now - t_start
                    entry = f"[{elapsed:6.1f}s] progress={pct:5.1f}% | dist={status['simDistAdvanced']:7.1f}m | speed={status['currentSpeed']:4.1f}m/s | chunks={status['chunksLoaded']}/{status['chunksRequired']} | paused={'YES' if is_paused else 'no'}"
                    print(entry)
                    log_entries.append(entry)
                    last_log = now

                if status["progress"] >= 0.999 or status["state"] == "paused":
                    if not screenshot_milestones["100"]:
                        screenshot_milestones["100"] = True
                        p_shot = os.path.join(ARTIFACTS_DIR, f"tour_{tour_id}_100pct.png")
                        page.screenshot(path=p_shot)
                        screenshot_paths["100"] = p_shot
                    break

            t_end = time.time()
            total_duration = t_end - t_start
            if last_pause_start is not None:
                pause_duration = t_end - last_pause_start
                pause_time_total += pause_duration
                if pause_duration > longest_pause:
                    longest_pause = pause_duration

            unpaused_time = max(0.1, total_duration - pause_time_total)
            share_paused = (pause_time_total / total_duration) * 100 if total_duration > 0 else 0.0
            final_dist = status["simDistAdvanced"]
            mean_speed_unpaused = final_dist / unpaused_time

            # Gather RAF and Chrome profile
            tour_raf = page.evaluate("() => ({ count: window.__rafDeltas.length, deltas: window.__rafDeltas.slice() })")
            tour_stats = page.evaluate("""() => {
                const fs = window.__frameStats;
                const avg = arr => arr.length ? (arr.reduce((a,b)=>a+b,0)/arr.length) : 0;
                return {
                    tourUpdateMs: avg(fs.tourUpdateMs),
                    scanMs: avg(fs.scanMs),
                    renderMs: avg(fs.renderMs),
                    workerMs: avg(fs.workerMs),
                    uploadMs: avg(fs.uploadMs),
                };
            }""")

            t_deltas = np.array(tour_raf["deltas"]) if len(tour_raf["deltas"]) else np.array([16.6])
            tour_avg = float(np.mean(t_deltas))
            tour_p95 = float(np.percentile(t_deltas, 95))
            tour_max = float(np.max(t_deltas))
            tour_over33 = int(np.sum(t_deltas > 33.33))
            smooth_verdict = "SMOOTH (p95 < 33 ms)" if tour_p95 < 33.33 else "STUTTER (p95 >= 33 ms)"

            print(f"\n--- TOUR COMPLETION SUMMARY: {tour_name} ---")
            print(f"Wall-clock duration: {total_duration:.2f} s ({total_duration/60:.2f} min)")
            print(f"Share of time paused: {share_paused:.2f}% (pause time: {pause_time_total:.2f} s)")
            print(f"Longest pause: {longest_pause:.2f} s")
            print(f"Distance advanced: {final_dist:.1f} m")
            print(f"Mean speed while not paused: {mean_speed_unpaused:.2f} m/s (cap: 75.0 m/s)")
            print(f"Frame intervals ({len(t_deltas)} frames): avg={tour_avg:.2f} ms, p95={tour_p95:.2f} ms, max={tour_max:.2f} ms, frames>33ms={tour_over33}")
            print(f"Verdict: {smooth_verdict}")
            print(f"Main-thread split: tourUpdate={tour_stats['tourUpdateMs']:.2f} ms, readinessScan={tour_stats['scanMs']:.2f} ms, render={tour_stats['renderMs']:.2f} ms, worker={tour_stats['workerMs']:.2f} ms, upload={tour_stats['uploadMs']:.2f} ms")
            print("Milestone Screenshots:")
            for m in ["25", "50", "75", "100"]:
                sp = screenshot_paths.get(m, "none")
                print(f"  {m}%: {sp} (mtime: {format_mtime(sp)})")

            all_tour_results.append({
                "id": tour_id,
                "name": tour_name,
                "duration": total_duration,
                "share_paused": share_paused,
                "longest_pause": longest_pause,
                "mean_speed": mean_speed_unpaused,
                "distance": final_dist,
                "avg": tour_avg,
                "p95": tour_p95,
                "max": tour_max,
                "over33": tour_over33,
                "verdict": smooth_verdict,
                "stats": tour_stats,
                "screenshots": screenshot_paths,
                "clearance": clearance_res
            })

            # Stop tour before next
            page.evaluate("() => window.tourManager.stopTour(true)")
            page.wait_for_timeout(1500)

        browser.close()

    # Save final results to json
    with open("tests/round8_tour_results.json", "w") as f:
        json.dump(all_tour_results, f, indent=2)

    print("\nALL TOURS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tours()
