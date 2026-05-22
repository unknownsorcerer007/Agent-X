/**
 * cdp-connector.ts — CDP Connection Module
 * Connects to user's real Chrome browser via Chrome DevTools Protocol.
 * Instead of launching a headless browser, we connect to the user's existing
 * Chrome instance running with --remote-debugging-port=9222.
 *
 * This solves:
 * - Headless detection (real Chrome = no detection)
 * - File upload failures (real file inputs work)
 * - Bot detection (user's real browser fingerprint)
 * - Cookie/session loss (--user-data-dir preserves everything)
 * - Extension support (user's extensions are available)
 */

import * as http from "http";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CDPConnectionConfig {
  /** Port the user's Chrome is listening on (default: 9222) */
  cdpPort: number;
  /** Host (default: localhost) */
  cdpHost: string;
  /** Optional user data dir path for --user-data-dir flag */
  userDataDir?: string;
  /** Timeout for connection attempts (ms, default: 10000) */
  connectionTimeout: number;
  /** Whether to auto-discover Chrome on common ports */
  autoDiscover: boolean;
}

export interface CDPTarget {
  id: string;
  type: string;
  title: string;
  url: string;
  webSocketDebuggerUrl: string;
}

export interface CDPVersion {
  Browser: string;
  "Protocol-Version": string;
  "User-Agent": string;
  "V8-Version": string;
  "WebKit-Version": string;
}

export interface CDPConnectionResult {
  connected: boolean;
  cdpPort: number;
  version: CDPVersion | null;
  targets: CDPTarget[];
  error?: string;
}

export interface ChromeLaunchInstruction {
  command: string;
  args: string[];
  userDataDir: string;
}

// ─── Default Config ──────────────────────────────────────────────────────────

const DEFAULT_CONFIG: CDPConnectionConfig = {
  cdpPort: 9222,
  cdpHost: "localhost",
  connectionTimeout: 10000,
  autoDiscover: true,
};

// Common ports to check for Chrome CDP
const CDP_PORTS = [9222, 9229, 9333, 9224, 9225];

// ─── CDP Discovery ───────────────────────────────────────────────────────────

/**
 * Fetch JSON from CDP endpoint
 */
function fetchCDPJson(host: string, port: number, path: string): Promise<any> {
  return new Promise((resolve, reject) => {
    const timeout = 5000;
    const req = http.get(
      `http://${host}:${port}/json${path}`,
      { timeout },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          try {
            const body = Buffer.concat(chunks).toString("utf-8");
            resolve(JSON.parse(body));
          } catch (err) {
            reject(new Error(`Invalid JSON from CDP: ${body.substring(0, 200)}`));
          }
        });
      }
    );
    req.on("error", (err) => reject(err));
    req.on("timeout", () => {
      req.destroy();
      reject(new Error(`Connection timeout to ${host}:${port}`));
    });
  });
}

/**
 * Check if Chrome CDP is available on a specific port
 */
export async function checkCDPPort(
  host: string = "localhost",
  port: number = 9222
): Promise<boolean> {
  try {
    await fetchCDPJson(host, port, "/version");
    return true;
  } catch {
    return false;
  }
}

/**
 * Discover Chrome CDP on common ports
 */
export async function discoverCDPPort(
  host: string = "localhost"
): Promise<number | null> {
  const results = await Promise.allSettled(
    CDP_PORTS.map((port) => checkCDPPort(host, port))
  );

  for (let i = 0; i < results.length; i++) {
    if (results[i].status === "fulfilled" && results[i].value) {
      return CDP_PORTS[i];
    }
  }
  return null;
}

/**
 * Get Chrome version info via CDP
 */
export async function getChromeVersion(
  host: string = "localhost",
  port: number = 9222
): Promise<CDPVersion | null> {
  try {
    const version = await fetchCDPJson(host, port, "/version");
    return version as CDPVersion;
  } catch {
    return null;
  }
}

/**
 * Get all CDP targets (tabs/pages)
 */
export async function getCDPTargets(
  host: string = "localhost",
  port: number = 9222
): Promise<CDPTarget[]> {
  try {
    const targets = await fetchCDPJson(host, port, "/list");
    return targets.filter((t: any) => t.type === "page");
  } catch {
    return [];
  }
}

/**
 * Full CDP connection check with discovery
 */
export async function connectToCDP(
  config: Partial<CDPConnectionConfig> = {}
): Promise<CDPConnectionResult> {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  let port = cfg.cdpPort;

  // If auto-discover is enabled, try to find Chrome
  if (cfg.autoDiscover) {
    const discoveredPort = await discoverCDPPort(cfg.cdpHost);
    if (discoveredPort) {
      port = discoveredPort;
    }
  }

  // Try to connect
  const available = await checkCDPPort(cfg.cdpHost, port);
  if (!available) {
    return {
      connected: false,
      cdpPort: port,
      version: null,
      targets: [],
      error: `Chrome not found on port ${port}. Launch Chrome with: google-chrome --remote-debugging-port=${port} --user-data-dir="$HOME/.agent-os/chrome-profile"`,
    };
  }

  // Get version and targets
  const [version, targets] = await Promise.all([
    getChromeVersion(cfg.cdpHost, port),
    getCDPTargets(cfg.cdpHost, port),
  ]);

  return {
    connected: true,
    cdpPort: port,
    version,
    targets,
  };
}

/**
 * Generate the Chrome launch instruction for the user
 */
export function getChromeLaunchInstruction(
  port: number = 9222,
  userDataDir?: string
): ChromeLaunchInstruction {
  const dir = userDataDir || `${process.env.HOME || "~"}/.agent-os/chrome-profile`;
  return {
    command: "google-chrome",
    args: [
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${dir}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--disable-infobars",
    ],
    userDataDir: dir,
  };
}

/**
 * Connect Playwright to existing Chrome via CDP
 * Returns the browser and first available page, or creates a new context
 */
export async function connectPlaywrightToCDP(
  playwrightModule: any,
  config: Partial<CDPConnectionConfig> = {}
): Promise<{
  browser: any;
  context: any;
  page: any;
  cdpSession: any;
  cdpPort: number;
} | null> {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const result = await connectToCDP(cfg);

  if (!result.connected) {
    console.error(`[CDPConnector] ${result.error}`);
    return null;
  }

  try {
    // Connect Playwright to the existing Chrome instance
    const browser = await playwrightModule.chromium.connectOverCDP(
      `http://${cfg.cdpHost}:${result.cdpPort}`
    );

    // Get existing contexts
    const contexts = browser.contexts();
    const context = contexts.length > 0 ? contexts[0] : await browser.newContext();

    // Get or create a page
    const pages = context.pages();
    const page = pages.length > 0 ? pages[0] : await context.newPage();

    // Get CDP session
    const cdpSession = await context.newCDPSession(page);

    console.log(
      `[CDPConnector] Connected to Chrome on port ${result.cdpPort}, ` +
      `Browser: ${result.version?.Browser || "unknown"}, ` +
      `Targets: ${result.targets.length}`
    );

    return {
      browser,
      context,
      page,
      cdpSession,
      cdpPort: result.cdpPort,
    };
  } catch (err: any) {
    console.error(`[CDPConnector] Failed to connect Playwright to CDP:`, err.message);
    return null;
  }
}
