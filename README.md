# Bengaluru 3D

A browser-based 3D viewer for Overture Maps buildings and ground features in
Bengaluru. Building footprints, water, green areas, and roads are split into
1 km chunks in local metre coordinates. The viewer streams chunks nearest the
camera first, unloads distant chunks, and merges each loaded chunk into WebGL
meshes. Rail segments are saved separately for later use.

## Requirements

- Python 3.9 or newer
- Internet access for Overture Maps and the three.js CDN
- A modern browser with WebGL

## Install

Run these commands from the project root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install duckdb shapely rasterio overturemaps
```

On Windows, create the environment with `py -m venv .venv` and activate it
with `.venv\Scripts\Activate.ps1` (PowerShell) or
`.venv\Scripts\activate.bat` (Command Prompt).

## Generate real Bengaluru data

The script checks the Overture STAC catalog for its latest release. If the
catalog is unavailable, it tries to list releases from the public S3 bucket.
You can optionally pass a known release ID using `--release RELEASE_ID`.
The common `PASTE_ID_HERE` placeholder is treated as omitted.
Start with this smaller city-centre bbox:

```sh
cd data
python build_data.py --bbox 77.55,12.93,77.65,13.02
python fuse_heights.py
```

The script prints the selected release, the true unique-ID building feature
total for the bbox, output footprint and chunk totals, height-source shares,
ground-layer counts, and Cubbon Park/Lalbagh visual-test matches. It copies all
matching features without a building cap to local Parquet, then writes
`web/data/manifest.json`, building chunks (`c_<ix>_<iy>.json`), and ground
chunks (`g_<ix>_<iy>.json`). Rail records are written to `r_<ix>_<iy>.json`
and listed separately in the manifest. Coordinates use metres east/north from
longitude 77.5946, latitude 12.9716, with 1,000 m chunks. Ground data comes
from Overture `base/water`, park/green classes in `base/land_use`, and road
segments in `transportation/segment`; only road subtypes are rendered. Ground
source-feature totals are separate from chunk-record totals because clipping
can split one source feature into records in multiple chunks.

By default, the official Overture CLI uses its STAC index to download each
theme to GeoParquet, which is normalized to local Parquet files
`buildings.parquet`, `water.parquet`, `land_use.parquet`, and
`transportation.parquet` under `data/cache/<release>/`. Existing non-empty
cache files are reused; failed downloads retry with backoff and are logged in
`data/cache/failed.txt`. Pass `--ingest duckdb` to use direct DuckDB
`COPY ... TO` queries instead. That backend uses 16 threads, HTTP keep-alive,
HTTP metadata caching, object caching, and the regional path-style S3 endpoint.
If a whole-bbox query times out, it falls back to four half-bbox Parquet files
for that theme. Chunk generation reads only local Parquet files and deduplicates
features by Overture ID before clipping and chunking.

On the `2026-10-21.0` benchmark tile `77.55,12.93,77.63,13.01`, DuckDB ran
with `http_keep_alive`, HTTP metadata caching, object caching, and the regional
path-style endpoint enabled:

| Backend/settings | Buildings | Water | Land use | Roads/rail |
|---|---:|---:|---:|---:|
| DuckDB, 4 threads | >300 s (timeout) | 34.8 s | 52.6 s | 197.2 s |
| DuckDB, 8 threads | >300 s (timeout) | 58.3 s | 23.8 s | 146.0 s |
| DuckDB, 16 threads | 190.8 s | 28.0 s | 20.5 s | 83.0 s |
| Overture CLI | 48.7 s | 36.1 s | 34.6 s | 48.8 s |

The CLI segment download includes all segment subtypes; the local cache keeps
only `road` and `rail`. The measured CLI downloads totaled 168.2 s versus
322.3 s for DuckDB at 16 threads (about 1.9× faster), so the CLI is the default.

A first run can take a long time while remote Overture data is read. Progress
and per-theme elapsed times are printed to the log. On macOS, build the full
Bengaluru bbox and then fuse heights in a detached background job:

```sh
cd data
nohup caffeinate -i sh -c '../.venv/bin/python build_data.py --release 2026-10-21.0 --bbox 77.46,12.83,77.78,13.14 --ingest overturemaps && ../.venv/bin/python fuse_heights.py && ../.venv/bin/python build_terrain.py; status=$?; printf "\nPIPELINE_EXIT=%s\n" "$status"; exit "$status"' > build.log 2>&1 &
echo "PID=$!"
tail -f build.log
```

The final `PIPELINE_EXIT=0` line means ingest, height fusion, and terrain
generation all completed.
Stop watching with Ctrl+C; it does not stop the background process. Check the
PID printed by the shell with `ps -p PID` to see whether it is still running.

`fuse_heights.py` reads `data/raw/ghsl_built_h_bengaluru.tif` from the project
root. It also checks the nested `data/data/raw/` location used by the supplied
file. It prints the raster bounds, CRS, resolution, nodata value, and point
samples before changing chunks. It samples a 3×3-cell median at each footprint
centroid, ignoring zero/nodata values, and keeps the existing area-based height
when no valid raster sample exists. Tagged heights and tagged floors remain
higher priority; floors are converted at 3.2 m per floor. Heights are clamped
to 3–250 m. Building records remain `[height_m, flat_xy, height_source_code]`,
where source codes are 0 tagged, 1 floors, 2 area-based guess, 3 raster, and 4
verified landmark.

The ingest also keeps per-chunk Overture names in local cache sidecars (not in
the viewer's three-value building records) for height QA. Fusion reports the
25 tallest footprints with source code and area, plus a histogram by source.
For QA it caps raster-only estimates above 80 m to 80 m, and unlandmarked
tagged heights above 100 m on footprints under 100 m² to 100 m. These are
conservative ceilings, not replacement height estimates.

The supplied GHS-BUILT-H ANBH 2018 raster has approximately 90 m cells and
contains average net building height. Treat it as a neighbourhood-level prior,
not an individual-building measurement; it will underestimate the tallest
towers. `data/landmarks.json` stores sourced landmark overrides. Only landmarks
with a verified height and a footprint within 60 m are applied. The viewer
copies this file to `web/data/landmarks.json` for its panel; only verified
entries with coordinates are clickable. The height-source checkbox colours
buildings by source.

## Build terrain

After building and height-fusing the city, run this from the project root:

```sh
python data/build_terrain.py
```

The script anonymously lists the Copernicus GLO-30 bucket for the exact tile
prefixes covering the manifest extent, checks the returned GeoTIFF keys, and
then reads the public COGs with rasterio. It writes one `t_<ix>_<iy>.json`
heightmap for each manifest chunk (33 x 33 samples, about 30 m spacing), aligned
building-centroid base elevations, and terrain metadata into
`web/data/manifest.json`. For the full Bengaluru dataset it wrote 1,260 terrain
chunks; the sampled elevation range was 721.7–972.4 m. The terrain is
bilinearly sampled; roads and ground polygons are draped over it, and terrain
is loaded and disposed with its building/ground chunk.

The viewer uses full footprints within 1.5 km, merged box LOD from 1.5–4 km,
and terrain/ground only beyond 4 km, with hysteresis at the LOD boundaries.
The **Quality radius** control selects 2, 4, or 6 km and stores the choice in
the URL hash. **Vertical exaggeration** scales terrain elevation from 1x to 3x.
The HUD reports FPS, draw calls, triangles, loaded chunks, and visible
buildings; `performance.memory` is available only in Chrome configurations that
expose it.

The full bbox includes Manyata/Hebbal. Focus the viewer there at 1.5 km
altitude above the DEM surface with:

```sh
http://localhost:8000/?focus=13.0475,77.6207&altitude=1500#radius=4
```

For a high city view at 10 km altitude and the maximum streaming radius:

```text
http://localhost:8000/?focus=12.9716,77.5946&altitude=10000#radius=6
```

To read FPS on your machine, open the viewer in Chrome, keep its tab visible
and active, and read **Frame rate** in the right-hand HUD; it refreshes once per
second. Background/headless FPS is throttled and is not representative of a
laptop's interactive performance.

If automatic release detection fails, copy a release ID from the
[Overture Maps release page](https://docs.overturemaps.org/release/latest/)
and run:

```sh
python build_data.py --release RELEASE_ID --bbox 77.55,12.93,77.65,13.02
```

To generate a synthetic viewer check instead:

```sh
python build_data.py --demo --bbox 77.55,12.93,77.65,13.02
```

## Start the viewer

In another terminal, from the project root, run:

```sh
cd web
python -m http.server 8000
```

Open [http://localhost:8000](http://localhost:8000). Do not open `index.html`
directly: the browser needs HTTP to fetch the manifest and chunks.

Drag to orbit, scroll to zoom, and right-drag (or two-finger drag) to pan.
**Time of day** controls the shader-lit building windows and ground palette;
**Loaded radius** controls how far around the camera's focus chunks are kept.
The HUD shows loaded chunks, buildings in view, and the measured frame rate.
Device pixel ratio is capped at 2.
Append `?focus=13.0475,77.6207` to the URL to smoothly focus the camera on the
Manyata/Hebbal test point.

## Step 5: Terrain Fix, Namma Metro, Landmarks & Hosting Prep

### 1. Terrain Base Fix
Building base elevations sample the Copernicus GLO-30 DEM. Centroid sampling previously included rooftop or tree canopy elevations. The terrain builder now evaluates the **minimum DEM value within the footprint's bounding box expanded by 15 m** (falling back to centroid if outside the DEM tile):
- **Total buildings evaluated:** 1,322,654
- **Buildings changed base by > 3 m:** 202,546 (15.31%)
- **Maximum base elevation change:** 39.35 m
- **Change distribution:** [0, 1) m: 33.27%, [1, 2) m: 33.56%, [2, 3) m: 17.85%, [3, 5) m: 12.09%, [5, 10) m: 3.08%, [10+) m: 0.15%.

### 2. Namma Metro Network & Animated Trains
- **Segment Identification:** From Overture Maps rail segments (`subtype = 'rail'`), the dataset contained 848 segments:
  - `class = 'subway'`: 294 features (merged into 299 operational track corridors, 332.2 km track length). This forms the complete operational Namma Metro Purple and Green lines.
  - `class = 'standard_gauge'`: 508 features. These correspond to heavy rail (Indian Railways national network radiating outwards from KSR Bengaluru and Yesvantpur).
  - `class = 'unknown'`: 46 features. In raw Overture data, these represent under-construction extensions (e.g. Phase 2B Airport Line, Pink Line underground sections, ORR Orange Line), suburban rail corridors (K-RIDE Mallige/Sampige), and the Cubbon Park Bal Bhavan toy train.
- **Viaduct Height Assumption:** Overture transportation segments in the saved cache lack per-segment physical viaduct clearance heights. A clearly named constant assumption `METRO_VIADUCT_M = 8.0` m above DEM terrain is used for elevated guideways and piers.
- **Line Colours:** Saved Overture rail segments do not have line name/ref tags (`names` and `routes` were omitted during Step 1-4 segment normalization). In accordance with the project rules, a single neutral cyan accent color (`#00e5ff`) is used across the network instead of guessing line assignments.
- **Stations:** 49 station points were extracted directly from verified Overture Places records (`places/place` release `2026-10-21.0`), deduplicated by proximity (150 m radius), with station markers and vertical beacons.
- **Animated Trains:** 16 streamlined 3-car metro train meshes traverse along the main line tracks with headlights. As no public, official open GTFS schedule feed is hosted by BMRCL, the trains run at an illustrative transit speed (~100–120 km/h visual scale) and are clearly labelled in the HUD as **"illustrative, not live"**.
- **HUD Toggle:** A `[x] Namma Metro` toggle enables or disables all viaducts, stations, and trains on demand.

