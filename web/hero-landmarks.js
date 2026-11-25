import * as THREE from "three";
import * as BufferGeometryUtils from "three/addons/utils/BufferGeometryUtils.js";

/**
 * Procedural Hero Landmarks for Bengaluru 3D
 * 1. Vidhana Soudha (46 m verified height; central dome, corner chattris, pillared Dravidian porch)
 * 2. UB City (123 m verified UB Tower; 4-tower complex on shared podium)
 * 3. Kempegowda International Airport Terminal 2 (bamboo lattice roof, tiered skylights, glass curtain walls)
 *
 * Footprints sourced directly from real Overture data polygons.
 */

export const HERO_DATA = {
  "vidhana_soudha": {
    "chunk": "-1,0",
    "index": 192,
    "height": 46.0,
    "polygon": [
      -494.35,
      811.73,
      -492.06,
      814.13,
      -465.72,
      789.12,
      -462.75,
      792.52,
      -460.96,
      790.7,
      -455.2,
      790.64,
      -451.09,
      794.64,
      -451.02,
      800.36,
      -453.17,
      802.55,
      -406.22,
      851.72,
      -406.24,
      849.83,
      -403.79,
      847.33,
      -400.28,
      847.3,
      -397.77,
      849.73,
      -397.48,
      850.88,
      -392.0,
      845.56,
      -391.24,
      844.82,
      -390.02,
      843.59,
      -388.86,
      842.51,
      -387.4,
      841.07,
      -387.19,
      840.87,
      -386.49,
      840.2,
      -385.74,
      840.95,
      -369.61,
      857.36,
      -368.89,
      858.09,
      -369.7,
      858.87,
      -371.42,
      860.73,
      -372.23,
      861.47,
      -374.37,
      863.43,
      -379.81,
      868.86,
      -380.47,
      869.31,
      -379.43,
      869.3,
      -376.91,
      871.74,
      -376.87,
      875.23,
      -379.33,
      877.73,
      -381.9,
      877.76,
      -379.85,
      879.9,
      -334.24,
      927.67,
      -333.28,
      926.69,
      -327.52,
      926.62,
      -323.4,
      930.61,
      -323.33,
      936.34,
      -324.68,
      937.7,
      -322.3,
      940.19,
      -343.45,
      960.1,
      -351.47,
      967.66,
      -343.54,
      975.97,
      -353.64,
      985.48,
      -361.58,
      977.18,
      -370.38,
      985.47,
      -393.88,
      1007.59,
      -395.25,
      1006.16,
      -396.08,
      1007.0,
      -401.83,
      1007.06,
      -405.95,
      1003.06,
      -406.01,
      997.34,
      -404.82,
      996.13,
      -451.86,
      946.87,
      -454.98,
      943.59,
      -457.73,
      946.17,
      -461.14,
      942.6,
      -465.05,
      946.28,
      -479.41,
      931.23,
      -475.79,
      927.82,
      -479.77,
      923.65,
      -476.46,
      920.53,
      -479.05,
      917.81,
      -524.87,
      869.8,
      -526.53,
      871.48,
      -532.29,
      871.54,
      -536.42,
      867.54,
      -536.48,
      861.82,
      -534.45,
      859.77,
      -537.32,
      856.77,
      -508.67,
      829.78,
      -510.96,
      827.38
    ],
    "source": 4
  },
  "ub_tower": {
    "chunk": "0,0",
    "index": 70,
    "height": 123.0,
    "polygon": [
      138.98,
      32.83,
      139.64,
      34.19,
      129.33,
      38.92,
      127.65,
      42.77,
      123.07,
      41.82,
      112.93,
      46.42,
      106.97,
      49.04,
      104.63,
      43.91,
      101.32,
      45.39,
      93.75,
      28.75,
      95.54,
      27.94,
      92.94,
      22.24,
      105.13,
      16.91,
      110.14,
      5.82,
      122.97,
      10.5,
      132.55,
      5.75,
      131.77,
      16.67,
      136.14,
      17.7,
      134.46,
      22.35
    ],
    "source": 4
  },
  "ub_complex": [
    {
      "index": 70,
      "height": 123.0,
      "polygon": [
        138.98,
        32.83,
        139.64,
        34.19,
        129.33,
        38.92,
        127.65,
        42.77,
        123.07,
        41.82,
        112.93,
        46.42,
        106.97,
        49.04,
        104.63,
        43.91,
        101.32,
        45.39,
        93.75,
        28.75,
        95.54,
        27.94,
        92.94,
        22.24,
        105.13,
        16.91,
        110.14,
        5.82,
        122.97,
        10.5,
        132.55,
        5.75,
        131.77,
        16.67,
        136.14,
        17.7,
        134.46,
        22.35
      ]
    },
    {
      "index": 64,
      "height": 60.0,
      "polygon": [
        195.07,
        35.7,
        203.12,
        32.14,
        217.65,
        25.72,
        224.39,
        40.74,
        219.89,
        42.74,
        222.8,
        43.04,
        226.49,
        45.0,
        229.14,
        48.22,
        230.34,
        52.2,
        229.92,
        56.34,
        227.94,
        60.0,
        224.69,
        62.63,
        220.69,
        63.82,
        216.52,
        63.4,
        215.19,
        66.05,
        213.35,
        66.64,
        210.72,
        67.83,
        207.45,
        69.25,
        172.72,
        84.62,
        163.31,
        63.66,
        200.27,
        47.29
      ]
    },
    {
      "index": 65,
      "height": 60.0,
      "polygon": [
        197.89,
        20.49,
        212.41,
        14.05,
        217.65,
        25.72,
        203.12,
        32.14
      ]
    },
    {
      "index": 68,
      "height": 26.5,
      "polygon": [
        141.68,
        6.02,
        152.75,
        1.27,
        161.85,
        22.21,
        150.58,
        27.05,
        142.01,
        30.72,
        132.91,
        9.77
      ]
    },
    {
      "index": 69,
      "height": 26.5,
      "polygon": [
        123.77,
        51.09,
        139.16,
        44.71,
        142.34,
        52.38,
        126.95,
        58.76
      ]
    }
  ],
  "kia_t2": {
    "chunk": "13,25",
    "index": 39,
    "height": 12.8,
    "polygon": [
      13190.56,
      25285.5,
      13182.49,
      25285.41,
      13182.43,
      25254.17,
      13349.24,
      25253.86,
      13349.14,
      25201.08,
      13325.88,
      25201.11,
      13325.85,
      25182.07,
      13307.78,
      25182.1,
      13307.81,
      25200.73,
      13118.17,
      25201.09,
      13082.7,
      25201.15,
      13082.4,
      25042.26,
      13262.75,
      25041.93,
      13271.35,
      25041.91,
      13480.47,
      25041.52,
      13480.34,
      24972.22,
      13503.31,
      24972.18,
      13522.4,
      24972.13,
      13522.21,
      24868.03,
      13522.21,
      24866.52,
      13548.67,
      24866.48,
      13548.74,
      24898.35,
      13597.86,
      24897.17,
      13597.95,
      24903.27,
      13548.75,
      24904.29,
      13548.92,
      24985.62,
      13599.51,
      24985.19,
      13599.34,
      24990.42,
      13548.91,
      24991.04,
      13549.04,
      25055.9,
      13600.45,
      25068.55,
      13599.21,
      25073.97,
      13549.05,
      25061.96,
      13549.38,
      25155.29,
      13602.27,
      25166.31,
      13601.62,
      25171.14,
      13549.29,
      25160.79,
      13549.39,
      25240.7,
      13602.71,
      25247.0,
      13602.31,
      25252.37,
      13549.4,
      25246.17,
      13549.42,
      25256.11,
      13587.31,
      25294.15,
      13601.0,
      25316.12,
      13596.12,
      25318.98,
      13583.58,
      25297.68,
      13549.43,
      25264.0,
      13549.46,
      25273.24,
      13541.49,
      25273.26,
      13541.51,
      25284.74,
      13519.95,
      25284.79,
      13520.89,
      25308.46,
      13540.51,
      25322.24,
      13537.93,
      25325.75,
      13516.71,
      25309.92,
      13516.61,
      25284.79,
      13471.65,
      25284.9,
      13472.86,
      25331.22,
      13467.2,
      25331.12,
      13459.71,
      25324.08,
      13460.14,
      25318.2,
      13464.45,
      25318.18,
      13464.09,
      25284.97,
      13363.05,
      25285.17,
      13364.28,
      25333.14,
      13356.57,
      25327.85,
      13355.81,
      25285.21,
      13271.64,
      25285.39,
      13271.58,
      25329.57,
      13267.91,
      25329.71,
      13267.25,
      25285.35,
      13195.45,
      25285.58,
      13195.73,
      25329.83,
      13191.16,
      25329.67
    ],
    "source": 1
  }
};

