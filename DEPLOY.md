# Deployment Guide — Bengaluru 3D

## Cloudflare Pages (recommended)

### Prerequisites
- A free Cloudflare account (<https://dash.cloudflare.com>)
- Node.js 18+ installed (for Wrangler)
- Wrangler CLI: `npm install -g wrangler`

### Steps

```bash
# 1. Authenticate with your Cloudflare account
wrangler login

# 2. Deploy the web/ directory
wrangler pages deploy web/ --project-name bengaluru-3d

# On first deploy you will be prompted to choose an account and project name.
# Subsequent deploys to the same project use the same command.
```

### What you need to do
1. **Cloudflare account**: Sign in at <https://dash.cloudflare.com> and note your account ID.
2. **Project name**: Choose a unique slug, e.g. `bengaluru-3d`. Cloudflare assigns a preview URL like `bengaluru-3d.pages.dev`.
3. **Custom domain** (optional): In Cloudflare Pages → your project → Custom Domains, add your domain. Cloudflare issues a free TLS certificate automatically.

### File count / size check (Nov 2026)
| Metric | Value | Limit |
|---|---|---|
| Files deployed | ~4,140 | 20,000 ✓ |
| Largest file | ≤ 400 KiB | 25 MiB ✓ |
| Total compressed | ~47 MiB | No per-deployment limit |

Cloudflare compresses `.json` and other text files automatically via Brotli/gzip — do **not** include pre-compressed `.gz` files. The `web/_headers` file sets long `Cache-Control` headers for `/data/*` so returning visitors load instantly.

### R2 object storage
Not needed. The file count and per-file sizes are well within Pages limits. R2 would only be needed if data files exceeded 25 MiB or if the total exceeded 20,000 files.

## Local development

```bash
cd web
python -m http.server 8000
# Open http://localhost:8000
```

## Building data locally (not done on Cloudflare)

All data files in `web/data/` are pre-built. To rebuild:

```bash
cd /path/to/bengaluru-3d
source .venv/bin/activate

# Terrain + buildings
python data/build_terrain.py

# Metro lines and stations (from OSM)
python data/build_osm_metro.py

# Landmarks
python data/build_landmarks.py
```

## Assumptions flagged in the app
- `METRO_VIADUCT_M = 8.0` — assumed constant clearance above terrain for elevated guideway; no per-segment height data was available from Overture.
- Metro train animations are illustrative only — no live or historical timetable data is used.
- Metro line colour `#00e5ff` (neutral cyan) — Overture transportation data for this region does not include route ref/name fields in the downloaded cache; real line colours were not assigned.