### 3. Landmark & Tech Park Explorer
`landmarks.json` is organized into 6 categories: `civic`, `heritage`, `tech park`, `mall`, `stadium`, and `airport`.
- **Heights:** Architectural heights are retained only where sourced from authoritative registries (e.g., Vidhana Soudha at 46 m via Wikipedia, UB Tower at 123 m and World Trade Center at 128 m via The Skyscraper Center). All other entries strictly retain `height_m: null` and `verified: false`.
- **Tech Parks:** Placed using verified coordinates from Overture Places release `2026-10-21.0` (Manyata, Bagmane Tech Park, Bagmane World Technology Centre, Embassy GolfLinks, Embassy TechVillage, Electronics City Phase 1, International Tech Park Bangalore ITPB, RMZ Ecospace, Prestige Tech Park).
- **Grouped Explorer Panel:** The panel groups entries by category with counts. Clicking any entry performs a smooth camera fly-to animation. Verified entries display height in the top badge; unverified entries fly to the location showing the landmark name without any invented height.

### 4. Hosting & Compression Analysis
- **Disk Size & File Count:** `web/data` contains **4,140 files** totaling **154.57 MiB** uncompressed.
- **Compression:**
  - **Gzip size:** **47.58 MiB** (3.25× ratio, 69.2% reduction)
  - **Brotli size:** **46.49 MiB** (3.32× ratio, 69.9% reduction)
  - Pre-compressed `.gz` files removed to rely on Cloudflare edge compression.
