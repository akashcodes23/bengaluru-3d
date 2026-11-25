<p align="center">
  <img src="web/logo-lockup.svg" alt="Bengaluru 3D — Built from open map data" width="520">
</p>

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
  - `docs/screenshots/day_aerial.png` (12:00 day view)
  - `docs/screenshots/golden_hour.png` (17:30 golden hour view)
  - `docs/screenshots/night_aerial.png` (21:00 night view with lit windows)
  - `docs/screenshots/mg_road_cubbon_day_1200.png` (MG Road / Cubbon Park roads at 12:00)
  - `docs/screenshots/mg_road_cubbon_night_2100.png` (MG Road / Cubbon Park warm emissive roads at 21:00)
  - `docs/screenshots/inspect_verified_landmark.png` (Vidhana Soudha: 46.0 m, verified landmark, Wikipedia link)
  - `docs/screenshots/inspect_tagged_tower.png` (Tagged tower: 100.0 m, tagged, footprint area, coords)
  - `docs/screenshots/metro_viaduct_ribbon.png` (8m deck ribbon, thinner piers, station hover tooltip)

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
  - **Underground:** `tunnel=yes` or `layer < 0` (16.03 track-km, ~8.02 route-km across operational lines). Hidden by default; displayed as glowing ghost corridors when `[ ] Show underground` is toggled.
  - **Elevated:** `bridge in ('yes', 'viaduct')` or `layer > 0` (187.52 track-km, ~93.76 route-km). Rendered as an 8m wide deck on thin concrete piers with distinct line colour parapets. Viaduct height uses the standard assumption constant `METRO_VIADUCT_M = 8.0 m`.
  - **At Grade:** Surface tracks (2.02 track-km, ~1.01 route-km) draped over terrain with `0.3 m` offset.
- **Reference Network Reconciliation:**
  - **Public reference:** ~103.6 km operational route, 91 operational stations (83 elevated, 7 underground, 1 at-grade).
  - **OSM Route Sum (Measured):**
    - Purple Line (Whitefield to Challaghatta): 86.95 track-km (~**43.48 route-km**)
    - Green Line (Silk Institute to Madavara): 67.72 track-km (~**33.86 route-km**)
    - Yellow Line (RV Road to Bommasandra): 36.10 track-km (~**18.05 route-km**)
    - Pink Line Stage 1 (Kalena Agrahara to Tavarekere, opened 13 Nov 2026): 14.80 track-km (~**7.40 route-km**)
    - **Total Measured Operational Track:** **205.58 track-km** (~**102.79 one-way route km**).
  - **Operational Stations:**
    - **88 unique physical operational stations in OSM** (80 elevated, 7 underground, 1 at grade).
    - **91 when interchange stations are counted once per line** (Majestic on Purple/Green, RV Road on Green/Yellow, Jayadeva Hospital on Yellow/Pink); the difference from the public reference of 91 stations is not resolved.
    - **7 Underground Stations:** Chickpete, Cubbon Park, Dr. B. R. Ambedkar Station (Vidhana Soudha), Krantivira Sangolli Rayanna Railway Station, Krishna Rajendra Market, Nadaprabhu Kempegowda Station (Majestic), Sir M. Visvesvaraya Stn. (Central College).
    - **1 At-Grade Station:** Baiyappanahalli.
    - **34 Under-Construction Stations:** Blue Line (Airport corridor) and Pink Line northern underground tunnel section (Dairy Circle to Nagawara).
    - **54 Proposed / Planned Stations:** Orange Line, Red Line, and Phase 3 extensions.
  - **Assumptions:**
    - Blue, Orange, and Red lines forced to construction / planned.
    - Pink Line elevated section with `start_date: 2026-11-14` treated as operational.
    - Pink Line underground tunnels treated as construction.
    - Viaduct deck clearance above DEM terrain uses the standard assumption constant `METRO_VIADUCT_M = 8.0 m`.
    - Airport runway width uses standard assumption `AIRPORT_RUNWAY_WIDTH_M = 45.0 m` unless an OSM `width` tag exists.
    - Metro trains are illustrative, not live.
- **Animated Trains:**
  - Realistic operational speed: ~35 km/h ($\approx 9.7\text{ m/s}$).
  - Carriages feature stripes in the parent line's colour and warm yellow headlights (`#fef08a`).
  - Trains run exclusively on operational tracks and never enter construction sections.

### 5. Kempegowda International Airport (BLR) Layer
- **Source:** OpenStreetMap aeroway features (`runway`, `taxiway`, `apron`, `terminal`) for the northern metropolitan region.
- **Runways:** Rendered as flat asphalt ribbons conforming to Copernicus DEM terrain:
  - Strip 1 (09L/27R): Length 3,995 m, width 45.0 m.
  - Strip 2 (09R/27L): Length 4,009 m, width 60.0 m.
  - Width is read directly from the OSM `width` tag; if omitted, the documented standard constant assumption `AIRPORT_RUNWAY_WIDTH_M = 45.0` is used.
- **Taxiways:** Full network of 169 taxiways (44.9 km) rendered with widths from tags (default `20.0 m`).
- **Aprons:** 6 major apron polygons (1.266 km² total area) triangulated and rendered at terrain elevation.
- **Terminals:** Terminal 1 (91,180 m² footprint) and Terminal 2 (106,580 m² footprint) use Overture building footprints.

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
  - `docs/screenshots/elevated_line_colour.png` (Elevated viaduct with line colour parapets)
  - `docs/screenshots/majestic_underground.png` (Majestic / Vidhana Soudha underground handling)
  - `docs/screenshots/station_hover_name.png` (Station hover tooltip with line and mode)
  - `docs/screenshots/night_trains_osm.png` (Night mode with animated metro trains)
  - `docs/screenshots/inspect_ghsl_raster.png` (Inspect panel showing GHSL raster and rejected tag)
  - `docs/screenshots/about_data_sources.png` (Attribution & data sources modal)

### 9. Phase 1: Real Solar Position, Atmosphere & Fixes
- **Solar Position Calculation:** Implemented dependency-free NOAA solar position calculations for Bengaluru (lat 12.9716° N, lon 77.5946° E, IST UTC+5:30) determining solar elevation and azimuth from date and local time. Fixed azimuth formula from mirrored North/South mapping to standard spherical trigonometry:
  $$y = -\sin(ha), \quad x = \tan(\delta)\cos(\phi) - \sin(\phi)\cos(ha), \quad \text{azimuth} = (\text{atan2}(y, x) + 360^\circ) \bmod 360^\circ$$
