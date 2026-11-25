#!/usr/bin/env python3
"""Build 1 km terrain heightmaps from the public Copernicus GLO-30 DEM."""

import argparse
import json
import math
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple

import numpy as np
import rasterio
from rasterio.windows import Window, from_bounds, transform as window_transform

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA_DIR = ROOT / "web" / "data"
CONFIG_PATH = ROOT / "data" / "config.json"


def _load_config_bbox() -> Tuple[float, float, float, float]:
    if CONFIG_PATH.is_file():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        b = cfg["bbox"]
        return (float(b["west"]), float(b["south"]), float(b["east"]), float(b["north"]))
    return (77.40, 12.76, 77.82, 13.28)


CONFIG_BBOX = _load_config_bbox()
BUCKET_URL = "https://copernicus-dem-30m.s3.amazonaws.com/"
CHUNK_SIZE = 1000
GRID_SIZE = 33
BBOX_PADDING_METERS = 15.0
ORIGIN_LON = 77.5946
ORIGIN_LAT = 12.9716
METERS_PER_DEGREE_LON = 111_319.49079327358 * math.cos(math.radians(ORIGIN_LAT))
METERS_PER_DEGREE_LAT = 110_574.0
S3_NAMESPACE = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


def local_to_lonlat(x: float, north: float) -> Tuple[float, float]:
    return (
        x / METERS_PER_DEGREE_LON + ORIGIN_LON,
        north / METERS_PER_DEGREE_LAT + ORIGIN_LAT,
    )


def tile_prefix(latitude: int, longitude: int) -> str:
    lat_name = "{}{:02d}".format("N" if latitude >= 0 else "S", abs(latitude))
    lon_name = "{}{:03d}".format("E" if longitude >= 0 else "W", abs(longitude))
    stem = "Copernicus_DSM_COG_10_{}_00_{}_00_DEM".format(lat_name, lon_name)
    return stem + "/"