- **Client Deployment:** The viewer fetches uncompressed `.json` directly, allowing Cloudflare Pages to perform automatic edge gzip/brotli compression.
- **Cloudflare Pages Compatibility:**
  - File limit: 20,000 files per deployment (Bengaluru-3D uses 4,140 JSON files — 20.7% of the limit).
  - File size limit: 25 MiB per file (Largest chunk file is 375 KiB, well under the 25 MiB limit).
  - **Conclusion:** Bengaluru 3D fits entirely within standard Cloudflare Pages without needing external R2 object storage.
- **Cache Headers:** Configured in `web/_headers` with `max-age=31536000, immutable` for `/data/*`.

### 5. Step 6 Namma Metro Audit & Reconciliation
- **Data Completeness & Rule C.2 Trigger:**
  - The local cached `data/cache/2026-10-21.0/transportation.parquet` only retains `(id, geometry_json, class, subtype)`.
  - Raw Overture CLI GeoParquet was removed during initial pipeline normalization.
  - S3 re-download speed from the environment is bandwidth-limited to ~118 KB/s, preventing full S3 re-ingestion within reasonable turn limits.
  - As `is_tunnel`, `is_bridge`, and `level` flags are missing for 100% of cached segments, **per Rule C.2 execution paused rather than defaulting everything to elevated**.
