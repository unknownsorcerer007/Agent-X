/**
 * state-manager.ts — Dual-Layer Session State Persistence
 *
 * Layer 1 (Primary): Chrome native profile (--user-data-dir)
 *   - Handles cookies, localStorage, IndexedDB, extensions, passwords
 *   - Preserved automatically across Chrome restarts
 *   - Zero extraction overhead
 *
 * Layer 2 (Secondary): Agent-OS local extraction
 *   - Explicit extraction of cookies, localStorage, IndexedDB
 *   - Saved as JSON files for backup/cross-session recovery
 *   - Used when Chrome profile is lost or on different machine
 *
 * What we save: Cookies, localStorage, IndexedDB, current URL, auth status
 * What we SKIP: sessionStorage (tab-specific, not shared), browser cache (volatile)
 */

import * as fs from "fs";
import * as path from "path";

// Configurable state directory via BROWSER_STATES_DIR env var
const STATE_DIR = process.env.BROWSER_STATES_DIR ||
  path.join(process.env.HOME || "/tmp", ".agent-os", "browser-states");
const STATE_VERSION = 3; // v3: dual-layer, skip sessionStorage/cache

export interface BrowserState {
  version: number;
  platform: string;
  username: string;
  savedAt: string;
  source: "chrome_profile" | "local_extraction" | "hybrid";
  cookies: Array<{
    name: string;
    value: string;
    domain: string;
    path: string;
    expires: number;
    httpOnly: boolean;
    secure: boolean;
    sameSite: string;
    priority?: string;
    sameParty?: boolean;
    sourceScheme?: string;
    sourcePort?: number;
  }>;
  localStorage: Record<string, string>;
  // NOT saving sessionStorage — it's tab-specific, not shared across tabs
  indexedDB: Record<string, Array<{ key: string; value: any }>>;
  // NOT saving cacheUrls — volatile, re-fetched automatically
  url: string;
  title: string;
  authStatus: {
    isAuthenticated: boolean;
    authCookieNames: string[];
    detectedAt: string;
  };
  chromeProfile: {
    userDataDir: string;
    hasProfile: boolean;
  };
}

// ─── Platform Auth Cookie Indicators ─────────────────────────────────────────

const AUTH_COOKIES: Record<string, string[]> = {
  instagram: ["sessionid", "ds_user_id"],
  twitter: ["auth_token", "ct0"],
  x: ["auth_token", "ct0"],
  facebook: ["c_user", "fr", "sb"],
  linkedin: ["li_at", "JSESSIONID"],
  gmail: ["SID", "HSID", "SSID"],
  google: ["SID", "HSID", "SSID"],
  github: ["_gh_sess", "logged_in"],
  reddit: ["reddit_session", "token_v2"],
  tiktok: ["sessionid", "sid_tt"],
  youtube: ["SID", "HSID", "APISID"],
  amazon: ["session-id", "ubid-main"],
  default: ["session", "sessionid", "auth_token", "token"],
};

function getAuthCookiesForPlatform(platform: string): string[] {
  return AUTH_COOKIES[platform] || AUTH_COOKIES.default;
}

function detectAuthStatus(
  cookies: Array<{ name: string }>,
  platform: string
): { isAuthenticated: boolean; authCookieNames: string[] } {
  const authCookieNames = getAuthCookiesForPlatform(platform);
  const found = cookies
    .filter((c) => authCookieNames.includes(c.name))
    .map((c) => c.name);

  return {
    isAuthenticated: found.length > 0,
    authCookieNames: found,
  };
}

// ─── Path Helpers ────────────────────────────────────────────────────────────

function getStatePath(platform: string, username: string): string {
  return path.join(STATE_DIR, platform, `${username}.json`);
}

