#!/usr/bin/env python3
"""Fuse Overture building heights with the GHSL neighbourhood height prior."""

import argparse
import csv
import json
import math
import statistics
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import rasterio
from rasterio.windows import Window
from shapely.geometry import Point, Polygon

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA_DIR = ROOT / "web" / "data"
LANDMARKS_PATH = ROOT / "data" / "landmarks.json"
CONFIG_PATH = ROOT / "data" / "config.json"


def _load_config_bbox() -> Tuple[float, float, float, float]:
    if CONFIG_PATH.is_file():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        b = cfg["bbox"]
        return (float(b["west"]), float(b["south"]), float(b["east"]), float(b["north"]))
    return (77.40, 12.76, 77.82, 13.28)


CONFIG_BBOX = _load_config_bbox()
RASTER_CANDIDATES = (
    ROOT / "data" / "raw" / "ghsl_built_h_bengaluru.tif",
    ROOT / "data" / "data" / "raw" / "ghsl_built_h_bengaluru.tif",
)

ORIGIN_LON = 77.5946
ORIGIN_LAT = 12.9716
METERS_PER_DEGREE_LON = 111_319.49079327358 * math.cos(math.radians(ORIGIN_LAT))
METERS_PER_DEGREE_LAT = 110_574.0
MIN_HEIGHT_M = 3.0
MAX_HEIGHT_M = 250.0
MAX_RASTER_HEIGHT_M = 80.0
SMALL_FOOTPRINT_AREA_M2 = 100.0
SMALL_TAGGED_TOWER_CAP_M = 100.0
TAG_REJECTION_CSV = ROOT / "data" / "qa" / "rejected_tags.csv"
SOURCE_NAMES = {
    0: "tagged",
    1: "floors",
    2: "guess",
    3: "raster",
    4: "verified landmark",
    5: "tag rejected",
    6: "OSM tag, unverified",
}
SOURCE_COLORS = {
    "tagged": "#4fc4a2",
    "floors": "#68a6ff",
    "guess": "#eb7676",
    "raster": "#ffc54a",
    "verified landmark": "#ff6cf0",
    "tag rejected": "#f28e5b",
    "OSM tag, unverified": "#a855f7",
}
CHECK_POINTS = {
    "Vidhana Soudha": (77.5907, 12.9796),
    "Manyata Tech Park": (77.6207, 13.0475),
    "Koramangala": (77.6245, 12.9352),
}
HISTOGRAM_BINS = (
    (0, 5, "[3, 5)"),
    (5, 10, "[5, 10)"),
    (10, 20, "[10, 20)"),
    (20, 30, "[20, 30)"),
    (30, 50, "[30, 50)"),
    (50, 75, "[50, 75)"),
    (75, 100, "[75, 100)"),
    (100, 150, "[100, 150)"),
    (150, 200, "[150, 200)"),
    (200, 251, "[200, 250]"),
)


def default_raster_path() -> Path:
    for candidate in RASTER_CANDIDATES:
        if candidate.is_file():
            return candidate
    return RASTER_CANDIDATES[0]


def local_to_lonlat(x: float, north: float) -> Tuple[float, float]:
    return (
        x / METERS_PER_DEGREE_LON + ORIGIN_LON,
        north / METERS_PER_DEGREE_LAT + ORIGIN_LAT,
    )


def clamp_height(value: float) -> float:
    return min(MAX_HEIGHT_M, max(MIN_HEIGHT_M, value))


def source_label(source: object) -> str:
    if isinstance(source, int) and source in SOURCE_NAMES:
        return SOURCE_NAMES[source]
    legacy = {
        "tagged": "tagged",
        "from floors": "floors",
        "guessed": "guess",
        "tag rejected": "tag rejected",
        "corroborated by floors": "OSM tag, unverified",
        "OSM tag, unverified": "OSM tag, unverified",
    }
    return legacy.get(str(source), "unknown")


