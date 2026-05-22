/**
 * browser-modes.ts — Smart Browser Modes
 * Three-tier browser mode system:
 *
 * FULL MODE: CDP + real Chrome + user profile
 *   - Use for: Login, signup, posting, any authenticated action
 *   - Memory: 300-500MB (real Chrome with profile)
 *   - Detection: Nearly impossible (it IS the user's browser)
 *
 * LIGHT MODE: Headless + quick scrape + close in <30 seconds
 *   - Use for: Research, scraping, data extraction
 *   - Memory: 50-80MB during task, 0MB after close
 *   - Detection: Stealth scripts handle basic detection
 *
 * GHOST MODE: API-only, no browser at all
 *   - Use for: API calls, webhooks, data processing
 *   - Memory: 0MB (no browser process)
 *   - Detection: N/A (no browser)
 */

import { randomUUID } from "crypto";
import { connectPlaywrightToCDP, checkCDPPort, discoverCDPPort } from "./cdp-connector";
import { generateFingerprint, BrowserFingerprint } from "./fingerprint";
import { getMasterStealthScript } from "./stealth";
import { getPlaywright } from "./browser-utils";

// ─── Types ───────────────────────────────────────────────────────────────────

export type BrowserMode = "full" | "light" | "ghost";

export type TaskCategory =
  | "login"
  | "signup"
  | "post"
  | "upload"
  | "delete"
  | "profile_edit"
  | "scrape"
  | "research"
  | "search"
  | "api_call"
  | "webhook"
  | "data_process"
  | "screenshot"
  | "monitor"
  | "custom";

export interface ModeDecision {
  mode: BrowserMode;
  reason: string;
  requiresAuth: boolean;
  requiresBrowser: boolean;
  requiresCDP: boolean;
  estimatedMemoryMB: number;
  estimatedDurationMs: number;
}

export interface SmartSession {
  sessionId: string;
  mode: BrowserMode;
  platform: string;
  username: string;
  stateId: string;
  taskCategory: TaskCategory;
  browser: any;
  context: any;
  page: any;
  cdpSession: any;
  cdpPort: number;
  fingerprint: BrowserFingerprint | null;
  createdAt: string;
  lastActivity: string;
  memoryEstimateMB: number;
  idleTimer: NodeJS.Timeout | null;
  taskComplete: boolean;
  handover: {
    active: boolean;
    reason: string;
    startedAt: string | null;
    sseClients: Set<any>;
    screenshotInterval: NodeJS.Timeout | null;
  };
}

// ─── Task → Mode Mapping ─────────────────────────────────────────────────────

const TASK_MODE_MAP: Record<TaskCategory, {
  mode: BrowserMode;
  requiresAuth: boolean;
  requiresBrowser: boolean;
  requiresCDP: boolean;
  estimatedMemoryMB: number;
  estimatedDurationMs: number;
}> = {
  login: { mode: "full", requiresAuth: true, requiresBrowser: true, requiresCDP: true, estimatedMemoryMB: 400, estimatedDurationMs: 60000 },
  signup: { mode: "full", requiresAuth: true, requiresBrowser: true, requiresCDP: true, estimatedMemoryMB: 400, estimatedDurationMs: 120000 },
  post: { mode: "full", requiresAuth: true, requiresBrowser: true, requiresCDP: true, estimatedMemoryMB: 400, estimatedDurationMs: 30000 },
  upload: { mode: "full", requiresAuth: true, requiresBrowser: true, requiresCDP: true, estimatedMemoryMB: 400, estimatedDurationMs: 45000 },
  delete: { mode: "full", requiresAuth: true, requiresBrowser: true, requiresCDP: true, estimatedMemoryMB: 400, estimatedDurationMs: 20000 },
  profile_edit: { mode: "full", requiresAuth: true, requiresBrowser: true, requiresCDP: true, estimatedMemoryMB: 400, estimatedDurationMs: 30000 },
  scrape: { mode: "light", requiresAuth: false, requiresBrowser: true, requiresCDP: false, estimatedMemoryMB: 60, estimatedDurationMs: 15000 },
  research: { mode: "light", requiresAuth: false, requiresBrowser: true, requiresCDP: false, estimatedMemoryMB: 60, estimatedDurationMs: 25000 },
  search: { mode: "light", requiresAuth: false, requiresBrowser: true, requiresCDP: false, estimatedMemoryMB: 60, estimatedDurationMs: 10000 },
  api_call: { mode: "ghost", requiresAuth: false, requiresBrowser: false, requiresCDP: false, estimatedMemoryMB: 0, estimatedDurationMs: 5000 },
  webhook: { mode: "ghost", requiresAuth: false, requiresBrowser: false, requiresCDP: false, estimatedMemoryMB: 0, estimatedDurationMs: 3000 },
  data_process: { mode: "ghost", requiresAuth: false, requiresBrowser: false, requiresCDP: false, estimatedMemoryMB: 0, estimatedDurationMs: 10000 },
  screenshot: { mode: "light", requiresAuth: false, requiresBrowser: true, requiresCDP: false, estimatedMemoryMB: 60, estimatedDurationMs: 8000 },
  monitor: { mode: "light", requiresAuth: false, requiresBrowser: true, requiresCDP: false, estimatedMemoryMB: 60, estimatedDurationMs: 30000 },
  custom: { mode: "light", requiresAuth: false, requiresBrowser: true, requiresCDP: false, estimatedMemoryMB: 60, estimatedDurationMs: 15000 },
};

