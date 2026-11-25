import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js";

const SOURCE_COLORS = [
  new THREE.Color("#4fc4a2"),
  new THREE.Color("#68a6ff"),
  new THREE.Color("#eb7676"),
  new THREE.Color("#ffc54a"),
  new THREE.Color("#ff6cf0"),
  new THREE.Color("#f28e5b"),
  new THREE.Color("#a855f7"),
];
const SOURCE_CODES = {
  tagged: 0,
  "from floors": 1,
  guessed: 2,
  raster: 3,
  "verified landmark": 4,
  "tag rejected": 5,
  "OSM tag, unverified": 6,
};
const ROAD_WIDTHS = {
  motorway: 14, trunk: 12, primary: 10, secondary: 8, tertiary: 6,
  unclassified: 4, residential: 3, living_street: 3, service: 3,
  pedestrian: 2, track: 2, cycleway: 2, footway: 1.5, bridleway: 2,
  path: 1.5, steps: 1.5, unknown: 3,
};

function colorGeometry(geometry, source) {
  const code = typeof source === "number" ? source : (SOURCE_CODES[source] ?? 2);
  const color = SOURCE_COLORS[code] || SOURCE_COLORS[2];
  const colors = new Uint8Array(geometry.attributes.position.count * 3);
  for (let index = 0; index < colors.length; index += 3) {
    colors[index] = Math.round(color.r * 255);
    colors[index + 1] = Math.round(color.g * 255);
    colors[index + 2] = Math.round(color.b * 255);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3, true));
}

function merge(geometries) {
  if (!geometries.length) return null;
  const geometry = new THREE.BufferGeometry();
  const attributeNames = Object.keys(geometries[0].attributes);
  for (const name of attributeNames) {
    const first = geometries[0].attributes[name];
    const length = geometries.reduce(
      (total, part) => total + part.attributes[name].array.length,
      0,
    );
    const array = new first.array.constructor(length);
    let offset = 0;
    for (const part of geometries) {
      const attribute = part.attributes[name];
      if (attribute.itemSize !== first.itemSize ||
          attribute.normalized !== first.normalized) {
        throw new Error(`Incompatible ${name} geometry attributes.`);
      }
      array.set(attribute.array, offset);
      offset += attribute.array.length;
    }
    geometry.setAttribute(
      name,
      new THREE.BufferAttribute(array, first.itemSize, first.normalized),
    );
  }
  const vertexCount = geometry.attributes.position.count;
  const indexCount = geometries.reduce(
    (total, part) => total + (part.index ? part.index.count : part.attributes.position.count),
    0,
  );
  const IndexArray = vertexCount > 65535 ? Uint32Array : Uint16Array;
  const indices = new IndexArray(indexCount);
  let indexOffset = 0;
  let vertexOffset = 0;
  for (const part of geometries) {
    if (part.index) {
      for (let index = 0; index < part.index.count; index += 1) {
        indices[indexOffset++] = part.index.array[index] + vertexOffset;
      }
    } else {
      for (let index = 0; index < part.attributes.position.count; index += 1) {
        indices[indexOffset++] = index + vertexOffset;
      }
    }
    vertexOffset += part.attributes.position.count;
  }
  geometry.setIndex(new THREE.BufferAttribute(indices, 1));
  for (const part of geometries) part.dispose();
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  return geometry;
}

function packGeometry(geometry) {
  if (!geometry) return null;
  const sphere = geometry.boundingSphere;
  return {
    position: geometry.attributes.position.array,
    normal: geometry.attributes.normal.array,
    uv: geometry.attributes.uv?.array || null,
    color: geometry.attributes.color?.array || null,
    colorNormalized: geometry.attributes.color?.normalized || false,
    index: geometry.index?.array || null,
    sphere: sphere
      ? [sphere.center.x, sphere.center.y, sphere.center.z, sphere.radius]
      : null,
  };
}