function ensureDir(filePath: string): void {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

// ─── State Version Migration ─────────────────────────────────────────────────

/**
 * Migrate a loaded state object to the current version.
 * v1→v2: Add version field, add savedAt timestamp
 * v2→v3: Add isAuthenticated field, restructure cookies array
 *
 * Throws an error if the state version cannot be migrated.
 */
function migrateState(rawState: any): BrowserState {
  const version = rawState.version || 1;

  if (version === STATE_VERSION) {
    return rawState as BrowserState;
  }

  if (version > STATE_VERSION) {
    throw new Error(
      `[StateManager] State version v${version} is newer than current v${STATE_VERSION}. ` +
      `Cannot load state from a newer version. Please update the browser engine.`
    );
  }

  let state = { ...rawState };

  // v1→v2: Add version field and savedAt timestamp
  if ((state.version || 1) < 2) {
    console.log("[StateManager] Migrating state v1→v2: adding version field and savedAt timestamp");
    state.version = 2;
    if (!state.savedAt) {
      state.savedAt = new Date().toISOString();
    }
  }

  // v2→v3: Add isAuthenticated field, restructure cookies array
  if (state.version < 3) {
    console.log("[StateManager] Migrating state v2→v3: adding authStatus and restructuring cookies");

    // Restructure cookies: v2 cookies may be a flat array of { name, value }
    // v3 expects full cookie objects with domain, path, etc.
    if (Array.isArray(state.cookies)) {
      state.cookies = state.cookies.map((c: any) => {
        // If cookie is already a full object, keep it
        if (c.domain !== undefined) return c;
        // Otherwise, restructure from v2 flat format
        return {
          name: c.name || "",
          value: c.value || "",
          domain: c.domain || "",
          path: c.path || "/",
          expires: c.expires || 0,
          httpOnly: c.httpOnly || false,
          secure: c.secure || false,
          sameSite: c.sameSite || "Lax",
        };
      });
    }

    // Add authStatus if missing
    if (!state.authStatus) {
      const platform = state.platform || "default";
      const authResult = detectAuthStatus(state.cookies || [], platform);
      state.authStatus = {
        isAuthenticated: authResult.isAuthenticated,
        authCookieNames: authResult.authCookieNames,
        detectedAt: new Date().toISOString(),
      };
    } else if (state.authStatus.isAuthenticated === undefined) {
      // Ensure isAuthenticated field exists even if authStatus was partially present
      const platform = state.platform || "default";
      const authResult = detectAuthStatus(state.cookies || [], platform);
      state.authStatus.isAuthenticated = authResult.isAuthenticated;
      if (!state.authStatus.authCookieNames) {
        state.authStatus.authCookieNames = authResult.authCookieNames;
      }
      if (!state.authStatus.detectedAt) {
        state.authStatus.detectedAt = new Date().toISOString();
      }
    }

    // Ensure chromeProfile exists
    if (!state.chromeProfile) {
      state.chromeProfile = {
        userDataDir: "",
        hasProfile: false,
      };
    }

    // Ensure source exists
    if (!state.source) {
      state.source = "local_extraction";
    }

    state.version = 3;
  }

  // Final validation: ensure all required v3 fields exist
  if (!state.version || !state.savedAt || !state.authStatus ||
      state.authStatus.isAuthenticated === undefined ||
      !Array.isArray(state.cookies)) {
    throw new Error(
      `[StateManager] State migration from v${version} to v${STATE_VERSION} failed: ` +
      `required fields are missing after migration. ` +
      `Missing: ${[
        !state.version && "version",
        !state.savedAt && "savedAt",
        (!state.authStatus || state.authStatus.isAuthenticated === undefined) && "authStatus.isAuthenticated",
        !Array.isArray(state.cookies) && "cookies",
      ].filter(Boolean).join(", ")}. ` +
      `Cannot load incompatible state.`
    );
  }

  return state as BrowserState;
}

// ─── Save State ──────────────────────────────────────────────────────────────

/**
 * Save complete browser state from a CDP session
 * Dual-layer: extracts from browser + notes if Chrome profile exists
 *
 * Returns saved state summary for callers that need to inspect the result.
 */
export async function saveState(
  cdpSession: any,
  page: any,
  platform: string,
  username: string,
  chromeProfileDir?: string
): Promise<{ cookieCount: number; isAuthenticated: boolean; savedAt: string; hasLocalStorage: boolean; hasIndexedDB: boolean }> {
  // Get cookies via CDP
  const { cookies } = await cdpSession.send("Network.getAllCookies");

  // Get localStorage (shared across tabs for the origin)
  const localStorageData = await page.evaluate(() => {
    const data: Record<string, string> = {};
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key) {
        data[key] = localStorage.getItem(key) || "";
      }
    }
    return data;
  }).catch((err: any) => {
    console.warn("[StateManager] Failed to extract localStorage, defaulting to empty:", err?.message || err);
    return {};
  });

  // Get IndexedDB data
  const indexedDBData = await page.evaluate(async () => {
    const data: Record<string, Array<{ key: string; value: any }>> = {};
    try {
      const databases = await indexedDB.databases();
      for (const dbInfo of databases) {
        if (!dbInfo.name) continue;
        try {
          const db = await new Promise<IDBDatabase>((resolve, reject) => {
            const req = indexedDB.open(dbInfo.name!);
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
          });

          const stores: Array<{ key: string; value: any }> = [];
          for (const storeName of Array.from(db.objectStoreNames)) {
            try {
              const tx = db.transaction(storeName, "readonly");
              const store = tx.objectStore(storeName);
              const allReq = store.getAll();
              const allKeysReq = store.getAllKeys();

              const [values, keys] = await Promise.all([
                new Promise<any[]>((resolve, reject) => {
                  allReq.onsuccess = () => resolve(allReq.result);
                  allReq.onerror = () => reject(allReq.error);
                }),
                new Promise<any[]>((resolve, reject) => {
                  allKeysReq.onsuccess = () => resolve(allKeysReq.result);
                  allKeysReq.onerror = () => reject(allKeysReq.error);
                }),
              ]);

              for (let i = 0; i < keys.length; i++) {
                try {
                  stores.push({
                    key: String(keys[i]),
                    value: values[i],
                  });
                } catch (storeItemErr: any) {
                  console.warn(`[StateManager] Failed to serialize IndexedDB key "${keys[i]}", storing null:`, storeItemErr?.message || storeItemErr);
                  stores.push({ key: String(keys[i]), value: null });
                }
              }
            } catch (storeErr: any) {
              console.warn(`[StateManager] Skipping IndexedDB store "${storeName}" that can't be read:`, storeErr?.message || storeErr);
            }
          }
          data[dbInfo.name] = stores;
          db.close();
        } catch (dbErr: any) {
          console.warn(`[StateManager] Skipping IndexedDB database "${dbInfo.name}" that can't be opened:`, dbErr?.message || dbErr);
        }
      }
    } catch (databasesErr: any) {
      console.warn("[StateManager] indexedDB.databases() not available or failed:", databasesErr?.message || databasesErr);
    }
    return data;
  }).catch((err: any) => {
    console.warn("[StateManager] Failed to extract IndexedDB, defaulting to empty:", err?.message || err);
    return {};
  });

  const url = page.url();
  const title = await page.title().catch((err: any) => {
    console.warn("[StateManager] Failed to get page title, defaulting to empty:", err?.message || err);
    return "";
  });

  // Detect auth status from cookies
  const authStatus = detectAuthStatus(cookies, platform);

  // Determine save source
  let source: "chrome_profile" | "local_extraction" | "hybrid" = "local_extraction";
  let hasChromeProfile = false;

  if (chromeProfileDir) {
    hasChromeProfile = fs.existsSync(chromeProfileDir);
    if (hasChromeProfile && cookies.length > 0) {
      source = "hybrid";
    } else if (hasChromeProfile) {
      source = "chrome_profile";
    }
  }

  const state: BrowserState = {
    version: STATE_VERSION,
    platform,
    username,
    savedAt: new Date().toISOString(),
    source,
    cookies,
    localStorage: localStorageData,
    indexedDB: indexedDBData,
    url,
    title,
    authStatus: {
      ...authStatus,
      detectedAt: new Date().toISOString(),
    },
    chromeProfile: {
      userDataDir: chromeProfileDir || "",
      hasProfile: hasChromeProfile,
    },
  };

  const filePath = getStatePath(platform, username);
  ensureDir(filePath);
  fs.writeFileSync(filePath, JSON.stringify(state, null, 2));

  console.log(
    `[StateManager] Saved ${source} state for ${platform}/${username} ` +
    `(${cookies.length} cookies, ${Object.keys(localStorageData).length} localStorage, ` +
    `auth: ${authStatus.isAuthenticated ? "YES" : "NO"})`
  );

  return {
    cookieCount: cookies.length,
    isAuthenticated: authStatus.isAuthenticated,
    savedAt: state.savedAt,
    hasLocalStorage: Object.keys(localStorageData).length > 0,
    hasIndexedDB: Object.keys(indexedDBData).length > 0,
  };
}