// Platforms that always require FULL mode (authenticated actions)
const AUTH_PLATFORMS = new Set([
  "instagram", "twitter", "x", "facebook", "linkedin",
  "gmail", "outlook", "github", "reddit", "tiktok",
]);

// ─── Mode Decision Engine ────────────────────────────────────────────────────

/**
 * Determine the optimal browser mode for a given task
 */
export function decideMode(
  taskCategory: TaskCategory,
  platform?: string,
  url?: string,
  forceMode?: BrowserMode
): ModeDecision {
  // Allow force override
  if (forceMode) {
    const base = TASK_MODE_MAP[taskCategory];
    const memoryMap: Record<BrowserMode, number> = { full: 400, light: 60, ghost: 0 };
    return {
      mode: forceMode,
      reason: `Force override to ${forceMode} mode`,
      requiresAuth: forceMode === "full",
      requiresBrowser: forceMode !== "ghost",
      requiresCDP: forceMode === "full",
      estimatedMemoryMB: memoryMap[forceMode],
      estimatedDurationMs: base.estimatedDurationMs,
    };
  }

  const mapping = TASK_MODE_MAP[taskCategory] || TASK_MODE_MAP.custom;

  // If platform is known to require auth, upgrade to FULL mode
  if (platform && AUTH_PLATFORMS.has(platform) && mapping.mode === "light") {
    return {
      mode: "full",
      reason: `Platform '${platform}' typically requires authentication, upgrading to FULL mode`,
      requiresAuth: true,
      requiresBrowser: true,
      requiresCDP: true,
      estimatedMemoryMB: 400,
      estimatedDurationMs: mapping.estimatedDurationMs * 2,
    };
  }

  // If URL contains login/signup/auth patterns, upgrade to FULL
  if (url) {
    const authPatterns = [
      /\/login/i, /\/signin/i, /\/auth/i, /\/accounts/i,
      /\/signup/i, /\/register/i, /\/oauth/i,
    ];
    if (authPatterns.some((p) => p.test(url))) {
      return {
        mode: "full",
        reason: `URL contains auth pattern, using FULL mode`,
        requiresAuth: true,
        requiresBrowser: true,
        requiresCDP: true,
        estimatedMemoryMB: 400,
        estimatedDurationMs: mapping.estimatedDurationMs,
      };
    }

    // Check URL domain against known auth-required platforms
    const authDomainPatterns = [
      /instagram\.com/i, /twitter\.com/i, /x\.com/i, /facebook\.com/i,
      /linkedin\.com/i, /gmail\.com/i, /outlook\.com/i, /github\.com/i,
      /reddit\.com/i, /tiktok\.com/i, /pinterest\.com/i, /snapchat\.com/i,
      /tumblr\.com/i, /whatsapp\.com/i,
    ];
    if (authDomainPatterns.some((p) => p.test(url))) {
      return {
        mode: "full",
        reason: `URL domain requires authentication, upgrading to FULL mode`,
        requiresAuth: true,
        requiresBrowser: true,
        requiresCDP: true,
        estimatedMemoryMB: 400,
        estimatedDurationMs: mapping.estimatedDurationMs * 2,
      };
    }
  }

  return {
    mode: mapping.mode,
    reason: `Task '${taskCategory}' mapped to ${mapping.mode} mode`,
    requiresAuth: mapping.requiresAuth,
    requiresBrowser: mapping.requiresBrowser,
    requiresCDP: mapping.requiresCDP,
    estimatedMemoryMB: mapping.estimatedMemoryMB,
    estimatedDurationMs: mapping.estimatedDurationMs,
  };
}