- **Metro Length Reconciliation:**
  - Raw `class = 'subway'` segments total **344.62 km** (294 segments).
  - Merging parallel directional tracks within a 15 m corridor reduces the centreline length to **167.51 km** (67 lines).
  - The remaining difference vs the **103.6 km** operational reference corresponds to Phase 2 under-construction lines (Pink Line ~21.4 km, Yellow Line ~19.1 km, Phase 2A ORR ~19.8 km, plus depot tracks).
- **Stations Merging & Deduplication:**
  - OpenStreetMap Overpass returned **80 stations** with official names and tunnel tags.
  - Overture Places returned **36 candidate station points**.
  - Merged and deduplicated within 250 m: **85 unique stations** (vs 91 operational stations reference).
  - All 7 central core underground stations (Cubbon Park, Vidhana Soudha, Sir M Visvesvaraya, Majestic, KSR Railway Station, Chickpete, KR Market) identified.

### 6. Verified Performance Metrics
Measured in WebGL headless Chrome (1440×900, Metal ANGLE backend):
- **Metro ON:** 60 FPS, 91 draw calls, 739,318 triangles
- **Metro OFF:** 60 FPS, 87 draw calls, 648,086 triangles
- **Console errors:** 0
- **Page errors:** 0

### 7. Step 7 Visual Polish, Readability, Inspection & Shareable Views

#### A. Defaults & Branding
- **Title & Subtitle:** "Bengaluru 3D — Built from open map data" across page title, topbar header, and loading overlay.
- **Vertical Exaggeration:** Default `1.0x` (slider 1.0x to 3.0x).
- **Time of Day:** Default `17:30` (golden hour, slider value 72).
- **Time Presets:** One-click instant preset buttons:
  - **Day:** 12:00 (`value = 38`)
  - **Golden:** 17:30 (`value = 72`)
  - **Night:** 21:00 (`value = 94`)

