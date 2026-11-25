/**
 * Bengaluru 3D - Guided Tours Engine
 * Round 6: Robust readiness-gated cinematic tours over open data.
 * Captions state data fields only; no invented claims.
 */

import * as THREE from "three";

const ORIGIN_LON = 77.5946;
const ORIGIN_LAT = 12.9716;
const METERS_PER_DEGREE_LON = 111319.49079327358 * Math.cos(ORIGIN_LAT * Math.PI / 180);
const METERS_PER_DEGREE_LAT = 110574;
const CHUNK_SIZE = 1000;
const MAX_SPEED_MS = 75; // Path speed cap lowered to 75 m/s to ensure robust chunk pre-loading

export function latLonToLocal(lat, lon) {
  const x = (lon - ORIGIN_LON) * METERS_PER_DEGREE_LON;
  const north = (lat - ORIGIN_LAT) * METERS_PER_DEGREE_LAT;
  return { x, north, z: -north };
}

export function localToLatLon(x, north) {
  const lon = ORIGIN_LON + x / METERS_PER_DEGREE_LON;
  const lat = ORIGIN_LAT + north / METERS_PER_DEGREE_LAT;
  return { lat, lon };
}

/**
 * Tour Definitions
 * Every caption names its source field (landmarks.json, metro_stations.json, building_names.json).
 * Station stops: "<name> · <line> · elevated/underground/at-grade", nothing else.
 */
