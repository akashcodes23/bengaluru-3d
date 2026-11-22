#!/usr/bin/env python3
"""Copy Overture features to local Parquet, then write 1 km viewer chunks."""

import argparse
import json
import math
import re
import sys
import tempfile
import threading
import time
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from shapely.geometry import Polygon, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import transform as transform_geometry

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "web" / "data"
CACHE_ROOT = ROOT / "data" / "cache"
STAC_CATALOG_URL = "https://stac.overturemaps.org/catalog.json"
S3_BUILDING_GLOB = (
    "s3://overturemaps-us-west-2/release/*/"
    "theme=buildings/type=building/*.parquet"
)
RELEASE_PREFIX = "s3://overturemaps-us-west-2/release/"
RELEASE_HELP_URL = "https://docs.overturemaps.org/release/latest"
S3_BUCKET = "s3://overturemaps-us-west-2"
ORIGIN_LON = 77.5946
ORIGIN_LAT = 12.9716
METERS_PER_DEGREE_LON = 111_319.49079327358 * math.cos(math.radians(ORIGIN_LAT))
METERS_PER_DEGREE_LAT = 110_574.0
CHUNK_SIZE = 1_000
DEFAULT_BBOX = (77.40, 12.75, 77.85, 13.20)
FULL_BENGALURU_BBOX = (77.46, 12.83, 77.78, 13.14)
CACHE_RETRIES = 3
CACHE_QUERY_TIMEOUT_SECONDS = 900
COARSE_CACHE_GRID_SIZE = 2
DUCKDB_THREADS = 16
MAX_OPEN_SPOOL_FILES = 32

GREEN_CLASSES = {
    "allotments",
    "dog_park",
    "flowerbed",
    "forest",
    "garden",
    "golf_course",
    "grass",
    "green",
    "greenfield",
    "meadow",
    "national_park",
    "nature_reserve",
    "orchard",
    "park",
    "playground",
    "recreation_ground",
    "species_management_area",
    "state_park",
    "strict_nature_reserve",
    "village_green",
    "wilderness_area",
}

Bounds = Tuple[float, float, float, float]
ChunkKey = Tuple[int, int]
Building = List[object]


def parse_bbox(value: str) -> Bounds:
    try:
        west, south, east, north = (float(part) for part in value.split(","))
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError(
            "bbox must be four comma-separated numbers: west,south,east,north"
        ) from error
    if not all(math.isfinite(number) for number in (west, south, east, north)):
        raise argparse.ArgumentTypeError("bbox values must be finite numbers")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise argparse.ArgumentTypeError(
            "bbox must be ordered west,south,east,north within geographic limits"
        )
    return west, south, east, north