function polygonCentroid(coordinates) {
  let twiceArea = 0;
  let xSum = 0;
  let northSum = 0;
  for (let index = 0; index < coordinates.length; index += 2) {
    const next = (index + 2) % coordinates.length;
    const cross =
      coordinates[index] * coordinates[next + 1] -
      coordinates[next] * coordinates[index + 1];
    twiceArea += cross;
    xSum += (coordinates[index] + coordinates[next]) * cross;
    northSum += (coordinates[index + 1] + coordinates[next + 1]) * cross;
  }
  if (Math.abs(twiceArea) < 1e-8) {
    let x = 0, north = 0;
    for (let index = 0; index < coordinates.length; index += 2) {
      x += coordinates[index];
      north += coordinates[index + 1];
    }
    const count = coordinates.length / 2;
    return [x / count, north / count];
  }
  return [xSum / (3 * twiceArea), northSum / (3 * twiceArea)];
}

function terrainHeight(terrain, ix, iy, x, north) {
  if (!terrain || terrain.width < 2 || terrain.heights.length !== terrain.width * terrain.height) {
    return 0;
  }
  const scale = terrain.width - 1;
  const fx = Math.max(0, Math.min(scale, (x / 1000 - ix) * scale));
  const fy = Math.max(0, Math.min(scale, (north / 1000 - iy) * scale));
  const x0 = Math.floor(fx), y0 = Math.floor(fy);
  const x1 = Math.min(scale, x0 + 1), y1 = Math.min(scale, y0 + 1);
  const tx = fx - x0, ty = fy - y0;
  const at = (col, row) => terrain.heights[row * terrain.width + col];
  const a = at(x0, y0) * (1 - tx) + at(x1, y0) * tx;
  const b = at(x0, y1) * (1 - tx) + at(x1, y1) * tx;
  return a * (1 - ty) + b * ty;
}

const HERO_LANDMARK_CHUNKS = {
  "-1,0": new Set([192]), // Vidhana Soudha
  "0,0": new Set([70, 64, 65, 68, 69]), // UB City Complex
  "13,25": new Set([39]) // KIA Terminal 2
};

function makeBuildingGeometry(buildings, bases, lod, ix, iy, terrain, exaggeration) {
  if (!Array.isArray(buildings) || lod === "far") {
    return { geometry: null, bounds: new Float32Array(), verticalExtents: new Float32Array() };
  }
  const geometries = [];
  const bounds = new Float32Array(buildings.length * 4);
  const verticalExtents = new Float32Array(buildings.length * 2);

  buildings.forEach(([height, coordinates, source], index) => {
    if (!Number.isFinite(height) || !Array.isArray(coordinates) ||
        coordinates.length < 6 || coordinates.length % 2 !== 0 ||
        coordinates.some(value => !Number.isFinite(value))) {
      throw new Error(`Invalid building record at index ${index}.`);
    }
    let minX = Infinity, minNorth = Infinity;
    let maxX = -Infinity, maxNorth = -Infinity;
    for (let offset = 0; offset < coordinates.length; offset += 2) {
      minX = Math.min(minX, coordinates[offset]);
      maxX = Math.max(maxX, coordinates[offset]);
      minNorth = Math.min(minNorth, coordinates[offset + 1]);
      maxNorth = Math.max(maxNorth, coordinates[offset + 1]);
    }
    const centerX = (minX + maxX) / 2;
    const centerNorth = (minNorth + maxNorth) / 2;

    const [cx, cn] = polygonCentroid(coordinates);
    const centerTerrain = terrain ? terrainHeight(terrain, ix, iy, cx, cn) : 0;
    let minTerrain = centerTerrain;
    let maxTerrain = centerTerrain;
    if (terrain) {
      for (let offset = 0; offset < coordinates.length; offset += 2) {
        const tz = terrainHeight(terrain, ix, iy, coordinates[offset], coordinates[offset + 1]);
        if (tz < minTerrain) minTerrain = tz;
        if (tz > maxTerrain) maxTerrain = tz;
      }
    }

    const effectiveHeight = Math.max(3, height);
    // Ensure the roof is elevated above the terrain at all points of the footprint:
    const roofElevation = Math.max(centerTerrain + effectiveHeight, maxTerrain + Math.min(3, effectiveHeight));
    // Foundation skirt: extend 1.5m below the lowest ground point under the footprint
    // so side walls embed into hillsides without floating gaps or digging down:
    const baseElevation = minTerrain - 1.5;

    const roofY = roofElevation * exaggeration;
    const baseY = baseElevation * exaggeration;
    const totalDepth = Math.max(1, roofY - baseY);
    const centerY = (baseY + roofY) / 2;

    bounds.set([
      centerX,
      centerY,
      -centerNorth,
      Math.hypot((maxX - minX) / 2, totalDepth / 2, (maxNorth - minNorth) / 2),
    ], index * 4);

    verticalExtents[index * 2] = baseY;
    verticalExtents[index * 2 + 1] = roofY;

    // Skip normal extrusion in chunk-worker for hero landmarks to prevent z-fighting with procedural hero mesh
    if (HERO_LANDMARK_CHUNKS[`${ix},${iy}`]?.has(index)) {
      return;
    }

    let geometry;
    if (lod === "mid") {
      geometry = new THREE.BoxGeometry(
        Math.max(1, maxX - minX),
        totalDepth,
        Math.max(1, maxNorth - minNorth),
      );
      geometry.translate(centerX, centerY, -centerNorth);
    } else {
      const shape = new THREE.Shape();
      shape.moveTo(coordinates[0], coordinates[1]);
      for (let offset = 2; offset < coordinates.length; offset += 2) {
        shape.lineTo(coordinates[offset], coordinates[offset + 1]);
      }
      shape.closePath();
      geometry = new THREE.ExtrudeGeometry(shape, {
        depth: totalDepth,
        bevelEnabled: false,
        curveSegments: 1,
      });
      geometry.rotateX(-Math.PI / 2);
      geometry.translate(0, baseY, 0);
    }
    colorGeometry(geometry, source);
    geometries.push(geometry);
  });
  return { geometry: merge(geometries), bounds, verticalExtents };
}

