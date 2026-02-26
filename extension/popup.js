/**
 * Popup logic — shows connection status and active approved scopes.
 */

document.getElementById("options-link").addEventListener("click", (e) => {
  e.preventDefault();
  browser.runtime.openOptionsPage();
});

async function loadStatus() {
  const statusEl = document.getElementById("connection-status");
  const scopesEl = document.getElementById("scopes-list");

  try {
    // Get local scope data from background script
    const status = await browser.runtime.sendMessage({ type: "GET_STATUS" });

    // Check backend health
    try {
      const healthResp = await fetch(`${status.apiUrl}/health`);
      if (healthResp.ok) {
        statusEl.className = "connected";
        statusEl.textContent = `✓ Connected to ${status.apiUrl}`;
      } else {
        statusEl.className = "disconnected";
        statusEl.textContent = `✗ Backend error: ${healthResp.status}`;
      }
    } catch {
      statusEl.className = "disconnected";
      statusEl.textContent = `✗ Cannot reach backend at ${status.apiUrl}`;
    }

    // Display active scopes
    if (status.scopes && status.scopes.length > 0) {
      scopesEl.innerHTML = "";
      for (const scope of status.scopes) {
        const minutes = Math.ceil(scope.remainingSeconds / 60);
        const card = document.createElement("div");
        card.className = "scope-card";
        const domainDiv = document.createElement("div");
        domainDiv.className = "domain";
        domainDiv.textContent = scope.domain;
        const detailsDiv = document.createElement("div");
        detailsDiv.className = "details";
        detailsDiv.textContent = `Scope: ${scope.pathPrefix} · ${minutes} min remaining`;
        card.appendChild(domainDiv);
        card.appendChild(detailsDiv);
        scopesEl.appendChild(card);
      }
    } else {
      scopesEl.innerHTML = '<div class="no-active">No active approvals. All conditional domains are blocked.</div>';
    }
  } catch (err) {
    statusEl.className = "disconnected";
    statusEl.textContent = "Error loading status";
    console.error(err);
  }
}

loadStatus();

// Refresh every 10 seconds while popup is open
setInterval(loadStatus, 10000);