def release_sort_key(release: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", release))


def release_from_stac() -> str:
    request = urllib.request.Request(
        STAC_CATALOG_URL, headers={"User-Agent": "bengaluru-3d/1.0"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        catalog = json.load(response)
    if not isinstance(catalog, dict):
        raise ValueError("STAC catalog response is not a JSON object")
    latest = catalog.get("latest")
    if not isinstance(latest, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", latest):
        raise ValueError("STAC catalog has no valid latest release field")
    return latest


def release_from_s3() -> str:
    import duckdb

    connection = duckdb.connect()
    try:
        connection.execute("INSTALL httpfs")
        connection.execute("LOAD httpfs")
        connection.execute("SET s3_region = 'us-west-2'")
        connection.execute("SET s3_endpoint = 's3.us-west-2.amazonaws.com'")
        connection.execute("SET s3_url_style = 'path'")
        paths = connection.execute(
            "SELECT file FROM glob(?)", [S3_BUILDING_GLOB]
        ).fetchall()
    finally:
        connection.close()

    releases = set()
    for (path,) in paths:
        match = re.match(re.escape(RELEASE_PREFIX) + r"([^/]+)/", path)
        if match:
            releases.add(match.group(1))
    if not releases:
        raise RuntimeError("The public S3 listing contained no Overture releases.")
    return max(releases, key=release_sort_key)


def detect_latest_release() -> str:
    stac_error: Optional[Exception] = None
    try:
        return release_from_stac()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        stac_error = error
        print("STAC release lookup failed; trying the public S3 listing.", file=sys.stderr)
    try:
        return release_from_s3()
    except Exception as s3_error:
        raise RuntimeError(
            "Could not detect the latest Overture Maps release "
            "(STAC: {}; S3: {}). Copy a release ID from {} and retry with "
            "`--release RELEASE_ID`.".format(stac_error, s3_error, RELEASE_HELP_URL)
        ) from s3_error


def open_overture_connection(spatial: bool = True):
    import duckdb

    connection = duckdb.connect()
    connection.execute("INSTALL httpfs")
    connection.execute("LOAD httpfs")
    if spatial:
        connection.execute("INSTALL spatial")
        connection.execute("LOAD spatial")
    connection.execute("SET threads = {}".format(DUCKDB_THREADS))
    connection.execute("SET http_keep_alive = true")
    connection.execute("SET enable_http_metadata_cache = true")
    connection.execute("SET enable_object_cache = true")
    connection.execute("SET s3_region = 'us-west-2'")
    connection.execute("SET s3_endpoint = 's3.us-west-2.amazonaws.com'")
    connection.execute("SET s3_url_style = 'path'")
    return connection


def release_table_path(release: str, theme: str, data_type: str) -> str:
    return "{}/release/{}/theme={}/type={}/*.parquet".format(
        S3_BUCKET, release, theme, data_type
    )


def polygon_parts(geometry: BaseGeometry) -> Iterable[Polygon]:
    if geometry.geom_type == "Polygon":
        yield geometry
    elif geometry.geom_type == "MultiPolygon":
        yield from geometry.geoms
    elif geometry.geom_type == "GeometryCollection":
        for item in geometry.geoms:
            yield from polygon_parts(item)


def line_parts(geometry: BaseGeometry) -> Iterable[BaseGeometry]:
    if geometry.geom_type in ("LineString", "LinearRing"):
        yield geometry
    elif geometry.geom_type in ("MultiLineString", "GeometryCollection"):
        for item in geometry.geoms:
            yield from line_parts(item)


def positive_number(value: object) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def building_height(
    polygon: Polygon, height_value: object, floors_value: object
) -> Tuple[float, str]:
    tagged_height = positive_number(height_value)
    if tagged_height is not None:
        return min(tagged_height, 300.0), "tagged"
    floors = positive_number(floors_value)
    if floors is not None:
        return min(floors * 3.0, 300.0), "from floors"
    min_lon, min_lat, max_lon, max_lat = polygon.bounds
    footprint_area = max(
        1.0,
        (max_lon - min_lon)
        * METERS_PER_DEGREE_LON
        * (max_lat - min_lat)
        * METERS_PER_DEGREE_LAT,
    )
    return min(max(math.sqrt(footprint_area) * 0.35, 6.0), 60.0), "guessed"


def normalize_building(
    geometry_data: Dict[str, object],
    height_value: object,
    floors_value: object,
    bounds: Bounds,
) -> List[Tuple[ChunkKey, Building]]:
    geometry = shape(geometry_data)
    if geometry.is_empty:
        return []
    clipped = geometry.intersection(box(*bounds))
    features = []
    for polygon in polygon_parts(clipped):
        if polygon.area <= 0:
            continue
        polygon = orient(polygon, sign=1.0)
        ring: List[float] = []
        for coordinate in list(polygon.exterior.coords)[:-1]:
            lon, lat = coordinate[:2]
            ring.extend(
                [
                    round((lon - ORIGIN_LON) * METERS_PER_DEGREE_LON, 2),
                    round((lat - ORIGIN_LAT) * METERS_PER_DEGREE_LAT, 2),
                ]
            )
        if len(ring) < 6:
            continue
        height, source = building_height(polygon, height_value, floors_value)
        center = polygon.representative_point()
        chunk_key = (
            math.floor((center.x - ORIGIN_LON) * METERS_PER_DEGREE_LON / CHUNK_SIZE),
            math.floor((center.y - ORIGIN_LAT) * METERS_PER_DEGREE_LAT / CHUNK_SIZE),
        )
        features.append((chunk_key, [round(height, 1), ring, source]))
    return features


def flatten_coords(coords: Iterable[Tuple[float, float]]) -> List[float]:
    flattened = []
    for coordinate in coords:
        x, y = coordinate[:2]
        flattened.extend([round(float(x), 2), round(float(y), 2)])
    return flattened


def project_geometry(geometry: BaseGeometry) -> BaseGeometry:
    def project(x, y, z=None):
        projected = (
            (x - ORIGIN_LON) * METERS_PER_DEGREE_LON,
            (y - ORIGIN_LAT) * METERS_PER_DEGREE_LAT,
        )
        if z is not None:
            return projected + (z,)
        return projected

    return transform_geometry(project, geometry)


def clip_to_chunks(geometry: BaseGeometry) -> Iterator[Tuple[ChunkKey, BaseGeometry]]:
    if geometry.is_empty:
        return
    min_x, min_y, max_x, max_y = geometry.bounds
    min_ix, max_ix = math.floor(min_x / CHUNK_SIZE), math.floor(max_x / CHUNK_SIZE)
    min_iy, max_iy = math.floor(min_y / CHUNK_SIZE), math.floor(max_y / CHUNK_SIZE)
    for ix in range(min_ix, max_ix + 1):
        for iy in range(min_iy, max_iy + 1):
            cell = box(
                ix * CHUNK_SIZE,
                iy * CHUNK_SIZE,
                (ix + 1) * CHUNK_SIZE,
                (iy + 1) * CHUNK_SIZE,
            )
            clipped = geometry.intersection(cell)
            if not clipped.is_empty:
                yield (ix, iy), clipped


def polygon_record(polygon: Polygon, **attributes) -> Dict[str, object]:
    polygon = orient(polygon, sign=1.0)
    record: Dict[str, object] = {
        "p": flatten_coords(polygon.exterior.coords[:-1]),
        "holes": [
            flatten_coords(interior.coords[:-1]) for interior in polygon.interiors
        ],
    }
    record.update(attributes)
    return record


def normalize_ground_geometry(
    geometry_data: Dict[str, object],
    bounds: Bounds,
    layer: str,
    attributes: Optional[Dict[str, object]] = None,
) -> List[Tuple[ChunkKey, Dict[str, object]]]:
    geometry = shape(geometry_data)
    if geometry.is_empty:
        return []
    clipped = geometry.intersection(box(*bounds))
    if clipped.is_empty:
        return []
    projected = project_geometry(clipped)
    features = []
    for chunk_key, chunk_geometry in clip_to_chunks(projected):
        if layer in ("water-polygons", "green"):
            for polygon in polygon_parts(chunk_geometry):
                if polygon.area > 0:
                    features.append(
                        (chunk_key, polygon_record(polygon, **(attributes or {})))
                    )
        if layer in ("water-lines", "roads", "rail"):
            for line in line_parts(chunk_geometry):
                coords = list(line.coords)
                flattened = flatten_coords(coords)
                if len(flattened) >= 4:
                    record = {"p": flattened}
                    record.update(attributes or {})
                    features.append((chunk_key, record))
    return features


class ChunkSpool:
    """Disk-backed JSONL writer with a bounded number of open chunk files."""

    def __init__(self, directory: Path, label: str):
        self.directory = directory
        self.label = label
        self.counts: Dict[ChunkKey, int] = {}
        self.paths: Dict[ChunkKey, Path] = {}
        self.handles: OrderedDict[ChunkKey, object] = OrderedDict()

    @property
    def keys(self):
        return set(self.counts)

    def append(self, chunk_key: ChunkKey, value: object) -> None:
        path = self.paths.setdefault(
            chunk_key,
            self.directory
            / "{}_{}_{}.jsonl".format(self.label, chunk_key[0], chunk_key[1]),
        )
        handle = self.handles.pop(chunk_key, None)
        if handle is None:
            if len(self.handles) >= MAX_OPEN_SPOOL_FILES:
                _, old_handle = self.handles.popitem(last=False)
                old_handle.close()
            handle = path.open("a", encoding="utf-8")
        self.handles[chunk_key] = handle
        json.dump(value, handle, separators=(",", ":"))
        handle.write("\n")
        self.counts[chunk_key] = self.counts.get(chunk_key, 0) + 1

    def close(self) -> None:
        for handle in self.handles.values():
            handle.close()
        self.handles.clear()

    def clear(self) -> None:
        self.close()
        for path in self.paths.values():
            path.unlink(missing_ok=True)
        self.paths.clear()
        self.counts.clear()

    def write_array(self, output, chunk_key: ChunkKey) -> None:
        output.write("[")
        path = self.paths.get(chunk_key)
        if path is not None:
            first = True
            with path.open(encoding="utf-8") as source:
                for line in source:
                    if not first:
                        output.write(",")
                    output.write(line.rstrip())
                    first = False
        output.write("]")


def chunk_name(prefix: str, chunk_key: ChunkKey) -> str:
    return "{}_{}_{}.json".format(prefix, chunk_key[0], chunk_key[1])


CACHE_LAYERS = {
    "buildings": (
        "buildings",
        "building",
        'id, ST_AsGeoJSON(geometry) AS geometry_json, height, num_floors, names."primary" AS name',
    ),
    "base_water": (
        "base",
        "water",
        "id, ST_AsGeoJSON(geometry) AS geometry_json, class, subtype",
    ),
    "base_land_use": (
        "base",
        "land_use",
        'id, ST_AsGeoJSON(geometry) AS geometry_json, class, subtype, names."primary" AS name',
    ),
    "transportation_segment": (
        "transportation",
        "segment",
        "id, ST_AsGeoJSON(geometry) AS geometry_json, class, subtype",
    ),
}
CLI_TYPES = {
    "buildings": "building",
    "base_water": "water",
    "base_land_use": "land_use",
    "transportation_segment": "segment",
}


def cache_file_stem(layer: str, bounds: Bounds) -> str:
    stems = {
        "buildings": "buildings",
        "base_water": "water",
        "base_land_use": "land_use",
        "transportation_segment": "transportation",
    }
    stem = stems[layer]
    if tuple(round(value, 6) for value in bounds) != FULL_BENGALURU_BBOX:
        suffix = "_".join(
            "{:.6f}".format(value).rstrip("0").rstrip(".").replace("-", "m").replace(".", "p")
            for value in bounds
        )
        stem += "_bbox_" + suffix
    return stem


def cache_file_path(
    cache_dir: Path,
    layer: str,
    bounds: Bounds,
    tile: Optional[ChunkKey] = None,
) -> Path:
    stem = cache_file_stem(layer, bounds)
    if tile is not None:
        stem += "_coarse_{}_{}".format(*tile)
    return cache_dir / (stem + ".parquet")


def coarse_cache_tiles(bounds: Bounds) -> List[Tuple[ChunkKey, Bounds]]:
    west, south, east, north = bounds
    middle_lon = (west + east) / 2
    middle_lat = (south + north) / 2
    return [
        ((0, 0), (west, south, middle_lon, middle_lat)),
        ((1, 0), (middle_lon, south, east, middle_lat)),
        ((0, 1), (west, middle_lat, middle_lon, north)),
        ((1, 1), (middle_lon, middle_lat, east, north)),
    ]


def cache_row_count(connection, path: Path) -> int:
    return int(
        connection.execute("SELECT COUNT(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]
    )


def copy_overture_layer(
    connection,
    release: str,
    layer: str,
    query_bounds: Bounds,
    destination: Path,
    timeout_seconds: int = CACHE_QUERY_TIMEOUT_SECONDS,
) -> int:
    theme, data_type, columns = CACHE_LAYERS[layer]
    source = release_table_path(release, theme, data_type)
    west, south, east, north = query_bounds
    subtype_filter = (
        " AND subtype IN ('road', 'rail')"
        if layer == "transportation_segment"
        else ""
    )
    query = """
        COPY (
            SELECT {}
            FROM read_parquet(?, hive_partitioning = true)
            WHERE bbox.xmax >= ?
              AND bbox.xmin <= ?
              AND bbox.ymax >= ?
              AND bbox.ymin <= ?
              {}
        ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
    """.format(columns, subtype_filter)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.unlink(missing_ok=True)
    timed_out = False

    def interrupt_query() -> None:
        nonlocal timed_out
        timed_out = True
        connection.interrupt()

    timer = threading.Timer(timeout_seconds, interrupt_query)
    timer.daemon = True
    timer.start()
    try:
        try:
            rows = connection.execute(
                query,
                [str(temporary), source, west, east, south, north],
            ).fetchone()
            timer.cancel()
        except Exception as error:
            if timed_out:
                raise TimeoutError(
                    "{} query timed out after {} seconds.".format(
                        layer, timeout_seconds
                    )
                ) from error
            raise
        if not temporary.is_file():
            raise RuntimeError("DuckDB COPY did not create {}".format(temporary))
        temporary.replace(destination)
        return int(rows[0]) if rows else cache_row_count(connection, destination)
    finally:
        timer.cancel()
        temporary.unlink(missing_ok=True)


def normalize_cli_geoparquet(
    source_path: Path, destination: Path, layer: str, bounds: Bounds
) -> int:
    import duckdb

    columns = {
        "buildings": (
            'id, ST_AsGeoJSON(geometry) AS geometry_json, height, num_floors, '
            'names."primary" AS name'
        ),
        "base_water": "id, ST_AsGeoJSON(geometry) AS geometry_json, class, subtype",
        "base_land_use": (
            'id, ST_AsGeoJSON(geometry) AS geometry_json, class, subtype, '
            'names."primary" AS name'
        ),
        "transportation_segment": (
            "id, ST_AsGeoJSON(geometry) AS geometry_json, class, subtype"
        ),
    }[layer]
    west, south, east, north = bounds
    subtype_filter = (
        " AND subtype IN ('road', 'rail')"
        if layer == "transportation_segment"
        else ""
    )
    query = """
        COPY (
            SELECT {}
            FROM read_parquet(?)
            WHERE bbox.xmax >= ?
              AND bbox.xmin <= ?
              AND bbox.ymax >= ?
              AND bbox.ymin <= ?
              {}
        ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
    """.format(columns, subtype_filter)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.unlink(missing_ok=True)
    connection = duckdb.connect()
    try:
        connection.execute("INSTALL spatial")
        connection.execute("LOAD spatial")
        connection.execute("SET threads = {}".format(DUCKDB_THREADS))
        rows = connection.execute(
            query,
            [str(temporary), str(source_path), west, east, south, north],
        ).fetchone()
        if not temporary.is_file():
            raise RuntimeError("DuckDB COPY did not create {}".format(temporary))
        temporary.replace(destination)
        return int(rows[0]) if rows else cache_row_count(connection, destination)
    finally:
        connection.close()
        temporary.unlink(missing_ok=True)


def download_cli_layer(
    release: str,
    layer: str,
    query_bounds: Bounds,
    destination: Path,
    timeout_seconds: int,
) -> int:
    import subprocess
    import duckdb

    raw_path = destination.with_name(destination.stem + ".cli-raw.parquet")
    state_path = Path(str(raw_path) + ".state")
    connection = duckdb.connect()
    try:
        connection.execute("INSTALL spatial")
        connection.execute("LOAD spatial")
        raw_rows = cached_file_rows(connection, raw_path)
    finally:
        connection.close()
    if raw_rows is None:
        raw_path.unlink(missing_ok=True)
        state_path.unlink(missing_ok=True)
        west, south, east, north = query_bounds
        command = [
            sys.executable,
            "-m",
            "overturemaps",
            "download",
            "--bbox={},{},{},{}".format(west, south, east, north),
            "--connect_timeout",
            "30",
            "--request_timeout",
            str(timeout_seconds),
            "-f",
            "geoparquet",
            "--type",
            CLI_TYPES[layer],
            "-r",
            release,
            "-o",
            str(raw_path),
        ]
        try:
            result = subprocess.run(
                command,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raw_path.unlink(missing_ok=True)
            state_path.unlink(missing_ok=True)
            raise TimeoutError(
                "Overture CLI {} query timed out after {} seconds.".format(
                    layer, timeout_seconds
                )
            ) from error
        if result.returncode:
            raw_path.unlink(missing_ok=True)
            state_path.unlink(missing_ok=True)
            raise RuntimeError(
                "Overture CLI {} query exited with status {}.".format(
                    layer, result.returncode
                )
            )
        if not raw_path.is_file() or raw_path.stat().st_size == 0:
            raw_path.unlink(missing_ok=True)
            state_path.unlink(missing_ok=True)
            raise RuntimeError(
                "Overture CLI did not create a non-empty GeoParquet file for {}.".format(
                    layer
                )
            )
    try:
        count = normalize_cli_geoparquet(raw_path, destination, layer, query_bounds)
    except Exception:
        raw_path.unlink(missing_ok=True)
        state_path.unlink(missing_ok=True)
        raise
    raw_path.unlink(missing_ok=True)
    state_path.unlink(missing_ok=True)
    return count


def cached_file_rows(connection, path: Path) -> Optional[int]:
    if not path.is_file():
        return None
    if path.stat().st_size == 0:
        print("  empty cache {} will be rebuilt.".format(path), file=sys.stderr, flush=True)
        path.unlink(missing_ok=True)
        return None
    try:
        return cache_row_count(connection, path)
    except Exception as error:
        print(
            "  invalid cache {} will be rebuilt: {}".format(path, error),
            file=sys.stderr,
            flush=True,
        )
        path.unlink(missing_ok=True)
        return None


def log_cache_failure(path: Path, message: str) -> None:
    with path.open("a", encoding="utf-8") as failed:
        failed.write("{}\n".format(" ".join(message.splitlines())))


def copy_with_retries(
    release: str,
    layer: str,
    query_bounds: Bounds,
    destination: Path,
    timeout_seconds: int,
    attempts: int = CACHE_RETRIES,
    retry_timeouts: bool = True,
    backend: str = "duckdb",
) -> int:
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        connection = None
        started = time.monotonic()
        try:
            if backend == "overturemaps":
                return download_cli_layer(
                    release, layer, query_bounds, destination, timeout_seconds
                )
            connection = open_overture_connection()
            return copy_overture_layer(
                connection, release, layer, query_bounds, destination, timeout_seconds
            )
        except Exception as error:
            last_error = error
            destination.unlink(missing_ok=True)
            if attempt + 1 == attempts or (
                isinstance(error, TimeoutError) and not retry_timeouts
            ):
                break
            delay = 2 ** (attempt + 1)
            print(
                "  {} attempt {}/{} failed after {:.1f}s: {}. Retrying in {}s.".format(
                    layer, attempt + 1, attempts, time.monotonic() - started, error, delay
                ),
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
        finally:
            if connection is not None:
                connection.close()
    raise RuntimeError(
        "{} query failed after {} attempt(s): {}".format(layer, attempt + 1, last_error)
    ) from last_error


def cache_overture_layers(
    release: str, bounds: Bounds, backend: str = "duckdb"
) -> Tuple[Path, Dict[str, int]]:
    import duckdb

    cache_dir = CACHE_ROOT / release
    cache_dir.mkdir(parents=True, exist_ok=True)
    failed_path = CACHE_ROOT / "failed.txt"
    failed_path.parent.mkdir(parents=True, exist_ok=True)
    failed_path.write_text("", encoding="utf-8")
    local = duckdb.connect()
    cached_rows: Dict[str, int] = {}
    print(
        "Caching {} Overture themes with {}; 2x2 fallback is enabled.".format(
            len(CACHE_LAYERS), backend
        ),
        flush=True,
    )
    try:
        for layer in CACHE_LAYERS:
            started = time.monotonic()
            whole_path = cache_file_path(cache_dir, layer, bounds)
            whole_count = cached_file_rows(local, whole_path)
            if whole_count is not None:
                cached_rows[layer] = whole_count
                print(
                    "  reuse {} cache ({} rows).".format(layer, whole_count),
                    flush=True,
                )
                continue

            coarse_tiles = coarse_cache_tiles(bounds)
            coarse_paths = [
                (tile, tile_bounds, cache_file_path(cache_dir, layer, bounds, tile))
                for tile, tile_bounds in coarse_tiles
            ]
            ready_coarse = [
                (tile, tile_bounds, path, cached_file_rows(local, path))
                for tile, tile_bounds, path in coarse_paths
            ]
            use_coarse = any(item[3] is not None for item in ready_coarse)
            if not use_coarse:
                print("  COPY {} for full bbox.".format(layer), flush=True)
                try:
                    rows = copy_with_retries(
                        release,
                        layer,
                        bounds,
                        whole_path,
                        CACHE_QUERY_TIMEOUT_SECONDS,
                        retry_timeouts=False,
                        backend=backend,
                    )
                    cached_rows[layer] = rows
                    print(
                        "  {}: {:,} rows in {:.1f}s.".format(
                            layer, rows, time.monotonic() - started
                        ),
                        flush=True,
                    )
                    continue
                except RuntimeError as error:
                    if not isinstance(error.__cause__, TimeoutError):
                        log_cache_failure(
                            failed_path,
                            "release={} layer={} failed after {:.1f}s: {}".format(
                                release, layer, time.monotonic() - started, error
                            ),
                        )
                        raise
                    log_cache_failure(
                        failed_path,
                        "release={} layer={} full bbox timed out after {:.1f}s; using 2x2 fallback: {}".format(
                            release, layer, time.monotonic() - started, error
                        ),
                    )
                    print(
                        "  full-bbox {} query timed out after {:.1f}s; falling back to 2x2.".format(
                            layer, time.monotonic() - started
                        ),
                        file=sys.stderr,
                        flush=True,
                    )

            total_rows = 0
            for tile, tile_bounds, path, existing_rows in ready_coarse:
                if existing_rows is not None:
                    rows = existing_rows
                    print(
                        "  reuse {} coarse tile {} ({} rows).".format(
                            layer, tile, rows
                        ),
                        flush=True,
                    )
                else:
                    print("  COPY {} coarse tile {}.".format(layer, tile), flush=True)
                    tile_started = time.monotonic()
                    try:
                        rows = copy_with_retries(
                            release,
                            layer,
                            tile_bounds,
                            path,
                            CACHE_QUERY_TIMEOUT_SECONDS,
                            backend=backend,
                        )
                    except RuntimeError as error:
                        log_cache_failure(
                            failed_path,
                            "release={} layer={} tile={} failed: {}".format(
                                release, layer, tile, error
                            ),
                        )
                        raise
                    print(
                        "  {} tile {}: {:,} rows in {:.1f}s.".format(
                            layer, tile, rows, time.monotonic() - tile_started
                        ),
                        flush=True,
                    )
                total_rows += rows
            cached_rows[layer] = total_rows
            print(
                "  {} coarse cache rows: {:,} in {:.1f}s.".format(
                    layer, total_rows, time.monotonic() - started
                ),
                flush=True,
            )
    finally:
        local.close()
    print("All theme caches ready: {}".format(cached_rows), flush=True)
    return cache_dir, cached_rows


def cached_layer_paths(cache_dir: Path, layer: str, bounds: Bounds) -> List[Path]:
    whole_path = cache_file_path(cache_dir, layer, bounds)
    if whole_path.is_file() and whole_path.stat().st_size > 0:
        return [whole_path]
    paths = [
        cache_file_path(cache_dir, layer, bounds, tile)
        for tile, _ in coarse_cache_tiles(bounds)
    ]
    missing = [path for path in paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise FileNotFoundError(
            "Required local {} cache file(s) missing: {}".format(
                layer, ", ".join(str(path) for path in missing)
            )
        )
    return paths


def iter_cached_rows(
    cache_dir: Path,
    layer: str,
    bounds: Bounds,
) -> Iterator[Tuple[object, ...]]:
    import duckdb

    connection = duckdb.connect()
    try:
        for path in cached_layer_paths(cache_dir, layer, bounds):
            cursor = connection.execute("SELECT * FROM read_parquet(?)", [str(path)])
            while rows := cursor.fetchmany(1000):
                yield from rows
    finally:
        connection.close()


def overlaps_bounds(geometry: BaseGeometry, bounds: Bounds) -> bool:
    west, south, east, north = bounds
    min_x, min_y, max_x, max_y = geometry.bounds
    return max_x >= west and min_x <= east and max_y >= south and min_y <= north


def require_feature_id(feature_id: object, layer: str) -> str:
    if feature_id is None or not str(feature_id):
        raise ValueError("{} cache row has no Overture id.".format(layer))
    return str(feature_id)


def read_cached_buildings(
    cache_dir: Path,
    bounds: Bounds,
    expected_feature_count: Optional[int],
    building_spool: ChunkSpool,
    names_spool: ChunkSpool,
    height_inputs_spool: ChunkSpool,
) -> Tuple[int, Dict[str, int], int]:
    seen_ids = set()
    feature_count = 0
    height_counts = {"tagged": 0, "from floors": 0, "guessed": 0}
    for row in iter_cached_rows(cache_dir, "buildings", bounds):
        feature_id, geometry_json, height, floors, name = row
        feature_id = require_feature_id(feature_id, "building")
        if feature_id in seen_ids:
            continue
        seen_ids.add(feature_id)
        geometry_data = json.loads(geometry_json)
        geometry = shape(geometry_data)
        if not overlaps_bounds(geometry, bounds):
            continue
        feature_count += 1
        records = normalize_building(geometry_data, height, floors, bounds)
        for chunk_key, building in records:
            building_spool.append(chunk_key, building)
            names_spool.append(chunk_key, str(name) if name else None)
            height_inputs_spool.append(
                chunk_key, [positive_number(height), positive_number(floors)]
            )
            height_counts[building[2]] += 1
        if feature_count and feature_count % 10_000 == 0:
            total = (
                "{:,}".format(expected_feature_count)
                if expected_feature_count is not None
                else "counted from cache"
            )
            print(
                "Processed {:,}/{} unique building features; emitted {:,} footprints.".format(
                    feature_count, total, sum(height_counts.values())
                ),
                flush=True,
            )
    if expected_feature_count is not None and feature_count != expected_feature_count:
        raise RuntimeError(
            "COUNT(*) found {:,} building features but local cached tiles contain {:,} "
            "unique IDs in the bbox.".format(expected_feature_count, feature_count)
        )
    print("TRUE building features in bbox: {:,}".format(feature_count), flush=True)
    building_spool.close()
    names_spool.close()
    return sum(height_counts.values()), height_counts, feature_count


def is_green(class_value: object, subtype_value: object) -> bool:
    class_name = str(class_value or "").lower()
    subtype = str(subtype_value or "").lower()
    return class_name in GREEN_CLASSES or any(
        hint in subtype for hint in ("forest", "garden", "green", "nature", "park", "recreation")
    )


def read_ground_layer(
    cache_dir: Path,
    bounds: Bounds,
    kind: str,
    spools: Dict[str, ChunkSpool],
    source_counts: Dict[str, int],
    landmark_counts: Dict[str, int],
    feature_counts: Dict[str, int],
) -> None:
    source_counts[kind] = 0
    seen_ids = set()
    processed = 0
    if kind == "roads":
        source_counts["rail"] = 0
    if kind == "green":
        landmark_counts["cubbonPark"] = 0
        landmark_counts["lalbagh"] = 0
    cache_layer = {
        "water": "base_water",
        "green": "base_land_use",
        "roads": "transportation_segment",
    }[kind]
    print("Building {} chunks from local cache.".format(kind), flush=True)
    for row in iter_cached_rows(cache_dir, cache_layer, bounds):
        feature_id, geometry_json, class_value, subtype_value = row[:4]
        feature_id = require_feature_id(feature_id, kind)
        if feature_id in seen_ids:
            continue
        seen_ids.add(feature_id)
        geometry_data = json.loads(geometry_json)
        geometry = shape(geometry_data)
        if not overlaps_bounds(geometry, bounds):
            continue
        processed += 1
        attributes: Dict[str, object]
        if kind == "water":
            attributes = {"class": str(class_value or "")}
            polygons = normalize_ground_geometry(
                geometry_data, bounds, "water-polygons", attributes
            )
            lines = normalize_ground_geometry(
                geometry_data, bounds, "water-lines", attributes
            )
            emitted = False
            for chunk_key, record in polygons:
                spools["water_polygons"].append(chunk_key, record)
                emitted = True
            for chunk_key, record in lines:
                spools["water_lines"].append(chunk_key, record)
                emitted = True
            if emitted:
                source_counts["water"] += 1
        elif kind == "green":
            name = str(row[4] or "")
            if not is_green(class_value, subtype_value):
                continue
            attributes = {"class": str(class_value or ""), "name": name}
            records = normalize_ground_geometry(
                geometry_data, bounds, "green", attributes
            )
            for chunk_key, record in records:
                spools["green"].append(chunk_key, record)
            if records:
                source_counts["green"] += 1
                landmark = name.lower()
                if "cubbon" in landmark:
                    landmark_counts["cubbonPark"] += 1
                if "lalbagh" in landmark:
                    landmark_counts["lalbagh"] += 1
        else:
            is_rail = str(subtype_value or "").lower() == "rail"
            target = "rail" if is_rail else "roads"
            layer = "rail" if is_rail else "roads"
            attributes = {"class": str(class_value or "unknown")}
            records = normalize_ground_geometry(
                geometry_data, bounds, layer, attributes
            )
            for chunk_key, record in records:
                spools[target].append(chunk_key, record)
            if records:
                source_counts[target] += 1
        if processed and processed % 10_000 == 0:
            print(
                "Processed {:,} unique {} features; retained {:,}.".format(
                    processed, kind, source_counts[kind]
                ),
                flush=True,
            )
    feature_key = {
        "water": "water",
        "green": "land_use",
        "roads": "transportation",
    }[kind]
    feature_counts[feature_key] = processed


def write_ground_file(
    path: Path, chunk_key: ChunkKey, spools: Dict[str, ChunkSpool]
) -> None:
    with path.open("w", encoding="utf-8") as output:
        output.write('{"water":{"polygons":')
        spools["water_polygons"].write_array(output, chunk_key)
        output.write(',"lines":')
        spools["water_lines"].write_array(output, chunk_key)
        output.write('},"green":')
        spools["green"].write_array(output, chunk_key)
        output.write(',"roads":')
        spools["roads"].write_array(output, chunk_key)
        output.write("}")


def write_dataset(
    release: str,
    bounds: Bounds,
    building_feature_count: Optional[int],
    demo: bool = False,
    ingest_backend: str = "duckdb",
) -> Dict[str, object]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache_dir = None
    theme_feature_counts: Dict[str, int] = {}
    if not demo:
        cache_dir, _ = cache_overture_layers(release, bounds, ingest_backend)
    with tempfile.TemporaryDirectory(
        prefix=".bengaluru-build-", dir=OUTPUT_DIR
    ) as temporary_directory:
        temp_path = Path(temporary_directory)
        spools = {
            "buildings": ChunkSpool(temp_path, "buildings"),
            "building_names": ChunkSpool(temp_path, "building_names"),
            "building_height_inputs": ChunkSpool(temp_path, "building_height_inputs"),
            "water_polygons": ChunkSpool(temp_path, "water_polygons"),
            "water_lines": ChunkSpool(temp_path, "water_lines"),
            "green": ChunkSpool(temp_path, "green"),
            "roads": ChunkSpool(temp_path, "roads"),
            "rail": ChunkSpool(temp_path, "rail"),
        }
        source_counts = {"water": 0, "green": 0, "roads": 0, "rail": 0}
        landmark_counts = {"cubbonPark": 0, "lalbagh": 0}
        if demo:
            height_counts = {"tagged": 0, "from floors": 0, "guessed": 0}
            for chunk_key, building in demo_buildings(bounds):
                spools["buildings"].append(chunk_key, building)
                spools["building_names"].append(chunk_key, None)
                spools["building_height_inputs"].append(chunk_key, [None, None])
                height_counts[building[2]] += 1
            spools["buildings"].close()
            spools["building_names"].close()
            spools["building_height_inputs"].close()
            building_count = sum(height_counts.values())
            building_feature_count = building_count
        else:
            if cache_dir is None:
                raise RuntimeError("The Overture cache directory was not initialized.")
            building_count, height_counts, building_feature_count = read_cached_buildings(
                cache_dir,
                bounds,
                building_feature_count,
                spools["buildings"],
                spools["building_names"],
                spools["building_height_inputs"],
            )
            theme_feature_counts["buildings"] = building_feature_count
            for kind in ("water", "green", "roads"):
                read_ground_layer(
                    cache_dir,
                    bounds,
                    kind,
                    spools,
                    source_counts,
                    landmark_counts,
                    theme_feature_counts,
                )
        for spool in spools.values():
            spool.close()

        if building_feature_count is None:
            raise RuntimeError("The true building feature count was not computed.")

        ground_labels = ("water_polygons", "water_lines", "green", "roads")
        ground_keys = set().union(*(spools[label].keys for label in ground_labels))
        all_keys = spools["buildings"].keys | ground_keys
        rail_keys = spools["rail"].keys
        for pattern in (
            "c_*.json",
            "g_*.json",
            "r_*.json",
            "rail_*.json",
            "chunk_*.json",
        ):
            for path in OUTPUT_DIR.glob(pattern):
                path.unlink()

        chunks = []
        for chunk_key in sorted(all_keys):
            building_records = spools["buildings"].counts.get(chunk_key, 0)
            ground_counts = {
                "waterPolygons": spools["water_polygons"].counts.get(chunk_key, 0),
                "waterLines": spools["water_lines"].counts.get(chunk_key, 0),
                "green": spools["green"].counts.get(chunk_key, 0),
                "roads": spools["roads"].counts.get(chunk_key, 0),
            }
            building_file = None
            ground_file = None
            if building_records:
                building_file = chunk_name("c", chunk_key)
                with (OUTPUT_DIR / building_file).open("w", encoding="utf-8") as output:
                    spools["buildings"].write_array(output, chunk_key)
                if cache_dir is not None:
                    names_path = cache_dir / "names_{}_{}.json".format(*chunk_key)
                    with names_path.open("w", encoding="utf-8") as output:
                        spools["building_names"].write_array(output, chunk_key)
                    height_inputs_path = cache_dir / "height_inputs_{}_{}.json".format(
                        *chunk_key
                    )
                    with height_inputs_path.open("w", encoding="utf-8") as output:
                        spools["building_height_inputs"].write_array(output, chunk_key)
            if any(ground_counts.values()):
                ground_file = chunk_name("g", chunk_key)
                write_ground_file(OUTPUT_DIR / ground_file, chunk_key, spools)
            chunks.append(
                {
                    "ix": chunk_key[0],
                    "iy": chunk_key[1],
                    "buildingFile": building_file,
                    "groundFile": ground_file,
                    "buildingCount": building_records,
                    "groundCounts": ground_counts,
                }
            )

        rail_chunks = []
        for chunk_key in sorted(rail_keys):
            name = chunk_name("r", chunk_key)
            with (OUTPUT_DIR / name).open("w", encoding="utf-8") as output:
                spools["rail"].write_array(output, chunk_key)
            rail_chunks.append(
                {
                    "ix": chunk_key[0],
                    "iy": chunk_key[1],
                    "name": name,
                    "count": spools["rail"].counts[chunk_key],
                }
            )

        ground_chunk_counts = {
            label: sum(spools[label].counts.values())
            for label in ("water_polygons", "water_lines", "green", "roads", "rail")
        }
        manifest: Dict[str, object] = {
            "version": 3,
            "source": release,
            "bounds": list(bounds),
            "origin": {"lon": ORIGIN_LON, "lat": ORIGIN_LAT},
            "chunkSize": CHUNK_SIZE,
            "chunks": chunks,
            "railChunks": rail_chunks,
            "buildingFeatureCount": building_feature_count,
            "buildingCount": building_count,
            "overtureFeatureCounts": theme_feature_counts,
            "heightSourceCounts": height_counts,
            "groundFeatureCounts": source_counts,
            "groundChunkRecords": ground_chunk_counts,
            "visualTestLandmarks": landmark_counts,
        }
        with (OUTPUT_DIR / "manifest.json").open("w", encoding="utf-8") as output:
            json.dump(manifest, output, indent=2)
            output.write("\n")

    print(
        "wrote {} building/ground chunks; {} rail chunks; {:,} building footprints "
        "from {:,} Overture building features.".format(
            len(chunks), len(rail_chunks), building_count, building_feature_count
        )
    )
    for source_name, source_count in height_counts.items():
        share = 100 * source_count / building_count if building_count else 0
        print(
            "height source {}: {} ({:.1f}%)".format(
                source_name, source_count, share
            )
        )
    print(
        "ground feature rows: water {}, green {}, roads {}, rail {}.".format(
            source_counts["water"],
            source_counts["green"],
            source_counts["roads"],
            source_counts["rail"],
        )
    )
    if theme_feature_counts:
        print(
            "true Overture features by theme: {}".format(
                ", ".join(
                    "{} {:,}".format(name, count)
                    for name, count in theme_feature_counts.items()
                )
            )
        )
    print("ground chunk records: {}".format(ground_chunk_counts))
    print("visual-test landmarks: {}".format(landmark_counts))
    return manifest


def demo_buildings(bounds: Bounds) -> Iterable[Tuple[ChunkKey, Building]]:
    west, south, east, north = bounds
    total_width = (east - west) * METERS_PER_DEGREE_LON
    total_height = (north - south) * METERS_PER_DEGREE_LAT
    for row in range(24):
        for column in range(24):
            width = 12 + (row * 7 + column * 11) % 18
            depth = 11 + (column * 5 + row * 13) % 19
            x = (column + 0.5) * total_width / 24
            y = (row + 0.5) * total_height / 24
            west_lon = west + (x + width * 0.08) / METERS_PER_DEGREE_LON
            south_lat = south + (y + depth * 0.08) / METERS_PER_DEGREE_LAT
            geometry = {
                "type": "Polygon",
                "coordinates": [[
                    [west_lon, south_lat],
                    [west_lon + width / METERS_PER_DEGREE_LON, south_lat],
                    [
                        west_lon + width / METERS_PER_DEGREE_LON,
                        south_lat + depth / METERS_PER_DEGREE_LAT,
                    ],
                    [west_lon, south_lat + depth / METERS_PER_DEGREE_LAT],
                    [west_lon, south_lat],
                ]],
            }
            height = 8 + ((row * 3 + column * 5) % 34)
            yield from normalize_building(geometry, height, None, bounds)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate chunked building and ground data for the Bengaluru viewer."
    )
    parser.add_argument("--demo", action="store_true", help="generate synthetic buildings")
    parser.add_argument("--release", help="Overture Maps release ID to read")
    parser.add_argument(
        "--ingest",
        choices=("overturemaps", "duckdb"),
        default="overturemaps",
        help="remote cache backend (default: faster Overture CLI; DuckDB COPY also available)",
    )
    parser.add_argument(
        "--bbox",
        type=parse_bbox,
        default=None,
        metavar="WEST,SOUTH,EAST,NORTH",
        help="longitude/latitude bounds (default: Bengaluru)",
    )
    args = parser.parse_args()
    if args.demo and args.release:
        parser.error("--demo and --release cannot be used together")
    release = args.release
    if release and release.upper() in {
        "PASTE_ID_HERE",
        "RELEASE_ID",
        "YOUR_RELEASE_ID",
    }:
        print(
            "Ignoring placeholder release ID; detecting the latest release.",
            file=sys.stderr,
        )
        release = None
    if release and not re.fullmatch(r"[A-Za-z0-9._-]+", release):
        parser.error("release ID may contain only letters, numbers, '.', '_' and '-'")

    bounds = args.bbox or DEFAULT_BBOX
    started = time.monotonic()
    try:
        if args.demo:
            print("Writing synthetic demo buildings.")
            write_dataset("synthetic demo", bounds, 0, demo=True)
            return 0
        release = release or detect_latest_release()
        print("Using Overture Maps release: {}".format(release), flush=True)
        print("Using ingest backend: {}".format(args.ingest), flush=True)
        write_dataset(release, bounds, None, ingest_backend=args.ingest)
    except Exception as error:
        print("Data generation failed: {}".format(error), file=sys.stderr)
        return 1
    finally:
        print("Build runtime: {:.1f} seconds.".format(time.monotonic() - started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