/**
 * Get task category from a natural language description
 */
export function detectTaskCategory(description: string): TaskCategory {
  const lower = description.toLowerCase();

  const patterns: Array<[TaskCategory, RegExp[]]> = [
    ["login", [/log\s*in/i, /sign\s*in/i, /authenticate/i, /auth/i]],
    ["signup", [/sign\s*up/i, /register/i, /create\s*account/i, /join/i]],
    ["post", [/post/i, /publish/i, /share/i, /tweet/i, /create\s*content/i]],
    ["upload", [/upload/i, /add\s*photo/i, /add\s*image/i, /add\s*video/i, /attach/i]],
    ["delete", [/delete/i, /remove/i, /unpublish/i, /take\s*down/i]],
    ["profile_edit", [/edit\s*profile/i, /update\s*profile/i, /change\s*bio/i, /update\s*bio/i]],
    ["scrape", [/scrape/i, /extract\s*data/i, /crawl/i, /parse/i, /collect\s*data/i]],
    ["research", [/research/i, /investigate/i, /analyze/i, /study/i, /find\s*info/i]],
    ["search", [/search/i, /find/i, /look\s*up/i, /query/i]],
    ["api_call", [/api\s*call/i, /fetch\s*api/i, /endpoint/i, /rest\s*api/i]],
    ["webhook", [/webhook/i, /callback/i, /notify/i]],
    ["data_process", [/process\s*data/i, /transform/i, /convert/i, /clean\s*data/i]],
    ["screenshot", [/screenshot/i, /capture/i, /snapshot/i, /screen\s*grab/i]],
    ["monitor", [/monitor/i, /watch/i, /track\s*changes/i, /observe/i]],
  ];

  for (const [category, regexes] of patterns) {
    if (regexes.some((r) => r.test(lower))) {
      return category;
    }
  }

  return "custom";
}

// ─── Session Launcher ────────────────────────────────────────────────────────

// getPlaywright() is now imported from ./browser-utils (shared singleton)

/**
 * Launch a FULL mode session (CDP + real Chrome + user profile)
 */