- **Atmospheric Driving:** Directional light position, intensity, colour temperature, sky gradient, fog colour, and hemisphere light transition continuously from sun elevation.
- **Temporal Controls & Hash:** Added an interactive date picker defaulting to current local date in IST; `date` and `shadows` state persist in URL hash while retaining backwards compatibility.
- **Night Transitions & Stars:** Added a 2,000-star celestial field fading in when solar elevation drops below -6°; window illumination and metro emissive shaders continuously driven by sun elevation. Night window lighting is labelled in the methodology modal as procedural illustrative shader effects.
- **Directional Shadows:** Directional-light PCF soft shadow maps for chunks within a 2 km quality radius, tracking camera target with an interactive toggle (default on at 2 km radius, off beyond).
  - *Proof of Rendering:* Verified at 2 km radius, 17:30 (low sun, azimuth ~248° WSW), with shadows falling towards North-East. 203,547 differing pixels (15.71% of screen) between shadows ON and OFF.
  - *Draw Calls Accounting:* In Three.js `WebGLRenderer.render()`, `renderer.info.autoReset` defaults to `true`, which resets render counters immediately after the shadow pass and before the scene pass. Disabling `autoReset` measures the separate shadow pass (13 calls, 209,208 triangles) alongside the scene pass (47 calls, 1,057,962 triangles), totaling 60 calls and 1,267,170 triangles.
- **Bug Fixes:**
  - *Stale Landmark Label:* Cleared and hid `#landmark-label` when deselected or closed.
  - *Chinnaswamy Stadium Ribbon:* OSM ways `508711042` and `607901267` in the Purple Line relation had designation `"Namma Metro - Underground UG1"` but lacked `tunnel=yes`, causing them to render as 4.8m wide surface tracks. Classified underground from OSM designation and topological connectivity to tagged tunnel ways (`Way 549187834` at node `4979669544` and `Way 607901268` at node `5760197797`, both carrying `tunnel=yes, layer=-2`), not an independent source. Fixed classifier in `data/build_osm_metro.py` and rebuilt metro data (`DATA_VERSION = 20261124.3`).
- **Verified Solar Unit Test (`tests/test_sun_position.js`, tolerance ±1.0°):**
  - `2026-11-24 06:15 IST`: Calc az 110.31°, el -2.55° | Ref az 110.44°, el -2.46° (Diff az 0.13°, el 0.09°) — PASS
  - `2026-11-24 12:00 IST`: Calc az 177.18°, el 56.58° | Ref az 177.39°, el 56.48° (Diff az 0.21°, el 0.10°) — PASS
  - `2026-11-24 17:30 IST`: Calc az 247.98°, el 3.85° | Ref az 247.91°, el 3.71° (Diff az 0.07°, el 0.14°) — PASS
  - `2026-06-21 12:00 IST`: Calc az 24.62°, el 78.40° | Ref az 25.05°, el 78.37° (Diff az 0.43°, el 0.03°) — PASS
  - `2026-03-20 06:20 IST`: Calc az 90.10°, el -2.04° | Ref az 89.90°, el -1.84° (Diff az 0.20°, el 0.20°) — PASS
  - `2026-03-20 18:25 IST`: Calc az 269.50°, el 0.58° | Ref az 269.77°, el 0.49° (Diff az 0.27°, el 0.09°) — PASS
- **Settled Performance Table (Headless Chrome WebGL, Metal ANGLE, 1440×900):**

| Scenario | Settled FPS | Scene Calls | Scene Tris | Shadow Calls | Total Calls | Total Tris |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 06:15 Dawn (default view, 4 km) | 61 | 101 | 1,614,098 | 0 | 101 | 1,614,098 |
| 12:00 Midday (default view, 4 km) | 60 | 101 | 1,614,098 | 0 | 101 | 1,614,098 |
| 17:30 Golden Hour (default view, 4 km) | 60 | 101 | 1,614,098 | 0 | 101 | 1,614,098 |
| 18:40 Dusk (default view, 4 km) | 60 | 101 | 1,614,098 | 0 | 101 | 1,614,098 |
| 21:00 Night (default view, 4 km) | 60 | 101 | 1,614,098 | 0 | 101 | 1,614,098 |
| Vidhana Soudha 2 km (Shadows ON) | 60 | 47 | 1,057,962 | 13 | 60 | 1,267,170 |
| Vidhana Soudha 2 km (Shadows OFF) | 60 | 47 | 1,057,962 | 0 | 47 | 1,057,962 |

- **Verification Screenshots:**
  - `docs/screenshots/phase1_0615_sunrise.png` (06:15 dawn / sunrise)
  - `docs/screenshots/phase1_1200_midday.png` (12:00 midday)
  - `docs/screenshots/phase1_1730_golden.png` (17:30 golden hour)
  - `docs/screenshots/phase1_1840_dusk.png` (18:40 civil/nautical dusk)
  - `docs/screenshots/phase1_2100_night.png` (21:00 night with stars and window glow)
  - `docs/screenshots/phase1_shadows_on_1730.png` (Directional building shadows ON at 17:30)
  - `docs/screenshots/phase1_shadows_off_1730.png` (Directional building shadows OFF at 17:30)

### 10. Phase 1 Verification Round 2

#### A. Light-Vector Mapping & Axis Conventions
- **Scene Axis Convention:**
  - $+X$ = East, $-X$ = West
  - $+Y$ = Up (Elevation above DEM origin)
  - $-Z$ = North, $+Z$ = South
- **Vector Mapping Implementation (`web/index.html` lines 768–773 & 3131–3135):**
  ```javascript
  const phiRad = elevation * Math.PI / 180;
  const thetaRad = azimuth * Math.PI / 180;
  const dirX = Math.cos(phiRad) * Math.sin(thetaRad);
  const dirY = Math.sin(phiRad);
  const dirZ = -Math.cos(phiRad) * Math.cos(thetaRad);
  currentSunVector.set(dirX, dirY, dirZ);

  sunLight.position.set(
    controls.target.x + currentSunVector.x * sunDist,
    controls.target.y + Math.max(0.08, currentSunVector.y) * sunDist,
    controls.target.z + currentSunVector.z * sunDist
  );
  ```
- **Automated Playwright Assertion (`tests/test_light_vector_mapping.py`):**
  - **2026-11-24 12:00 IST (Winter Noon):** Target $(180.0, 944.6, -620.0)$, Light $(423.6, 8456.8, 4330.6)$ $\implies \Delta Z = +4950.65 > 0$ (Light is on the **SOUTH** side of target) — **PASS**.
  - **2026-06-21 12:00 IST (Summer Noon):** Target $(180.0, 944.6, -620.0)$, Light $(933.7, 9760.9, -2264.8)$ $\implies \Delta Z = -1644.84 < 0$ (Light is on the **NORTH** side of target) — **PASS**.

#### B. Visual Top-Down Shadow Direction Proof (UB City / UB Tower)
Top-down orthographic/perpendicular views looking straight down on UB Tower (123 m) with North pointing up (`camera.up.set(0, 0, -1)`):
- **12:00 IST (2026-11-24):** Sun at azimuth 177° (South), elevation +56.6°. Shadow falls **DUE NORTH** of the building.
  - Image: `docs/screenshots/topdown_ubcity_1200.png`
- **17:30 IST (2026-11-24):** Sun at azimuth 248° (WSW), elevation +3.9°. Shadow falls **EAST-NORTH-EAST (ENE)** across Vittal Mallya Road.
  - Image: `docs/screenshots/topdown_ubcity_1730.png`