export const HERO_CONFIGS = {
  vidhana_soudha: {
    id: "vidhana_soudha",
    name: "Vidhana Soudha",
    category: "Civic",
    chunkKey: "-1,0",
    buildingIndex: 192,
    verifiedHeight: 46.0,
    baseElevation: 913.9,
    centroid: [-416.0, 890.0],
    sourceUrl: "https://en.wikipedia.org/wiki/Vidhana_Soudha"
  },
  ub_city: {
    id: "ub_city",
    name: "UB City (UB Tower)",
    category: "Commercial",
    chunkKey: "0,0",
    buildingIndex: 70,
    verifiedHeight: 123.0,
    baseElevation: 902.3,
    centroid: [117.9, 28.9],
    sourceUrl: "https://www.skyscrapercenter.com/building/ub-tower/13883"
  },
  kia_t2: {
    id: "kia_t2",
    name: "Kempegowda International Airport (Terminal 2)",
    category: "Airport",
    chunkKey: "13,25",
    buildingIndex: 39,
    verifiedHeight: null, // Unverified procedural estimate
    baseElevation: 895.4,
    centroid: [13446.3, 25183.8],
    sourceUrl: "https://en.wikipedia.org/wiki/Kempegowda_International_Airport"
  }
};

export class HeroLandmarksManager {
  constructor(scene) {
    this.scene = scene;
    this.landmarksGroup = new THREE.Group();
    this.landmarksGroup.name = "heroLandmarksGroup";
    this.scene.add(this.landmarksGroup);

    this.landmarks = new Map();
    this.lodDistance = 300.0; // 300m LOD transition boundary
    this.currentExaggeration = 1.0;
    this.enabled = true; // Debug switch for hero landmarks overall
    this.heroDetailEnabled = true; // Debug switch for hero detail vs normal box
  }

