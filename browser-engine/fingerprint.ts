/**
 * fingerprint.ts — Generates realistic, consistent browser fingerprints
 * Each fingerprint is a coherent set of values that look like a real browser.
 */

export interface BrowserFingerprint {
  userAgent: string;
  platform: string;
  vendor: string;
  productSub: string;
  webglVendor: string;
  webglRenderer: string;
  screenWidth: number;
  screenHeight: number;
  availWidth: number;
  availHeight: number;
  colorDepth: number;
  pixelRatio: number;
  languages: string[];
  timezone: string;
  hardwareConcurrency: number;
  deviceMemory: number;
  maxTouchPoints: number;
  connectionType: string;
}

interface UAProfile {
  ua: string;
  platform: string;
  vendor: string;
  productSub: string;
  os: "windows" | "mac" | "linux";
  webglPairs: Array<{ vendor: string; renderer: string }>;
  resolutions: Array<{ w: number; h: number }>;
  timezones: string[];
  languages: string[][];
}

const PROFILES: UAProfile[] = [
  {
    ua: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    platform: "Win32",
    vendor: "Google Inc.",
    productSub: "20030107",
    os: "windows",
    webglPairs: [
      { vendor: "Google Inc. (NVIDIA)", renderer: "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)" },
      { vendor: "Google Inc. (NVIDIA)", renderer: "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)" },
      { vendor: "Google Inc. (Intel)", renderer: "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)" },
      { vendor: "Google Inc. (AMD)", renderer: "ANGLE (AMD, AMD Radeon RX 580 Series Direct3D11 vs_5_0 ps_5_0, D3D11)" },
    ],
    resolutions: [
      { w: 1920, h: 1080 },
      { w: 2560, h: 1440 },
      { w: 1366, h: 768 },
      { w: 1536, h: 864 },
    ],
    timezones: ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Phoenix"],
    languages: [["en-US", "en"], ["en-US", "en", "es"]],
  },
  {
    ua: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    platform: "Win32",
    vendor: "Google Inc.",
    productSub: "20030107",
    os: "windows",
    webglPairs: [
      { vendor: "Google Inc. (NVIDIA)", renderer: "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)" },
      { vendor: "Google Inc. (NVIDIA)", renderer: "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)" },
      { vendor: "Google Inc. (Intel)", renderer: "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)" },
    ],
    resolutions: [
      { w: 1920, h: 1080 },
      { w: 2560, h: 1440 },
      { w: 1440, h: 900 },
    ],
    timezones: ["America/New_York", "America/Chicago", "America/Los_Angeles"],
    languages: [["en-US", "en"], ["en-US", "en", "fr"]],
  },
  {
    ua: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    platform: "MacIntel",
    vendor: "Google Inc.",
    productSub: "20030107",
    os: "mac",
    webglPairs: [
      { vendor: "Google Inc. (Apple)", renderer: "ANGLE (Apple, Apple M1, OpenGL 4.1)" },
      { vendor: "Google Inc. (Apple)", renderer: "ANGLE (Apple, Apple M2, OpenGL 4.1)" },
      { vendor: "Google Inc. (Intel)", renderer: "ANGLE (Intel, Intel(R) Iris(TM) Plus Graphics 655, OpenGL 4.1)" },
    ],
    resolutions: [
      { w: 1680, h: 1050 },
      { w: 1920, h: 1080 },
      { w: 2560, h: 1600 },
      { w: 1440, h: 900 },
    ],
    timezones: ["America/New_York", "America/Chicago", "America/Los_Angeles", "America/Anchorage", "Pacific/Honolulu"],
    languages: [["en-US", "en"], ["en-US", "en", "de"]],
  },
  {
    ua: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    platform: "MacIntel",
    vendor: "Google Inc.",
    productSub: "20030107",
    os: "mac",
    webglPairs: [
      { vendor: "Google Inc. (Apple)", renderer: "ANGLE (Apple, Apple M2 Pro, OpenGL 4.1)" },
      { vendor: "Google Inc. (Apple)", renderer: "ANGLE (Apple, Apple M3, OpenGL 4.1)" },
    ],
    resolutions: [
      { w: 1920, h: 1080 },
      { w: 2560, h: 1600 },
      { w: 3024, h: 1964 },
    ],
    timezones: ["America/New_York", "America/Chicago", "America/Los_Angeles"],
    languages: [["en-US", "en"]],
  },
  {
    ua: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    platform: "Linux x86_64",
    vendor: "Google Inc.",
    productSub: "20030107",
    os: "linux",
    webglPairs: [
      { vendor: "Google Inc. (NVIDIA)", renderer: "ANGLE (NVIDIA, NVIDIA GeForce GTX 1080/PCIe/SSE2)" },
      { vendor: "Google Inc. (Mesa)", renderer: "ANGLE (Mesa, AMD RADV NAVI10 (ACO))" },
      { vendor: "Google Inc. (Intel)", renderer: "ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2))" },
    ],
    resolutions: [
      { w: 1920, h: 1080 },
      { w: 2560, h: 1440 },
      { w: 3840, h: 2160 },
    ],
    timezones: ["America/New_York", "America/Chicago", "America/Los_Angeles", "UTC"],
    languages: [["en-US", "en"]],
  },
];

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function randInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export function generateFingerprint(): BrowserFingerprint {
  const profile = pick(PROFILES);
  const webgl = pick(profile.webglPairs);
  const resolution = pick(profile.resolutions);

  // Slight random variation in viewport (subtract some pixels for browser chrome)
  const viewportWidth = resolution.w - randInt(0, 20);
  const viewportHeight = resolution.h - randInt(80, 160);

  const pixelRatio = pick([1, 1, 1, 1.25, 1.5, 2, 2]);
  const hardwareConcurrency = profile.os === "mac" ? pick([8, 10, 12]) : pick([4, 6, 8, 12, 16]);
  const deviceMemory = profile.os === "mac" ? pick([8, 16, 32]) : pick([4, 8, 16, 32]);

  return {
    userAgent: profile.ua,
    platform: profile.platform,
    vendor: profile.vendor,
    productSub: profile.productSub,
    webglVendor: webgl.vendor,
    webglRenderer: webgl.renderer,
    screenWidth: resolution.w,
    screenHeight: resolution.h,
    availWidth: viewportWidth,
    availHeight: viewportHeight,
    colorDepth: pick([24, 24, 24, 32]),
    pixelRatio,
    languages: pick(profile.languages),
    timezone: pick(profile.timezones),
    hardwareConcurrency,
    deviceMemory,
    maxTouchPoints: profile.os === "windows" ? pick([0, 0, 0, 10]) : 0,
    connectionType: pick(["4g", "4g", "4g", "wifi"]),
  };
}

