function calculateSunPosition(dateStr, hours, minutes) {
  const parts = (dateStr || "2026-11-24").split("-");
  const year = parseInt(parts[0], 10) || 2026;
  const month = parseInt(parts[1], 10) || 11;
  const day = parseInt(parts[2], 10) || 24;

  const N1 = Math.floor(275 * month / 9);
  const N2 = Math.floor((month + 9) / 12);
  const N3 = (1 + Math.floor((year - 4 * Math.floor(year / 4) + 2) / 3));
  const dayOfYear = N1 - (N2 * N3) + day - 30;

  const totalHours = hours + minutes / 60;
  const gamma = 2 * Math.PI / 365 * (dayOfYear - 1 + (totalHours - 12) / 24);

  const eqtime = 229.18 * (0.000075 + 0.001868 * Math.cos(gamma) - 0.032077 * Math.sin(gamma)
    - 0.014615 * Math.cos(2 * gamma) - 0.040849 * Math.sin(2 * gamma));

  const decl = 0.006918 - 0.399912 * Math.cos(gamma) + 0.070257 * Math.sin(gamma)
    - 0.006758 * Math.cos(2 * gamma) + 0.000907 * Math.sin(2 * gamma)
    - 0.002697 * Math.cos(3 * gamma) + 0.00148 * Math.sin(3 * gamma);

  const timeOffset = eqtime + 4 * 77.5946 - 330.0;
  const trueSolarTime = totalHours * 60 + timeOffset;

  const ha = (trueSolarTime / 4.0) - 180.0;
  const haRad = ha * Math.PI / 180;
  const latRad = 12.9716 * Math.PI / 180;

  const cosZenith = Math.sin(latRad) * Math.sin(decl) + Math.cos(latRad) * Math.cos(decl) * Math.cos(haRad);
  const zenithRad = Math.acos(Math.max(-1.0, Math.min(1.0, cosZenith)));
  const elevationDeg = 90.0 - zenithRad * 180 / Math.PI;

  const y = -Math.sin(haRad);
  const x = Math.tan(decl) * Math.cos(latRad) - Math.sin(latRad) * Math.cos(haRad);
  let azimuthDeg = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;

  return { elevation: elevationDeg, azimuth: azimuthDeg };
}

const testCases = [
  { desc: "2026-11-24 06:15 IST (sunrise)", date: "2026-11-24", h: 6, m: 15, expElev: -2.46, expAz: 110.44 },
  { desc: "2026-11-24 12:00 IST (near noon / south)", date: "2026-11-24", h: 12, m: 0, expElev: 56.48, expAz: 177.39 },
  { desc: "2026-11-24 17:30 IST (golden / sunset)", date: "2026-11-24", h: 17, m: 30, expElev: 3.71, expAz: 247.91 },
  { desc: "2026-06-21 12:00 IST (summer midday)", date: "2026-06-21", h: 12, m: 0, expElev: 78.37, expAz: 25.05 },
  { desc: "2026-03-20 06:20 IST (equinox sunrise / east)", date: "2026-03-20", h: 6, m: 20, expElev: -1.84, expAz: 89.90 },
  { desc: "2026-03-20 18:25 IST (equinox sunset / west)", date: "2026-03-20", h: 18, m: 25, expElev: 0.49, expAz: 269.77 },
];

console.log("=== Solar Azimuth & Elevation Unit Test (Tolerance ±1.0°) ===");
let allPassed = true;
const TOLERANCE = 1.0;

for (const t of testCases) {
  const actual = calculateSunPosition(t.date, t.h, t.m);
  const azDiff = Math.abs(actual.azimuth - t.expAz);
  const elDiff = Math.abs(actual.elevation - t.expElev);
  const azPass = azDiff <= TOLERANCE;
  const elPass = elDiff <= TOLERANCE;
  const pass = azPass && elPass;
  if (!pass) allPassed = false;
  
  console.log(`[${pass ? "PASS" : "FAIL"}] ${t.desc}`);
  console.log(`       Calculated: Azimuth ${actual.azimuth.toFixed(2)}°, Elevation ${actual.elevation.toFixed(2)}°`);
  console.log(`       Reference:  Azimuth ${t.expAz.toFixed(2)}°, Elevation ${t.expElev.toFixed(2)}°`);
  console.log(`       Diff:       Azimuth ${azDiff.toFixed(2)}° (tol ±${TOLERANCE}°), Elevation ${elDiff.toFixed(2)}°`);
}

if (!allPassed) {
  console.error("TEST FAILED");
  process.exit(1);
} else {
  console.log("ALL 6 SOLAR TESTS PASSED");
}