def report_raster(dataset) -> None:
    bounds = dataset.bounds
    print("Raster:", dataset.name)
    print("  bounds:", tuple(bounds))
    print("  CRS:", dataset.crs)
    print("  resolution:", dataset.res)
    print("  nodata:", dataset.nodata)
    print("  shape:", dataset.shape)
    for name, point in CHECK_POINTS.items():
        lon, lat = point
        if not (bounds.left <= lon <= bounds.right and bounds.bottom <= lat <= bounds.top):
            raise RuntimeError(
                "GHSL raster bounds do not cover Bengaluru: {} is outside.".format(name)
            )
        value = next(dataset.sample([point], masked=True))[0]
        if bool(getattr(value, "mask", False)):
            print("  {} ({}, {}): nodata".format(name, lat, lon))
        else:
            print("  {} ({}, {}): {:.3f} m".format(name, lat, lon, float(value)))
    bengaluru = (
        min(point[0] for point in CHECK_POINTS.values()),
        min(point[1] for point in CHECK_POINTS.values()),
        max(point[0] for point in CHECK_POINTS.values()),
        max(point[1] for point in CHECK_POINTS.values()),
    )
    if not (
        bounds.left <= bengaluru[0]
        and bounds.bottom <= bengaluru[1]
        and bounds.right >= bengaluru[2]
        and bounds.top >= bengaluru[3]
    ):
        raise RuntimeError("GHSL raster bounds do not cover all Bengaluru check points.")


class HeightSampler:
    def __init__(self, dataset):
        if dataset.crs is None or dataset.crs.to_epsg() != 4326:
            raise ValueError("GHSL raster must use EPSG:4326 for this sampler.")
        self.dataset = dataset
        self.cache: Dict[Tuple[int, int], Optional[float]] = {}

    def sample(self, lon: float, lat: float) -> Optional[float]:
        dataset = self.dataset
        if not (
            dataset.bounds.left <= lon <= dataset.bounds.right
            and dataset.bounds.bottom <= lat <= dataset.bounds.top
        ):
            return None
        row, col = dataset.index(lon, lat)
        key = (row, col)
        if key in self.cache:
            return self.cache[key]

        values = dataset.read(
            1,
            window=Window(col - 1, row - 1, 3, 3),
            boundless=True,
            masked=True,
        ).compressed()
        valid = [
            float(value)
            for value in values
            if math.isfinite(float(value))
            and float(value) > 0
            and (dataset.nodata is None or float(value) != dataset.nodata)
        ]
        result = statistics.median(valid) if valid else None
        self.cache[key] = result
        return result


def read_landmarks(path: Path) -> List[dict]:
    try:
        landmarks = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Could not read landmarks file {}: {}".format(path, error)) from error
    if not isinstance(landmarks, list):
        raise ValueError("Landmarks JSON must be an array.")
    for landmark in landmarks:
        if not isinstance(landmark, dict) or not isinstance(landmark.get("name"), str):
            raise ValueError("Each landmark must be an object with a name.")
    return landmarks


def record_polygon(record: list) -> Polygon:
    if not isinstance(record, list) or len(record) != 3:
        raise ValueError("Building records must remain [height, flat_xy, source].")
    coordinates = record[1]
    if (
        not isinstance(coordinates, list)
        or len(coordinates) < 6
        or len(coordinates) % 2
        or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in coordinates)
    ):
        raise ValueError("Building footprint coordinates must be finite flat XY values.")
    return Polygon(list(zip(coordinates[::2], coordinates[1::2])))


def fused_height(
    record: list, polygon: Polygon, sampler: HeightSampler
) -> Tuple[float, int]:
    height, _, source = record
    label = source_label(source)
    if label in ("tagged", "OSM tag, unverified", "corroborated by floors") or source in (0, 6):
        return clamp_height(float(height)), 0
    if label == "floors":
        if isinstance(source, int):
            floor_height = float(height)
        else:
            floor_height = float(height) * (3.2 / 3.0)
        return clamp_height(floor_height), 1
    if label == "verified landmark":
        return clamp_height(float(height)), 4
    if label == "tag rejected" or source == 5:
        return clamp_height(float(height)), 5
    if label not in ("guess", "raster"):
        raise ValueError("Unrecognized height source {!r}.".format(source))

    center = polygon.centroid
    lon, lat = local_to_lonlat(center.x, center.y)
    raster_height = sampler.sample(lon, lat)
    if raster_height is not None:
        return clamp_height(raster_height), 3
    return clamp_height(float(height)), 2


def read_chunk_records(path: Path) -> List[list]:
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Could not read building chunk {}: {}".format(path, error)) from error
    if not isinstance(records, list):
        raise ValueError("Building chunk {} must contain a JSON array.".format(path))
    return records