const NEAR_MASK_RADIUS_M = 2000;
const NEAR_MASK_SIZE = 512;
const FAR_MASK_SIZE = 256;
const CAMERA_START_X = 180;
const CAMERA_START_NORTH = 620;

function getMaskSizeForChunk(ix, iy) {
  const chunkCenterX = ix * 1000 + 500;
  const chunkCenterNorth = iy * 1000 + 500;
  const dist = Math.hypot(chunkCenterX - CAMERA_START_X, chunkCenterNorth - CAMERA_START_NORTH);
  return dist <= NEAR_MASK_RADIUS_M ? NEAR_MASK_SIZE : FAR_MASK_SIZE;
}

function buildMaskTexture(ground, ix, iy) {
  const maskSize = getMaskSizeForChunk(ix, iy);
  const canvas = new OffscreenCanvas(maskSize, maskSize);
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  ctx.fillStyle = "rgb(0,0,0)";
  ctx.fillRect(0, 0, maskSize, maskSize);
  ctx.globalCompositeOperation = "lighter";

  const chunkWest = ix * 1000;
  const chunkNorth = (iy + 1) * 1000;
  const pxPerMetre = maskSize / 1000;

  function toPx(x, north) {
    return [
      (x - chunkWest) * pxPerMetre,
      (chunkNorth - north) * pxPerMetre,
    ];
  }

  function drawPolygon(coordinates, holes) {
    if (!Array.isArray(coordinates) || coordinates.length < 6) return;
    ctx.beginPath();
    const [startX, startY] = toPx(coordinates[0], coordinates[1]);
    ctx.moveTo(startX, startY);
    for (let i = 2; i < coordinates.length; i += 2) {
      const [px, py] = toPx(coordinates[i], coordinates[i + 1]);
      ctx.lineTo(px, py);
    }
    ctx.closePath();

    for (const hole of holes || []) {
      if (!Array.isArray(hole) || hole.length < 6) continue;
      const [hx, hy] = toPx(hole[0], hole[1]);
      ctx.moveTo(hx, hy);
      for (let i = 2; i < hole.length; i += 2) {
        const [px, py] = toPx(hole[i], hole[i + 1]);
        ctx.lineTo(px, py);
      }
      ctx.closePath();
    }
    ctx.fill("evenodd");
  }

  // 1. Draw Green polygons in Red (rgb(255, 0, 0))
  ctx.fillStyle = "rgb(255,0,0)";
  for (const record of ground?.green || []) {
    drawPolygon(record.p, record.holes);
  }

  // 2. Draw Water polygons in Green (rgb(0, 255, 0))
  ctx.fillStyle = "rgb(0,255,0)";
  const water = ground?.water || {};
  for (const record of water.polygons || []) {
    drawPolygon(record.p, record.holes);
  }

  // Also draw water lines (streams, canals) into green channel
  if (Array.isArray(water.lines)) {
    ctx.strokeStyle = "rgb(0,255,0)";
    ctx.lineWidth = Math.max(1, 2.5 * pxPerMetre);
    for (const record of water.lines) {
      const coords = record.p;
      if (!Array.isArray(coords) || coords.length < 4) continue;
      ctx.beginPath();
      const [sx, sy] = toPx(coords[0], coords[1]);
      ctx.moveTo(sx, sy);
      for (let i = 2; i < coords.length; i += 2) {
        const [px, py] = toPx(coords[i], coords[i + 1]);
        ctx.lineTo(px, py);
      }
      ctx.stroke();
    }
  }

  return canvas.transferToImageBitmap();
}