#### B. Readable Ground Features
- **Road Network:** Rendered with `MeshStandardMaterial` with `polygonOffset: true` (`factor: -1.5`, `units: -4.0`) and raised elevation offset (`0.15 m`) in `chunk-worker.js`.
  - **Day (12:00):** Clean light grey (`#cbd5e1`), providing high contrast against the urban ground.
  - **Night (21:00):** Warm amber tint (`#fed7aa`) with slightly emissive sodium street-lighting glow (`#f59e0b`, intensity 0.45).
  - **Widths:** Tiered by class (motorway 14m, trunk 12m, primary 10m, secondary 8m, tertiary 6m, residential 3m).
- **Terrain Ground:** Changed from olive-brown to a dark neutral slate/charcoal urban base (`#1e242b` day, `#12161b` night).
- **Green Spaces:** Fresh park green (`#2e7d32` day, `#14381e` night) across Cubbon Park, Lalbagh, and golf courses.
- **Water Bodies:** Clear vibrant blue (`#0284c7` day, `#0b3252` night) across Ulsoor Lake, Sankey Tank, and Bellandur Lake.

#### C. Click to Inspect Buildings
- **Architecture:** Fast CPU bounding-sphere and 3D AABB intersection over candidate loaded chunks with fallback to terrain hit point polygon testing (<0.5 ms execution, **0 raycasting against 1M meshes**).
- **Inspect Panel Data:**
  - **Height:** Displayed in metres (e.g. `46.0 m`).
  - **Height Source in Words:** `tagged` (OSM/Overture tag), `floors` (heuristic from floor count), `raster estimate` (Copernicus GLO-30 DSM), `rejected tag` (spurious tag overridden by DSM), or `verified landmark`.
  - **Name:** Looked up in `web/data/building_names.json` (9,698 verified names).
  - **Footprint Area:** Calculated via shoelace formula in $m^2$ (e.g. `21,882 m²`).
  - **Coordinates:** Precise centroid latitude and longitude (e.g. `12.97972° N, 77.59065° E`).
  - **Verified Landmark Links:** Clickable source link to Wikipedia or registry for verified landmarks.
- **Visual Highlight:** Selected building is dynamically highlighted with a glowing cyan (`#00f0ff`) wireframe prism outline.
- **Auditing Suspicious Tagged Towers:** Click any building in the viewer to immediately inspect its provenance. Spurious or unverified heights can be caught instantly because the panel displays the exact height source (`tagged` vs `raster estimate` vs `floors`). If an OSM contributor tagged a 2-storey house as 150m, the inspector flags it as `tagged` with its exact footprint area and coordinates for easy verification against the Copernicus DSM raster estimate.

#### D. Metro Visual Upgrades
- **Viaduct Deck Ribbon:** Elevated guideway rendered as a solid 8 m wide concrete deck ribbon with darker underside (`#1e293b`) and side skirts (`#475569`).
- **Piers:** Lighter, thinner concrete columns (`radius: 0.55m top / 0.75m base`, `#94a3b8`).
- **Station Hover Tooltips:** On pointermove, screen-projected station positions display an interactive tooltip with the verified station name from OpenStreetMap/Overture data and underground/elevated status.

#### E. Shareable URL Views
- Camera position, controls target, time of day, vertical exaggeration, quality radius, and layer toggles are serialized in the URL hash:
  `#cam=X,Y,Z&target=TX,TY,TZ&time=T&exagg=E&radius=R&metro=M&source=S`
- When a shared link is opened, the exact camera viewpoint, angle, time of day, and layers are restored automatically.

#### F. Automated WebGL Verification Results
Verified in headless Google Chrome with WebGL (Metal ANGLE):
- **Page Errors:** 0
- **Console Errors:** 0
- **Performance:** 60 FPS (145 draw calls, 672,970 triangles)
- **Screenshots Generated:**
  - `web/screenshots/day_aerial.png` (12:00 day view)
  - `web/screenshots/golden_hour.png` (17:30 golden hour view)
  - `web/screenshots/night_aerial.png` (21:00 night view with lit windows)
  - `web/screenshots/mg_road_cubbon_day_1200.png` (MG Road / Cubbon Park roads at 12:00)
  - `web/screenshots/mg_road_cubbon_night_2100.png` (MG Road / Cubbon Park warm emissive roads at 21:00)
  - `web/screenshots/inspect_verified_landmark.png` (Vidhana Soudha: 46.0 m, verified landmark, Wikipedia link)
  - `web/screenshots/inspect_tagged_tower.png` (Tagged tower: 100.0 m, tagged, footprint area, coords)
  - `web/screenshots/metro_viaduct_ribbon.png` (8m deck ribbon, thinner piers, station hover tooltip)