  async init(dataUrl = "data/hero_landmarks.json") {
    try {
      const res = await fetch(dataUrl);
      if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${dataUrl}`);
      const data = await res.json();
      this.buildVidhanaSoudha(data.vidhana_soudha);
      this.buildUBCity(data.ub_tower, data.ub_complex);
      this.buildKIAT2(data.kia_t2);
      console.log("[HeroLandmarks] Initialized 3 procedural hero landmarks successfully.");
    } catch (e) {
      console.error("[HeroLandmarks] Initialization failed:", e);
    }
  }

  // Helper to build a Three.js shape from flat [x0, y0, x1, y1...] coords
  makeShape(flatCoords) {
    const shape = new THREE.Shape();
    if (!flatCoords || flatCoords.length < 6) return shape;
    shape.moveTo(flatCoords[0], flatCoords[1]);
    for (let i = 2; i < flatCoords.length; i += 2) {
      shape.lineTo(flatCoords[i], flatCoords[i + 1]);
    }
    shape.closePath();
    return shape;
  }

  safeMergeGeometries(geos) {
    if (!geos || geos.length === 0) return null;
    if (geos.length === 1) return geos[0];
    const nonIndexed = geos.map(g => (g.index ? g.toNonIndexed() : g));
    return BufferGeometryUtils.mergeGeometries(nonIndexed);
  }

  // ---------------------------------------------------------------------------
  // 1. Vidhana Soudha (46 m)
  // ---------------------------------------------------------------------------
  buildVidhanaSoudha(data) {
    const config = HERO_CONFIGS.vidhana_soudha;
    const group = new THREE.Group();
    group.name = "hero_vidhana_soudha";
    group.userData = { landmarkConfig: config };

    // Common materials (4 materials = 4 draw calls)
    const graniteMat = new THREE.MeshStandardMaterial({
      color: 0xd6cec0,
      roughness: 0.75,
      metalness: 0.1,
      bumpScale: 0.05
    });
    const domeMat = new THREE.MeshStandardMaterial({
      color: 0xdecba4,
      roughness: 0.35,
      metalness: 0.45
    });
    const goldMat = new THREE.MeshStandardMaterial({
      color: 0xffd700,
      roughness: 0.25,
      metalness: 0.8
    });
    const pillarMat = new THREE.MeshStandardMaterial({
      color: 0xe0d7c7,
      roughness: 0.6,
      metalness: 0.1
    });

    const heroGroup = new THREE.Group();
    heroGroup.name = "hero_detail";

    const graniteGeos = [];
    const domeGeos = [];
    const goldGeos = [];
    const pillarGeos = [];

    // A. Main Palace Base (extruded real 76-vertex footprint)
    const shape = this.makeShape(data.polygon);
    const baseGeo = new THREE.ExtrudeGeometry(shape, {
      depth: 22.0,
      bevelEnabled: false
    });
    baseGeo.rotateX(-Math.PI / 2);
    baseGeo.translate(0, -1.5, 0);
    graniteGeos.push(baseGeo);

    // B. Central Grand Dravidian Dome (at -416.0, 890.0)
    const cx = config.centroid[0];
    const cz = -config.centroid[1];

    // Dome Drum
    const drumGeo = new THREE.CylinderGeometry(14, 14, 8, 24);
    drumGeo.translate(cx, 24.5, cz);
    graniteGeos.push(drumGeo);

    // Ribbed Hemispherical Dome
    const domeGeo = new THREE.SphereGeometry(14, 24, 16, 0, Math.PI * 2, 0, Math.PI / 2);
    domeGeo.translate(cx, 28.5, cz);
    domeGeos.push(domeGeo);

    // Golden Kalasa Finial & Spire (reaching 46m)
    const spireGeo = new THREE.CylinderGeometry(0.4, 2.0, 7.5, 12);
    spireGeo.translate(cx, 42.25, cz);
    goldGeos.push(spireGeo);

    // Crowning finial apex
    const apexGeo = new THREE.ConeGeometry(0.8, 2.0, 12);
    apexGeo.translate(cx, 45.0, cz);
    goldGeos.push(apexGeo);

    // C. 4 Corner Chattris (octagonal domed corner pavilions)
    const chattriCorners = [
      [-480, -825],
      [-480, -955],
      [-350, -825],
      [-350, -955]
    ];
    for (const [x, z] of chattriCorners) {
      for (let a = 0; a < 8; a++) {
        const rad = (a / 8) * Math.PI * 2;
        const px = x + Math.cos(rad) * 3.2;
        const pz = z + Math.sin(rad) * 3.2;
        const pGeo = new THREE.CylinderGeometry(0.35, 0.35, 6, 8);
        pGeo.translate(px, 23.5, pz);
        pillarGeos.push(pGeo);
      }
      const cDomeGeo = new THREE.SphereGeometry(3.6, 16, 12, 0, Math.PI * 2, 0, Math.PI / 2);
      cDomeGeo.translate(x, 26.5, z);
      domeGeos.push(cDomeGeo);

      const fGeo = new THREE.ConeGeometry(0.4, 2.5, 8);
      fGeo.translate(x, 31.25, z);
      goldGeos.push(fGeo);
    }

    // D. Grand East Dravidian Entrance Porch (at x = -365, z = -890)
    for (let s = 0; s < 4; s++) {
      const stepGeo = new THREE.BoxGeometry(32 - s * 2, 1.2, 22 - s * 4);
      stepGeo.translate(-365 + s * 2, s * 1.2 + 0.6, cz);
      graniteGeos.push(stepGeo);
    }
    for (let r = 0; r < 2; r++) {
      for (let c = -3; c <= 3; c++) {
        if (c === 0) continue;
        const colGeo = new THREE.CylinderGeometry(0.7, 0.7, 16, 12);
        colGeo.translate(-368 + r * 6, 13.0, cz + c * 4.2);
        pillarGeos.push(colGeo);
      }
    }
    const pedGeo = new THREE.BoxGeometry(14, 3.5, 30);
    pedGeo.translate(-365, 22.5, cz);
    graniteGeos.push(pedGeo);

    // Merge geometries per material -> exactly 4 draw calls!
    const mergedGranite = this.safeMergeGeometries(graniteGeos);
    const graniteMesh = new THREE.Mesh(mergedGranite, graniteMat);
    graniteMesh.castShadow = true;
    graniteMesh.receiveShadow = true;
    heroGroup.add(graniteMesh);

    const mergedDome = this.safeMergeGeometries(domeGeos);
    const domeMesh = new THREE.Mesh(mergedDome, domeMat);
    domeMesh.castShadow = true;
    heroGroup.add(domeMesh);

    const mergedGold = this.safeMergeGeometries(goldGeos);
    const goldMesh = new THREE.Mesh(mergedGold, goldMat);
    heroGroup.add(goldMesh);

    const mergedPillars = this.safeMergeGeometries(pillarGeos);
    const pillarMesh = new THREE.Mesh(mergedPillars, pillarMat);
    pillarMesh.castShadow = true;
    heroGroup.add(pillarMesh);

    // Normal box LOD (for distance >= 300m)
    const normalGeo = new THREE.ExtrudeGeometry(shape, {
      depth: 46.0,
      bevelEnabled: false
    });
    normalGeo.rotateX(-Math.PI / 2);
    normalGeo.translate(0, -1.5, 0);
    const normalMesh = new THREE.Mesh(normalGeo, graniteMat);
    normalMesh.name = "normal_box";

    group.add(heroGroup);
    group.add(normalMesh);

    this.landmarks.set("vidhana_soudha", {
      group,
      heroGroup,
      normalMesh,
      materials: [graniteMat, domeMat, goldMat, pillarMat],
      config
    });
    this.landmarksGroup.add(group);
  }

  // ---------------------------------------------------------------------------
  // 2. UB City (123 m UB Tower, 4-tower complex on shared podium)
  // ---------------------------------------------------------------------------
  buildUBCity(ubTowerData, ubComplexData) {
    const config = HERO_CONFIGS.ub_city;
    const group = new THREE.Group();
    group.name = "hero_ub_city";
    group.userData = { landmarkConfig: config };

    const glassTowerMat = new THREE.MeshStandardMaterial({
      color: 0x3b6680,
      roughness: 0.15,
      metalness: 0.85
    });
    const glassCurtainMat = new THREE.MeshStandardMaterial({
      color: 0x27495f,
      roughness: 0.2,
      metalness: 0.75
    });
    const podiumMat = new THREE.MeshStandardMaterial({
      color: 0xbeb6a4,
      roughness: 0.7,
      metalness: 0.2
    });
    const crownSpireMat = new THREE.MeshStandardMaterial({
      color: 0x93b4c9,
      roughness: 0.2,
      metalness: 0.9
    });

    const heroGroup = new THREE.Group();
    heroGroup.name = "hero_detail";

    const podiumGeos = [];
    const glassTowerGeos = [];
    const glassCurtainGeos = [];
    const crownSpireGeos = [];

    // A. Shared Retail & Piazza Podium (15m height)
    const podiumGeo = new THREE.BoxGeometry(140, 16, 95);
    podiumGeo.translate(165, 8.0 - 1.5, -35);
    podiumGeos.push(podiumGeo);

    // B. UB Tower (123 m verified, index 70 footprint)
    const ubShape = this.makeShape(ubTowerData.polygon);
    // Lower tier (0 to 75m)
    const lowerGeo = new THREE.ExtrudeGeometry(ubShape, { depth: 75, bevelEnabled: false });
    lowerGeo.rotateX(-Math.PI / 2);
    lowerGeo.translate(0, -1.5, 0);
    glassTowerGeos.push(lowerGeo);

    // Mid tier with setback (75m to 105m)
    const midGeo = new THREE.BoxGeometry(28, 30, 24);
    midGeo.translate(118, 90.0 - 1.5, -29);
    glassCurtainGeos.push(midGeo);

    // Upper crown (105m to 115m)
    const crownGeo = new THREE.BoxGeometry(22, 10, 18);
    crownGeo.translate(118, 110.0 - 1.5, -29);
    crownSpireGeos.push(crownGeo);

    // Architectural Spire (reaching 123.0m)
    const spireGeo = new THREE.CylinderGeometry(0.3, 1.2, 8.0, 8);
    spireGeo.translate(118, 119.0 - 1.5, -29);
    crownSpireGeos.push(spireGeo);

    // C. Other 3 Towers of UB City Complex (Concorde 95m, Canberra 85m, Comet 72m)
    if (Array.isArray(ubComplexData)) {
      for (const b of ubComplexData) {
        if (b.index === 70) continue; // Already built as UB Tower
        const bShape = this.makeShape(b.polygon);
        let h = 70.0;
        let isTowerMat = false;
        if (b.index === 64) { h = 95.0; isTowerMat = true; } // Concorde
        else if (b.index === 65) h = 85.0; // Canberra
        else if (b.index === 68) h = 72.0; // Comet
        else h = 40.0; // Kingfisher / Annex

        const tGeo = new THREE.ExtrudeGeometry(bShape, { depth: h, bevelEnabled: false });
        tGeo.rotateX(-Math.PI / 2);
        tGeo.translate(0, -1.5, 0);
        if (isTowerMat) glassTowerGeos.push(tGeo);
        else glassCurtainGeos.push(tGeo);
      }
    }

    // Merge geometries per material -> exactly 4 draw calls!
    const mergedPodium = this.safeMergeGeometries(podiumGeos);
    const podiumMesh = new THREE.Mesh(mergedPodium, podiumMat);
    podiumMesh.castShadow = true;
    heroGroup.add(podiumMesh);

    const mergedGlassTower = this.safeMergeGeometries(glassTowerGeos);
    const lowerMesh = new THREE.Mesh(mergedGlassTower, glassTowerMat);
    lowerMesh.castShadow = true;
    heroGroup.add(lowerMesh);

    const mergedGlassCurtain = this.safeMergeGeometries(glassCurtainGeos);
    const midMesh = new THREE.Mesh(mergedGlassCurtain, glassCurtainMat);
    midMesh.castShadow = true;
    heroGroup.add(midMesh);

    const mergedCrownSpire = this.safeMergeGeometries(crownSpireGeos);
    const crownMesh = new THREE.Mesh(mergedCrownSpire, crownSpireMat);
    heroGroup.add(crownMesh);

    // Normal box LOD (for distance >= 300m)
    const normalGeo = new THREE.ExtrudeGeometry(ubShape, { depth: 123.0, bevelEnabled: false });
    normalGeo.rotateX(-Math.PI / 2);
    normalGeo.translate(0, -1.5, 0);
    const normalMesh = new THREE.Mesh(normalGeo, glassTowerMat);
    normalMesh.name = "normal_box";

    group.add(heroGroup);
    group.add(normalMesh);

    this.landmarks.set("ub_city", {
      group,
      heroGroup,
      normalMesh,
      materials: [glassTowerMat, glassCurtainMat, podiumMat, crownSpireMat],
      config
    });
    this.landmarksGroup.add(group);
  }

  // ---------------------------------------------------------------------------
  // 3. Kempegowda International Airport Terminal 2 (25 m)
  // ---------------------------------------------------------------------------
  buildKIAT2(data) {
    const config = HERO_CONFIGS.kia_t2;
    const group = new THREE.Group();
    group.name = "hero_kia_t2";
    group.userData = { landmarkConfig: config };

    // "Terminal in a Garden" Bamboo & Glass Materials
    const bambooRoofMat = new THREE.MeshStandardMaterial({
      color: 0xc89858,
      roughness: 0.65,
      metalness: 0.15
    });
    const curtainGlassMat = new THREE.MeshStandardMaterial({
      color: 0x98c2d8,
      roughness: 0.1,
      metalness: 0.85,
      transparent: true,
      opacity: 0.88
    });
    const gardenGreenMat = new THREE.MeshStandardMaterial({
      color: 0x2d6a4f,
      roughness: 0.8,
      metalness: 0.05
    });
    const skylightGlassMat = new THREE.MeshStandardMaterial({
      color: 0xe6f4fa,
      roughness: 0.1,
      metalness: 0.9,
      transparent: true,
      opacity: 0.95
    });

    const heroGroup = new THREE.Group();
    heroGroup.name = "hero_detail";

    const curtainGeos = [];
    const gardenGeos = [];
    const bambooGeos = [];
    const skylightGeos = [];

    // A. Main Glass Terminal Concourse Body (extruded real 74-vertex footprint)
    const shape = this.makeShape(data.polygon);
    const curtainGeo = new THREE.ExtrudeGeometry(shape, { depth: 16.0, bevelEnabled: false });
    curtainGeo.rotateX(-Math.PI / 2);
    curtainGeo.translate(0, -1.5, 0);
    curtainGeos.push(curtainGeo);

    // B. Internal Botanical Terraces & Living Gardens
    const gardenGeo = new THREE.BoxGeometry(320, 4.0, 180);
    gardenGeo.translate(config.centroid[0], 2.0 - 1.5, -config.centroid[1]);
    gardenGeos.push(gardenGeo);

    // C. Engineered Bamboo Diagrid Canopy
    const roofGeo = new THREE.BoxGeometry(420, 2.8, 240);
    roofGeo.translate(config.centroid[0], 17.4 - 1.5, -config.centroid[1]);
    bambooGeos.push(roofGeo);

    // D. 18 Tiered Skylight Lanterns (6 x 3 rhythmic grid)
    const cx = config.centroid[0];
    const cz = -config.centroid[1];
    for (let gx = -2.5; gx <= 2.5; gx += 1.0) {
      for (let gz = -1.0; gz <= 1.0; gz += 1.0) {
        const lx = cx + gx * 65.0;
        const lz = cz + gz * 65.0;
        // Skylight lantern base
        const skBaseGeo = new THREE.BoxGeometry(22, 3.5, 22);
        skBaseGeo.translate(lx, 19.5 - 1.5, lz);
        bambooGeos.push(skBaseGeo);

        // Skylight pyramid glass cap
        const skCapGeo = new THREE.ConeGeometry(14, 5.0, 4);
        skCapGeo.rotateY(Math.PI / 4);
        skCapGeo.translate(lx, 23.5 - 1.5, lz);
        skylightGeos.push(skCapGeo);
      }
    }

    // E. 16 Bamboo Flared Tree Columns supporting the roof
    for (let gx = -1.5; gx <= 1.5; gx += 1.0) {
      for (let gz = -1.5; gz <= 1.5; gz += 1.0) {
        const px = cx + gx * 85.0;
        const pz = cz + gz * 50.0;
        const colGeo = new THREE.CylinderGeometry(3.5, 1.2, 16.0, 8);
        colGeo.translate(px, 8.0 - 1.5, pz);
        bambooGeos.push(colGeo);
      }
    }

    // Merge geometries per material -> exactly 4 draw calls!
    const mergedCurtain = this.safeMergeGeometries(curtainGeos);
    const curtainMesh = new THREE.Mesh(mergedCurtain, curtainGlassMat);
    curtainMesh.castShadow = true;
    heroGroup.add(curtainMesh);

    const mergedGarden = this.safeMergeGeometries(gardenGeos);
    const gardenMesh = new THREE.Mesh(mergedGarden, gardenGreenMat);
    heroGroup.add(gardenMesh);

    const mergedBamboo = this.safeMergeGeometries(bambooGeos);
    const roofMesh = new THREE.Mesh(mergedBamboo, bambooRoofMat);
    roofMesh.castShadow = true;
    heroGroup.add(roofMesh);

    const mergedSkylights = this.safeMergeGeometries(skylightGeos);
    const skylightMesh = new THREE.Mesh(mergedSkylights, skylightGlassMat);
    heroGroup.add(skylightMesh);

    // Normal box LOD (for distance >= 300m)
    const normalGeo = new THREE.ExtrudeGeometry(shape, { depth: 25.0, bevelEnabled: false });
    normalGeo.rotateX(-Math.PI / 2);
    normalGeo.translate(0, -1.5, 0);
    const normalMesh = new THREE.Mesh(normalGeo, bambooRoofMat);
    normalMesh.name = "normal_box";

    group.add(heroGroup);
    group.add(normalMesh);

    this.landmarks.set("kia_t2", {
      group,
      heroGroup,
      normalMesh,
      materials: [bambooRoofMat, curtainGlassMat, gardenGreenMat, skylightGlassMat],
      config
    });
    this.landmarksGroup.add(group);
  }

  // ---------------------------------------------------------------------------
  // Per-Frame Update: LOD Switching, Exaggeration, and Night Illumination
  // ---------------------------------------------------------------------------
  update(camera, exaggeration, timeMinutes, sunElevation) {
    this.currentExaggeration = exaggeration;
    const isNight = timeMinutes >= 1200 || timeMinutes < 360 || sunElevation < 2.0;

    for (const [id, item] of this.landmarks) {
      if (!this.enabled || window.heroLandmarksEnabled === false) {
        item.group.visible = false;
        continue;
      }
      item.group.visible = true;

      const cfg = item.config;
      const worldTarget = new THREE.Vector3(
        cfg.centroid[0],
        cfg.baseElevation * exaggeration,
        -cfg.centroid[1]
      );

      // 1. Dynamic Exaggeration Seating
      item.group.position.y = cfg.baseElevation * exaggeration;
      item.group.scale.y = exaggeration;

      // 2. Distance-based LOD Switch (at 300m threshold)
      const dist = camera.position.distanceTo(worldTarget);
      const showHeroDetail = (this.heroDetailEnabled !== false) &&
                             (window.heroDetailEnabled !== false) &&
                             (dist < this.lodDistance);

      if (showHeroDetail) {
        item.heroGroup.visible = true;
        item.normalMesh.visible = false;
      } else {
        item.heroGroup.visible = false;
        item.normalMesh.visible = true;
      }

      // 3. Time-of-Day Night Illumination
      if (id === "vidhana_soudha") {
        const floodMat = item.materials[0]; // granite
        const domeMat = item.materials[1];
        if (isNight) {
          floodMat.emissive = new THREE.Color(0xff9e2c);
          floodMat.emissiveIntensity = 0.55;
          domeMat.emissive = new THREE.Color(0xffb74d);
          domeMat.emissiveIntensity = 0.7;
        } else {
          floodMat.emissiveIntensity = 0.0;
          domeMat.emissiveIntensity = 0.0;
        }
      } else if (id === "ub_city") {
        const glass1 = item.materials[0];
        const glass2 = item.materials[1];
        if (isNight) {
          glass1.emissive = new THREE.Color(0x90caf9);
          glass1.emissiveIntensity = 0.65;
          glass2.emissive = new THREE.Color(0x64b5f6);
          glass2.emissiveIntensity = 0.55;
        } else {
          glass1.emissiveIntensity = 0.0;
          glass2.emissiveIntensity = 0.0;
        }
      } else if (id === "kia_t2") {
        const curtainGlass = item.materials[1];
        const skylightGlass = item.materials[3];
        if (isNight) {
          curtainGlass.emissive = new THREE.Color(0xffb74d);
          curtainGlass.emissiveIntensity = 0.75;
          skylightGlass.emissive = new THREE.Color(0xffe082);
          skylightGlass.emissiveIntensity = 0.85;
        } else {
          curtainGlass.emissiveIntensity = 0.0;
          skylightGlass.emissiveIntensity = 0.0;
        }
      }
    }
  }

  // Return triangle count and draw call stats for budget verification
  getStats() {
    const stats = {};
    for (const [id, item] of this.landmarks) {
      let heroTriangles = 0;
      let heroDrawCalls = 0;
      item.heroGroup.traverse(child => {
        if (child.isMesh && child.geometry) {
          heroDrawCalls += 1;
          const index = child.geometry.index;
          if (index) {
            heroTriangles += index.count / 3;
          } else if (child.geometry.attributes.position) {
            heroTriangles += child.geometry.attributes.position.count / 3;
          }
        }
      });

      let normalTriangles = 0;
      let normalDrawCalls = 1;
      if (item.normalMesh.geometry) {
        const index = item.normalMesh.geometry.index;
        if (index) {
          normalTriangles = index.count / 3;
        } else if (item.normalMesh.geometry.attributes.position) {
          normalTriangles = item.normalMesh.geometry.attributes.position.count / 3;
        }
      }

      stats[id] = {
        name: item.config.name,
        heroTriangles: Math.round(heroTriangles),
        heroDrawCalls,
        normalTriangles: Math.round(normalTriangles),
        normalDrawCalls
      };
    }
    return stats;
  }
}
