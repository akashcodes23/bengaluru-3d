<p align="center">
  <img src="web/logo-lockup.svg" alt="Bengaluru 3D — Built from open map data" width="520">
</p>

# Bengaluru 3D

A browser-based 3D viewer for Overture Maps buildings and ground features in
Bengaluru. Building footprints, water, green areas, and roads are split into
1 km chunks in local metre coordinates. The viewer streams chunks nearest the
camera first, unloads distant chunks, and merges each loaded chunk into WebGL
meshes. Copernicus GLO-30 DEM terrain provides base elevation. Namma Metro tracks,
stations, and illustrative trains are integrated with real solar positioning,
directional building shadows, and illustrative road traffic streams.

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
Start with this smaller city-centre bbox:

```sh
cd data
python build_data.py --bbox 77.55,12.93,77.65,13.02
python fuse_heights.py
```

The script prints the selected release, the unique-ID building feature total,
output footprint and chunk totals, height-source shares, ground-layer counts,
and Cubbon Park/Lalbagh visual matches. Coordinates use metres east/north from
longitude 77.5946, latitude 12.9716, with 1,000 m chunks. Ground data comes
from Overture `base/water`, park/green classes in `base/land_use`, and road
segments in `transportation/segment`.

On macOS, build the full Bengaluru bbox and fuse heights in a detached job:

```sh
cd data
nohup caffeinate -i sh -c '../.venv/bin/python build_data.py --release 2026-10-21.0 --bbox 77.46,12.83,77.78,13.14 --ingest overturemaps && ../.venv/bin/python fuse_heights.py && ../.venv/bin/python build_terrain.py; status=$?; printf "\nPIPELINE_EXIT=%s\n" "$status"; exit "$status"' > build.log 2>&1 &
echo "PID=$!"
tail -f build.log
```

## Build terrain

After building and height-fusing the city, run this from the project root:

```sh
python data/build_terrain.py
```

The script queries the Copernicus GLO-30 bucket for GeoTIFF COGs covering the
manifest extent. It writes one `t_<ix>_<iy>.json` heightmap for each manifest chunk
(33 x 33 samples, ~30 m spacing) and aligns building base elevations to the local DEM.

## Start the viewer

In another terminal, from the project root, run:

```sh
cd web
python -m http.server 8000
```

Open [http://localhost:8000](http://localhost:8000). Do not open `index.html`
directly: the browser needs HTTP to fetch the manifest and chunks.

Drag to orbit, scroll to zoom, and right-drag (or two-finger drag) to pan.
- **Time of day** controls the shader-lit building windows, sky gradient, and ground palette.
- **Loaded radius** controls how far around the camera focus chunks are kept (2, 4, or 6 km).
- **Vertical exaggeration** scales terrain elevation from 1x to 3x with fixed metric clearances.
- Append `?focus=13.0475,77.6207&altitude=600` to focus directly on specific coordinates.

## Methodology & Height Sources

Building heights in Bengaluru 3D are derived from a hierarchical pipeline:
1. **Verified Landmarks:** Authoritative architectural heights sourced from official registries or reference documentation:
   - Vidhana Soudha: 46.0 m (Wikipedia)
   - World Trade Center Bangalore: 128.0 m (The Skyscraper Center)
   - UB City: verified 123 m (Skyscraper Center, 'UB Tower'), matched to the nearest footprint polygon within 60 m of landmark coordinates (automatic match; the footprint may be a neighbouring tower of the complex; name in OSM data: Concorde).
2. **Tagged Heights:** OpenStreetMap / Overture `height` tags, filtered for suspect values (> 165 m capped unless verified).
3. **Floors Heuristic:** Estimated from `num_floors` at 3.2 m per storey.
4. **Raster Estimates:** Sourced from the European Commission GHSL GHS-BUILT-H (ANBH 2018) ~90 m raster grid.

Clicking any building in the viewer displays its provenance, footprint area, and coordinates in the HUD inspection card.

## Guided Tours Engine

The guided tours engine offers automated, cinematic flyovers through Bengaluru:
- **Default State:** `TOURS_ENABLED = false` by default.
- **Enabling Tours:** Add `#tours=1` to the URL (e.g., `http://localhost:8000/#tours=1`).
- **Available Tours:**
  - *Core City:* Historic and administrative core (Vidhana Soudha, Cubbon Park, UB City, MG Road, Majestic).
  - *Silicon Plateau: North & Central:* Tech hubs from World Trade Center and Manyata to Bagmane and Embassy GolfLinks.
  - *Silicon Plateau: East & South:* Outer Ring Road and Electronics City corridors (ITPB, RMZ Ecospace, Electronic City).
  - *Namma Metro Purple Line:* Continuous track flight along the operational Purple Line from Baiyappanahalli to Majestic.
- **Dual Clearance Guarantee:** Enforces $\text{margin} = \text{alt} - \max(\text{ground} + 120\text{ m}, \text{roof} + 40\text{ m}) \ge 0$ everywhere along flight trajectories.
- **Strict Readiness Gating:** The tour advances only when the chunk under the camera and all flight corridor chunks within 1.2 km along the next 1.0 km are loaded in GPU memory; flight halts without rendering empty void.

## Known Limitations

1. **Divided-Carriageway Directionality:** Carriageway pairing is an automated geometric inference based on parallel major-road polylines (angle < 10°, length ratio < 2.5, separation 7–40 m), not tagged one-way data from OpenStreetMap.
2. **Illustrative Traffic & Metro Transit:** Vehicle particles and metro train movements are illustrative simulations running on geometric splines, not live GPS telemetry or real-time transit schedule feeds.
3. **Raster Height Averaging:** GHSL raster estimates represent ~90 m neighbourhood-level averages, which underestimate individual high-rise towers.
4. **Hero Landmark Procedural Models:** Procedural landmark geometry represents stylised architectural envelopes built on real footprint outlines, not survey-grade CAD models.
5. **UB Tower Proximity Match:** The 123 m height is assigned by an automated proximity rule to the nearest footprint polygon within 60 m of landmark coordinates; the footprint may represent a neighbouring tower of the complex.

## Licenses & Data Attributions

- **OpenStreetMap:** © OpenStreetMap contributors, licensed under the Open Database License (ODbL) 1.0.
- **Overture Maps Foundation:** Overture Maps release `2026-10-21.0`, licensed under ODbL and CDLA Permissive v2.0.
- **Copernicus DEM:** Copernicus GLO-30 Digital Elevation Model, © European Space Agency (ESA).
- **GHSL:** European Commission Joint Research Centre (JRC) Global Human Settlement Layer (GHS-BUILT-H).
- **Three.js:** Licensed under the MIT License.
- **Disclaimers:** Building heights are estimates (raster average ~90 m cells; verified only for named landmarks); metro trains and road traffic streams are illustrative, not live.

## Troubleshooting

- **Release detection fails:** Confirm internet access. Copy an ID from the [Overture Maps release page](https://docs.overturemaps.org/release/latest/) and pass `--release RELEASE_ID`.
- **Blank screen:** Check the browser console and confirm internet access to jsDelivr (the three.js CDN).
- **Low frame rate:** Reduce **Quality radius** in the HUD. The viewer caps device pixel ratio at 2 and frustum-culls chunks.

---

For historical development logs, mathematical proofs, and verification reports, see [docs/BUILD_LOG.md](docs/BUILD_LOG.md).