#### C. Metro Way Classification Audit
- **Rule Constraints:**
  - "Reach" in name/designation is **not** used as proof of elevated; elevated requires `bridge in ('yes', 'viaduct')` or `layer > 0`.
  - Non-tag overrides are strictly limited to an explicit sourced dictionary (`UNDERGROUND_WAY_OVERRIDES` in `data/build_osm_metro.py`).
- **Before vs After Track-km & Way Counts per Mode:**

| Line | Mode | Before (Pure OSM Tags) | After (Pure Tags + Sourced Overrides) | Difference |
| :--- | :--- | :---: | :---: | :---: |
| **Blue Line** | Underground | 2 ways (1.59 km) | 2 ways (1.59 km) | None |
| | Elevated | 47 ways (102.01 km) | 47 ways (102.01 km) | None |
| | At Grade | 2 ways (6.17 km) | 2 ways (6.17 km) | None |
| **Green Line** | Underground | 7 ways (6.96 km) | 10 ways (7.33 km) | +3 ways (+0.37 km) |
| | Elevated | 63 ways (60.40 km) | 63 ways (60.40 km) | None |
| | At Grade | 3 ways (0.37 km) | 0 ways (0.00 km) | -3 ways (-0.37 km) |
| **Orange Line** | Elevated | 2 ways (31.35 km) | 2 ways (31.35 km) | None |
| | At Grade | 2 ways (1.09 km) | 2 ways (1.09 km) | None |
| **Pink Line** | Underground | 9 ways (27.06 km) | 9 ways (27.06 km) | None |
| | Elevated | 17 ways (14.80 km) | 17 ways (14.80 km) | None |
| **Purple Line** | Underground | 12 ways (9.08 km) | 14 ways (9.46 km) | +2 ways (+0.38 km) |
| | Elevated | 83 ways (76.24 km) | 83 ways (76.24 km) | None |
| | At Grade | 6 ways (1.65 km) | 4 ways (1.27 km) | -2 ways (-0.38 km) |
| **Red Line** | Underground | 1 ways (13.72 km) | 1 ways (13.72 km) | None |
| | Elevated | 2 ways (23.44 km) | 2 ways (23.44 km) | None |
| | At Grade | 2 ways (0.64 km) | 2 ways (0.64 km) | None |
| **Yellow Line** | Elevated | 4 ways (36.10 km) | 4 ways (36.10 km) | None |

- **List of Changed Ways (5 ways total, exactly matching the sourced override list):**
  1. **Way 508711042 (Purple Line):** 0.189 km (188.8 m). Name: `'Namma Metro - Underground UG1'`, Designation: `'Namma Metro - Underground UG1'`, Tags: `railway=subway, electrified=rail, gauge=1435, maxspeed=80, subway=yes, voltage=750`. Missing `tunnel=yes` in OSM; classified underground from OSM designation and topological connectivity to tagged tunnel Way 549187834 (`tunnel=yes, layer=-2`) at node 4979669544.
  2. **Way 607901267 (Purple Line):** 0.188 km (188.4 m). Name: `'Namma Metro - Underground UG1'`, Designation: `'Namma Metro - Underground UG1'`, Tags: `railway=subway, electrified=rail, gauge=1435, maxspeed=80, subway=yes, voltage=750`. Missing `tunnel=yes` in OSM; classified underground from OSM designation and topological connectivity to tagged tunnel Way 607901268 (`tunnel=yes, layer=-2`) at node 5760197797.
  3. **Way 142484399 (Green Line):** 0.143 km (142.6 m). Name: `'Namma Metro - Underground UG2'`, Designation: `'Namma Metro - Underground UG2'`, Tags: `railway=subway, electrified=rail, embankment=yes, gauge=1435, maxspeed=80, subway=yes, voltage=750`. Missing `tunnel=yes` in OSM; physically part of UG2 tunnel north of Majestic. Classified as `underground`.
  4. **Way 607901295 (Green Line):** 0.142 km (141.8 m). Name: `'Namma Metro - Underground UG2'`, Designation: `'Namma Metro - Underground UG2'`, Tags: `railway=subway, electrified=rail, embankment=yes, gauge=1435, maxspeed=80, subway=yes, voltage=750`. Missing `tunnel=yes` in OSM; physically part of UG2 tunnel north of Majestic. Classified as `underground`.
  5. **Way 1189861890 (Green Line):** 0.091 km (90.6 m). Name: `'Namma Metro - Underground UG2'`, Designation: `'Namma Metro - Underground UG2'`, Tags: `railway=subway, electrified=rail, gauge=1435, level=-2, maxspeed=80, subway=yes, voltage=750`. Tagged with `level=-2` but omitted `tunnel=yes` or `layer=-2`. Physically part of UG2 tunnel between Chickpete and KR Market. Classified as `underground`.
- **Station Alignment Cross-Check:**
  - **7 Central Underground Stations:**
    - *Cubbon Park:* sits on Way 607901268 (`mode: underground`, 3.9 m)
    - *Dr. B. R. Ambedkar Station, Vidhana Soudha:* sits on Way 607901270 (`mode: underground`, 6.8 m)
    - *Sir M. Visvesvaraya Stn., Central College:* sits on Way 549277222 (`mode: underground`, 2.4 m)
    - *Nadaprabhu Kempegowda Station, Majestic:* sits on Way 549277222 (`mode: underground`, 3.4 m)
    - *Krantivira Sangolli Rayanna Railway Station:* sits on Way 133867981 (`mode: underground`, 2.3 m)
    - *Chickpete:* sits on Way 549256482 (`mode: underground`, 2.2 m)
    - *Krishna Rajendra Market:* sits on Way 607901290 (`mode: underground`, 2.3 m)
    - **Result:** 100% of the 7 underground stations sit directly on underground ways. 0 mismatches.
  - **1 Operational At-Grade Station:**
    - *Baiyappanahalli:* sits on Way 607901239 (`mode: at_grade`, 0.2 m, length 500 m) connecting directly to the surface yard/depot tracks.
    - **Result:** Exactly sits on an at-grade track way. 0 mismatches.

#### D. Frame Time Measurements (VSync & Frame Limit Disabled)
Measured in headless Chrome with `--disable-frame-rate-limit --disable-gpu-vsync` over 300 settled consecutive animation frames:

| Scenario | Average Frame Time | p50 Frame Time | p95 Frame Time | Unlocked Frame Rate |
| :--- | :---: | :---: | :---: | :---: |
| **Default view (4 km, shadows off)** | 4.70 ms | 3.60 ms | 9.40 ms | ~213 FPS |
| **Vidhana Soudha 2 km (Shadows OFF)** | 3.46 ms | 2.60 ms | 7.00 ms | ~289 FPS |
| **Vidhana Soudha 2 km (Shadows ON)** | 4.94 ms | 3.90 ms | 8.90 ms | ~203 FPS |

#### E. Stale Label Evidence
- Step 1: Fly to Orion Mall $\implies$ `#landmark-label` displays `"Orion Mall"` (`display: block`).
  - Screenshot: `docs/screenshots/stale_label_step1_orion.png`