def list_dem_tile(latitude: int, longitude: int) -> str:
    prefix = tile_prefix(latitude, longitude)
    query = urllib.parse.urlencode(
        {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
    )
    request = urllib.request.Request(
        BUCKET_URL + "?" + query,
        headers={"User-Agent": "bengaluru-3d-terrain-builder"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            root = ET.fromstring(response.read())
    except Exception as error:
        raise RuntimeError(
            "Could not anonymously list Copernicus DEM tile prefix {}: {}".format(
                prefix, error
            )
        ) from error
    expected_suffix = prefix + prefix[:-1] + ".tif"
    keys = [
        item.text
        for item in root.findall("s3:Contents/s3:Key", S3_NAMESPACE)
        if item.text
    ]
    matches = [key for key in keys if key == expected_suffix]
    if len(matches) != 1:
        raise RuntimeError(
            "Anonymous bucket listing did not return the expected DEM COG under {}. "
            "Returned keys: {}".format(prefix, ", ".join(keys))
        )
    print("Verified anonymous DEM tile:", matches[0], flush=True)
    return matches[0]


class RasterTile:
    def __init__(self, key: str, bounds: Tuple[float, float, float, float]):
        uri = "/vsicurl/" + BUCKET_URL + urllib.parse.quote(key, safe="/")
        self.key = key
        with rasterio.open(uri) as dataset:
            if dataset.crs is None or dataset.crs.to_epsg() != 4326:
                raise ValueError("{} is not EPSG:4326.".format(key))
            self.bounds = dataset.bounds
            self.resolution = dataset.res
            west = max(bounds[0], dataset.bounds.left)
            south = max(bounds[1], dataset.bounds.bottom)
            east = min(bounds[2], dataset.bounds.right)
            north = min(bounds[3], dataset.bounds.top)
            if west >= east or south >= north:
                raise ValueError("{} does not overlap the terrain bounds.".format(key))
            requested = from_bounds(west, south, east, north, dataset.transform)
            requested = requested.round_offsets().round_lengths()
            requested = requested.intersection(Window(0, 0, dataset.width, dataset.height))
            col0 = max(0, int(requested.col_off) - 1)
            row0 = max(0, int(requested.row_off) - 1)
            col1 = min(dataset.width, int(requested.col_off + requested.width) + 1)
            row1 = min(dataset.height, int(requested.row_off + requested.height) + 1)
            self.window = Window(col0, row0, col1 - col0, row1 - row0)
            values = dataset.read(1, window=self.window, masked=True)
            self.values = np.asarray(values.filled(np.nan), dtype=np.float32)
            self.transform = window_transform(self.window, dataset.transform)
            self.nodata = dataset.nodata
            print(
                "  opened {}: {}x{} at {} degrees".format(
                    key, self.values.shape[1], self.values.shape[0], dataset.res[0]
                ),
                flush=True,
            )

    def contains(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        return (
            (lon >= self.bounds.left)
            & (lon <= self.bounds.right)
            & (lat >= self.bounds.bottom)
            & (lat <= self.bounds.top)
        )

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        col = (lon - self.transform.c) / self.transform.a - 0.5
        row = (lat - self.transform.f) / self.transform.e - 0.5
        col = np.clip(col, 0, self.values.shape[1] - 1)
        row = np.clip(row, 0, self.values.shape[0] - 1)
        col0 = np.floor(col).astype(np.int64)
        row0 = np.floor(row).astype(np.int64)
        col1 = np.minimum(col0 + 1, self.values.shape[1] - 1)
        row1 = np.minimum(row0 + 1, self.values.shape[0] - 1)
        tx = col - col0
        ty = row - row0
        samples = np.stack(
            (
                self.values[row0, col0],
                self.values[row0, col1],
                self.values[row1, col0],
                self.values[row1, col1],
            ),
            axis=1,
        )
        weights = np.stack(
            (
                (1 - tx) * (1 - ty),
                tx * (1 - ty),
                (1 - tx) * ty,
                tx * ty,
            ),
            axis=1,
        )
        valid = np.isfinite(samples)
        if self.nodata is not None:
            valid &= samples != self.nodata
        weights *= valid
        total = weights.sum(axis=1)
        result = np.full(len(lon), np.nan, dtype=np.float64)
        good = total > 0
        result[good] = (
            np.where(valid, samples, 0)[good] * weights[good]
        ).sum(axis=1) / total[good]
        return result

    def minimum_in_bounds(
        self, west: float, south: float, east: float, north: float
    ) -> float:
        west = max(west, self.bounds.left)
        south = max(south, self.bounds.bottom)
        east = min(east, self.bounds.right)
        north = min(north, self.bounds.top)
        if west >= east or south >= north:
            return math.nan

        col0 = math.floor((west - self.transform.c) / self.transform.a)
        col1 = math.ceil((east - self.transform.c) / self.transform.a)
        row0 = math.floor((north - self.transform.f) / self.transform.e)
        row1 = math.ceil((south - self.transform.f) / self.transform.e)
        col0 = max(0, col0)
        row0 = max(0, row0)
        col1 = min(self.values.shape[1], col1)
        row1 = min(self.values.shape[0], row1)
        values = self.values[row0:row1, col0:col1]
        valid = np.isfinite(values)
        if self.nodata is not None:
            valid &= values != self.nodata
        if not valid.any():
            return math.nan
        return float(np.min(values[valid]))


class TerrainSampler:
    def __init__(self, tiles: List[RasterTile]):
        self.tiles = tiles

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        flat_lon = np.asarray(lon, dtype=np.float64).reshape(-1)
        flat_lat = np.asarray(lat, dtype=np.float64).reshape(-1)
        result = np.full(len(flat_lon), np.nan, dtype=np.float64)
        for tile in self.tiles:
            mask = np.isnan(result) & tile.contains(flat_lon, flat_lat)
            if mask.any():
                result[mask] = tile.sample(flat_lon[mask], flat_lat[mask])
        if not np.isfinite(result).all():
            missing = int((~np.isfinite(result)).sum())
            raise RuntimeError(
                "{} terrain sample(s) were outside the listed DEM tiles or nodata.".format(
                    missing
                )
            )
        return result

    def minimum_in_bounds(
        self, west: float, south: float, east: float, north: float
    ) -> float:
        minima = [
            value
            for tile in self.tiles
            if math.isfinite(
                value := tile.minimum_in_bounds(west, south, east, north)
            )
        ]
        return min(minima) if minima else math.nan


def polygon_centroid(coordinates: List[float]) -> Tuple[float, float]:
    twice_area = 0.0
    x_sum = 0.0
    north_sum = 0.0
    count = len(coordinates) // 2
    for index in range(count):
        next_index = (index + 1) % count
        x0, north0 = coordinates[index * 2 : index * 2 + 2]
        x1, north1 = coordinates[next_index * 2 : next_index * 2 + 2]
        cross = x0 * north1 - x1 * north0
        twice_area += cross
        x_sum += (x0 + x1) * cross
        north_sum += (north0 + north1) * cross
    if abs(twice_area) < 1e-8:
        return (
            sum(coordinates[::2]) / count,
            sum(coordinates[1::2]) / count,
        )
    return x_sum / (3 * twice_area), north_sum / (3 * twice_area)


def write_json(path: Path, value: object) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=".terrain-", suffix=".tmp"
    ) as temporary:
        temporary_path = Path(temporary.name)
        json.dump(value, temporary, separators=(",", ":"))
        temporary.write("\n")
    temporary_path.replace(path)


def build_terrain(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("Viewer manifest has no chunks to terrainize.")
    min_x = min(int(chunk["ix"]) * CHUNK_SIZE for chunk in chunks)
    max_x = max((int(chunk["ix"]) + 1) * CHUNK_SIZE for chunk in chunks)
    min_north = min(int(chunk["iy"]) * CHUNK_SIZE for chunk in chunks)
    max_north = max((int(chunk["iy"]) + 1) * CHUNK_SIZE for chunk in chunks)
    west, south = local_to_lonlat(min_x, min_north)
    east, north = local_to_lonlat(max_x, max_north)
    west, east = min(west, east), max(west, east)
    south, north = min(south, north), max(south, north)

    latitudes = range(math.floor(south), math.floor(north) + 1)
    longitudes = range(math.floor(west), math.floor(east) + 1)
    tile_keys = [
        list_dem_tile(latitude, longitude)
        for latitude in latitudes
        for longitude in longitudes
    ]
    started = time.monotonic()
    tiles = [RasterTile(key, (west, south, east, north)) for key in tile_keys]
    sampler = TerrainSampler(tiles)
    min_elevation = math.inf
    max_elevation = -math.inf
    bases_changed_over_3m = 0
    max_base_change = 0.0
    compared_building_bases = 0
    output_dir = Path(manifest_path).resolve().parent

    for position, chunk in enumerate(chunks, start=1):
        ix, iy = int(chunk["ix"]), int(chunk["iy"])
        xs = ix * CHUNK_SIZE + np.linspace(0, CHUNK_SIZE, GRID_SIZE)
        northings = iy * CHUNK_SIZE + np.linspace(0, CHUNK_SIZE, GRID_SIZE)
        grid_x, grid_north = np.meshgrid(xs, northings)
        grid_lon = grid_x / METERS_PER_DEGREE_LON + ORIGIN_LON
        grid_lat = grid_north / METERS_PER_DEGREE_LAT + ORIGIN_LAT
        heights = sampler.sample(grid_lon, grid_lat)

        building_bases: List[float] = []
        filename = chunk.get("buildingFile")
        terrain_file = "t_{}_{}.json".format(ix, iy)
        previous_terrain_path = output_dir / terrain_file
        previous_bases: List[float] = []
        if previous_terrain_path.is_file():
            previous_record = json.loads(
                previous_terrain_path.read_text(encoding="utf-8")
            )
            previous_bases = previous_record.get("buildingBases", [])
        if filename:
            records = json.loads((output_dir / filename).read_text(encoding="utf-8"))
            for record_index, record in enumerate(records):
                coordinates = record[1]
                west_local = min(coordinates[::2]) - BBOX_PADDING_METERS
                east_local = max(coordinates[::2]) + BBOX_PADDING_METERS
                south_local = min(coordinates[1::2]) - BBOX_PADDING_METERS
                north_local = max(coordinates[1::2]) + BBOX_PADDING_METERS
                west, south = local_to_lonlat(west_local, south_local)
                east, north = local_to_lonlat(east_local, north_local)
                base = sampler.minimum_in_bounds(
                    min(west, east), min(south, north), max(west, east), max(south, north)
                )
                if not math.isfinite(base):
                    center_x, center_north = polygon_centroid(coordinates)
                    center_lon, center_lat = local_to_lonlat(center_x, center_north)
                    base = float(
                        sampler.sample(
                            np.asarray([center_lon]), np.asarray([center_lat])
                        )[0]
                    )
                building_bases.append(round(base, 1))
                if record_index < len(previous_bases):
                    change = abs(base - float(previous_bases[record_index]))
                    compared_building_bases += 1
                    if change > 3:
                        bases_changed_over_3m += 1
                    max_base_change = max(max_base_change, change)

        min_elevation = min(min_elevation, float(np.min(heights)))
        max_elevation = max(max_elevation, float(np.max(heights)))
        if building_bases:
            min_elevation = min(min_elevation, min(building_bases))
            max_elevation = max(max_elevation, max(building_bases))
        terrain_record = {
            "width": GRID_SIZE,
            "height": GRID_SIZE,
            "heights": [round(float(value), 1) for value in heights],
            "buildingBases": building_bases,
        }
        write_json(output_dir / terrain_file, terrain_record)
        chunk["terrainFile"] = terrain_file
        if position == 1 or position % 100 == 0 or position == len(chunks):
            print(
                "Terrain chunk {}/{}: {} ({} building bases).".format(
                    position, len(chunks), terrain_file, len(building_bases)
                ),
                flush=True,
            )

    manifest["terrain"] = {
        "source": "Copernicus GLO-30 DEM",
        "bucket": "copernicus-dem-30m",
        "tileKeys": tile_keys,
        "gridSize": GRID_SIZE,
        "chunkSize": CHUNK_SIZE,
        "sampleSpacingMeters": CHUNK_SIZE / (GRID_SIZE - 1),
        "interpolation": "bilinear",
        "minElevationMeters": round(min_elevation, 1),
        "maxElevationMeters": round(max_elevation, 1),
        "chunkCount": len(chunks),
    }
    write_json(manifest_path, manifest)
    result = manifest["terrain"]
    print(
        "Building bases: {:,} compared; {:,} changed by >3 m; max change {:.1f} m.".format(
            compared_building_bases, bases_changed_over_3m, max_base_change
        ),
        flush=True,
    )
    print(
        "Terrain ready: {:,} chunks; elevation {:.1f} to {:.1f} m; {:.1f} seconds.".format(
            len(chunks),
            result["minElevationMeters"],
            result["maxElevationMeters"],
            time.monotonic() - started,
        ),
        flush=True,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build 1 km terrain heightmaps from Copernicus GLO-30."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=WEB_DATA_DIR / "manifest.json",
        help="viewer data manifest",
    )
    args = parser.parse_args()
    if not args.manifest.is_file():
        parser.error("Viewer manifest not found: {}".format(args.manifest))
    build_terrain(args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
