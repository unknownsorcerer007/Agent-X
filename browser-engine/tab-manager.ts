/**
 * tab-manager.ts — Auto Tab Management
 * Prevents device hang from too many open tabs by:
 * 1. Auto-closing tabs after task completion
 * 2. Idle timeout for inactive tabs
 * 3. Memory tracking and pressure alerts
 * 4. Tab pooling for LIGHT mode (reuse browser instance)
 */

// ─── Types ───────────────────────────────────────────────────────────────────

export interface TabInfo {
  tabId: string;
  sessionId: string;
  url: string;
  title: string;
  mode: "full" | "light" | "ghost";
  createdAt: string;
  lastActivity: string;
  memoryEstimateMB: number;
  idleSeconds: number;
  status: "active" | "idle" | "closing" | "closed";
}

export interface MemoryStats {
  totalEstimatedMB: number;
  activeTabs: number;
  idleTabs: number;
  fullModeTabs: number;
  lightModeTabs: number;
  ghostModeTabs: number;
  pressureLevel: "low" | "medium" | "high" | "critical";
  pressurePercent: number;
}

export interface TabManagerConfig {
  /** Maximum memory allowed in MB before triggering cleanup (default: 1024) */
  maxMemoryMB: number;
  /** Idle timeout in seconds before auto-closing LIGHT tabs (default: 30) */
  lightIdleTimeoutSec: number;
  /** Idle timeout in seconds before alerting about FULL tabs (default: 300) */
  fullIdleTimeoutSec: number;
  /** Maximum number of concurrent LIGHT mode tabs (default: 5) */
  maxLightTabs: number;
  /** Maximum number of concurrent FULL mode sessions (default: 3) */
  maxFullSessions: number;
  /** How often to check idle tabs in seconds (default: 10) */
  checkIntervalSec: number;
  /** Whether to auto-close idle LIGHT tabs (default: true) */
  autoCloseIdle: boolean;
}

// ─── Defaults ────────────────────────────────────────────────────────────────

const DEFAULT_CONFIG: TabManagerConfig = {
  maxMemoryMB: 1024,
  lightIdleTimeoutSec: 30,
  fullIdleTimeoutSec: 300,
  maxLightTabs: 5,
  maxFullSessions: 3,
  checkIntervalSec: 10,
  autoCloseIdle: true,
};

// ─── Tab Manager ─────────────────────────────────────────────────────────────

export class TabManager {
  private config: TabManagerConfig;
  private tabs: Map<string, TabInfo> = new Map();
  private sessions: Map<string, any> = new Map(); // sessionId → session object
  private checkInterval: NodeJS.Timeout | null = null;
  private onTabClose: ((tabId: string, sessionId: string) => Promise<void>) | null = null;