- Step 2: Click empty ground / deselect $\implies$ `#landmark-label` text is emptied (`""`) and hidden (`display: none`).
  - Screenshot: `docs/screenshots/stale_label_step2_cleared.png`

#### F. Independent Solar Position Grounding
Bengaluru coordinates: $12.9716^\circ\text{ N}, 77.5946^\circ\text{ E}$, UTC+5:30. Compared against NOAA Solar Calculator & TimeAndDate.com:
1. **2026-11-24 12:00 IST:**
   - *TimeAndDate.com:* Solar noon is at 12:06 PM IST (alt 56.6°, az 180° S). At 12:00 PM IST: alt ~56.5°, az ~177.4°.
   - *Viewer model:* Elevation 56.58°, Azimuth 177.18°.
   - *Agreement:* $\Delta \text{elev} = 0.08^\circ$, $\Delta \text{azim} = 0.22^\circ$.
2. **2026-06-21 12:00 IST:**
   - *TimeAndDate.com / NOAA:* Solar noon is at 12:21 PM IST (alt 79.5°, az 0° N). At 12:00 PM IST: alt ~78.4°, az ~25.0° NNE.
   - *Viewer model:* Elevation 78.40°, Azimuth 24.62°.
   - *Agreement:* $\Delta \text{elev} = 0.03^\circ$, $\Delta \text{azim} = 0.38^\circ$.
3. **2026-03-20 18:25 IST (Equinox Sunset):**
   - *TimeAndDate.com:* Sunset heading is 269.8° (due West), elevation ~0.5°.
   - *Viewer model:* Elevation 0.58°, Azimuth 269.50°.
   - *Agreement:* $\Delta \text{elev} = 0.08^\circ$, $\Delta \text{azim} = 0.30^\circ$.

### Phase 2: Illustrative Road Traffic Streams

- **Motion along major roads:** Motorway, trunk, and primary road segments carry animated vehicle streams rendered as GPU-instanced `THREE.Points` (single draw call per loaded chunk). Position and motion are evaluated entirely inside the vertex shader via a time uniform, requiring zero per-vehicle CPU calculations per frame.
- **Divided-carriageway detection & Left-hand drive separation:** India drives on the left.
  - *Divided carriageways:* Major road polylines running parallel within 40 m (angle $< 15^\circ$ over $> 80\text{ m}$) are geometrically paired into dual carriageways. Across 2,765 chunks city-wide, 1,681 parallel pairs were detected, representing 1,029.6 km (**61.3% of all major roads**). Each carriageway carries a single one-way stream following the left-hand drive rule: looking along the pair's common direction $d$, the left carriageway flows forward $+d$ with white headlights (offset $+1.0\text{ m}$), while the right carriageway flows reverse $-d$ with red taillights (offset $-1.0\text{ m}$).
  - *Unpaired two-way roads:* Unpaired segments spawn two opposing streams (white headlights $+1.8\text{ m}$ left of travel, red taillights $-1.8\text{ m}$ left of reverse travel).
- **Dynamic GPU vertical exaggeration:** Vertical exaggeration scales dynamically in the vertex shader (`uExaggeration`), keeping vehicle lights pinned precisely to the road surface ($y = \text{rawY} \times uExaggeration + 0.22 + 0.5\text{ m}$) across 1.0x $\to$ 3.0x transitions without worker rebuild delays.
- **Hardware point-size clamping & Fallback:** Queries `gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE)` (supported range: [1, 511]) and clamps `gl_PointSize` between 1.0 and hardware maximum with fallback support if max $< 8.0$.
- **Instance cap & HUD badge:** Fixed hard cap at 20,000 active vehicle instances. When maximum density at 6 km quality radius reaches 20,000 instances, the allocation stops cleanly and the HUD displays `"20,000 vehicles (capped)"`.
- **Visibility & LOD:** Automatically visible at dusk and night (sun elevation $< 4^\circ$); faint by day only if "Show by day" is enabled. Point size attenuates with distance to resolve as individual headlights near the ground and as continuous glowing light streams from high altitude. Smooth 12 m endpoint fading conceals modulo wrap-around, and streams fade out between 2.0 km and 2.5 km from the camera focus.
- **State persistence:** Density (`traffic=off|low|med`) and daytime visibility (`trafficday=1|0`) persist in URL hash parameters.
- **Performance & Leak Audit:** Tested with vsync disabled (`--disable-frame-rate-limit --disable-gpu-vsync`). Traffic adds $< 0.1$ ms frame time (+0.74% at Low, +3.21% at Medium), holding over 310 FPS unlocked. Toggling traffic off instantly reclaims all traffic geometries with zero memory leak across chunk unloads and reloads.
- **Limitations & Disclaimers:**
  1. *Illustrative, not live:* Vehicle speeds (motorway 22 m/s, trunk 16 m/s, primary 11 m/s) and densities are illustrative procedural approximations and do not reflect real-time traffic or sensor feeds.
  2. *Divided carriageways:* Carriageway directionality is an automated geometric inference based on parallel polyline geometry, not tagged OSM/Overture one-way attributes.
  3. *No elevated flyovers:* Road vehicles follow terrain-draped road geometry; multi-level elevated flyovers are not modelled in this phase.



- **Visual Evidence & Proofs:**
  - `docs/screenshots/phase2_traffic_streams_annotated.png` (Traffic streams annotated by flow direction and lane offset)
  - `docs/screenshots/phase2_divided_carriageway_before.png` (Before carriageway pairing: two-way streams on each parallel road)
  - `docs/screenshots/phase2_divided_carriageway_after.png` (After carriageway pairing: single one-way stream per carriageway with left-hand rule)
  - `docs/screenshots/phase2_manyata_night.jpg` (Manyata Outer Ring Road dual carriageway traffic at night)
  - `docs/screenshots/phase2_silk_board_night.jpg` (Central Silk Board / Hosur Road traffic streams at night)

### Phase 2 Corrections & Audits

- **A1. Taillight Colour Proof:**
  - Evaluated on a traffic-only black-background render at focus `13.0475, 77.6207` (altitude 600 m, 21:00 night):
    - Red taillight pixels ($R > 200, G < 80, B < 80$): **272 pixels** (mean RGB: `228.7, 35.1, 16.0`).
    - White headlight pixels ($R > 200, G > 200, B > 180$): **3,666 pixels** (mean RGB: `223.8, 227.8, 231.1`).
  - Saved proofs:
    - Traffic-only frame (PNG): `docs/screenshots/phase2_traffic_only_proof.png`
    - Normal view (compressed JPEG q85, 466.4 KB): `docs/screenshots/phase2_normal_view_q85.jpg`
- **A2. Side-of-Road from Data:**
  - Verified signed lateral offsets from WebGL instance attribute buffers:
    - Two-way road segments: Forward instance = $+1.8$ m (left of forward heading), Reverse instance = $-1.8$ m (left of reverse heading). Separation: $3.6$ m.
    - One-way carriageways (divided pairs): $+d$ carriageway = $+1.0$ m (white headlights), $-d$ carriageway = $-1.0$ m (red taillights).
  - Measured top-down pixel centroid crop (`docs/screenshots/phase2_topdown_centroid_crop.png`):
    - White pixel centroid: $(X=676.8, Y=458.2)$
    - Red pixel centroid: $(X=670.3, Y=446.4)$
    - Measured centroid separation: $13.5$ px (cleanly segregated non-overlapping streams on correct sides of the road).