export const TOURS_CONFIG = [
  {
    id: "core-city",
    title: "Core City",
    time: 17.5, // 17:30 Golden Hour
    traffic: false,
    waypoints: [
      {
        name: "Cubbon Park (metro station)",
        lat: 12.980944,
        lon: 77.597571,
        alt_m: 230,
        dwell_s: 5,
        caption: {
          text: "Cubbon Park · Purple Line · underground",
          source: "metro_stations.json: Cubbon Park"
        }
      },
      {
        name: "Vidhana Soudha",
        lat: 12.9796,
        lon: 77.5906,
        alt_m: 230,
        dwell_s: 6,
        caption: {
          text: "Vidhana Soudha · civic · 46 m (verified) · Stylised model, not survey geometry",
          source: "landmarks.json: Vidhana Soudha"
        }
      },
      {
        name: "UB City (UB Tower)",
        lat: 12.97175,
        lon: 77.5958333,
        alt_m: 250,
        dwell_s: 6,
        caption: {
          text: "UB City (UB Tower) · mall · 123 m (verified) · Stylised model, not survey geometry",
          source: "landmarks.json: UB City (UB Tower)"
        }
      },
      {
        name: "Mahatma Gandhi Road",
        lat: 12.975705,
        lon: 77.607184,
        alt_m: 230,
        dwell_s: 5,
        caption: {
          text: "Mahatma Gandhi Road · Purple Line · elevated",
          source: "metro_stations.json: Mahatma Gandhi Road"
        }
      },
      {
        name: "Nadaprabhu Kempegowda Station, Majestic",
        lat: 12.97563,
        lon: 77.572935,
        alt_m: 230,
        dwell_s: 6,
        caption: {
          text: "Nadaprabhu Kempegowda Station, Majestic · Purple Line · underground",
          source: "metro_stations.json: Nadaprabhu Kempegowda Station, Majestic"
        }
      }
    ]
  },
  {
    id: "silicon-plateau",
    title: "Silicon Plateau",
    time: 12.0, // 12:00 Day Midday
    traffic: false,
    // Dropped to respect <= 4 min (240 s) budget:
    // - Brigade Gateway (co-located with WTC, 25 m separation)
    // - Electronics City Phase 1 (12 km southern outlier, adds >150 s flight)
    // - ITPB (8 km eastern outlier in Whitefield, adds >100 s flight)
    // - Bagmane WTC, Embassy TechVillage, Prestige Tech Park (redundant ORR clustering)
    waypoints: [
      {
        name: "World Trade Center Bangalore",
        lat: 13.0123,
        lon: 77.5562,
        alt_m: 270,
        dwell_s: 5,
        caption: {
          text: "World Trade Center Bangalore · tech park · 128 m (verified)",
          source: "landmarks.json: World Trade Center Bangalore"
        }
      },
      {
        name: "Manyata Embassy Business Park (tallest tower)",
        lat: 13.0475,
        lon: 77.6207,
        alt_m: 250,
        dwell_s: 5,
        caption: {
          text: "Manyata Embassy Business Park (tallest tower) · tech park · Height not verified",
          source: "landmarks.json: Manyata Embassy Business Park (tallest tower)"
        }
      },
      {
        name: "Bagmane Tech Park",
        lat: 12.978383,
        lon: 77.660947,
        alt_m: 250,
        dwell_s: 5,
        caption: {
          text: "Bagmane Tech Park · tech park · Height not verified",
          source: "landmarks.json: Bagmane Tech Park"
        }
      },
      {
        name: "Embassy GolfLinks Business Park",
        lat: 12.949102,
        lon: 77.644314,
        alt_m: 250,
        dwell_s: 5,
        caption: {
          text: "Embassy GolfLinks Business Park · tech park · Height not verified",
          source: "landmarks.json: Embassy GolfLinks Business Park"
        }
      },
      {
        name: "RMZ Ecospace",
        lat: 12.926435,
        lon: 77.68052,
        alt_m: 250,
        dwell_s: 6,
        caption: {
          text: "RMZ Ecospace · tech park · Height not verified",
          source: "landmarks.json: RMZ Ecospace"
        }
      }
    ]
  },
  {
    id: "purple-line",
    title: "Namma Metro Purple Line",
    time: 19.0, // 19:00 Night glow
    traffic: true,
    waypoints: [
      {
        name: "Baiyappanahalli",
        lat: 12.990716,
        lon: 77.652375,
        alt_m: 230,
        dwell_s: 4,
        caption: {
          text: "Baiyappanahalli · Purple Line · at-grade",
          source: "metro_stations.json: Baiyappanahalli"
        }
      },
      {
        name: "Swami Vivekananda Road",
        lat: 12.985933,
        lon: 77.644898,
        alt_m: 230,
        dwell_s: 4,
        caption: {
          text: "Swami Vivekananda Road · Purple Line · elevated",
          source: "metro_stations.json: Swami Vivekananda Road"
        }
      },
      {
        name: "Indiranagar",
        lat: 12.978331,
        lon: 77.638659,
        alt_m: 230,
        dwell_s: 4,
        caption: {
          text: "Indiranagar · Purple Line · elevated",
          source: "metro_stations.json: Indiranagar"
        }
      },
      {
        name: "Halasuru",
        lat: 12.976502,
        lon: 77.626686,
        alt_m: 230,
        dwell_s: 4,
        caption: {
          text: "Halasuru · Purple Line · elevated",
          source: "metro_stations.json: Halasuru"
        }
      },
      {
        name: "Trinity",
        lat: 12.973019,
        lon: 77.617019,
        alt_m: 230,
        dwell_s: 4,
        caption: {
          text: "Trinity · Purple Line · elevated",
          source: "metro_stations.json: Trinity"
        }
      },
      {
        name: "Mahatma Gandhi Road",
        lat: 12.975705,
        lon: 77.607184,
        alt_m: 230,
        dwell_s: 4,
        caption: {
          text: "Mahatma Gandhi Road · Purple Line · elevated",
          source: "metro_stations.json: Mahatma Gandhi Road"
        }
      },
      {
        name: "Cubbon Park",
        lat: 12.980944,
        lon: 77.597571,
        alt_m: 230,
        dwell_s: 4,
        caption: {
          text: "Cubbon Park · Purple Line · underground",
          source: "metro_stations.json: Cubbon Park"
        }
      },
      {
        name: "Dr. B. R. Ambedkar Station, Vidhana Soudha",
        lat: 12.97857,
        lon: 77.591526,
        alt_m: 230,
        dwell_s: 4,
        caption: {
          text: "Dr. B. R. Ambedkar Station, Vidhana Soudha · Purple Line · underground",
          source: "metro_stations.json: Dr. B. R. Ambedkar Station, Vidhana Soudha"
        }
      },
      {
        name: "Sir M. Visvesvaraya Stn., Central College",
        lat: 12.97728,
        lon: 77.58448,
        alt_m: 230,
        dwell_s: 4,
        caption: {
          text: "Sir M. Visvesvaraya Stn., Central College · Purple Line · underground",
          source: "metro_stations.json: Sir M. Visvesvaraya Stn., Central College"
        }
      },
      {
        name: "Nadaprabhu Kempegowda Station, Majestic",
        lat: 12.97563,
        lon: 77.572935,
        alt_m: 230,
        dwell_s: 5,
        caption: {
          text: "Nadaprabhu Kempegowda Station, Majestic · Purple Line · underground",
          source: "metro_stations.json: Nadaprabhu Kempegowda Station, Majestic"
        }
      }
    ]
  }
];

export class TourManager {
  constructor() {
    this.tours = new Map();
    for (const t of TOURS_CONFIG) {
      this.tours.set(t.id, t);
    }
    this.activeTour = null;
    this.state = "idle"; // "idle" | "playing" | "paused" | "stalled"
    this.progress = 0.0;
    this.currentWaypointIndex = 0;
    this.stallsCount = 0;
    this.isStalled = false;
    this.isPreparing = false;
    this.isPausedForLoading = false;
    this.minClearanceTerrain = 0;
    this.minClearanceBuilding = 0;
    this.minClearance = 0;

    // References to host scene & controls
    this.camera = null;
    this.controls = null;
    this.renderer = null;
    this.loadedChunks = null;
    this.getChunks = null;
    this.getTerrainElevation = null;
    this.setTime = null;
    this.setTimeRaw = null;
    this.setRadius = null;
    this.setTraffic = null;
    this.setTrafficDay = null;
    this.setExaggeration = null;
    this.setShadows = null;
    this.requestChunkLoad = null;

    // Saved state to restore on cancel
    this.savedSettings = null;

    // Spline curves
    this.cameraCurve = null;
    this.targetCurve = null;
    this.totalDistance = 0;
    this.currentSpeed = 0;
    this.dwellRemaining = 0;
    this.frameTimes = [];

    // Accessibility
    this.isReducedMotion = false;
    this.fadeOverlay = null;

    // UI elements
    this.cardElement = null;
    this.titleElement = null;
    this.stepElement = null;
    this.stopNameElement = null;
    this.captionTextElement = null;
    this.sourceElement = null;
    this.progressBarElement = null;
    this.playBtnElement = null;
    this.prevBtnElement = null;
    this.nextBtnElement = null;
    this.closeBtnElement = null;
    this.stallMsgElement = null;
  }

