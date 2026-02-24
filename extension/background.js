/**
 * Productivity Guard — Background Script
 *
 * Intercepts navigation to conditional (blocked) domains.
 * If the URL is within an approved scope, allows it.
 * Otherwise, redirects to blocked.html which prompts the user for a reason.
 *
 * Communicates with the FastAPI backend on the Pi for access decisions.
 */

// ── Configuration ──────────────────────────────────────────────────────────

const DEFAULT_API_URL = "http://192.168.22.1:8800";

// Domains that are conditionally blocked (must match backend config)
// These are loaded from storage on startup and can be updated via options page
let CONDITIONAL_DOMAINS = [
  "reddit.com",
  "www.reddit.com",
  "youtube.com",
  "www.youtube.com",
  "inv.nadeko.net",
  "yewtu.be",
  "invidious.nerdvpn.de",
];

let apiUrl = DEFAULT_API_URL;

// ── State ──────────────────────────────────────────────────────────────────

/**
 * Active approved scopes.
 * Map of domain -> { pathPrefix, expires (unix ms), originalUrl, scope }
 */
const approvedScopes = new Map();

/**
 * Pending requests — URLs currently waiting for user input in the popup.
 * Map of tabId -> { url, domain }
 */
const pendingRequests = new Map();

// ── Initialization ─────────────────────────────────────────────────────────

// Load settings from storage
browser.storage.local.get(["apiUrl", "conditionalDomains"]).then((result) => {
  if (result.apiUrl) apiUrl = result.apiUrl;
  if (result.conditionalDomains) CONDITIONAL_DOMAINS = result.conditionalDomains;
  setupRequestListener();
});

// ── Request Interception ───────────────────────────────────────────────────

function setupRequestListener() {
  // Build URL match patterns for all conditional domains
  const patterns = [];
  for (const domain of CONDITIONAL_DOMAINS) {
    patterns.push(`*://${domain}/*`);
  }

  // Remove existing listener if any (for re-initialization)
  if (browser.webRequest.onBeforeRequest.hasListener(handleRequest)) {
    browser.webRequest.onBeforeRequest.removeListener(handleRequest);
  }

  browser.webRequest.onBeforeRequest.addListener(
    handleRequest,
    { urls: patterns, types: ["main_frame"] },
    ["blocking"]
  );
}

function handleRequest(details) {
  const url = new URL(details.url);
  const domain = url.hostname;

  // Check if this domain is in our conditional list
  if (!isDomainConditional(domain)) {
    return {};
  }

  // Check if we have an active approved scope for this domain + path
  const scope = approvedScopes.get(domain);
  if (scope && Date.now() < scope.expires) {
    // Check path matches scope
    if (pathMatchesScope(url.pathname + url.search, scope.pathPrefix)) {
      return {}; // Allow
    }
  }

  // Store the pending request for this tab
  pendingRequests.set(details.tabId, {
    url: details.url,
    domain: domain,
  });

  // Redirect to our blocked page
  const blockedUrl = browser.runtime.getURL("blocked.html") +
    "?url=" + encodeURIComponent(details.url) +
    "&domain=" + encodeURIComponent(domain);

  return { redirectUrl: blockedUrl };
}

function isDomainConditional(hostname) {
  return CONDITIONAL_DOMAINS.some((d) => {
    return hostname === d || hostname.endsWith("." + d);
  });
}

function pathMatchesScope(fullPath, scopePrefix) {
  if (!scopePrefix || scopePrefix === "/*" || scopePrefix === "/") {
    return true; // Wildcard scope — all paths allowed
  }

  // Remove trailing * for prefix matching
  const prefix = scopePrefix.replace(/\*$/, "");
  return fullPath.startsWith(prefix);
}

// ── Communication with Popup / Blocked Page ────────────────────────────────

browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "REQUEST_ACCESS") {
    handleAccessRequest(message.url, message.reason, sender.tab?.id)
      .then(sendResponse);
    return true; // async response
  }

  if (message.type === "GET_PENDING") {
    const tabId = sender.tab?.id;
    const pending = pendingRequests.get(tabId);
    sendResponse(pending || null);
    return false;
  }

  if (message.type === "GET_STATUS") {
    const scopes = [];
    for (const [domain, scope] of approvedScopes.entries()) {
      if (Date.now() < scope.expires) {
        scopes.push({
          domain,
          pathPrefix: scope.pathPrefix,
          expires: scope.expires,
          remainingSeconds: Math.round((scope.expires - Date.now()) / 1000),
        });
      }
    }
    sendResponse({ scopes, apiUrl });
    return false;
  }

  if (message.type === "UPDATE_SETTINGS") {
    if (message.apiUrl) {
      apiUrl = message.apiUrl;
      browser.storage.local.set({ apiUrl });
    }
    if (message.conditionalDomains) {
      CONDITIONAL_DOMAINS = message.conditionalDomains;
      browser.storage.local.set({ conditionalDomains: CONDITIONAL_DOMAINS });
      setupRequestListener();
    }
    sendResponse({ ok: true });
    return false;
  }
});

// ── API Communication ──────────────────────────────────────────────────────

async function handleAccessRequest(url, reason, tabId) {
  try {
    const response = await fetch(`${apiUrl}/request-access`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, reason }),
    });

    if (!response.ok) {
      return {
        approved: false,
        message: `Backend error: ${response.status} ${response.statusText}`,
      };
    }

    const data = await response.json();

    if (data.approved) {
      // Store the approved scope
      const parsedUrl = new URL(url);
      const domain = parsedUrl.hostname;
      const durationMs = (data.duration_minutes || 15) * 60 * 1000;

      approvedScopes.set(domain, {
        pathPrefix: data.scope || "/*",
        expires: Date.now() + durationMs,
        originalUrl: url,
        scope: data.scope,
      });

      // Also set for www/non-www variant
      const altDomain = domain.startsWith("www.")
        ? domain.slice(4)
        : "www." + domain;
      if (CONDITIONAL_DOMAINS.includes(altDomain)) {
        approvedScopes.set(altDomain, {
          pathPrefix: data.scope || "/*",
          expires: Date.now() + durationMs,
          originalUrl: url,
          scope: data.scope,
        });
      }

      // Schedule scope cleanup
      setTimeout(() => {
        approvedScopes.delete(domain);
        approvedScopes.delete(altDomain);
      }, durationMs);

      // Wait for DNS to propagate (dnsmasq SIGHUP + client cache)
      // then navigate to the original URL
      if (tabId) {
        setTimeout(() => {
          browser.tabs.update(tabId, { url: url });
        }, 2500);
      }
    }

    return data;
  } catch (err) {
    console.error("Productivity Guard API error:", err);
    return {
      approved: false,
      message: `Cannot reach Productivity Guard backend at ${apiUrl}. Is the service running? Error: ${err.message}`,
    };
  }
}

// ── Periodic Scope Cleanup ─────────────────────────────────────────────────

setInterval(() => {
  const now = Date.now();
  for (const [domain, scope] of approvedScopes.entries()) {
    if (now >= scope.expires) {
      approvedScopes.delete(domain);
    }
  }
}, 30000); // Clean up every 30 seconds