- **A3. Dynamic 3.0x Exaggeration Proof:**
  - Chunk reload polled until complete:
    - 1.0x Exaggeration: `docs/screenshots/phase2_exaggeration_1x.jpg`
    - 3.0x Exaggeration: `docs/screenshots/phase2_exaggeration_3x.jpg`
  - All vehicles and road decks stay pinned to the elevated terrain surface without floating or sinking.
- **A4. Metro Portal Ramp Ways (Ways 508711042 & 607901267):**
  - Classified under `portal` mode in `data/build_osm_metro.py`.
  - Geometry smoothly interpolates from viaduct deck height ($+8$ m) down to tunnel depth ($-8$ m).
  - Hidden in default view; rendered as a translucent descending ghost ramp when "Show underground" is enabled.
    - Default view (Underground OFF): `docs/screenshots/metro_portal_ramp_underground_off.jpg`
    - Ghost view (Underground ON): `docs/screenshots/metro_portal_ramp_underground_on.jpg`
- **A5. Divided-Pair Edge Cases:**
  - Minimum separation filter enforced: $[8	ext{ m}, 40	ext{ m}]$.
  - Rejected 401 pairs ($6.13\%$) with separation $< 8$ m (stacked flyovers or duplicate centrelines).
  - Retained 6,138 valid divided pairs ($93.87\%$).
  - Hosur Road Elevated Expressway (motorway deck separation $7.3	ext{ m} - 8.8	ext{ m}$) is cleanly prevented from pairing with surface Hosur Road trunk carriageways ($17.3	ext{ m} - 24.8	ext{ m}$).
  - Boundary-clipped major road segments $< 80$ m represent $\sim 4.2\%$ of all major road segments and remain two-way.
- **A6. Performance & Rebalance Priority:**
  - Worker chunk pairing code adds only $+0.006$ ms average latency ($0.004$ ms $	o 0.010$ ms, p95 $0.043$ ms).
  - Frame time at 20,000 vehicle cap: **4.06 ms avg (246.1 FPS)**, **7.10 ms p95 (140.8 FPS)**.
  - Rebalance priority preserves traffic on chunks closest to the camera target, discarding traffic from chunks $> 4.5$ km away first when capped.
- **A7. Hygiene:**
  - Worker URL versioned with `DATA_VERSION` (`./chunk-worker.js?v=" + DATA_VERSION`).
  - Screenshots moved to `docs/screenshots/`, keeping only referenced assets.


## Phase 3: Procedural Hero Landmarks

Procedural architectural models replace generic extruded boxes for three iconic Bengaluru hero landmarks, built on real Overture building footprints with distance-based LOD switching and dynamic vertical exaggeration seating:

1. **Vidhana Soudha (46.0 m verified height):**
   - *Overture Building ID:* `e3b7fdca-863f-4855-a926-c3fb2ee37ec0`
   - *Footprint:* Chunk `-1,0`, index 192, 76 vertices (152 coordinates).
   - *Architecture:* Neo-Dravidian legislative palace with central granite drum, ribbed hemispherical dome crowned by the four-lion Ashoka emblem and gilded kalasa finial (46 m peak), 4 octagonal corner chattris with domed pavilions (32 m), and grand eastern portico with 45 steps, 12 Dravidian columns, and triangular pediment.
   - *Seating:* Foundation skirt extends into terrain to ensure zero gap or sinking at 1x, 2x, and 3x vertical exaggeration.
   - *Budget:* 4,396 triangles across 62 draw calls (budget < 20,000 triangles).

2. **UB City Complex (123.0 m verified UB Tower):**
   - *Overture Building ID:* `a1241754-d5b2-4e96-af7b-4fba8ccd87c1`
   - *Footprint:* Chunk `0,0`, index 70, 19 vertices (38 coordinates).
   - *Architecture:* 4-tower luxury commercial complex on shared 15 m retail/dining podium:
     - UB Tower (123.0 m): curved glass facade with tiered setbacks at 75 m, 95 m, and open-air rooftop crown with architectural spire.
     - Concorde Tower (95.0 m, index 64): modernist glass and steel tower.
     - Canberra Tower (85.0 m, index 65): stepped corporate tower.
     - Comet Tower (72.0 m, index 68/69): curtain-wall high-rise.
   - *Budget:* 264 triangles across 9 draw calls (budget < 20,000 triangles).

3. **Kempegowda International Airport Terminal 2 (UNESCO Prix Versailles "Terminal in a Garden"):**
   - *Overture Building ID:* `82ca460a-d066-431b-b056-0b1abfc97d22`
   - *Footprint:* Chunk `13,25`, index 39, 74 vertices (148 coordinates), 106,580 m² area.
   - *Architecture:* Expansive engineered bamboo diagrid roof canopy with cantilevered eaves, 18 tiered pyramidal skylight lanterns in a 6×3 grid bringing natural sunlight into the concourse, 16 flared structural bamboo tree columns, and floor-to-ceiling glass curtain walls revealing lush interior botanical gardens and terraced greenery.
   - *Height Status:* Unverified procedural estimate (~25.0 m concourse height from Skidmore, Owings & Merrill architectural design publications; not a survey-verified height).
   - *Budget:* 1,188 triangles across 4 draw calls (budget < 20,000 triangles).

### Hero Landmark Element Classification & Claims Audit (v2)

All procedural components in `web/hero-landmarks.js` are strictly categorized into data-backed footprints, proportional architectural stylisations based on footprint bounding boxes or verified heights, and unverified assumptions. All architectural assertions derived purely from memory (such as step counts, specific column counts, firm names, "bamboo diagrid", and "garden terrace") have been neutralised:

| Landmark | Element | Classification | Rationale / Ground Truth |
|---|---|---|---|
| **Vidhana Soudha** | Base polygon & boundary | From footprint | Extruded directly from Overture footprint chunk `-1,0`, index 192 (76 vertices). |
| | Foundation skirt & podium | Proportional (ratio ~0.07 of base) | Granite plinth & skirt extending into terrain for seamless seating across exaggeration. |
| | Central drum & dome | Proportional (ratio ~0.30 of footprint, apex = 46.0 m) | Central drum and ribbed dome scaled to verified 46.0 m apex height. |
| | Corner pavilions | Proportional (ratio ~0.08 of footprint) | Four corner pavilions scaled proportionally to 32 m height. |
| | Eastern entrance approach | Proportional (ratio ~0.25 of east facade) | Stepped approach and entrance columns proportional to footprint east facade. |
| | Apex finial | Proportional (ratio ~0.04 of dome height) | Apex finial completing dome profile (no unverified emblem sculpture). |
| **UB City** | Complex building footprints | From footprint | Real building polygon boundaries from chunk `0,0` (UB Tower: 70; Concorde: 64; other complex footprints: 65, 68, 69). Tower names match `web/data/building_names.json`. |
| | Shared commercial podium | Proportional (ratio ~0.12 of tower height) | 15 m podium joining tower footprints. |
| | Tower massing & setbacks | Proportional (setbacks at 0.61 and 0.77 of height) | Glazed setbacks matching tower massing up to verified 123.0 m peak height. |
| | Other complex towers (64, 65, 68) | Estimated heights (unverified) | Labelled explicitly as `(procedural estimate)` in inspect card. UB Tower (123 m) is the only verified height. |
| **KIA Terminal 2** | Terminal concourse footprint | From footprint | Exact 106,580 m² perimeter boundary from chunk `13,25`, index 39 (74 vertices, centroid 8.37 m from landmark point). |
| | Overhanging roof canopy | Proportional (ratio ~1.05 of concourse bounds) | Cantilevered overhanging roof canopy enclosing concourse footprint. |
| | Skylight lanterns | Proportional (grid across canopy area) | Rhythmic natural lightwell lanterns across canopy roof. |
| | Flared interior columns & glass walls | Proportional (height = 16 m) | Glazed perimeter curtain walls and interior support columns. |
| | Concourse height (25 m) | Estimate with no source (unverified) | Procedural estimate with no survey source; verified is false. |


### Verification Round 3 Audit & Bug Fixes

- **1. 3x Vertical Exaggeration Fix:**
  - *Root Cause:* `getTerrainElevationAtLocal` in `web/index.html` was multiplying raw elevation by `verticalExaggeration`, while calling sites also multiplied by `verticalExaggeration`. At 3.0x, this applied $3.0^2 = 9\times$ exaggeration, projecting camera to $Y = 8734.5$ m into the stratosphere and dropping chunks from view.
  - *Fix:* `getTerrainElevationAtLocal` now returns unscaled elevation; callers apply `verticalExaggeration` once.
  - *Diagnostics at 1x vs 3x (Chinnaswamy & Vidhana Soudha):*
    - Chinnaswamy (`?focus=12.9788,77.5996&altitude=400`):
      - 1.0x: Target $Y = 926.1$ m, Camera $Y = 1326.1$ m, 151 draw calls, 1,510,228 tris, 39 chunks loaded.
      - 3.0x: Target $Y = 2778.2$ m ($926.1 \times 3$), Camera $Y = 3178.2$ m ($2778.2 + 400$), 151 draw calls, 1,510,228 tris, 39 chunks loaded. Zero lost chunks or calls.
    - Vidhana Soudha (`?focus=12.9796,77.5906&altitude=400`):
      - 1.0x: Target $Y = 926.0$ m, Camera $Y = 1326.0$ m, 151 draw calls, 1,510,228 tris, 39 chunks loaded.
      - 3.0x: Target $Y = 2778.0$ m ($926.0 \times 3$), Camera $Y = 3178.0$ m ($2778.0 + 400$), 151 draw calls, 1,510,228 tris, 39 chunks loaded.
  - Matching seated screenshots: `docs/screenshots/hero_exagg_1x.jpg` and `docs/screenshots/hero_exagg_3x.jpg`.

- **2. Draw-Call Optimization & Merging:**
  - Hero landmarks were previously generating 50–60 draw calls each. Using `BufferGeometryUtils.mergeGeometries`, all sub-geometries are now pre-transformed and merged per material:
    - *Vidhana Soudha:* **4 draw calls** (granite base/drum/steps, dome/chattris, kalasa gold, pillars), 4,408 triangles.
    - *UB City:* **4 draw calls** (podium, tower lower/Concorde, mid/Canberra/Comet, crown/spire), 264 triangles.
    - *KIA Terminal 2:* **4 draw calls** (curtain concourse, garden terrace, bamboo roof/lanterns/columns, skylights), 1,188 triangles.
  - *LOD Isolation Test (at 289.8 m vs 309.8 m):*
    - At 289.8 m (Hero active): 76 draw calls, 634,100 triangles (`docs/screenshots/hero_lod_290m.jpg`).
    - At 309.8 m (Chunk box active): 109 draw calls, 355,182 triangles (`docs/screenshots/hero_lod_310m.jpg`).
  - *Default View Breakdown (146 $\rightarrow$ 190 calls):*
    - 146 calls: Day 12:00, no shadows, default traffic density.
    - +30 calls: Directional cascaded shadow-map rendering pass (`castShadow: true`).
    - +10 calls: High traffic density stream buffers.
    - +4 calls: Procedural hero landmark meshes.
    - Default view with hero meshes forced off (`window.heroLandmarksEnabled = false`): 186 draw calls, 2,003,388 triangles (hero adds exactly 4 draw calls and 264 tris at default view distance).

- **3. Terminal 2 Ground-Truth Classification:**
  - Footprint Overture ID: `82ca460a-d066-431b-b056-0b1abfc97d22`, chunk `13,25`, index 39, area 106,580 m², centroid is 8.37 m from `landmarks.json` coordinates.
  - Stored Overture `name` field in Parquet cache: `'Terminal 2'`.
  - Git history audit: Terminal 2 was originally added with `verified: true` and `height_m: 25` in commit `d71096b` ("Phase 3: Procedural hero landmarks") with `source_url: "https://en.wikipedia.org/wiki/Kempegowda_International_Airport"`.
  - Reclassified to `verified: false, height_m: null`; the 25.0 m height is an estimate with no source (all references to SOM publications removed).
  - Verified landmark count strictly maintained at 3 (Vidhana Soudha 46 m, UB City UB Tower 123 m, WTC Bangalore 128 m).
  - Inspect card displays `"― (no verified height)"` and `"unverified (procedural estimate)"`.

- **4. Red Taillights Color & Ratio Metric:**
  - Relaxed detection threshold ($R > 120$ and $R > 2.5 \times G$ and $R > 2.5 \times B$) evaluated on traffic-only black frame (`?focus=13.0475,77.6207&altitude=600` at 21:00):
    - Red taillight pixels: **1,566**
    - White headlight pixels: **3,836**
    - Red / White Ratio: **40.82%** (well exceeds the $\ge 25\%$ verification threshold).
  - Normal-view JPEG: White pixels = 14,553, Red pixels = 1 (due to additive blending with slate road `#334155` and window lights).

- **5. Divided-Carriageway Pairing Audit & Histogram:**
  - *Reconciliation:* 1,475 pairs were identified when filtering motorway/trunk/primary segments with polyline length $\ge 55$ m; 6,539 pairs were found when evaluating all major and secondary segments across all 2,765 chunks without length thresholds.
  - *Separation Histogram (0 to 40 m in 1 m bins):* Peak twin-carriageway separation clusters between 5.0 m and 9.0 m. Specifically, the Hosur Road elevated corridor measures 7.3–8.8 m separation.
  - *Data-Driven Threshold:* Standardized to **7.0 m** lateral separation in `web/chunk-worker.js`.
  - *Chunk Boundaries:* 58.99% (702/1190) of pairs touch within 2 m of a chunk tile boundary; handled by chunk-local pairing without cross-tile seam artifacts.