function makeRibbonGeometry(records, widthForClass, offset, terrain, ix, iy, exaggeration) {
  const vertices = [];
  const indices = [];
  for (const record of records) {
    const coordinates = record.p;
    if (!Array.isArray(coordinates) || coordinates.length < 4 ||
        coordinates.length % 2 !== 0) {
      throw new Error("Invalid ground line.");
    }
    const width = widthForClass(record.class);
    for (let index = 0; index + 3 < coordinates.length; index += 2) {
      const x1 = coordinates[index], north1 = coordinates[index + 1];
      const x2 = coordinates[index + 2], north2 = coordinates[index + 3];
      const dx = x2 - x1, dn = north2 - north1;
      const length = Math.hypot(dx, dn);
      if (length < 0.01) continue;
      const steps = terrain ? Math.max(1, Math.ceil(length / 30)) : 1;
      const offsetX = -dn / length * width / 2;
      const offsetNorth = dx / length * width / 2;
      for (let step = 0; step < steps; step += 1) {
        const t0 = step / steps, t1 = (step + 1) / steps;
        const ax = x1 + dx * t0, an = north1 + dn * t0;
        const bx = x1 + dx * t1, bn = north1 + dn * t1;
        const base = vertices.length / 3;
        const points = [
          [ax + offsetX, an + offsetNorth],
          [ax - offsetX, an - offsetNorth],
          [bx - offsetX, bn - offsetNorth],
          [bx + offsetX, bn + offsetNorth],
        ];
        for (const [x, north] of points) {
          vertices.push(
            x,
            terrainHeight(terrain, ix, iy, x, north) * exaggeration + offset,
            -north,
          );
        }
        indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
      }
    }
  }
  if (!vertices.length) return null;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  return geometry;
}