def add_landmark_overrides(
    records_by_path: Dict[Path, List[list]], landmarks: List[dict]
) -> List[dict]:
    matches = []
    located = []
    for landmark in landmarks:
        lat, lon = landmark.get("lat"), landmark.get("lon")
        if not (
            isinstance(lat, (int, float))
            and math.isfinite(float(lat))
            and isinstance(lon, (int, float))
            and math.isfinite(float(lon))
        ):
            matches.append(
                {"landmark": landmark, "status": "not matched (no coordinates)"}
            )
            continue
        located.append(landmark)

    candidates = {landmark["name"]: None for landmark in located}
    for path, records in records_by_path.items():
        for index, record in enumerate(records):
            polygon = record_polygon(record)
            min_x, min_y, max_x, max_y = polygon.bounds
            for landmark in located:
                target_x = (float(landmark["lon"]) - ORIGIN_LON) * METERS_PER_DEGREE_LON
                target_y = (float(landmark["lat"]) - ORIGIN_LAT) * METERS_PER_DEGREE_LAT
                dx = max(min_x - target_x, 0.0, target_x - max_x)
                dy = max(min_y - target_y, 0.0, target_y - max_y)
                if math.hypot(dx, dy) > 60:
                    continue
                distance = polygon.distance(Point(target_x, target_y))
                current = candidates[landmark["name"]]
                if distance <= 60 and (current is None or distance < current[0]):
                    candidates[landmark["name"]] = (distance, path, index)

    for landmark in located:
        candidate = candidates[landmark["name"]]
        if candidate is None:
            matches.append(
                {"landmark": landmark, "status": "not matched (no footprint within 60 m)"}
            )
            continue
        distance, path, index = candidate
        has_verified_height = (
            landmark.get("verified") is True
            and isinstance(landmark.get("height_m"), (int, float))
            and math.isfinite(float(landmark["height_m"]))
        )
        if has_verified_height:
            record = records_by_path[path][index]
            record[0] = round(clamp_height(float(landmark["height_m"])), 1)
            record[2] = 4
            status = "matched and height overridden"
        else:
            status = "matched nearby; no verified height override"
        matches.append(
            {
                "landmark": landmark,
                "status": status,
                "distance_m": distance,
                "chunk": path.name,
            }
        )
    return matches


def source_counts(records_by_path: Dict[Path, List[list]]) -> Counter:
    return Counter(source_label(record[2]) for records in records_by_path.values() for record in records)


def height_histogram(records_by_path: Dict[Path, List[list]]) -> Dict[str, int]:
    counts = {label: 0 for _, _, label in HISTOGRAM_BINS}
    for records in records_by_path.values():
        for height, _, _ in records:
            for low, high, label in HISTOGRAM_BINS:
                if low <= float(height) < high:
                    counts[label] += 1
                    break
    return counts


def height_histogram_by_source(
    records_by_path: Dict[Path, List[list]]
) -> Dict[str, Dict[str, int]]:
    histograms = {
        name: {label: 0 for _, _, label in HISTOGRAM_BINS}
        for name in SOURCE_NAMES.values()
    }
    for records in records_by_path.values():
        for height, _, source in records:
            histogram = histograms[source_label(source)]
            for low, high, label in HISTOGRAM_BINS:
                if low <= float(height) < high:
                    histogram[label] += 1
                    break
    return histograms


def load_chunk_names(
    manifest: dict, chunk: dict, path: Path, record_count: int
) -> List[Optional[str]]:
    cache_dir = ROOT / "data" / "cache" / str(manifest.get("source", ""))
    names_path = cache_dir / "names_{}_{}.json".format(chunk["ix"], chunk["iy"])
    if not names_path.is_file():
        return [None] * record_count
    try:
        names = json.loads(names_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Could not read building-name sidecar {}: {}".format(names_path, error)) from error
    if not isinstance(names, list) or len(names) != record_count:
        raise ValueError(
            "Building-name sidecar {} is not aligned with {} records.".format(
                names_path, record_count
            )
        )
    return [str(name) if name else None for name in names]


def load_height_inputs(
    manifest: dict, chunk: dict, record_count: int, records: List[list]
) -> List[List[Optional[float]]]:
    cache_dir = ROOT / "data" / "cache" / str(manifest.get("source", ""))
    inputs_path = cache_dir / "height_inputs_{}_{}.json".format(
        chunk["ix"], chunk["iy"]
    )
    if not inputs_path.is_file():
        if any(
            source_label(record[2]) == "tag rejected"
            or (
                source_label(record[2]) == "tagged"
                and float(record[0]) > 60
            )
            for record in records
        ):
            raise FileNotFoundError(
                "Missing tagged-height metadata {}. Rerun build_data.py to preserve "
                "raw height and floor values before fusion.".format(inputs_path)
            )
        return [[None, None] for _ in records]
    try:
        values = json.loads(inputs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Could not read tagged-height metadata {}: {}".format(inputs_path, error)
        ) from error
    if not isinstance(values, list) or len(values) != record_count:
        raise ValueError(
            "Tagged-height metadata {} is not aligned with its building chunk.".format(
                inputs_path
            )
        )
    for pair in values:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or any(
                value is not None
                and (
                    not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                )
                for value in pair
            )
        ):
            raise ValueError("Invalid tagged-height metadata in {}.".format(inputs_path))
    return values