async function launchFullSession(
  platform: string,
  username: string,
  stateId: string,
  cdpPort?: number
): Promise<SmartSession> {
  const pw = await getPlaywright();

  // Try to connect to existing Chrome via CDP
  const connection = await connectPlaywrightToCDP(pw, {
    cdpPort: cdpPort || 9222,
    autoDiscover: true,
  });

  let browser: any;
  let context: any;
  let page: any;
  let cdpSession: any;
  let actualCdpPort = cdpPort || 9222;

  if (connection) {
    browser = connection.browser;
    context = connection.context;
    page = connection.page;
    cdpSession = connection.cdpSession;
    actualCdpPort = connection.cdpPort;
    console.log("[BrowserModes] FULL mode: Connected to user's Chrome via CDP");
  } else {
    // Fallback: Launch new Chrome with CDP (not ideal but functional)
    console.log("[BrowserModes] FULL mode: CDP not available, launching new Chrome with user-data-dir");

    const { execSync } = await import("child_process");
    const path = await import("path");
    const fs = await import("fs");

    const userDataDir = path.join(
      process.env.HOME || "/tmp",
      ".agent-os",
      "chrome-profile",
      platform,
      username
    );

    // Ensure profile dir exists
    if (!fs.existsSync(userDataDir)) {
      fs.mkdirSync(userDataDir, { recursive: true });
    }

    actualCdpPort = cdpPort || 9300 + Math.floor(Math.random() * 100);

    const fingerprint = generateFingerprint();
    const launchArgs = [
      `--remote-debugging-port=${actualCdpPort}`,
      `--window-size=${fingerprint.screenWidth},${fingerprint.screenHeight}`,
      "--disable-blink-features=AutomationControlled",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-infobars",
      "--disable-background-networking",
    ];

    try {
      // Use launchPersistentContext for user-data-dir support
      context = await pw.chromium.launchPersistentContext(userDataDir, {
        headless: !process.env.DISPLAY,
        args: process.env.DISPLAY ? launchArgs : [...launchArgs, "--headless=new"],
        userAgent: fingerprint.userAgent,
        viewport: { width: fingerprint.availWidth, height: fingerprint.availHeight },
        screen: { width: fingerprint.screenWidth, height: fingerprint.screenHeight },
        locale: "en-US",
        timezoneId: fingerprint.timezone,
      });
      browser = context.browser();
      page = context.pages()[0] || await context.newPage();
      cdpSession = await context.newCDPSession(page);
    } catch (launchErr: any) {
      // Last resort: fallback to LIGHT mode
      console.log("[BrowserModes] FULL mode launch failed, falling back to LIGHT mode:", launchErr.message);
      return launchLightSession(platform, username, stateId);
    }

    // Inject stealth scripts
    const stealthScript = getMasterStealthScript(fingerprint);
    await cdpSession.send("Page.addScriptToEvaluateOnNewDocument", {
      source: stealthScript,
    });
  }

  return {
    sessionId: randomUUID(),
    mode: "full",
    platform,
    username,
    stateId,
    taskCategory: "custom",
    browser,
    context,
    page,
    cdpSession,
    cdpPort: actualCdpPort,
    fingerprint,
    createdAt: new Date().toISOString(),
    lastActivity: new Date().toISOString(),
    memoryEstimateMB: 400,
    idleTimer: null,
    taskComplete: false,
    handover: {
      active: false,
      reason: "",
      startedAt: null,
      sseClients: new Set(),
      screenshotInterval: null,
    },
  };
}

/**
 * Launch a LIGHT mode session (headless + quick scrape + auto-close)
 */
async function launchLightSession(
  platform: string,
  username: string,
  stateId: string
): Promise<SmartSession> {
  const pw = await getPlaywright();
  const fingerprint = generateFingerprint();

  const launchArgs = [
    `--window-size=${fingerprint.screenWidth},${fingerprint.screenHeight}`,
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-sync",
    "--disable-translate",
    "--metrics-recording-only",
    "--headless=new",
    `--user-agent=${fingerprint.userAgent}`,
  ];

  const browser = await pw.chromium.launch({
    headless: true,
    args: launchArgs,
  });

  const context = await browser.newContext({
    userAgent: fingerprint.userAgent,
    viewport: { width: fingerprint.availWidth, height: fingerprint.availHeight },
    screen: { width: fingerprint.screenWidth, height: fingerprint.screenHeight },
    locale: "en-US",
    timezoneId: fingerprint.timezone,
    deviceScaleFactor: fingerprint.pixelRatio,
    ignoreHTTPSErrors: true,
  });

  const page = await context.newPage();
  const cdpSession = await context.newCDPSession(page);

  // Inject stealth scripts for basic bot detection evasion (dual-layer: CDP + initScript)
  const stealthScript = getMasterStealthScript(fingerprint);
  await cdpSession.send("Page.addScriptToEvaluateOnNewDocument", {
    source: stealthScript,
  });
  // Also inject via context.addInitScript as fallback (works better in headless=new)
  await context.addInitScript(stealthScript);

  console.log("[BrowserModes] LIGHT mode: Launched headless browser for quick task");

  return {
    sessionId: randomUUID(),
    mode: "light",
    platform,
    username,
    stateId,
    taskCategory: "custom",
    browser,
    context,
    page,
    cdpSession,
    cdpPort: 0, // No CDP port exposed
    fingerprint,
    createdAt: new Date().toISOString(),
    lastActivity: new Date().toISOString(),
    memoryEstimateMB: 60,
    idleTimer: null,
    taskComplete: false,
    handover: {
      active: false,
      reason: "",
      startedAt: null,
      sseClients: new Set(),
      screenshotInterval: null,
    },
  };
}

/**
 * Launch a GHOST mode session (API-only, no browser)
 */