function makeTerrainGeometry(terrain, ix, iy, exaggeration) {
  if (!terrain) return null;
  const positions = [];
  const uvs = [];
  const indices = [];
  const width = terrain.width;
  const height = terrain.height;
  for (let row = 0; row < height; row += 1) {
    for (let col = 0; col < width; col += 1) {
      positions.push(
        ix * 1000 + (col / (width - 1)) * 1000,
        terrain.heights[row * width + col] * exaggeration,
        -(iy * 1000 + (row / (height - 1)) * 1000),
      );
      uvs.push(
        col / (width - 1),
        row / (height - 1),
      );
    }
  }
  for (let row = 0; row < height - 1; row += 1) {
    for (let col = 0; col < width - 1; col += 1) {
      const a = row * width + col;
      const b = a + 1;
      const c = a + width;
      const d = c + 1;
      indices.push(a, b, c, b, d, c);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  return geometry;
}

function reverseRoadPts(road) {
  const oldPts = road.pts;
  const numPts = oldPts.length / 4;
  const newPts = new Float32Array(oldPts.length);
  let cumDist = 0.0;
  let prevX = oldPts[(numPts - 1) * 4];
  let prevY = oldPts[(numPts - 1) * 4 + 1];
  let prevZ = oldPts[(numPts - 1) * 4 + 2];
  newPts[0] = prevX;
  newPts[1] = prevY;
  newPts[2] = prevZ;
  newPts[3] = 0.0;

  for (let i = 1; i < numPts; i++) {
    const srcIdx = (numPts - 1 - i) * 4;
    const curX = oldPts[srcIdx];
    const curY = oldPts[srcIdx + 1];
    const curZ = oldPts[srcIdx + 2];
    const stepDist = Math.hypot(curX - prevX, curZ - prevZ);
    cumDist += stepDist;
    newPts[i * 4] = curX;
    newPts[i * 4 + 1] = curY;
    newPts[i * 4 + 2] = curZ;
    newPts[i * 4 + 3] = cumDist;
    prevX = curX;
    prevY = curY;
    prevZ = curZ;
  }
  road.pts = newPts;
  road.totalLength = cumDist;
}

function extractMajorRoads(records, terrain, ix, iy) {
  const result = [];
  if (!records || !Array.isArray(records)) return result;

  for (const record of records) {
    const className = record.class;
    if (!["motorway", "trunk", "primary"].includes(className)) continue;
    const coordinates = record.p;
    if (!Array.isArray(coordinates) || coordinates.length < 4 || coordinates.length % 2 !== 0) continue;

    const points3D = [];
    let cumDist = 0.0;

    let prevX = coordinates[0];
    let prevNorth = coordinates[1];
    let prevRawY = terrainHeight(terrain, ix, iy, prevX, prevNorth);
    let prevZ = -prevNorth;
    points3D.push(prevX, prevRawY, prevZ, 0.0);

    for (let i = 0; i + 3 < coordinates.length; i += 2) {
      const x1 = coordinates[i], north1 = coordinates[i + 1];
      const x2 = coordinates[i + 2], north2 = coordinates[i + 3];
      const dx = x2 - x1, dn = north2 - north1;
      const segLen = Math.hypot(dx, dn);
      if (segLen < 0.01) continue;

      const steps = terrain ? Math.max(1, Math.ceil(segLen / 35)) : 1;
      for (let s = 1; s <= steps; s++) {
        const t = s / steps;
        const curX = x1 + dx * t;
        const curNorth = north1 + dn * t;
        const curRawY = terrainHeight(terrain, ix, iy, curX, curNorth);
        const curZ = -curNorth;

        const stepDist = Math.hypot(curX - prevX, curNorth - prevNorth);
        cumDist += stepDist;
        points3D.push(curX, curRawY, curZ, cumDist);

        prevX = curX;
        prevNorth = curNorth;
        prevZ = curZ;
      }
    }

    if (cumDist >= 15.0 && points3D.length >= 8) {
      result.push({
        class: className,
        pts: new Float32Array(points3D),
        totalLength: cumDist,
        isOneWay: false,
        flowDir: 0,
      });
    }
  }

  // Divided-carriageway detection (Tightened per Round 7 audit):
  // Minimum length 50.0m, mutual-nearest partner matching, angle < 10 degrees (dot >= 0.9848),
  // matching road class, balanced length ratio (<= 2.5) to avoid junction flares.
  const candidatePairs = [];
  for (let i = 0; i < result.length; i++) {
    const r1 = result[i];
    if (r1.totalLength < 50.0) continue;
    const p1 = r1.pts;
    const dx1 = p1[p1.length - 4] - p1[0];
    const dz1 = p1[p1.length - 2] - p1[2];
    const hyp1 = Math.hypot(dx1, dz1);
    if (hyp1 < 0.01) continue;
    const ux1 = dx1 / hyp1, uz1 = dz1 / hyp1;

    for (let j = i + 1; j < result.length; j++) {
      const r2 = result[j];
      if (r2.totalLength < 50.0) continue;
      if (r1.class !== r2.class) continue;
      const lenRatio = Math.max(r1.totalLength, r2.totalLength) / Math.min(r1.totalLength, r2.totalLength);
      if (lenRatio > 2.5) continue;

      const p2 = r2.pts;
      const dx2 = p2[p2.length - 4] - p2[0];
      const dz2 = p2[p2.length - 2] - p2[2];
      const hyp2 = Math.hypot(dx2, dz2);
      if (hyp2 < 0.01) continue;
      const ux2 = dx2 / hyp2, uz2 = dz2 / hyp2;

      // Cosine of angle between polylines (angle < 10 degrees -> dot >= 0.9848)
      const dot = Math.abs(ux1 * ux2 + uz1 * uz2);
      if (dot < 0.9848) continue;

      const mid1 = Math.floor(p1.length / 8) * 4;
      const mid2 = Math.floor(p2.length / 8) * 4;
      const vx = p2[mid2] - p1[mid1];
      const vz = p2[mid2 + 2] - p1[mid1 + 2];
      const dist = Math.hypot(vx, vz);
      if (dist < 7.0 || dist > 40.0) continue;

      candidatePairs.push({ i, j, dist, ux1, uz1, vx, vz });
    }
  }

  // Mutual-nearest partner matching
  candidatePairs.sort((a, b) => a.dist - b.dist);
  const pairedIndices = new Set();
  for (const pair of candidatePairs) {
    if (pairedIndices.has(pair.i) || pairedIndices.has(pair.j)) continue;
    pairedIndices.add(pair.i);
    pairedIndices.add(pair.j);

    const r1 = result[pair.i];
    const r2 = result[pair.j];
    const { ux1, uz1, vx, vz } = pair;

    const side = vx * uz1 - vz * ux1;
    const leftRoad = side > 0 ? r2 : r1;
    const rightRoad = side > 0 ? r1 : r2;

    const l_dx = leftRoad.pts[leftRoad.pts.length - 4] - leftRoad.pts[0];
    const l_dz = leftRoad.pts[leftRoad.pts.length - 2] - leftRoad.pts[2];
    if (l_dx * ux1 + l_dz * uz1 < 0) {
      reverseRoadPts(leftRoad);
    }
    leftRoad.isOneWay = true;
    leftRoad.flowDir = +1;

    const r_dx = rightRoad.pts[rightRoad.pts.length - 4] - rightRoad.pts[0];
    const r_dz = rightRoad.pts[rightRoad.pts.length - 2] - rightRoad.pts[2];
    if (r_dx * ux1 + r_dz * uz1 < 0) {
      reverseRoadPts(rightRoad);
    }
    rightRoad.isOneWay = true;
    rightRoad.flowDir = -1;
  }

  return result;
}

function build(message) {
  const buildings = message.buildingsText ? JSON.parse(message.buildingsText) : [];
  const ground = message.groundText ? JSON.parse(message.groundText) : null;
  const terrain = message.terrainText ? JSON.parse(message.terrainText) : null;
  const ix = message.ix;
  const iy = message.iy;
  const exaggeration = Number.isFinite(message.exaggeration)
    ? message.exaggeration
    : 1;
  const building = makeBuildingGeometry(
    buildings,
    terrain?.buildingBases || message.buildingBases,
    message.lod || "near",
    ix,
    iy,
    terrain,
    exaggeration,
  );
  const maskBitmap = message.lodOnly
    ? null
    : buildMaskTexture(ground, ix, iy);
  const groundMeshes = message.lodOnly
    ? { terrain: null, roads: null }
    : {
      terrain: makeTerrainGeometry(terrain, ix, iy, exaggeration),
      roads: makeRibbonGeometry(
        ground?.roads || [],
        className => ROAD_WIDTHS[className] || ROAD_WIDTHS.unknown,
        0.22,
        terrain,
        ix,
        iy,
        exaggeration,
      ),
    };
  const majorRoads = message.lodOnly
    ? null
    : extractMajorRoads(ground?.roads, terrain, ix, iy);
  return {
    building: packGeometry(building.geometry),
    bounds: building.bounds,
    verticalExtents: building.verticalExtents,
    maskBitmap,
    majorRoads,
    ground: Object.fromEntries(
      Object.entries(groundMeshes).map(([name, geometry]) => [name, packGeometry(geometry)]),
    ),
  };
}

self.onmessage = event => {
  const { id } = event.data;
  try {
    const result = build(event.data);
    const transfer = [result.bounds.buffer];
    if (result.verticalExtents?.buffer) transfer.push(result.verticalExtents.buffer);
    if (result.maskBitmap) transfer.push(result.maskBitmap);
    if (result.majorRoads) {
      for (const road of result.majorRoads) {
        if (road.pts?.buffer && !transfer.includes(road.pts.buffer)) {
          transfer.push(road.pts.buffer);
        }
      }
    }
    for (const item of [result.building, ...Object.values(result.ground)]) {
      if (!item) continue;
      for (const value of [item.position, item.normal, item.uv, item.color, item.index]) {
        if (value?.buffer && !transfer.includes(value.buffer)) transfer.push(value.buffer);
      }
      if (item.sphere) item.sphere = Float32Array.from(item.sphere);
      if (item.sphere?.buffer) transfer.push(item.sphere.buffer);
    }
    self.postMessage({ id, result }, transfer);
  } catch (error) {
    self.postMessage({ id, error: error instanceof Error ? error.message : String(error) });
  }
};