def landmark_nearby_name(
    lon: float, lat: float, landmarks: List[dict]
) -> Optional[str]:
    for landmark in landmarks:
        if not (
            isinstance(landmark.get("lat"), (int, float))
            and isinstance(landmark.get("lon"), (int, float))
        ):
            continue
        distance = math.hypot(
            (lon - float(landmark["lon"])) * METERS_PER_DEGREE_LON,
            (lat - float(landmark["lat"])) * METERS_PER_DEGREE_LAT,
        )
        if distance <= 60:
            return str(landmark["name"])
    return None


def area_based_guess(polygon: Polygon) -> float:
    min_x, min_y, max_x, max_y = polygon.bounds
    footprint_area = max(1.0, (max_x - min_x) * (max_y - min_y))
    return clamp_height(min(max(math.sqrt(footprint_area) * 0.35, 6.0), 60.0))


def reject_suspect_tagged(
    records_by_path: Dict[Path, List[list]],
    names_by_path: Dict[Path, List[Optional[str]]],
    height_inputs_by_path: Dict[Path, List[List[Optional[float]]]],
    landmarks: List[dict],
    sampler: HeightSampler,
) -> List[dict]:
    candidates = []
    for path, records in records_by_path.items():
        names = names_by_path[path]
        height_inputs = height_inputs_by_path[path]
        for index, record in enumerate(records):
            if record[2] == 4:
                continue
            tag = height_inputs[index][0]
            if tag is None:
                if record[2] in (0, 5, 6):
                    tag = float(record[0])
                else:
                    continue
            polygon = record_polygon(record)
            center = polygon.centroid
            lon, lat = local_to_lonlat(center.x, center.y)
            candidates.append(
                {
                    "path": path,
                    "index": index,
                    "height": float(tag),
                    "floors": height_inputs[index][1],
                    "name": names[index],
                    "polygon": polygon,
                    "area_m2": polygon.area,
                    "x": center.x,
                    "y": center.y,
                    "lat": lat,
                    "lon": lon,
                    "raster": sampler.sample(lon, lat),
                    "landmark": (
                        names[index]
                        if names[index]
                        and any(
                            names[index].strip().casefold()
                            == str(item["name"]).strip().casefold()
                            for item in landmarks
                        )
                        else landmark_nearby_name(lon, lat, landmarks)
                    ),
                }
            )

    clusters: Dict[float, List[dict]] = {}
    for candidate in candidates:
        if candidate["height"] >= 100.0:
            clusters.setdefault(candidate["height"], []).append(candidate)

    csv_rows = []
    for candidate in candidates:
        tag = candidate["height"]
        floors = candidate["floors"]
        floors_h = float(floors) * 3.2 if (floors is not None and floors > 0) else None
        raster_val = candidate["raster"]

        if tag >= 100.0 and tag in clusters:
            shared_count = sum(
                math.hypot(candidate["x"] - other["x"], candidate["y"] - other["y"]) <= 300
                for other in clusters[tag]
            )
        else:
            shared_count = 0

        reasons = []
        # (a) tag > 165 m and building is not in landmarks.json
        if tag > 165.0 and candidate["landmark"] is None:
            reasons.append("tag > 165 m not in landmarks.json")
        # (b) 5 or more buildings within 300 m share the same tag value and that value is >= 100 m
        if tag >= 100.0 and shared_count >= 5:
            reasons.append(
                "at least 5 buildings within 300 m share tagged height {:.1f} m".format(tag)
            )

        record = records_by_path[candidate["path"]][candidate["index"]]

        if reasons:
            # Reject tag (source 5): fall back to GHSL raster value (NOT floors*3.2); if no raster value exists, use area-based guess
            if raster_val is not None:
                fallback_height = clamp_height(float(raster_val))
            else:
                fallback_height = area_based_guess(candidate["polygon"])
            
            final_height = fallback_height
            final_source = 5
            record[0] = round(final_height, 1)
            record[2] = 5

            csv_rows.append({
                "lat": f"{candidate['lat']:.6f}",
                "lon": f"{candidate['lon']:.6f}",
                "tagged_height_m": f"{tag:.1f}",
                "name": candidate["name"] or "",
                "reason": "; ".join(reasons),
                "raster_value_m": f"{raster_val:.1f}" if raster_val is not None else "",
                "floors_height_m": f"{floors_h:.1f}" if floors_h is not None else "",
                "final_height_m": f"{final_height:.1f}",
                "final_source": 5,
            })
        else:
            # Kept tag
            final_height = tag
            # Kept tags >= 80 m where raster is < 40 m get source 6 ("OSM tag, unverified")
            if tag >= 80.0 and raster_val is not None and raster_val < 40.0:
                final_source = 6
                record[0] = round(tag, 1)
                record[2] = 6
                csv_rows.append({
                    "lat": f"{candidate['lat']:.6f}",
                    "lon": f"{candidate['lon']:.6f}",
                    "tagged_height_m": f"{tag:.1f}",
                    "name": candidate["name"] or "",
                    "reason": "kept unverified: tag >= 80 m with raster < 40 m",
                    "raster_value_m": f"{raster_val:.1f}" if raster_val is not None else "",
                    "floors_height_m": f"{floors_h:.1f}" if floors_h is not None else "",
                    "final_height_m": f"{final_height:.1f}",
                    "final_source": 6,
                })
            else:
                final_source = 0
                record[0] = round(tag, 1)
                record[2] = 0

    TAG_REJECTION_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "lat",
        "lon",
        "tagged_height_m",
        "name",
        "reason",
        "raster_value_m",
        "floors_height_m",
        "final_height_m",
        "final_source",
    ]
    with TAG_REJECTION_CSV.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(csv_rows)

    print("Rejected/unverified tags CSV written: {}".format(TAG_REJECTION_CSV))
    print("Row count: {:,}".format(len(csv_rows)))
    source_counts_csv = Counter(r["final_source"] for r in csv_rows)
    print("Counts per final_source: {}".format(dict(source_counts_csv)))
    print("Head -15 rows of rejected_tags.csv:")
    with TAG_REJECTION_CSV.open("r", encoding="utf-8") as f:
        for i in range(16):
            line = f.readline()
            if not line:
                break
            print(line.rstrip())

    # Also update web/data/rejected_tags.json
    rejected_dict = {}
    for r in csv_rows:
        if r["final_source"] == 5:
            key = f"{float(r['lat']):.5f}_{float(r['lon']):.5f}"
            rejected_dict[key] = {
                "tagged_height": float(r["tagged_height_m"]),
                "fallback_height": float(r["final_height_m"]),
                "raster_value_m": float(r["raster_value_m"]) if r["raster_value_m"] else None,
                "reason": r["reason"],
                "final_source": r["final_source"],
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
            }
    (WEB_DATA_DIR / "rejected_tags.json").write_text(
        json.dumps(rejected_dict, indent=2), encoding="utf-8"
    )
    return csv_rows