function launchGhostSession(
  platform: string,
  username: string,
  stateId: string
): SmartSession {
  console.log("[BrowserModes] GHOST mode: No browser needed, API-only");

  return {
    sessionId: randomUUID(),
    mode: "ghost",
    platform,
    username,
    stateId,
    taskCategory: "custom",
    browser: null,
    context: null,
    page: null,
    cdpSession: null,
    cdpPort: 0,
    fingerprint: null,
    createdAt: new Date().toISOString(),
    lastActivity: new Date().toISOString(),
    memoryEstimateMB: 0,
    idleTimer: null,
    taskComplete: false,
    handover: {
      active: false,
      reason: "",
      startedAt: null,
      sseClients: new Set(),
      screenshotInterval: null,
    },
  };
}

/**
 * Main entry: Launch a smart session with the appropriate mode
 */
export async function launchSmartSession(
  taskCategory: TaskCategory,
  platform: string,
  username: string,
  options?: {
    stateId?: string;
    cdpPort?: number;
    forceMode?: BrowserMode;
    url?: string;
  }
): Promise<{ session: SmartSession; decision: ModeDecision }> {
  const decision = decideMode(
    taskCategory,
    platform,
    options?.url,
    options?.forceMode
  );

  const stateId = options?.stateId || randomUUID();

  let session: SmartSession;

  switch (decision.mode) {
    case "full":
      session = await launchFullSession(
        platform,
        username,
        stateId,
        options?.cdpPort
      );
      break;
    case "light":
      session = await launchLightSession(platform, username, stateId);
      break;
    case "ghost":
      session = launchGhostSession(platform, username, stateId);
      break;
    default:
      session = launchGhostSession(platform, username, stateId);
  }

  session.taskCategory = taskCategory;

  return { session, decision };
}

/**
 * Close a smart session, freeing all resources
 */
export async function closeSmartSession(session: SmartSession): Promise<void> {
  // Clear idle timer
  if (session.idleTimer) {
    clearTimeout(session.idleTimer);
    session.idleTimer = null;
  }

  // Stop handover streaming
  if (session.handover.screenshotInterval) {
    clearInterval(session.handover.screenshotInterval);
    session.handover.screenshotInterval = null;
  }

  // Close SSE clients
  for (const client of session.handover.sseClients) {
    try { client.end(); } catch (e) { console.warn('[BrowserModes] Failed to close SSE client:', e); }
  }
  session.handover.sseClients.clear();

  // Close browser resources (skip for ghost mode and CDP connections)
  if (session.mode !== "ghost" && session.browser) {
    if (session.mode === "light") {
      // Light mode: close everything immediately
      try { await session.context.close(); } catch (e) { console.warn(`[BrowserModes] Failed to close context for LIGHT session ${session.sessionId}:`, e); }
      try { await session.browser.close(); } catch (e) { console.warn(`[BrowserModes] Failed to close browser for LIGHT session ${session.sessionId}:`, e); }
      console.log(`[BrowserModes] LIGHT session ${session.sessionId} closed, memory freed`);
    } else if (session.mode === "full") {
      // Full mode (CDP): only close our context, don't close the user's Chrome
      try {
        // Check if browser is connected via CDP (not launched by us)
        const browserUrl = session.browser._initializer?.url || "";
        if (browserUrl.includes("9222") || browserUrl.includes("cdp")) {
          // CDP connection — don't close the browser, just our page
          // But we should close the page we created if we created one
          console.log(`[BrowserModes] FULL session ${session.sessionId}: keeping Chrome alive (CDP)`);
        } else {
          // We launched this browser, close it
          try { await session.context.close(); } catch (e) { console.warn(`[BrowserModes] Failed to close context for FULL session ${session.sessionId}:`, e); }
          try { await session.browser.close(); } catch (e) { console.warn(`[BrowserModes] Failed to close browser for FULL session ${session.sessionId}:`, e); }
          console.log(`[BrowserModes] FULL session ${session.sessionId} closed`);
        }
      } catch {
        // If we can't determine, try closing context only
        try { await session.context.close(); } catch (e) { console.warn(`[BrowserModes] Fallback context close failed for FULL session ${session.sessionId}:`, e); }
      }
    }
  }

  session.taskComplete = true;
}