  init(options) {
    this.camera = options.camera;
    this.controls = options.controls;
    this.renderer = options.renderer;
    this.loadedChunks = options.loadedChunks;
    this.getChunks = options.getChunks;
    this.getTerrainElevation = options.getTerrainElevation;
    this.setTime = options.setTime;
    this.setTimeRaw = options.setTimeRaw;
    this.setRadius = options.setRadius;
    this.setTraffic = options.setTraffic;
    this.setTrafficDay = options.setTrafficDay;
    this.setExaggeration = options.setExaggeration;
    this.setShadows = options.setShadows;
    this.requestChunkLoad = options.requestChunkLoad;

    this.isReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    this.bindUi();
    this.bindCancelListeners();
  }

  bindUi() {
    this.cardElement = document.querySelector("#tour-card");
    this.titleElement = document.querySelector("#tour-title");
    this.stepElement = document.querySelector("#tour-step");
    this.stopNameElement = document.querySelector("#tour-stop-name");
    this.captionTextElement = document.querySelector("#tour-caption-text");
    this.sourceElement = document.querySelector("#tour-card-source");
    this.progressBarElement = document.querySelector("#tour-progress-bar");
    this.playBtnElement = document.querySelector("#tour-play-btn");
    this.prevBtnElement = document.querySelector("#tour-prev-btn");
    this.nextBtnElement = document.querySelector("#tour-next-btn");
    this.closeBtnElement = document.querySelector("#tour-close-btn");
    this.stallMsgElement = document.querySelector("#tour-stall-msg");

    // Fade overlay for reduced motion transitions
    this.fadeOverlay = document.createElement("div");
    this.fadeOverlay.id = "tour-fade-overlay";
    this.fadeOverlay.style.cssText =
      "position:fixed;inset:0;background:#000;opacity:0;pointer-events:none;z-index:999;transition:opacity 120ms ease-out;";
    document.body.appendChild(this.fadeOverlay);

    if (this.playBtnElement) {
      this.playBtnElement.addEventListener("click", () => this.togglePlayPause());
    }
    if (this.prevBtnElement) {
      this.prevBtnElement.addEventListener("click", () => this.prevWaypoint());
    }
    if (this.nextBtnElement) {
      this.nextBtnElement.addEventListener("click", () => this.nextWaypoint());
    }
    if (this.closeBtnElement) {
      this.closeBtnElement.addEventListener("click", () => this.stopTour(true));
    }

    // Panel tour buttons
    document.querySelectorAll(".tour-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const tourId = btn.getAttribute("data-tour");
        if (tourId) this.startTour(tourId);
      });
    });
  }

  bindCancelListeners() {
    const handleCancel = event => {
      if (this.state === "idle" || !this.activeTour) return;

      // Ignore interactions inside tour card UI
      if (this.cardElement && this.cardElement.contains(event.target)) return;

      if (event.type === "keydown") {
        if (event.key === "Escape" || event.key.startsWith("Arrow")) {
          this.stopTour(true);
        }
      } else if (event.type === "pointerdown" || event.type === "wheel") {
        this.stopTour(true);
      }
    };

    window.addEventListener("pointerdown", handleCancel, { passive: true });
    window.addEventListener("wheel", handleCancel, { passive: true });
    window.addEventListener("keydown", handleCancel);
  }

  async buildTourSplines(tour) {
    const camPoints = [];
    const targetPoints = [];

    if (tour.id === "purple-line" && window.metroData && window.metroData.tracks) {
      const chained = this.chainPurpleLineWays(window.metroData.tracks);
      if (chained.length > 0) {
        const step = Math.max(1, Math.floor(chained.length / 80));
        for (let i = 0; i < chained.length; i += step) {
          const pt = chained[i];
          const x = pt[0];
          const north = pt[1];
          const groundY = pt[3] || (await this.getElevation(x, north));
          const camY = groundY + 230;
          camPoints.push(new THREE.Vector3(x, camY, -north));

          const aheadIdx = Math.min(chained.length - 1, i + Math.floor(300 / 2.5));
          const aheadPt = chained[aheadIdx];
          const aheadGroundY = aheadPt[3] || (await this.getElevation(aheadPt[0], aheadPt[1]));
          targetPoints.push(new THREE.Vector3(aheadPt[0], aheadGroundY + 15, -aheadPt[1]));
        }
      }
    }

    if (camPoints.length < 2) {
      for (let i = 0; i < tour.waypoints.length; i++) {
        const wp = tour.waypoints[i];
        const local = latLonToLocal(wp.lat, wp.lon);
        const groundY = await this.getElevation(local.x, local.north);
        const camY = groundY + (wp.alt_m || 240);

        const offsetDist = 450;
        const angle = (i * 0.8) % (2 * Math.PI);
        const camX = local.x + Math.sin(angle) * offsetDist;
        const camZ = local.z + Math.cos(angle) * offsetDist;

        camPoints.push(new THREE.Vector3(camX, camY, camZ));
        targetPoints.push(new THREE.Vector3(local.x, groundY + 25, local.z));
      }
    }

    this.cameraCurve = new THREE.CatmullRomCurve3(camPoints, false, "centripetal");
    this.targetCurve = new THREE.CatmullRomCurve3(targetPoints, false, "centripetal");
    this.totalDistance = this.cameraCurve.getLength();
    this.precomputeRequiredChunks();
  }

  precomputeRequiredChunks() {
    if (!this.cameraCurve || !this.totalDistance) return;
    const allChunks = this.getChunks ? this.getChunks() : [];
    const validChunkKeys = new Set(allChunks.map(c => `${c.ix},${c.iy}`));

    this.precomputedRequiredSegments = [];
    const NUM_SEGMENTS = 100;

    for (let i = 0; i <= NUM_SEGMENTS; i++) {
      const u = i / NUM_SEGMENTS;
      const curDist = u * this.totalDistance;
      const endDist = Math.min(this.totalDistance, curDist + 1000);

      const sampleDistances = [];
      for (let d = curDist; d <= endDist; d += 150) {
        sampleDistances.push(d);
      }
      if (sampleDistances[sampleDistances.length - 1] < endDist) {
        sampleDistances.push(endDist);
      }

      const checkPoints = sampleDistances.map(d => {
        const pU = this.totalDistance > 0 ? d / this.totalDistance : 0;
        const pt = this.cameraCurve.getPointAt(Math.min(1.0, Math.max(0.0, pU)));
        return { x: pt.x, north: -pt.z };
      });

      const required = new Set();
      // Chunk directly under camera
      const curPt = this.cameraCurve.getPointAt(u);
      const camIx = Math.floor(curPt.x / CHUNK_SIZE);
      const camIy = Math.floor(-curPt.z / CHUNK_SIZE);
      if (validChunkKeys.has(`${camIx},${camIy}`)) {
        required.add(`${camIx},${camIy}`);
      }

      // Fast bounding box check around each checkpoint (avoids scanning 2769 chunks)
      for (const cp of checkPoints) {
        const minIx = Math.floor((cp.x - 1200) / CHUNK_SIZE);
        const maxIx = Math.floor((cp.x + 1200) / CHUNK_SIZE);
        const minIy = Math.floor((cp.north - 1200) / CHUNK_SIZE);
        const maxIy = Math.floor((cp.north + 1200) / CHUNK_SIZE);

        for (let ix = minIx; ix <= maxIx; ix++) {
          for (let iy = minIy; iy <= maxIy; iy++) {
            const key = `${ix},${iy}`;
            if (validChunkKeys.has(key)) {
              const cx = (ix + 0.5) * CHUNK_SIZE;
              const cy = (iy + 0.5) * CHUNK_SIZE;
              const dx = cx - cp.x;
              const dy = cy - cp.north;
              if (dx * dx + dy * dy <= 1200 * 1200) {
                required.add(key);
              }
            }
          }
        }
      }

      this.precomputedRequiredSegments.push(required);
    }
  }

  chainPurpleLineWays(tracks) {
    const purpleTracks = tracks.filter(t => t.line === "Purple" && !t.is_construction);
    const baiyappa = [6267.42, 2113.71];
    const majestic = [-2350.16, 445.61];

    const dist2d = (p1, p2) => Math.hypot(p1[0] - p2[0], p1[1] - p2[1]);

    const nodes = [];
    const getNode = (pt, tol = 5.0) => {
      for (let i = 0; i < nodes.length; i++) {
        if (dist2d(nodes[i], pt) < tol) return i;
      }
      nodes.push(pt);
      return nodes.length - 1;
    };

    const adj = new Map();
    for (let i = 0; i < purpleTracks.length; i++) {
      const t = purpleTracks[i];
      const u = getNode(t.points[0]);
      const v = getNode(t.points[t.points.length - 1]);
      if (!adj.has(u)) adj.set(u, []);
      if (!adj.has(v)) adj.set(v, []);
      adj.get(u).push({ neighbor: v, trackIdx: i, rev: false });
      adj.get(v).push({ neighbor: u, trackIdx: i, rev: true });
    }

    const startNode = getNode(baiyappa, 50.0);
    const queue = [[startNode, []]];
    const visited = new Set([startNode]);
    let foundPath = null;

    while (queue.length > 0) {
      const [curr, path] = queue.shift();
      if (dist2d(nodes[curr], majestic) < 50) {
        foundPath = path;
        break;
      }
      for (const edge of adj.get(curr) || []) {
        if (!visited.has(edge.neighbor)) {
          visited.add(edge.neighbor);
          queue.push([edge.neighbor, [...path, edge]]);
        }
      }
    }

    if (!foundPath) return [];

    const chainedPoints = [];
    for (const edge of foundPath) {
      const t = purpleTracks[edge.trackIdx];
      const pts = edge.rev ? [...t.points].reverse() : t.points;
      if (chainedPoints.length === 0) {
        chainedPoints.push(...pts);
      } else {
        chainedPoints.push(...pts.slice(1));
      }
    }
    return chainedPoints;
  }

  async getElevation(x, north) {
    if (this.getTerrainElevation) {
      const val = await this.getTerrainElevation(x, north);
      const exagg = window.verticalExaggeration || 1.0;
      return val * exagg;
    }
    return 900.0 * (window.verticalExaggeration || 1.0);
  }

  /**
   * Determine required chunks for progress s:
   * 1. Chunk under camera
   * 2. Every chunk within 1.2 km of any point along the next 1.0 km of the path
   * Uses O(1) precomputed segment lookup for tour frame performance.
   */
  getRequiredChunkKeys(progress) {
    if (this.precomputedRequiredSegments && this.precomputedRequiredSegments.length > 0) {
      const idx = Math.min(
        this.precomputedRequiredSegments.length - 1,
        Math.max(0, Math.floor(progress * (this.precomputedRequiredSegments.length - 1)))
      );
      return this.precomputedRequiredSegments[idx];
    }

    const required = new Set();
    if (!this.cameraCurve) return required;

    const allChunks = this.getChunks ? this.getChunks() : [];
    if (!allChunks || allChunks.length === 0) return required;

    const curDist = progress * this.totalDistance;
    const endDist = Math.min(this.totalDistance, curDist + 1000);

    // Sample along next 1 km in 150m steps
    const sampleDistances = [];
    for (let d = curDist; d <= endDist; d += 150) {
      sampleDistances.push(d);
    }
    if (sampleDistances[sampleDistances.length - 1] < endDist) {
      sampleDistances.push(endDist);
    }

    const checkPoints = sampleDistances.map(d => {
      const u = this.totalDistance > 0 ? d / this.totalDistance : 0;
      const pt = this.cameraCurve.getPointAt(Math.min(1.0, Math.max(0.0, u)));
      return { x: pt.x, north: -pt.z };
    });

    // Chunk directly under camera
    const curPt = this.cameraCurve.getPointAt(progress);
    const camIx = Math.floor(curPt.x / CHUNK_SIZE);
    const camIy = Math.floor(-curPt.z / CHUNK_SIZE);
    required.add(`${camIx},${camIy}`);

    // Chunks within 1.2 km of path points
    for (const chunk of allChunks) {
      const cx = (chunk.ix + 0.5) * CHUNK_SIZE;
      const cy = (chunk.iy + 0.5) * CHUNK_SIZE;

      for (const cp of checkPoints) {
        const dx = cx - cp.x;
        const dy = cy - cp.north;
        if (Math.hypot(dx, dy) <= 1200) {
          required.add(`${chunk.ix},${chunk.iy}`);
          break;
        }
      }
    }

    return required;
  }

  /**
   * Check how many required chunks are loaded with terrain and buildings.
   * Throttled to a 250 ms interval during frame updates to eliminate main thread overhead.
   */
  checkReadiness(progress, force = false) {
    const now = performance.now();
    if (!force && this._cachedReadiness && (now - (this._lastReadinessCheckTime || 0) < 250)) {
      this._lastScanDuration = 0;
      return this._cachedReadiness;
    }
    const tScan0 = performance.now();
    this._lastReadinessCheckTime = now;

    const requiredKeys = this.getRequiredChunkKeys(progress);
    let loadedCount = 0;

    for (const key of requiredKeys) {
      const state = this.loadedChunks ? (this.loadedChunks.get(key) || this.loadedChunks.get(key.replace(",", "_"))) : null;
      if (state && state.terrainMesh) {
        if (!state.chunk?.buildingCount || state.buildingMesh) {
          loadedCount++;
        }
      } else {
        // Trigger load
        const [ix, iy] = key.split(",").map(Number);
        if (this.requestChunkLoad) {
          this.requestChunkLoad(ix, iy);
        }
      }
    }

    const result = {
      isReady: loadedCount >= requiredKeys.size,
      chunksLoaded: loadedCount,
      chunksRequired: requiredKeys.size
    };
    this._cachedReadiness = result;
    this._lastScanDuration = performance.now() - tScan0;
    return result;
  }

  async startTour(tourId) {
    const tour = this.tours.get(tourId);
    if (!tour) return; // Invalid ID ignored gracefully per spec

    this.activeTour = tour;
    this.progress = 0.0;
    this.currentWaypointIndex = 0;
    this.stallsCount = 0;
    this.isStalled = false;
    this.isPreparing = true;
    this.isPausedForLoading = false;
    this.dwellRemaining = tour.waypoints[0]?.dwell_s || 4;

    // Save full user settings to restore on cancel/close
    this.savedSettings = {
      time: document.querySelector("#time")?.value || 72,
      timeClock: document.querySelector("#time-label")?.textContent || "17:30",
      radius: document.querySelector("#radius")?.value || 4,
      traffic: document.querySelector("#traffic-density")?.value || window.currentTrafficSetting || "off",
      trafficDay: document.querySelector("#traffic-day-toggle")?.checked || false,
      exaggeration: window.verticalExaggeration || 1.0,
      shadows: document.querySelector("#shadows-toggle")?.checked || false,
      cameraPos: this.camera.position.clone(),
      controlsTarget: this.controls.target.clone()
    };

    // Apply tour environmental presets
    if (this.setTime && typeof tour.time === "number") {
      this.setTime(tour.time);
    }
    if (this.setRadius) {
      this.setRadius(Math.max(4, Number(this.savedSettings.radius)));
    }
    if (this.setTraffic) {
      if (tour.traffic) {
        this.setTraffic("med");
      }
    }

    await this.buildTourSplines(tour);

    // Initial camera placement
    const p0 = this.cameraCurve.getPointAt(0);
    const t0 = this.targetCurve.getPointAt(0);
    this.camera.position.copy(p0);
    this.controls.target.copy(t0);
    this.controls.update();

    this.state = "playing";
    this.showCard();
    this.updateCardUi();
    this.updatePanelButtons();

    if (this.stallMsgElement) {
      this.stallMsgElement.textContent = "Preparing tour...";
      this.stallMsgElement.style.display = "inline-block";
    }
  }

  stopTour(restoreSettings = true, restoreCamera = false) {
    if (this.state === "idle" && !this.activeTour) return;

    this.state = "idle";
    const tour = this.activeTour;
    this.activeTour = null;
    this.isPreparing = false;
    this.isPausedForLoading = false;

    if (restoreSettings && this.savedSettings) {
      this.restoreSettings();
      if (restoreCamera && this.savedSettings.cameraPos && this.savedSettings.controlsTarget) {
        this.camera.position.copy(this.savedSettings.cameraPos);
        this.controls.target.copy(this.savedSettings.controlsTarget);
        this.controls.update();
      }
    }

    this.hideCard();
    this.updatePanelButtons();
  }

  restoreSettings() {
    if (!this.savedSettings) return;
    if (this.setTimeRaw && this.savedSettings.time !== undefined) {
      this.setTimeRaw(this.savedSettings.time);
    } else if (this.setTime && this.savedSettings.time !== undefined) {
      const timeVal = (Number(this.savedSettings.time) * 24) / 100;
      this.setTime(timeVal);
    }
    if (this.setRadius && this.savedSettings.radius !== undefined) {
      this.setRadius(Number(this.savedSettings.radius));
    }
    if (this.setTraffic && this.savedSettings.traffic !== undefined) {
      this.setTraffic(this.savedSettings.traffic);
    }
    if (this.setTrafficDay && this.savedSettings.trafficDay !== undefined) {
      this.setTrafficDay(this.savedSettings.trafficDay);
    }
    if (this.setExaggeration && this.savedSettings.exaggeration !== undefined) {
      this.setExaggeration(this.savedSettings.exaggeration);
    }
    if (this.setShadows && this.savedSettings.shadows !== undefined) {
      this.setShadows(this.savedSettings.shadows);
    }
  }

  finishTour() {
    this.progress = 1.0;
    const wpCount = this.activeTour?.waypoints?.length || 1;
    this.jumpToWaypoint(wpCount - 1);
    this.state = "paused";
    if (this.playBtnElement) this.playBtnElement.textContent = "► Replay";
    this.restoreSettings();
  }

  togglePlayPause() {
    if (this.state === "playing") {
      this.state = "paused";
      if (this.playBtnElement) this.playBtnElement.textContent = "► Play";
    } else if (this.state === "paused") {
      this.state = "playing";
      if (this.playBtnElement) this.playBtnElement.textContent = "❚❚ Pause";
    }
  }

  nextWaypoint() {
    if (!this.activeTour) return;
    const count = this.activeTour.waypoints.length;
    if (this.currentWaypointIndex < count - 1) {
      this.jumpToWaypoint(this.currentWaypointIndex + 1);
    }
  }

  prevWaypoint() {
    if (!this.activeTour) return;
    if (this.currentWaypointIndex > 0) {
      this.jumpToWaypoint(this.currentWaypointIndex - 1);
    }
  }

  jumpToWaypoint(idx) {
    if (!this.activeTour || !this.cameraCurve || !this.targetCurve) return;
    this.currentWaypointIndex = Math.max(0, Math.min(this.activeTour.waypoints.length - 1, idx));
    const targetProgress = this.currentWaypointIndex / (this.activeTour.waypoints.length - 1 || 1);
    this.progress = targetProgress;
    this.dwellRemaining = this.activeTour.waypoints[this.currentWaypointIndex]?.dwell_s || 4;

    if (this.isReducedMotion) {
      if (this.fadeOverlay) {
        this.fadeOverlay.style.opacity = "1";
        setTimeout(() => {
          const p = this.cameraCurve.getPointAt(this.progress);
          const t = this.targetCurve.getPointAt(this.progress);
          this.camera.position.copy(p);
          this.controls.target.copy(t);
          this.controls.update();
          this.fadeOverlay.style.opacity = "0";
        }, 80);
      }
    } else {
      const p = this.cameraCurve.getPointAt(this.progress);
      const t = this.targetCurve.getPointAt(this.progress);
      this.camera.position.copy(p);
      this.controls.target.copy(t);
      this.controls.update();
    }
    this.updateCardUi();
  }

  update(dt) {
    if (this.state !== "playing" || !this.activeTour || !this.cameraCurve) return;

    if (this.progress >= 1.0) {
      this.finishTour();
      return;
    }

    // Clamp per-frame dt to 100 ms (was 50 ms) so slow frames do not skip distance, and track skipped time
    const maxDt = 0.10;
    const safeDt = Math.min(maxDt, dt);
    if (dt > maxDt) {
      this.totalSkippedTime = (this.totalSkippedTime || 0) + (dt - maxDt);
    }

    if (this.isReducedMotion) {
      return;
    }

    // Check readiness gating: chunk under camera and every chunk within 1.2 km along next 1.0 km
    const readiness = this.checkReadiness(this.progress);
    if (!readiness.isReady) {
      if (!this.isStalled) {
        this.isStalled = true;
        this.stallsCount++;
      }
      this.isPausedForLoading = true;
      if (this.stallMsgElement) {
        this.stallMsgElement.textContent = this.isPreparing ? "Preparing tour..." : "Loading...";
        this.stallMsgElement.style.display = "inline-block";
      }
      return; // DO NOT ADVANCE DISTANCE
    }

    if (this.isStalled) {
      this.isStalled = false;
    }
    this.isPausedForLoading = false;
    this.isPreparing = false;
    if (this.stallMsgElement) {
      this.stallMsgElement.style.display = "none";
    }

    // Check dwell at current waypoint
    if (this.dwellRemaining > 0) {
      this.dwellRemaining -= safeDt;
      return;
    }

    // Eased cruise speed capped at MAX_SPEED_MS (75 m/s)
    // Trapezoidal speed envelope: 6% ramp up, 88% full cruise at 75 m/s, 6% ramp down
    const wpCount = this.activeTour.waypoints.length;
    const segT = (this.progress * (wpCount - 1)) % 1.0;
    let ease = 1.0;
    if (segT < 0.06) {
      ease = 0.33 + 0.67 * Math.sin((segT / 0.06) * (Math.PI / 2));
    } else if (segT > 0.94) {
      ease = 0.33 + 0.67 * Math.sin(((1.0 - segT) / 0.06) * (Math.PI / 2));
    } else {
      ease = 1.0;
    }
    this.currentSpeed = ease * MAX_SPEED_MS;

    const ds = this.currentSpeed * safeDt;
    this.progress += ds / (this.totalDistance || 1);
    this.simCruiseTime = (this.simCruiseTime || 0) + safeDt;
    this.simDistAdvanced = (this.simDistAdvanced || 0) + ds;

    if (this.progress >= 1.0) {
      this.finishTour();
      return;
    }

    const newWpIndex = Math.min(
      wpCount - 1,
      Math.floor(this.progress * (wpCount - 1) + 0.1)
    );
    if (newWpIndex !== this.currentWaypointIndex) {
      this.currentWaypointIndex = newWpIndex;
      this.dwellRemaining = this.activeTour.waypoints[newWpIndex]?.dwell_s || 4;
      this.updateCardUi();
    }

    const newCamPos = this.cameraCurve.getPointAt(this.progress);
    const newTargetPos = this.targetCurve.getPointAt(this.progress);
    this.camera.position.copy(newCamPos);
    this.controls.target.copy(newTargetPos);
    this.controls.update();

    if (this.progressBarElement) {
      this.progressBarElement.style.width = `${Math.round(this.progress * 100)}%`;
    }

    if (safeDt > 0) {
      this.frameTimes.push(safeDt * 1000);
      if (this.frameTimes.length > 500) this.frameTimes.shift();
    }
  }

  getFrameMetrics() {
    if (this.frameTimes.length === 0) return { avg: 16.6, p95: 16.6, over33: 0, count: 0 };
    const sorted = [...this.frameTimes].sort((a, b) => a - b);
    const avg = this.frameTimes.reduce((a, b) => a + b, 0) / this.frameTimes.length;
    const p95 = sorted[Math.floor(sorted.length * 0.95)] || 0;
    const over33 = this.frameTimes.filter(t => t > 33.33).length;
    return { avg, p95, over33, count: this.frameTimes.length };
  }

  showCard() {
    if (this.cardElement) this.cardElement.style.display = "block";
  }

  hideCard() {
    if (this.cardElement) this.cardElement.style.display = "none";
  }

  updateCardUi() {
    if (!this.activeTour) return;
    const tour = this.activeTour;
    const wp = tour.waypoints[this.currentWaypointIndex] || tour.waypoints[0];

    if (this.titleElement) this.titleElement.textContent = tour.title;
    if (this.stepElement) {
      this.stepElement.textContent = `${this.currentWaypointIndex + 1} / ${tour.waypoints.length}`;
    }
    if (this.stopNameElement) this.stopNameElement.textContent = wp.name;
    if (this.captionTextElement) this.captionTextElement.textContent = wp.caption.text;
    if (this.sourceElement) {
      this.sourceElement.textContent = `Source: ${wp.caption.source}`;
    }
    if (this.progressBarElement) {
      this.progressBarElement.style.width = `${Math.round(this.progress * 100)}%`;
    }
    if (this.playBtnElement) {
      this.playBtnElement.textContent = this.state === "paused" ? "► Play" : "❚❚ Pause";
    }
  }

  updatePanelButtons() {
    document.querySelectorAll(".tour-btn").forEach(btn => {
      const tourId = btn.getAttribute("data-tour");
      if (this.activeTour && this.activeTour.id === tourId) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  /**
   * Sample clearance every 25 m along tour curve
   * Compute BOTH:
   * 1. (alt - (terrain + 120))
   * 2. (alt - (tallest building within 100 m + 40))
   * Both must be >= 0.
   */
  async sampleClearance(tourId) {
    const tour = this.tours.get(tourId);
    if (!tour) return { minClearanceTerrain: 0, minClearanceBuilding: 0, minClearance: 0, samplesCount: 0, lowestSamples: [] };

    await this.buildTourSplines(tour);
    const curve = this.cameraCurve;
    const totalLen = curve.getLength();
    const step = 25.0; // every 25 m
    const numSamples = Math.max(2, Math.floor(totalLen / step));

    let minClearanceTerrain = 999999;
    let minClearanceBuilding = 999999;
    const samples = [];

    for (let i = 0; i <= numSamples; i++) {
      const u = i / numSamples;
      const pt = curve.getPointAt(u);
      const x = pt.x;
      const north = -pt.z;
      const camY = pt.y;

      const groundY = await this.getElevation(x, north);

      // Query tallest building top within 100 m
      let tallestBldgTop = groundY;
      let tallestBldgHeight = 0;
      if (!this._parsedChunkBuildings) {
        this._parsedChunkBuildings = new Map();
      }

      const allChunks = this.getChunks ? this.getChunks() : [];
      for (const chunk of allChunks) {
        const cx = (chunk.ix + 0.5) * CHUNK_SIZE;
        const cy = (chunk.iy + 0.5) * CHUNK_SIZE;
        // Check if chunk is within 1.2 km
        if (Math.hypot(cx - x, cy - north) <= 1200) {
          const key = `${chunk.ix},${chunk.iy}`;
          const state = this.loadedChunks?.get(key) || this.loadedChunks?.get(`${chunk.ix}_${chunk.iy}`);
          if (state && state.buildingText) {
            let bldgs = this._parsedChunkBuildings.get(key);
            if (!bldgs) {
              try {
                bldgs = JSON.parse(state.buildingText);
                this._parsedChunkBuildings.set(key, bldgs);
              } catch (e) {
                bldgs = [];
              }
            }
            if (Array.isArray(bldgs)) {
              for (const b of bldgs) {
                const bH = b[0] || 0;
                const coords = b[1];
                if (coords && coords.length >= 2) {
                  const bx = chunk.ix * CHUNK_SIZE + coords[0];
                  const by = chunk.iy * CHUNK_SIZE + coords[1];
                  if (Math.hypot(bx - x, by - north) <= 100) {
                    const topY = groundY + bH;
                    if (topY > tallestBldgTop) {
                      tallestBldgTop = topY;
                      tallestBldgHeight = bH;
                    }
                  }
                }
              }
            }
          }
        }
      }

      const clrTerrain = camY - (groundY + 120);
      const clrBuilding = camY - (tallestBldgTop + 40);

      if (clrTerrain < minClearanceTerrain) minClearanceTerrain = clrTerrain;
      if (clrBuilding < minClearanceBuilding) minClearanceBuilding = clrBuilding;

      samples.push({
        dist: i * step,
        u,
        x,
        north,
        camY,
        groundY,
        tallestBldgTop,
        tallestBldgHeight,
        clrTerrain,
        clrBuilding,
        margin: Math.min(clrTerrain, clrBuilding)
      });
    }

    const sortedSamples = [...samples].sort((a, b) => a.margin - b.margin);

    this.minClearanceTerrain = minClearanceTerrain;
    this.minClearanceBuilding = minClearanceBuilding;
    this.minClearance = Math.min(minClearanceTerrain, minClearanceBuilding);

    return {
      minClearanceTerrain,
      minClearanceBuilding,
      minClearance: this.minClearance,
      samplesCount: numSamples,
      lowestSamples: sortedSamples.slice(0, 3)
    };
  }
}
