/**
 * browser-utils.ts — Shared utilities for Browser Engine
 * Extracted from index.ts and browser-modes.ts to avoid duplication.
 */

let playwrightModule: any = null;

/**
 * Lazy-load the Playwright module (shared singleton).
 * Used by both index.ts (legacy browser launch) and browser-modes.ts (smart sessions).
 */
export async function getPlaywright() {
  if (!playwrightModule) {
    playwrightModule = await import("playwright");
  }
  return playwrightModule;
}