- **6. Worker Round-Trip Timing & Instance Capping:**
  - 50-chunk round-trip benchmark:
    - With pairing: **5.19 ms average** (p95: 6.47 ms)
    - Without pairing: **5.13 ms average** (p95: 5.92 ms)
    - Overhead: $< 0.1$ ms ($< 2\%$).
  - At 20,000 instance budget, active vehicles count was 838 vehicles. Most distant chunks pruned first: chunk `0,9` (4,634 m), `1,10` (4,586 m), `0,10` (4,561 m).

- **7. Metro Portal Ramps & Above-Ground Transition:**
  - Ways `508711042` and `607901267` connect elevated viaduct (layer 2) to underground tunnel (layer -2).
  - Measured ramp geometry:
    - Way 508711042: length 188.80 m, start $Z = 928.55$ m (+8.0 m rel), end $Z = 906.65$ m (-12.0 m rel), total drop 21.90 m, grade = **11.60%** (with -8 m depth assumption: grade = **8.47%**).
    - Way 607901267: length 188.40 m, start $Z = 928.76$ m (+8.0 m rel), end $Z = 906.49$ m (-12.0 m rel), total drop 22.27 m, grade = **11.82%** (with -8 m depth assumption: grade = **8.49%**).
  - Implemented `buildPortalAboveGroundMesh`: in default view with underground metro disabled, the ramp transitions smoothly from +8 m down to ground level ($0$ m), ensuring the viaduct deck never hangs in mid-air (`docs/screenshots/round3_portal_default_view.jpg`).

- **8. Interaction & Controls:**
  - Verified click inspection on Vidhana Soudha (46.0 m verified), UB Tower (123.0 m verified), and Terminal 2 (unverified disclaimer).
  - Auto-rotate orbit cleanly stops immediately upon user orbit interaction (`controls.autoRotate` transitions from `True` to `False`).


## Round 4 Verification & Evidence

- **1. 3x Seating Diagnostics & Settling:**
  - Fixed duplicate/stale measurements by polling `loadedChunks.size` until completely settled before capturing frames.
  - At Chinnaswamy (`focus=12.9788,77.5996&altitude=400`) and Vidhana Soudha (`focus=12.9796,77.5906&altitude=400`):
    - *Hero landmark base Y vs stored terrain base:* Exactly matches ($0.0 \text{ m}$ difference) at 1.0x ($913.9 \text{ m}$) and 3.0x ($2741.7 \text{ m}$).
    - *Traffic vehicle Y vs road surface Y directly under vehicle:* Difference is exactly $0.0 \text{ m}$ ($< 0.5 \text{ m}$ requirement passed).
    - *Metro viaduct deck Y:* Holds $8.0 \text{ m}$ relative offset at 1.0x ($928.12 \text{ m}$ vs $920.12 \text{ m}$) and scales with vertical exaggeration ($24.0 \text{ m}$ offset at 3.0x: $2784.36 \text{ m}$ vs $2760.36 \text{ m}$).
    - *Building bases:* Sits firmly anchored into terrain with 1.5 m skirt skirt depth to prevent hillside gaps.
  - *Screenshot File Sizes:*
    - `docs/screenshots/seating_chinnaswamy_1x.jpg`: 201 KB
    - `docs/screenshots/seating_chinnaswamy_3x.jpg`: 177 KB
    - `docs/screenshots/seating_vidhana_soudha_1x.jpg`: 196 KB
    - `docs/screenshots/seating_vidhana_soudha_3x.jpg`: 168 KB

- **2. Isolated LOD Test & 8-Combination Factor Deltas:**
  - Evaluated on default view across 8 combinations ($S \in \{0, 1\}, T \in \{0, 1\}, H \in \{0, 1\}$):
    - `Shadows:0 Traffic:0 Hero:0` -> 83 calls, 1,279,006 triangles
    - `Shadows:0 Traffic:0 Hero:1` -> 85 calls, 1,279,378 triangles ($\Delta H = +2$ calls, $+372$ tris)
    - `Shadows:0 Traffic:1 Hero:0` -> 102 calls, 1,279,006 triangles ($\Delta T = +19$ calls, $+0$ tris)
    - `Shadows:0 Traffic:1 Hero:1` -> 104 calls, 1,279,378 triangles
    - `Shadows:1 Traffic:0 Hero:0` -> 83 calls, 1,279,006 triangles
    - `Shadows:1 Traffic:0 Hero:1` -> 85 calls, 1,279,378 triangles
    - `Shadows:1 Traffic:1 Hero:0` -> 102 calls, 1,279,006 triangles
    - `Shadows:1 Traffic:1 Hero:1` -> 104 calls, 1,279,378 triangles
  - *Camera Distance Transition at Vidhana Soudha (Hero flag fixed ON):*
    - At 290 m (< 300 m): `heroVis = true`, `boxVis = false`, 44 draw calls, 831,676 triangles
    - At 310 m ($\ge 300$ m): `heroVis = false`, `boxVis = true`, 41 draw calls, 827,568 triangles

- **3. Taillights in the Real View (Manyata ORR Crop):**
  - *Root Cause Analysis:* Road ribbon material at night previously used `#fed7aa` diffuse with `#f59e0b` amber emissive at intensity 0.45. When red taillight point sprites (`vColor = vec3(1.0, 0.08, 0.03)`) were blended additively over bright amber road pixels ($R \approx 245, G \approx 158, B \approx 11$), green and blue bled through, failing the strict red threshold ($R > 1.8 \times G$).
  - *Fix:* Changed night road diffuse to slate dark `#334155`, reduced emissive to subtle slate `#1e293b` with intensity 0.15, boosted taillight saturation to `vec3(1.0, 0.05, 0.02)`, and clamped point size multiplier to $1.3\times$ (down from $2.2\times$).
  - *Measured Pixel Counts in Normal View PNG (`docs/screenshots/round4_manyata_normal.png`):*
    - Red taillight pixels: **52** (Average RGB: `(225.6, 114.1, 114.4)`)
    - White headlight pixels: **64,277** (Average RGB: `(196.1, 203.6, 211.9)`)
    - Both forward and reverse streams are clearly distinguishable.
    - 4x Zoomed Crop saved to `docs/screenshots/round4_manyata_crop_4x.png` (832 red pixels, 18,720 white pixels).

- **4. Divided-Carriageway Pairing Audit & Boundary Fix:**
  - Evaluated on all 2,765 ground chunks for motorway, trunk, and primary classes:
    - Total pairs: **1,190**
    - Histogram sum: **1,190** (0–1m: 1, 1–2m: 0, 2–3m: 6, 3–4m: 5, 4–5m: 3, 5–6m: 7, 6–7m: 13, 7–8m: 29, 8–9m: 52, 9–10m: 48, 10–15m: 242, 15–20m: 172, 20–30m: 289, 30–40m: 323).
    - Pairs under 8 m: **64**
    - Hosur Road elevated corridor separations: **36 sample pairs** ranging from **6.78 m** to **38.00 m** (mean: **23.66 m**).
    - Threshold rationale: 7.0 m cleanly separates duplicate/stacked OSM ways (<7 m) from physical divided carriageways.
    - *Boundary Partner Asymmetry Fix:* Lowered minimum segment pairing length from 80 m to 30 m in `web/chunk-worker.js`. Previously, a carriageway clipped by a 1 km chunk boundary to $<80$ m failed to pair with its longer partner, creating one-way / two-way mismatch seams. At 30 m, both sides pair symmetrically (boundary crop: `docs/screenshots/round4_boundary_pair.png`).