def sanity_check_and_cap(
    records_by_path: Dict[Path, List[list]],
    names_by_path: Dict[Path, List[Optional[str]]],
    landmarks: List[dict],
) -> List[dict]:
    flagged = []
    capped = []
    for path, records in records_by_path.items():
        names = names_by_path[path]
        for index, record in enumerate(records):
            height, coordinates, source = record
            if source not in (0, 3, 6):
                continue
            polygon = record_polygon(record)
            center = polygon.centroid
            lon, lat = local_to_lonlat(center.x, center.y)
            nearby = landmark_nearby_name(lon, lat, landmarks)
            area = polygon.area
            if float(height) > 100 and nearby is None:
                flagged.append(
                    {
                        "height_m": float(height),
                        "lat": lat,
                        "lon": lon,
                        "source_code": source,
                        "area_m2": area,
                        "name": names[index],
                        "footprint_check": (
                            "small footprint; questionable for a tower"
                            if area < SMALL_FOOTPRINT_AREA_M2
                            else "footprint area is compatible with a tower"
                        ),
                    }
                )
            cap = None
            reason = None
            if source == 3 and float(height) > MAX_RASTER_HEIGHT_M:
                cap = MAX_RASTER_HEIGHT_M
                reason = "coarse raster prior ceiling"
            elif (
                source == 0
                and float(height) > SMALL_TAGGED_TOWER_CAP_M
                and area < SMALL_FOOTPRINT_AREA_M2
                and nearby is None
            ):
                cap = SMALL_TAGGED_TOWER_CAP_M
                reason = "small unlandmarked tagged footprint ceiling"
            if cap is not None:
                capped.append(
                    {
                        "height_before_m": float(height),
                        "height_after_m": cap,
                        "lat": lat,
                        "lon": lon,
                        "source_code": source,
                        "area_m2": area,
                        "name": names[index],
                        "reason": reason,
                    }
                )
                record[0] = cap
    print("Height sanity flags (>100 m tagged/raster, not near a listed landmark):")
    if not flagged:
        print("  none")
    for item in flagged:
        print(
            "  {height_m:.1f} m source={source_code} area={area_m2:.1f} m² "
            "at {lat:.6f},{lon:.6f} name={name!r}: {footprint_check}".format(**item)
        )
    print("Height caps applied:")
    if not capped:
        print("  none")
    for item in capped:
        print(
            "  {height_before_m:.1f} -> {height_after_m:.1f} m "
            "source={source_code} area={area_m2:.1f} m² "
            "at {lat:.6f},{lon:.6f} name={name!r}: {reason}".format(**item)
        )
    return capped