// ─── Load State ──────────────────────────────────────────────────────────────

/**
 * Load browser state into a CDP session
 * Restores: cookies, localStorage, IndexedDB
 * Skips: sessionStorage, cache
 */
export async function loadState(
  cdpSession: any,
  page: any,
  platform: string,
  username: string
): Promise<boolean> {
  const filePath = getStatePath(platform, username);

  if (!fs.existsSync(filePath)) {
    console.log(`[StateManager] No saved state found for ${platform}/${username}`);
    return false;
  }

  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const rawState = JSON.parse(raw);

    // Handle version migration — throws on incompatible state
    const state = migrateState(rawState);

    // Set cookies via CDP
    if (state.cookies && state.cookies.length > 0) {
      await cdpSession.send("Network.setCookies", {
        cookies: state.cookies.map((c) => ({
          name: c.name,
          value: c.value,
          domain: c.domain,
          path: c.path || "/",
          expires: c.expires,
          httpOnly: c.httpOnly,
          secure: c.secure,
          sameSite: (c.sameSite as any) || "Lax",
          priority: (c.priority as any) || "Medium",
          sameParty: c.sameParty || false,
          sourceScheme: (c.sourceScheme as any) || "Unset",
          sourcePort: c.sourcePort,
        })),
      });
    }

    // Navigate to the domain first (needed for localStorage/IndexedDB)
    if (state.url) {
      await page.goto(state.url, { waitUntil: "domcontentloaded", timeout: 15000 }).catch((err: any) => {
        console.warn(`[StateManager] Failed to navigate to saved URL "${state.url}" during state load:`, err?.message || err);
      });
    }

    // Restore localStorage
    if (state.localStorage && Object.keys(state.localStorage).length > 0) {
      await page.evaluate((data) => {
        for (const [key, value] of Object.entries(data)) {
          try {
            localStorage.setItem(key, value as string);
          } catch (lsErr: any) {
            console.warn(`[StateManager] Failed to set localStorage key "${key}":`, lsErr?.message || lsErr);
          }
        }
      }, state.localStorage);
    }

    // Restore IndexedDB
    if (state.indexedDB && Object.keys(state.indexedDB).length > 0) {
      await page.evaluate(async (databases) => {
        for (const [dbName, stores] of Object.entries(databases)) {
          if (!Array.isArray(stores)) continue;
          try {
            const db = await new Promise<IDBDatabase>((resolve, reject) => {
              const req = indexedDB.open(dbName);
              req.onupgradeneeded = () => {
                const d = req.result;
                if (!d.objectStoreNames.contains("data")) {
                  d.createObjectStore("data", { keyPath: "key" });
                }
              };
              req.onsuccess = () => resolve(req.result);
              req.onerror = () => reject(req.error);
            });

            for (const item of stores) {
              try {
                const tx = db.transaction("data", "readwrite");
                const store = tx.objectStore("data");
                store.put(item);
                await new Promise<void>((resolve, reject) => {
                  tx.oncomplete = () => resolve();
                  tx.onerror = () => reject(tx.error);
                });
              } catch (itemErr: any) {
                console.warn(`[StateManager] Failed to write IndexedDB item in "${dbName}":`, itemErr?.message || itemErr);
              }
            }
            db.close();
          } catch (dbErr: any) {
            console.warn(`[StateManager] Failed to open/create IndexedDB "${dbName}" for restoration:`, dbErr?.message || dbErr);
          }
        }
      }, state.indexedDB).catch((err: any) => {
        console.warn("[StateManager] Failed to restore IndexedDB data:", err?.message || err);
      });
    }

    console.log(
      `[StateManager] Loaded state for ${platform}/${username} ` +
      `(${state.cookies?.length || 0} cookies, ${Object.keys(state.localStorage || {}).length} localStorage, ` +
      `source: ${state.source || "unknown"})`
    );

    return true;
  } catch (err) {
    console.error(`[StateManager] Error loading state:`, err);
    return false;
  }
}