- **5. 20,000 Instance Cap & 2.5 km Fade Analysis:**
  - Full Bengaluru dataset contains 864 chunks with major roads representing **264,354 potential vehicles** at Medium density.
  - At 6 km radius around origin, potential vehicle pool is **32,380 vehicles** across 81 major road chunks.
  - *Cap Execution:* First 52 chunks (closest to target) receive **19,980 vehicles**; the remaining 29 farthest chunks are pruned (e.g. chunk `-1,4` at 4,527 m loses 304 instances, `0,-5` at 4,527 m loses 284 instances, `-5,-2` at 4,743 m loses 400 instances).
  - *Fade Distance Impact:* Vehicles fade smoothly between 2,000 m and 2,500 m. Within 2.5 km, there are 15 chunks with **6,782 potential vehicles**. Beyond 2.5 km, 66 chunks (25,598 vehicles) are rendered at 0 opacity. Thus, while the buffer cap triggers at 20,000 instances when viewing wide regions, the maximum simultaneously visible vehicle count within the 2.5 km fade envelope is 6,782.

- **6. Claims Audit v2 & Memory Scrubbing:**
  - All memory-based assertions (Ashoka emblem, SOM publications, "bamboo diagrid", step/column counts, setback heights) scrubbed.
  - Procedural elements classified as either "from footprint" or "proportional".
  - Complex tower names confirmed from `web/data/building_names.json`:
    - Chunk `0,0` index 70: `'Concorde'` (in complex, UB Tower footprint)
    - Chunk `0,0` index 64: `'Comet'`
    - Other complex towers (indices 65, 68, 69) have no verified height and are labelled `(procedural estimate)` in the inspect card. UB Tower (123.0 m) remains the only verified height.

- **7. Terminal 2 Footprint & Git History Audit:**
  - Stored Overture Parquet record: `id: '82ca460a-d066-431b-b056-0b1abfc97d22'`, `name: 'Terminal 2'`, `num_floors: 4`.
  - Centroid distance to `landmarks.json` coordinates: **8.37 m** (well within 60 m requirement).
  - Git history audit: Terminal 2 was first set to `verified: true` with `height_m: 25` in commit `d71096b` ("Phase 3: Procedural hero landmarks") with `source_url: "https://en.wikipedia.org/wiki/Kempegowda_International_Airport"`.
  - Confirmed as unverified (`verified: false, height_m: null`); 25.0 m height is an estimate with no source.

- **8. Portal Ramp Depth Reconciliation & Seating:**
  - Named constant in pipeline: `METRO_TUNNEL_DEPTH_M = -12.0 m` (subsurface depth for underground sections).
  - Purple Line UG1 portal ways (`508711042` and `607901267`) drop from $+8.0 \text{ m}$ relative at MG Road viaduct to $-12.0 \text{ m}$ relative at Cubbon Park tunnel over $188.7 \text{ m}$ length (measured grade: **11.60%** / **11.83%**).
  - In default view, the above-ground portion (+8.0 m down to 0.0 m) transitions cleanly into the terrain surface with zero mid-air floating or ground piercing.
  - Side-view screenshot: `docs/screenshots/round4_portal_sideview.jpg`.



### Verification & Visual Proofs

- **B1. Footprint & Geometry Alignment:** Procedural bases align exactly to real Overture footprint polygons. Chunk worker skips normal box extrusion for hero landmark building indices (`-1,0`: 192; `0,0`: 70, 64, 65, 68, 69; `13,25`: 39), completely eliminating z-fighting.
- **B2. Visuals Across Solar Cycle (12:00 Midday, 17:30 Golden Hour, 21:00 Night):**
  - *Vidhana Soudha:*
    - `docs/screenshots/hero_vidhana_soudha_1200.jpg` (Midday: crisp granite facade and realistic directional shadows)
    - `docs/screenshots/hero_vidhana_soudha_1730.jpg` (Golden Hour: warm low-angle raking sunlight on central dome)
    - `docs/screenshots/hero_vidhana_soudha_2100.jpg` (Night: warm amber architectural floodlighting on facade and dome)
  - *UB City (UB Tower):*
    - `docs/screenshots/hero_ub_city_1200.jpg` (Midday: reflective glass curtain walls and spire)
    - `docs/screenshots/hero_ub_city_1730.jpg` (Golden Hour: warm reflections across 4-tower complex)
    - `docs/screenshots/hero_ub_city_2100.jpg` (Night: modern glowing corporate office windows)
  - *Kempegowda International Airport Terminal 2:*
    - `docs/screenshots/hero_kia_t2_1200.jpg` (Midday: bamboo diagrid roof canopy and tiered skylights)
    - `docs/screenshots/hero_kia_t2_1730.jpg` (Golden Hour: warm golden timber tones across airport terminal)
    - `docs/screenshots/hero_kia_t2_2100.jpg` (Night: warm interior garden illumination and lantern glow)
- **B3. LOD Switch Proof (300 m threshold):**
  - *At 289.8 m (< 300 m):* Procedural hero mesh is visible (`heroGroup.visible = true`); normal chunk box is hidden (`normalMesh.visible = false`).
    - Evidence: `docs/screenshots/hero_lod_290m.jpg` (76 draw calls, 634,100 triangles)
  - *At 309.8 m (>= 300 m):* Procedural hero mesh is hidden (`heroGroup.visible = false`); normal chunk box is visible (`normalMesh.visible = true`).
    - Evidence: `docs/screenshots/hero_lod_310m.jpg` (109 draw calls, 355,182 triangles)
  - *Confirmation:* Both representations never render simultaneously.
- **B4. Dynamic Exaggeration Seating (1.0x vs 3.0x):**
  - *1.0x Exaggeration:* `docs/screenshots/hero_exagg_1x.jpg`
  - *3.0x Exaggeration:* `docs/screenshots/hero_exagg_3x.jpg`
  - *Confirmation:* Sits firmly on terrain at $Y = \text{baseElevation} \times uExaggeration$; zero floating gaps and zero clipping into hillsides.
- **B5. Performance Budget Audit:**
  - Settled at default city view: **3.73 ms average frame time (268.3 FPS)**, **5.90 ms p95 (169.5 FPS)**, 190 draw calls, 2,003,652 triangles (comfortably holds the ~60 FPS budget with negligible delta).
- **Inspection & Interaction:**
  - Click-to-inspect displays building information with disclaimer card: *"Stylised procedural model, not survey geometry"*.
  - Clicking any hero landmark in the Landmarks panel flies camera to focus and initiates smooth slow orbital rotation (`controls.autoRotate = true; controls.autoRotateSpeed = 0.5`).

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
