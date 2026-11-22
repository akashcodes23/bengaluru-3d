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
  "corroborated by floors": 6,
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

function makeBuildingGeometry(buildings, bases, lod, ix, iy, terrain, exaggeration) {
  if (!Array.isArray(buildings) || lod === "far") {
    return { geometry: null, bounds: new Float32Array() };
  }
  const geometries = [];
  const bounds = new Float32Array(buildings.length * 4);
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
    const rawBaseY = Number.isFinite(bases?.[index])
      ? bases[index]
      : terrainHeight(terrain, ix, iy, ...polygonCentroid(coordinates));
    const baseY = rawBaseY * exaggeration;
    const buildingHeight = Math.max(3, height) * exaggeration;
    const centerY = baseY + buildingHeight / 2;
    bounds.set([
      centerX,
      centerY,
      -centerNorth,
      Math.hypot((maxX - minX) / 2, buildingHeight / 2, (maxNorth - minNorth) / 2),
    ], index * 4);

    let geometry;
    if (lod === "mid") {
      geometry = new THREE.BoxGeometry(
        Math.max(1, maxX - minX),
        buildingHeight,
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
        depth: buildingHeight,
        bevelEnabled: false,
        curveSegments: 1,
      });
      geometry.rotateX(-Math.PI / 2);
      geometry.translate(0, baseY, 0);
    }
    colorGeometry(geometry, source);
    geometries.push(geometry);
  });
  return { geometry: merge(geometries), bounds };
}

function shapeFromRecord(record, name) {
  const coordinates = record.p;
  if (!Array.isArray(coordinates) || coordinates.length < 6 ||
      coordinates.length % 2 !== 0 ||
      coordinates.some(value => !Number.isFinite(value))) {
    throw new Error(`Invalid ${name} polygon.`);
  }
  const shape = new THREE.Shape();
  shape.moveTo(coordinates[0], coordinates[1]);
  for (let index = 2; index < coordinates.length; index += 2) {
    shape.lineTo(coordinates[index], coordinates[index + 1]);
  }
  shape.closePath();
  for (const holeCoordinates of record.holes || []) {
    const hole = new THREE.Path();
    hole.moveTo(holeCoordinates[0], holeCoordinates[1]);
    for (let index = 2; index < holeCoordinates.length; index += 2) {
      hole.lineTo(holeCoordinates[index], holeCoordinates[index + 1]);
    }
    hole.closePath();
    shape.holes.push(hole);
  }
  return shape;
}

function drapeGeometry(geometry, offset, terrain, ix, iy, exaggeration) {
  geometry.rotateX(-Math.PI / 2);
  const positions = geometry.attributes.position;
  for (let index = 0; index < positions.count; index += 1) {
    const x = positions.getX(index);
    const north = -positions.getZ(index);
    positions.setY(
      index,
      terrainHeight(terrain, ix, iy, x, north) * exaggeration + offset,
    );
  }
  positions.needsUpdate = true;
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  return geometry;
}

function makePolygonGeometry(records, offset, kind, terrain, ix, iy, exaggeration) {
  const geometries = [];
  for (const record of records) {
    let geometry = new THREE.ShapeGeometry(shapeFromRecord(record, kind));
    if (terrain) {
      geometry = drapeGeometry(geometry, offset, terrain, ix, iy, exaggeration);
    }
    else {
      geometry.rotateX(-Math.PI / 2);
      geometry.translate(0, offset, 0);
    }
    geometries.push(geometry);
  }
  return merge(geometries);
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
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  return geometry;
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
  const water = ground?.water || {};
  const groundMeshes = message.lodOnly
    ? { terrain: null, water: null, waterLines: null, green: null, roads: null }
    : {
      terrain: makeTerrainGeometry(terrain, ix, iy, exaggeration),
      water: makePolygonGeometry(
        water.polygons || [], 0.05, "water", terrain, ix, iy, exaggeration,
      ),
      waterLines: makeRibbonGeometry(
        water.lines || [], () => 2.5, 0.05, terrain, ix, iy, exaggeration,
      ),
      green: makePolygonGeometry(
        ground?.green || [], 0.03, "green", terrain, ix, iy, exaggeration,
      ),
      roads: makeRibbonGeometry(
        ground?.roads || [],
        className => ROAD_WIDTHS[className] || ROAD_WIDTHS.unknown,
        0.25,
        terrain,
        ix,
        iy,
        exaggeration,
      ),
    };
  return {
    building: packGeometry(building.geometry),
    bounds: building.bounds,
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
    for (const item of [result.building, ...Object.values(result.ground)]) {
      if (!item) continue;
      for (const value of [item.position, item.normal, item.color, item.index]) {
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