def top_buildings(
    records_by_path: Dict[Path, List[list]],
    names_by_path: Dict[Path, List[Optional[str]]],
    landmarks: List[dict],
    limit: int = 25,
) -> List[dict]:
    tallest = []
    for path, records in records_by_path.items():
        names = names_by_path[path]
        for index, (height, coordinates, source) in enumerate(records):
            polygon = Polygon(list(zip(coordinates[::2], coordinates[1::2])))
            center = polygon.centroid
            lon, lat = local_to_lonlat(center.x, center.y)
            name = names[index] or landmark_nearby_name(lon, lat, landmarks)
            tallest.append(
                {
                    "height_m": float(height),
                    "lat": lat,
                    "lon": lon,
                    "name": name,
                    "source_code": int(source),
                    "area_m2": polygon.area,
                }
            )
    return sorted(tallest, key=lambda item: item["height_m"], reverse=True)[:limit]


def atomic_write_json(path: Path, value: object) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=".fuse-", suffix=".tmp"
    ) as temporary:
        temporary_path = Path(temporary.name)
        json.dump(value, temporary, separators=(",", ":"))
        temporary.write("\n")
    temporary_path.replace(path)


def fuse_dataset(raster_path: Path, landmarks_path: Path) -> dict:
    manifest_path = WEB_DATA_DIR / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("No viewer manifest found at {}.".format(manifest_path))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest.get("chunks"), list):
        raise ValueError("Viewer manifest has no chunks array.")
    landmarks = read_landmarks(landmarks_path)

    with rasterio.open(raster_path) as raster:
        report_raster(raster)
        sampler = HeightSampler(raster)
        records_by_path: Dict[Path, List[list]] = {}
        names_by_path: Dict[Path, List[Optional[str]]] = {}
        height_inputs_by_path: Dict[Path, List[List[Optional[float]]]] = {}
        before = Counter()
        total = 0
        for chunk in manifest["chunks"]:
            filename = chunk.get("buildingFile")
            if not filename:
                continue
            path = WEB_DATA_DIR / filename
            records = read_chunk_records(path)
            names_by_path[path] = load_chunk_names(
                manifest, chunk, path, len(records)
            )
            height_inputs_by_path[path] = load_height_inputs(
                manifest, chunk, len(records), records
            )
            for record in records:
                polygon = record_polygon(record)
                before[source_label(record[2])] += 1
                height, source = fused_height(record, polygon, sampler)
                record[0] = round(height, 1)
                record[2] = source
            records_by_path[path] = records
            total += len(records)

        if total == 0:
            raise ValueError("No building records were found in the viewer chunks.")
        overrides = add_landmark_overrides(records_by_path, landmarks)
        rejected = reject_suspect_tagged(
            records_by_path,
            names_by_path,
            height_inputs_by_path,
            landmarks,
            sampler,
        )
        capped = sanity_check_and_cap(records_by_path, names_by_path, landmarks)
        after = source_counts(records_by_path)
        if sum(after.values()) != total:
            raise RuntimeError("Fused height source totals do not match the building count.")

        for path, records in records_by_path.items():
            atomic_write_json(path, records)

    manifest["heightSourceCounts"] = {
        SOURCE_NAMES[code]: after.get(SOURCE_NAMES[code], 0) for code in SOURCE_NAMES
    }
    manifest["heightSourceCodes"] = {str(code): name for code, name in SOURCE_NAMES.items()}
    manifest["heightRaster"] = {
        "file": str(raster_path.relative_to(ROOT)),
        "product": "GHS-BUILT-H ANBH 2018",
        "crs": "EPSG:4326",
        "sampling": "3x3-cell median at footprint centroid; zero/nodata ignored",
        "resolution_note": "Approximately 90 m cells; values are neighbourhood-level averages.",
    }
    atomic_write_json(manifest_path, manifest)
    atomic_write_json(WEB_DATA_DIR / "landmarks.json", landmarks)

    print("Buildings fused: {:,}".format(total))
    print("Height sources before fusion:")
    for name in (
        "tagged",
        "floors",
        "raster",
        "guess",
        "verified landmark",
        "tag rejected",
        "OSM tag, unverified",
    ):
        count = before.get(name, 0)
        print("  {}: {:,} ({:.2f}%)".format(name, count, 100 * count / total))
    print("Height sources after fusion:")
    for name in (
        "tagged",
        "floors",
        "raster",
        "guess",
        "verified landmark",
        "tag rejected",
        "OSM tag, unverified",
    ):
        count = after.get(name, 0)
        print("  {}: {:,} ({:.2f}%)".format(name, count, 100 * count / total))
    print("Height histogram (metres):")
    for label, count in height_histogram(records_by_path).items():
        print("  {:>12}: {:,}".format(label, count))
    print("Height histogram by source (metres):")
    for source_name, histogram in height_histogram_by_source(records_by_path).items():
        nonzero = [
            "{}={:,}".format(bin_name, count)
            for bin_name, count in histogram.items()
            if count
        ]
        print("  {}: {}".format(source_name, ", ".join(nonzero) or "none"))
    print("Buildings >= 100 m by source:")
    ge_100_by_source = Counter()
    for records in records_by_path.values():
        for r in records:
            if float(r[0]) >= 100.0:
                ge_100_by_source[source_label(r[2])] += 1
    for src_name, c_cnt in sorted(ge_100_by_source.items()):
        print("  {}: {:,}".format(src_name, c_cnt))
    print("25 tallest footprints:")
    for item in top_buildings(records_by_path, names_by_path, landmarks):
        print(
            "  {height_m:6.1f} m  lat={lat:.6f} lon={lon:.6f} "
            "source_code={source_code} area={area_m2:.1f} m² name={name}".format(**item)
        )
    print("Landmark matches (chunk data has no Overture building names; nearest footprint used):")
    for match in overrides:
        landmark = match["landmark"]
        distance = match.get("distance_m")
        suffix = " ({:.1f} m, {})".format(distance, match["chunk"]) if distance is not None else ""
        print("  {}: {}{}".format(landmark["name"], match["status"], suffix))
    print(
        "GHSL GHS-BUILT-H is a ~90 m neighbourhood-level average, not a per-building "
        "measurement; it will underestimate the tallest towers."
    )
    return {
        "building_count": total,
        "before": dict(before),
        "after": dict(after),
        "height_histogram": height_histogram(records_by_path),
        "height_histogram_by_source": height_histogram_by_source(records_by_path),
        "height_caps": capped,
        "rejected_tags": rejected,
        "landmark_matches": overrides,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fuse local Overture building chunks with a GHSL height raster."
    )
    parser.add_argument("--raster", type=Path, default=default_raster_path())
    parser.add_argument("--landmarks", type=Path, default=LANDMARKS_PATH)
    args = parser.parse_args()
    if not args.raster.is_file():
        parser.error("GHSL raster not found: {}".format(args.raster))
    fuse_dataset(args.raster.resolve(), args.landmarks.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