// ─── List / Delete ───────────────────────────────────────────────────────────

export function listStates(): Array<{
  platform: string;
  username: string;
  savedAt: string;
  url: string;
  cookieCount: number;
  isAuthenticated: boolean;
  source: string;
}> {
  const results: Array<{
    platform: string;
    username: string;
    savedAt: string;
    url: string;
    cookieCount: number;
    isAuthenticated: boolean;
    source: string;
  }> = [];

  if (!fs.existsSync(STATE_DIR)) {
    return results;
  }

  const platforms = fs.readdirSync(STATE_DIR);
  for (const platform of platforms) {
    const platformDir = path.join(STATE_DIR, platform);
    if (!fs.statSync(platformDir).isDirectory()) continue;

    const files = fs.readdirSync(platformDir);
    for (const file of files) {
      if (!file.endsWith(".json")) continue;

      try {
        const raw = fs.readFileSync(path.join(platformDir, file), "utf-8");
        const state: BrowserState = JSON.parse(raw);
        results.push({
          platform: state.platform,
          username: state.username,
          savedAt: state.savedAt,
          url: state.url || "",
          cookieCount: state.cookies?.length || 0,
          isAuthenticated: state.authStatus?.isAuthenticated || false,
          source: state.source || "unknown",
        });
      } catch (err: any) {
        console.warn(`[StateManager] Failed to parse state file ${path.join(platform, file)}:`, err?.message || err);
      }
    }
  }

  return results;
}

