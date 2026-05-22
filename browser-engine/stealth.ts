/**
 * stealth.ts — Anti-detection injection scripts
 * These scripts are injected BEFORE any page loads to prevent bot detection.
 * Each function returns a complete, self-contained JS string to be evaluated.
 */

/**
 * Master stealth script that combines all anti-detection measures.
 * This is injected via Page.addScriptToEvaluateOnNewDocument
 */
export function getMasterStealthScript(fingerprint: {
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
}): string {
  return `
(function() {
  'use strict';

  // =====================================================
  // 1. Override navigator.webdriver
  // =====================================================
  Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true
  });

  // Also delete the property from the prototype chain
  if (Navigator.prototype.hasOwnProperty('webdriver')) {
    Object.defineProperty(Navigator.prototype, 'webdriver', {
      get: () => undefined,
      configurable: true
    });
  }

  // =====================================================
  // 2. Mock chrome.runtime
  // =====================================================
  if (!window.chrome) {
    window.chrome = {};
  }
  if (!window.chrome.runtime) {
    window.chrome.runtime = {
      OnInstalledReason: {
        CHROME_UPDATE: 'chrome_update',
        INSTALL: 'install',
        SHARED_MODULE_UPDATE: 'shared_module_update',
        UPDATE: 'update'
      },
      OnRestartRequiredReason: {
        APP_UPDATE: 'app_update',
        OS_UPDATE: 'os_update',
        PERIODIC: 'periodic'
      },
      PlatformArch: {
        ARM: 'arm',
        ARM64: 'arm64',
        MIPS: 'mips',
        MIPS64: 'mips64',
        X86_32: 'x86-32',
        X86_64: 'x86-64'
      },
      PlatformNaclArch: {
        ARM: 'arm',
        MIPS: 'mips',
        MIPS64: 'mips64',
        X86_32: 'x86-32',
        X86_64: 'x86-64'
      },
      PlatformOs: {
        ANDROID: 'android',
        CROS: 'cros',
        LINUX: 'linux',
        MAC: 'mac',
        OPENBSD: 'openbsd',
        WIN: 'win'
      },
      RequestUpdateCheckStatus: {
        NO_UPDATE: 'no_update',
        THROTTLED: 'throttled',
        UPDATE_AVAILABLE: 'update_available'
      },
      connect: function() { return { onDisconnect: { addListener: function() {} }, onMessage: { addListener: function() {} }, postMessage: function() {}, disconnect: function() {} }; },
      sendMessage: function() {},
      id: undefined,
      getManifest: function() { return {}; },
      getURL: function(path) { return 'chrome-extension://invalid/' + path; }
    };
  }

  // =====================================================
  // 3. Override Permissions API
  // =====================================================
  const originalQuery = window.navigator.permissions?.query;
  if (originalQuery) {
    window.navigator.permissions.query = function(parameters) {
      if (parameters.name === 'notifications') {
        return Promise.resolve({ state: Notification.permission });
      }
      return originalQuery.call(this, parameters).then(function(result) {
        return result;
      }).catch(function() {
        return { state: 'prompt', onchange: null };
      });
    };
  }

  // =====================================================
  // 4. Mock PluginArray and plugins
  // =====================================================
  const fakePlugins = [
    {
      name: 'Chrome PDF Plugin',
      description: 'Portable Document Format',
      filename: 'internal-pdf-viewer',
      length: 1,
      0: { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' }
    },
    {
      name: 'Chrome PDF Viewer',
      description: '',
      filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
      length: 1,
      0: { type: 'application/pdf', suffixes: 'pdf', description: '' }
    },
    {
      name: 'Native Client',
      description: '',
      filename: 'internal-nacl-plugin',
      length: 2,
      0: { type: 'application/x-nacl', suffixes: '', description: 'Native Client Executable' },
      1: { type: 'application/x-pnacl', suffixes: '', description: 'Portable Native Client Executable' }
    }
  ];

  // Use Proxy to avoid redefining non-configurable 'length' on arrays
  const pluginArrayProxy = new Proxy(fakePlugins, {
    get(target, prop) {
      if (prop === 'length') return target.length;
      if (prop === 'item') return (i) => target[i] || null;
      if (prop === 'namedItem') return (name) => target.find(p => p.name === name) || null;
      if (prop === 'refresh') return () => {};
      return target[prop];
    }
  });

  Object.defineProperty(navigator, 'plugins', {
    get: () => pluginArrayProxy,
    configurable: true
  });

  Object.defineProperty(navigator, 'mimeTypes', {
    get: () => {
      const mimes = [
        { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: fakePlugins[1] },
        { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: fakePlugins[0] }
      ];
      const mimeArrayProxy = new Proxy(mimes, {
        get(target, prop) {
          if (prop === 'length') return target.length;
          if (prop === 'item') return (i) => target[i] || null;
          if (prop === 'namedItem') return (name) => target.find(m => m.type === name) || null;
          return target[prop];
        }
      });
      return mimeArrayProxy;
    },
    configurable: true
  });

  // =====================================================
  // 5. Override WebGL renderer/vendor
  // =====================================================
  const getParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return '${fingerprint.webglVendor}';
    if (param === 37446) return '${fingerprint.webglRenderer}';
    return getParameter.call(this, param);
  };

  if (typeof WebGL2RenderingContext !== 'undefined') {
    const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(param) {
      if (param === 37445) return '${fingerprint.webglVendor}';
      if (param === 37446) return '${fingerprint.webglRenderer}';
      return getParameter2.call(this, param);
    };
  }

  // Override getExtension to return proper debug info
  const getExtension = WebGLRenderingContext.prototype.getExtension;
  WebGLRenderingContext.prototype.getExtension = function(name) {
    const ext = getExtension.call(this, name);
    if (name === 'WEBGL_debug_renderer_info') {
      return {
        UNMASKED_VENDOR_WEBGL: 37445,
        UNMASKED_RENDERER_WEBGL: 37446
      };
    }
    return ext;
  };

  // =====================================================
  // 6. Override navigator properties for consistency
  // =====================================================
  Object.defineProperty(navigator, 'platform', {
    get: () => '${fingerprint.platform}',
    configurable: true
  });

  Object.defineProperty(navigator, 'vendor', {
    get: () => '${fingerprint.vendor}',
    configurable: true
  });

  Object.defineProperty(navigator, 'productSub', {
    get: () => '${fingerprint.productSub}',
    configurable: true
  });

  Object.defineProperty(navigator, 'languages', {
    get: () => ${JSON.stringify(fingerprint.languages)},
    configurable: true
  });

  Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => ${fingerprint.hardwareConcurrency},
    configurable: true
  });

  Object.defineProperty(navigator, 'deviceMemory', {
    get: () => ${fingerprint.deviceMemory},
    configurable: true
  });

  Object.defineProperty(navigator, 'maxTouchPoints', {
    get: () => ${fingerprint.maxTouchPoints},
    configurable: true
  });

  // =====================================================
  // 7. Override screen properties
  // =====================================================
  Object.defineProperty(screen, 'width', { get: () => ${fingerprint.screenWidth}, configurable: true });
  Object.defineProperty(screen, 'height', { get: () => ${fingerprint.screenHeight}, configurable: true });
  Object.defineProperty(screen, 'availWidth', { get: () => ${fingerprint.availWidth}, configurable: true });
  Object.defineProperty(screen, 'availHeight', { get: () => ${fingerprint.availHeight}, configurable: true });
  Object.defineProperty(screen, 'colorDepth', { get: () => ${fingerprint.colorDepth}, configurable: true });
  Object.defineProperty(screen, 'pixelDepth', { get: () => ${fingerprint.colorDepth}, configurable: true });

  Object.defineProperty(window, 'devicePixelRatio', {
    get: () => ${fingerprint.pixelRatio},
    configurable: true
  });

  // =====================================================
  // 8. Mock IntersectionObserver
  // =====================================================
  if (typeof IntersectionObserver === 'undefined') {
    window.IntersectionObserver = function(callback, options) {
      this.observe = function() {};
      this.unobserve = function() {};
      this.disconnect = function() {};
      this.takeRecords = function() { return []; };
    };
  }

  // =====================================================
  // 9. Prevent iframe content window detection
  // =====================================================
  try {
    const iframeProto = HTMLIFrameElement.prototype;
    const origContentWindow = Object.getOwnPropertyDescriptor(iframeProto, 'contentWindow');
    if (origContentWindow) {
      Object.defineProperty(iframeProto, 'contentWindow', {
        get: function() {
          const win = origContentWindow.get.call(this);
          if (win) {
            try {
              // Make the iframe's navigator match the parent
              Object.defineProperty(win.navigator, 'webdriver', { get: () => undefined });
            } catch(e) {}
          }
          return win;
        },
        configurable: true
      });
    }
  } catch(e) {}

  // =====================================================
  // 10. Override navigator.getBattery
  // =====================================================
  if (navigator.getBattery) {
    navigator.getBattery = function() {
      return Promise.resolve({
        charging: true,
        chargingTime: 0,
        dischargingTime: Infinity,
        level: 0.95 + Math.random() * 0.05,
        addEventListener: function() {},
        removeEventListener: function() {},
        dispatchEvent: function() { return true; }
      });
    };
  }

  // =====================================================
  // 11. Override navigator.connection
  // =====================================================
  if (!navigator.connection) {
    Object.defineProperty(navigator, 'connection', {
      get: () => ({
        effectiveType: '4g',
        rtt: 50 + Math.floor(Math.random() * 50),
        downlink: 5 + Math.random() * 5,
        saveData: false,
        addEventListener: function() {},
        removeEventListener: function() {}
      }),
      configurable: true
    });
  }

  // =====================================================
  // 12. Fix toString detection on overridden methods
  // =====================================================
  const nativeToString = Function.prototype.toString;
  const fnsToPatch = [];

  function patchFn(fn, name) {
    const str = nativeToString.call(fn);
    fn.toString = function() {
      return 'function ' + name + '() { [native code] }';
    };
    fn.toString.toString = function() {
      return 'function toString() { [native code] }';
    };
    fnsToPatch.push(fn);
  }

  // Patch our overridden functions to look native
  try {
    patchFn(navigator.permissions.query, 'query');
    patchFn(WebGLRenderingContext.prototype.getParameter, 'getParameter');
    if (typeof WebGL2RenderingContext !== 'undefined') {
      patchFn(WebGL2RenderingContext.prototype.getParameter, 'getParameter');
    }
    patchFn(WebGLRenderingContext.prototype.getExtension, 'getExtension');
    patchFn(navigator.getBattery, 'getBattery');
  } catch(e) {
    console.warn('[Stealth] Warning: toString patching failed for some functions — overridden methods may have non-native toString signatures');
  }

  // =====================================================
  // 13. Hide automation indicators
  // =====================================================
  // Remove CDP artifacts
  delete window.__cdp_bindings__;
  delete window._cdp;

  // Remove Playwright/Puppeteer artifacts
  delete window.__playwright;
  delete window.__pw_manual;

  // Clean up document properties that leak automation
  const docProto = Document.prototype;
  const origHasFocus = docProto.hasFocus;
  docProto.hasFocus = function() { return true; };

  // =====================================================
  // 14. Override Date/timezone
  // =====================================================
  // Ensure Intl.DateTimeFormat matches our timezone
  const origDateTimeFormat = Intl.DateTimeFormat;
  const targetTimezone = '${fingerprint.timezone}';

  if (origDateTimeFormat && targetTimezone) {
    const origResolvedOptions = Intl.DateTimeFormat.prototype.resolvedOptions;
    Intl.DateTimeFormat = function(...args) {
      if (args.length === 0 || (args.length === 1 && typeof args[0] === 'string')) {
        args = [targetTimezone, ...(args.length === 1 ? [args[0]] : [])];
      } else if (args.length >= 1 && args[0] !== targetTimezone) {
        args[0] = targetTimezone;
      }
      return new origDateTimeFormat(...args);
    };
    Intl.DateTimeFormat.prototype = origDateTimeFormat.prototype;
    // Override resolvedOptions to return the target timezone
    Intl.DateTimeFormat.prototype.resolvedOptions = function() {
      const opts = origResolvedOptions.call(this);
      opts.timeZone = targetTimezone;
      return opts;
    };
  }

  // =====================================================
  // 15. Canvas fingerprint noise (subtle)
  // =====================================================
  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(type) {
    // Only add noise to small canvases (fingerprint canvases are usually small)
    if (this.width <= 500 && this.height <= 500) {
      const ctx = this.getContext('2d');
      if (ctx) {
        try {
          const imageData = ctx.getImageData(0, 0, 1, 1);
          // Add imperceptible noise to one pixel
          imageData.data[3] = imageData.data[3] ^ 1;
          ctx.putImageData(imageData, 0, 0);
        } catch(e) {}
      }
    }
    return origToDataURL.apply(this, arguments);
  };

  // =====================================================
  // 16. Fix Notification permission
  // =====================================================
  if (Notification.permission === 'denied') {
    Object.defineProperty(Notification, 'permission', {
      get: () => 'default',
      configurable: true
    });
  }

  // =====================================================
  // 17. Mock speech synthesis (some detectors check this)
  // =====================================================
  if (!window.speechSynthesis) {
    Object.defineProperty(window, 'speechSynthesis', {
      get: () => ({
        getVoices: () => [],
        speak: function() {},
        cancel: function() {},
        pause: function() {},
        resume: function() {},
        addEventListener: function() {},
        removeEventListener: function() {}
      }),
      configurable: true
    });
  }

  // =====================================================
  // 18. Error stack trace cleaning
  // =====================================================
  const OrigError = Error;
  const origCaptureStackTrace = Error.captureStackTrace;
  if (origCaptureStackTrace) {
    Error.captureStackTrace = function(obj, fn) {
      origCaptureStackTrace.call(this, obj, fn);
      if (obj.stack) {
        // Remove lines that reference our injected code
        obj.stack = obj.stack.split('\\n').filter(line =>
          !line.includes('puppeteer') &&
          !line.includes('playwright') &&
          !line.includes('__puppeteer')
        ).join('\\n');
      }
    };
  }

  // =====================================================
  // 19. Override navigator.userAgent
  // =====================================================
  Object.defineProperty(navigator, 'userAgent', {
    get: () => '${fingerprint.userAgent}',
    configurable: true
  });

  // Also override on iframe navigator
  try {
    const iframes = document.querySelectorAll('iframe');
    for (let i = 0; i < iframes.length; i++) {
      try {
        Object.defineProperty(iframes[i].contentWindow.navigator, 'webdriver', { get: () => undefined });
      } catch(e) {}
    }
  } catch(e) {}

})();
`;
}
