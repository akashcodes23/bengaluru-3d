#!/usr/bin/env python3
"""Pre-compress web data files and produce hosting size analysis."""

import gzip
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA_DIR = ROOT / "web" / "data"

def compress_files():
    print("Pre-compressing data files with gzip...")
    t0 = time.time()
    count = 0
    total_raw = 0
    total_gz = 0
    
    # Pre-compress main files and all chunk json files
    for root, _, files in os.walk(WEB_DATA_DIR):
        for f in files:
            if not f.endswith(".json"):
                continue
            p = Path(root) / f
            gz_p = Path(root) / (f + ".gz")
            content = p.read_bytes()
            compressed = gzip.compress(content, compresslevel=6)
            gz_p.write_bytes(compressed)
            count += 1
            total_raw += len(content)
            total_gz += len(compressed)
            if count % 1000 == 0:
                print(f"  Pre-compressed {count} files...", flush=True)

    elapsed = time.time() - t0
    print(f"Completed pre-compression in {elapsed:.1f}s.")
    print(f"Total JSON files compressed: {count:,}")
    print(f"Original size: {total_raw / (1024*1024):.2f} MiB")
    print(f"Gzip size: {total_gz / (1024*1024):.2f} MiB (compression ratio: {total_raw/total_gz:.2f}x, {100*(1 - total_gz/total_raw):.1f}% reduction)")
    
    # Update manifest with compression metadata
    manifest_path = WEB_DATA_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["compression"] = {
        "preCompressedGzipAvailable": True,
        "rawSizeMiB": round(total_raw / (1024*1024), 2),
        "gzipSizeMiB": round(total_gz / (1024*1024), 2),
        "totalFiles": count,
        "fallbackSupported": True
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Also gzip manifest.json itself
    (WEB_DATA_DIR / "manifest.json.gz").write_bytes(
        gzip.compress(manifest_path.read_bytes(), compresslevel=6)
    )
    print("Updated manifest.json and manifest.json.gz with compression metadata.")

if __name__ == "__main__":
    compress_files()