export function deleteState(platform: string, username: string): boolean {
  const filePath = getStatePath(platform, username);

  if (!fs.existsSync(filePath)) {
    return false;
  }

  fs.unlinkSync(filePath);
  console.log(`[StateManager] Deleted state for ${platform}/${username}`);
  return true;
}

/**
 * Check if a platform has authenticated state saved.
 * Returns an object indicating existence and auth status.
 * On parse error, returns { exists: true, error: true, errorMessage: "..." }
 * rather than misleadingly returning { exists: false }.
 */
export function hasAuthState(platform: string, username: string): {
  exists: boolean;
  isAuthenticated: boolean;
  error?: boolean;
  errorMessage?: string;
} {
  const filePath = getStatePath(platform, username);

  if (!fs.existsSync(filePath)) {
    return { exists: false, isAuthenticated: false };
  }

  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const state: BrowserState = JSON.parse(raw);
    return {
      exists: true,
      isAuthenticated: state.authStatus?.isAuthenticated || false,
    };
  } catch (err: any) {
    const errorMessage = err?.message || String(err);
    console.error(`[StateManager] Error parsing state file for hasAuthState(${platform}/${username}):`, errorMessage);
    return {
      exists: true,
      isAuthenticated: false,
      error: true,
      errorMessage,
    };
  }
}

/**
 * Get state info without loading full state.
 * On parse error, returns { exists: true, error: true, errorMessage: "..." }
 * rather than misleadingly returning { exists: false }.
 */
export function getStateInfo(platform: string, username: string): {
  exists: boolean;
  savedAt?: string;
  isAuthenticated?: boolean;
  source?: string;
  cookieCount?: number;
  hasChromeProfile?: boolean;
  error?: boolean;
  errorMessage?: string;
} {
  const filePath = getStatePath(platform, username);

  if (!fs.existsSync(filePath)) {
    return { exists: false };
  }

  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const state: BrowserState = JSON.parse(raw);
    return {
      exists: true,
      savedAt: state.savedAt,
      isAuthenticated: state.authStatus?.isAuthenticated,
      source: state.source,
      cookieCount: state.cookies?.length,
      hasChromeProfile: state.chromeProfile?.hasProfile,
    };
  } catch (err: any) {
    const errorMessage = err?.message || String(err);
    console.error(`[StateManager] Error parsing state file for getStateInfo(${platform}/${username}):`, errorMessage);
    return {
      exists: true,
      error: true,
      errorMessage,
    };
  }
}