  constructor(
    config: Partial<TabManagerConfig> = {},
    onClose?: (tabId: string, sessionId: string) => Promise<void>
  ) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.onTabClose = onClose || null;
  }

  /**
   * Start the idle check loop
   */
  start(): void {
    if (this.checkInterval) return;

    this.checkInterval = setInterval(() => {
      this.checkIdleTabs();
    }, this.config.checkIntervalSec * 1000);

    console.log(`[TabManager] Started with check interval ${this.config.checkIntervalSec}s`);
  }

  /**
   * Stop the idle check loop
   */
  stop(): void {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }
    console.log("[TabManager] Stopped");
  }

  /**
   * Register a tab/session
   */
  registerTab(
    tabId: string,
    sessionId: string,
    mode: "full" | "light" | "ghost",
    url: string = "",
    title: string = "",
    memoryEstimateMB: number = 0
  ): void {
    const now = new Date().toISOString();
    this.tabs.set(tabId, {
      tabId,
      sessionId,
      url,
      title,
      mode,
      createdAt: now,
      lastActivity: now,
      memoryEstimateMB,
      idleSeconds: 0,
      status: "active",
    });
  }

  /**
   * Update tab activity (reset idle timer)
   */
  updateActivity(tabId: string, url?: string, title?: string): void {
    const tab = this.tabs.get(tabId);
    if (tab) {
      tab.lastActivity = new Date().toISOString();
      tab.idleSeconds = 0;
      tab.status = "active";
      if (url) tab.url = url;
      if (title) tab.title = title;
    }
  }

  /**
   * Mark a tab as task complete (triggers close for LIGHT mode)
   */
  markTaskComplete(tabId: string): void {
    const tab = this.tabs.get(tabId);
    if (tab && tab.mode === "light") {
      tab.status = "closing";
      this.closeTab(tabId);
    } else if (tab) {
      // For FULL mode, just update activity
      tab.lastActivity = new Date().toISOString();
      tab.idleSeconds = 0;
    }
  }

  /**
   * Close a tab and free its resources
   */
  async closeTab(tabId: string): Promise<void> {
    const tab = this.tabs.get(tabId);
    if (!tab) return;

    tab.status = "closing";

    // Call the close handler if set
    if (this.onTabClose) {
      try {
        await this.onTabClose(tabId, tab.sessionId);
      } catch (err) {
        console.error(`[TabManager] Error closing tab ${tabId}:`, err);
      }
    }

    tab.status = "closed";
    this.tabs.delete(tabId);

    console.log(`[TabManager] Tab ${tabId} closed (was ${tab.mode} mode, ~${tab.memoryEstimateMB}MB freed)`);
  }

  /**
   * Check all tabs for idle timeout
   */
  private async checkIdleTabs(): Promise<void> {
    const now = Date.now();

    for (const [tabId, tab] of this.tabs) {
      if (tab.status !== "active") continue;

      const lastActivity = new Date(tab.lastActivity).getTime();
      const idleSeconds = Math.floor((now - lastActivity) / 1000);
      tab.idleSeconds = idleSeconds;

      // LIGHT mode: auto-close after idle timeout
      if (
        tab.mode === "light" &&
        this.config.autoCloseIdle &&
        idleSeconds >= this.config.lightIdleTimeoutSec
      ) {
        console.log(
          `[TabManager] LIGHT tab ${tabId} idle for ${idleSeconds}s, auto-closing`
        );
        await this.closeTab(tabId);
        continue;
      }

      // FULL mode: warn but don't auto-close (user may be using it)
      if (tab.mode === "full" && idleSeconds >= this.config.fullIdleTimeoutSec) {
        console.warn(
          `[TabManager] FULL session ${tabId} idle for ${idleSeconds}s (${Math.floor(idleSeconds / 60)}min), consider closing`
        );
      }
    }

    // Check memory pressure
    const stats = this.getMemoryStats();
    if (stats.pressureLevel === "critical") {
      console.error(
        `[TabManager] CRITICAL memory pressure: ${stats.totalEstimatedMB}MB / ${this.config.maxMemoryMB}MB`
      );
      // Force close oldest LIGHT tabs
      await this.forceCleanup();
    } else if (stats.pressureLevel === "high") {
      console.warn(
        `[TabManager] HIGH memory pressure: ${stats.totalEstimatedMB}MB / ${this.config.maxMemoryMB}MB`
      );
    }
  }

  /**
   * Force cleanup of oldest LIGHT mode tabs
   */
  async forceCleanup(): Promise<number> {
    const lightTabs = Array.from(this.tabs.values())
      .filter((t) => t.mode === "light" && t.status === "active")
      .sort((a, b) => new Date(a.lastActivity).getTime() - new Date(b.lastActivity).getTime());

    let closed = 0;
    for (const tab of lightTabs) {
      await this.closeTab(tab.tabId);
      closed++;

      // Check if we've freed enough
      const stats = this.getMemoryStats();
      if (stats.pressureLevel !== "critical") break;
    }

    return closed;
  }

  /**
   * Get current memory statistics
   */
  getMemoryStats(): MemoryStats {
    const activeTabs = Array.from(this.tabs.values()).filter(
      (t) => t.status === "active"
    );

    const totalMB = activeTabs.reduce((sum, t) => sum + t.memoryEstimateMB, 0);
    const pressurePercent = Math.round((totalMB / this.config.maxMemoryMB) * 100);

    let pressureLevel: "low" | "medium" | "high" | "critical";
    if (pressurePercent < 50) pressureLevel = "low";
    else if (pressurePercent < 75) pressureLevel = "medium";
    else if (pressurePercent < 90) pressureLevel = "high";
    else pressureLevel = "critical";

    return {
      totalEstimatedMB: totalMB,
      activeTabs: activeTabs.filter((t) => t.idleSeconds < 30).length,
      idleTabs: activeTabs.filter((t) => t.idleSeconds >= 30).length,
      fullModeTabs: activeTabs.filter((t) => t.mode === "full").length,
      lightModeTabs: activeTabs.filter((t) => t.mode === "light").length,
      ghostModeTabs: activeTabs.filter((t) => t.mode === "ghost").length,
      pressureLevel,
      pressurePercent,
    };
  }

  /**
   * Get all tab info
   */
  getAllTabs(): TabInfo[] {
    return Array.from(this.tabs.values());
  }

  /**
   * Get a specific tab
   */
  getTab(tabId: string): TabInfo | undefined {
    return this.tabs.get(tabId);
  }

  /**
   * Check if we can launch a new session of a given mode
   */
  canLaunch(mode: "full" | "light" | "ghost"): { allowed: boolean; reason?: string } {
    const stats = this.getMemoryStats();

    if (stats.pressureLevel === "critical") {
      return { allowed: false, reason: "Memory pressure is critical, close existing sessions first" };
    }

    if (mode === "full" && stats.fullModeTabs >= this.config.maxFullSessions) {
      return { allowed: false, reason: `Maximum FULL mode sessions reached (${this.config.maxFullSessions})` };
    }

    if (mode === "light" && stats.lightModeTabs >= this.config.maxLightTabs) {
      return { allowed: false, reason: `Maximum LIGHT mode tabs reached (${this.config.maxLightTabs})` };
    }

    // Check memory budget
    const modeMemory = mode === "full" ? 400 : mode === "light" ? 60 : 0;
    if (stats.totalEstimatedMB + modeMemory > this.config.maxMemoryMB) {
      return { allowed: false, reason: `Insufficient memory budget (${stats.totalEstimatedMB}MB used, ${this.config.maxMemoryMB}MB max)` };
    }

    return { allowed: true };
  }

  /**
   * Destroy all tabs and cleanup
   */
  async destroyAll(): Promise<void> {
    this.stop();
    for (const [tabId] of this.tabs) {
      await this.closeTab(tabId);
    }
    this.tabs.clear();
  }
}