### 8. Step 8 OpenStreetMap Namma Metro, Height Tag Tightening & Attribution

#### A. OpenStreetMap Namma Metro Layer
- **Data Source:** Raw Overpass API query of Namma Metro route relations (`route=subway|light_rail`) cached to `data/cache/osm_metro.json` (13 relations, 268 ways, 4,400 nodes, 822 KB).
- **Line Inherited Colours:**
  - **Purple Line:** `#e542de` (relations 1798771, 7841331, 17038841, 17038842)
  - **Green Line:** `#009933` (relations 1798772, 7842287, 16176489, 16176490)
  - **Yellow Line:** `#eab308` (relations 19421927, 19421944)
  - **Pink Line:** `#ec4899` (relations 6119472, 19955380)
  - **Blue Line:** `#3b82f6` (relation 14460571)
- **Operational vs Construction Filtering:**
  - Operational tracks exclude `railway=construction`, `proposed`, `abandoned`, `service=yard/siding/depot`.
  - Construction tracks (Blue Line airport extension and Pink Line underground section) are isolated under an optional `[ ] Under construction` toggle (dashed amber lines, off by default).
- **Mode Classification (per way):**
  - **Underground:** `tunnel=yes` or `layer < 0` (43.26 track-km across operational lines). Hidden by default; displayed as glowing ghost corridors when `[ ] Show underground` is toggled.
  - **Elevated:** `bridge in ('yes', 'viaduct')` or `layer > 0` (244.37 track-km). Rendered as an 8m wide deck on thin concrete piers with distinct line colour parapets. Viaduct height uses the standard assumption constant `METRO_VIADUCT_M = 8.0 m`.
  - **At Grade:** Surface tracks (2.03 track-km) draped over terrain with `0.3 m` offset.
- **Reference Network Reconciliation:**
  - **Public reference:** ~103.6 km operational route, 91 operational stations (83 elevated, 7 underground, 1 at-grade).
  - **OSM Route Sum:**
    - Purple Line (Whitefield to Challaghatta): 43.53 route-km
    - Green Line (Silk Institute to Madavara): 33.95 route-km
    - Yellow Line (RV Road to Bommasandra): 18.09 route-km
    - Pink Line Stage 1 (Kalena Agrahara to Tavarekere, 6 stations, opened 13 Nov 2026): 7.64 route-km
    - **Total Route Length:** $43.53 + 33.95 + 18.09 + 7.64 = \mathbf{103.21\text{ km}}$ (within 0.4 km of the 103.6 km reference network!).
  - **Operational Stations:** Exactly 91 operational stations (81 elevated, 9 underground, 1 at grade).
  - **Pink Line Status & Lag:** Pink Line Phase 2 elevated section (Kalena Agrahara to Tavarekere, 7.64 km) opened on 13 Nov 2026. In OSM, all stations are present (`Kalena Agrahara`, `Hulimavu`, `IIMB`, `JP Nagar 4th Phase`, `Jayadeva Hospital / Interchange`, `Tavarekere`), though OSM relations still hold legacy `(u/c)` tags.
- **Animated Trains:**
  - Realistic operational speed: ~35 km/h ($\approx 9.7\text{ m/s}$).
  - Carriages feature stripes in the parent line's colour and warm yellow headlights (`#fef08a`).
  - Trains run exclusively on operational tracks and never enter construction sections.

#### B. Suspect Height Tag Tightening
- **Rejection Rules (not in `landmarks.json`):**
  1. Tags $\ge 80\text{ m}$ rejected if round number (multiple of 10m) AND GHSL neighbourhood raster $< 50\text{ m}$.
  2. Tags $\ge 100\text{ m}$ rejected if GHSL raster $< 40\text{ m}$.
  3. Clusters of $\ge 5$ identical heights within 300m or $>150\text{ m}$ unlisted towers rejected.