/** Returns the Chrome launch viewport argument from the fingerprint */
export function fingerprintToViewportArg(fp: BrowserFingerprint): string {
  return `--window-size=${fp.screenWidth},${fp.screenHeight}`;
}

/**
 * Simple deterministic hash from a string to a number.
 * Uses FNV-1a-inspired algorithm for good distribution.
 */
function hashSeed(seed: string): number {
  let hash = 2166136261; // FNV offset basis
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16777619); // FNV prime
  }
  return hash >>> 0; // Ensure unsigned
}

/**
 * Deterministically pick an element from an array using a hash-derived index.
 * Uses a portion of the hash bits so that successive calls yield different picks.
 */
function seededPick<T>(arr: T[], hash: number, shift: number): T {
  const index = (hash >>> shift) % arr.length;
  return arr[Math.abs(index)];
}

/**
 * Deterministically pick a value from weighted array entries (by repetition).
 * Same as seededPick but works with the weighted arrays like [1, 1, 1, 1.25, 1.5, 2, 2].
 */
function seededPickWeighted<T>(arr: T[], hash: number, shift: number): T {
  return seededPick(arr, hash, shift);
}

/**
 * Generate a deterministic fingerprint from a seed string (e.g., username).
 * The same seed will always produce the same fingerprint.
 * Useful for fingerprint persistence across sessions for the same user.
 */
export function generateFingerprintFromSeed(seed: string): BrowserFingerprint {
  const hash = hashSeed(seed);

  // Use bits 0-7 to pick profile
  const profile = seededPick(PROFILES, hash, 0);

  // Use bits 8-11 to pick webgl pair
  const webgl = seededPick(profile.webglPairs, hash, 8);

  // Use bits 12-15 to pick resolution
  const resolution = seededPick(profile.resolutions, hash, 12);

  // Deterministic viewport offset based on hash
  const viewportOffsetW = ((hash >>> 16) & 0xFF) % 21; // 0-20
  const viewportOffsetH = 80 + ((hash >>> 20) & 0xFF) % 81; // 80-160
  const viewportWidth = resolution.w - viewportOffsetW;
  const viewportHeight = resolution.h - viewportOffsetH;

  // Deterministic pixel ratio (weighted toward common values)
  const pixelRatios = [1, 1, 1, 1.25, 1.5, 2, 2];
  const pixelRatio = seededPickWeighted(pixelRatios, hash, 24);

  // Deterministic hardware concurrency
  const macCores = [8, 10, 12];
  const otherCores = [4, 6, 8, 12, 16];
  const hardwareConcurrency = profile.os === "mac"
    ? seededPick(macCores, hash, 26)
    : seededPick(otherCores, hash, 26);

  // Deterministic device memory
  const macMemory = [8, 16, 32];
  const otherMemory = [4, 8, 16, 32];
  const deviceMemory = profile.os === "mac"
    ? seededPick(macMemory, hash, 28)
    : seededPick(otherMemory, hash, 28);

  // Deterministic color depth (weighted toward 24)
  const colorDepths = [24, 24, 24, 32];
  const colorDepth = seededPickWeighted(colorDepths, hash, 30);

  // Deterministic language from profile
  const languages = seededPick(profile.languages, hash, 0);

  // Deterministic timezone from profile
  const timezone = seededPick(profile.timezones, hash, 4);

  // Deterministic maxTouchPoints
  const winTouch = [0, 0, 0, 10];
  const maxTouchPoints = profile.os === "windows"
    ? seededPick(winTouch, hash, 2)
    : 0;

  // Deterministic connection type (weighted toward 4g)
  const connectionTypes = ["4g", "4g", "4g", "wifi"];
  const connectionType = seededPickWeighted(connectionTypes, hash, 6);

  return {
    userAgent: profile.ua,
    platform: profile.platform,
    vendor: profile.vendor,
    productSub: profile.productSub,
    webglVendor: webgl.vendor,
    webglRenderer: webgl.renderer,
    screenWidth: resolution.w,
    screenHeight: resolution.h,
    availWidth: viewportWidth,
    availHeight: viewportHeight,
    colorDepth,
    pixelRatio,
    languages,
    timezone,
    hardwareConcurrency,
    deviceMemory,
    maxTouchPoints,
    connectionType,
  };
}