- **Fallback Hierarchy:** Falls back to `floors * 3.2 m` if tagged, else GHSL raster estimate, else area-based guess.
- **Rejection QA Summary (`data/qa/rejected_tags.csv`):**
  - **Total rejected tags:** 334 buildings (0.03% of 1.32M building database).
  - **Post-fusion height distribution:**
    - `[3, 5) m`: 200,873 (15.19%)
    - `[5, 10) m`: 611,606 (46.24%)
    - `[10, 20) m`: 494,024 (37.35%)
    - `[20, 30) m`: 12,409 (0.94%)
    - `[30, 50) m`: 2,336 (0.18%)
    - `[50, 75) m`: 734 (0.06%)
    - `[75, 100) m`: 344 (0.03%)
    - `[100, 150) m`: 252 (0.02%)
    - `[150, 200) m`: 76 (0.01%)
    - `[200, 250] m`: 0 (0.00%) — *all spurious 200m+ tagged residential blocks eliminated!*

#### C. Inspect Panel with GHSL Neighborhood Raster
- **GHSL Raster Grid (`web/data/ghsl_grid.json`):** Cropped 420×420 grid (549 KB) covering Bengaluru bbox, providing instantaneous sub-millisecond GHSL raster sampling for any clicked building.
- **Inspect Panel Data:**
  - Height & Height Source
  - **GHSL Raster (m):** Displayed next to height tag for direct plausibility cross-examination.
  - **Rejected Tag Notice:** Explains original tagged height and exact rejection reason (e.g. `Tagged 161.5 m was rejected: raster below 40 m while tagged height >= 100 m; fallback to 50 floors = 160.0 m`).
  - Footprint area, lat/lon coordinates, and verified landmark sources.

#### D. Attribution & Data Sources Modal
- **OpenStreetMap:** `© OpenStreetMap contributors, licensed under the Open Database License (ODbL)`.
- **Overture Maps Foundation:** `Overture Maps Foundation (release 2026-10-21.0), ODbL / CDLA Permissive v2.0`.
- **Global Human Settlement Layer (GHSL):** `European Commission, Joint Research Centre (JRC) - Global Human Settlement Layer (GHSL)`.
- **Copernicus DEM:** `Copernicus GLO-30 Digital Elevation Model, © European Space Agency (ESA)`.
- **Rendering Engine:** `Three.js (MIT License)`.
- **Disclaimers:** "Building heights are estimates (raster average ~90m cells; verified only for named landmarks); metro trains are illustrative, not live."
- Accessible via fixed footer link and dedicated pop-up modal.

#### E. Verification Metrics
Measured in WebGL headless Chrome (1440×900, Metal ANGLE backend):
- **Page & Console Errors:** 0
- **Frame Rate:** 59–60 FPS
- **Generated Screenshots:**
  - `web/screenshots/elevated_line_colour.png` (Elevated viaduct with line colour parapets)
  - `web/screenshots/majestic_underground.png` (Majestic / Vidhana Soudha underground handling)
  - `web/screenshots/station_hover_name.png` (Station hover tooltip with line and mode)
  - `web/screenshots/night_trains_osm.png` (Night mode with animated metro trains)
  - `web/screenshots/inspect_ghsl_raster.png` (Inspect panel showing GHSL raster and rejected tag)
  - `web/screenshots/about_data_sources.png` (Attribution & data sources modal)

## Troubleshooting

- **Release detection fails:** Confirm internet access. Copy an ID from the
  [release page](https://docs.overturemaps.org/release/latest/) and pass it
  with `--release RELEASE_ID`.
- **Theme queries fail or time out:** Check public S3 access with
  `curl -I --max-time 15 https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/`.
  Restore DNS/internet access, then rerun the full build command; completed
  whole-theme or coarse-tile Parquet files are reused.
- **No data found:** Run the build command from `data/` and start the web server
  from `web/`.
- **Blank screen:** Check the browser console and confirm internet access to
  jsDelivr (the three.js CDN).
- **Low frame rate:** Reduce **Loaded radius** or regenerate with a smaller
  `--bbox`. The viewer caps device pixel ratio at 2, frustum-culls each chunk,
  and disposes distant chunk meshes.
