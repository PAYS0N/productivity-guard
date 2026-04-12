/**
 * Blocked page logic.
 * Reads the blocked URL from query params, sends the reason to the background
 * script, and displays the LLM's response.
 */

// Parse query params
const params = new URLSearchParams(window.location.search);
const blockedUrl = params.get("url") || "";
const blockedDomain = params.get("domain") || "";

// Display blocked URL info
document.getElementById("domain-display").textContent = blockedDomain;
document.getElementById("url-display").textContent = blockedUrl;

document.getElementById("submit-btn").addEventListener("click", submitRequest);

// Allow Enter key to submit (Shift+Enter for newline)
document.getElementById("reason").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submitRequest();
  }
});

async function submitRequest() {
  const reason = document.getElementById("reason").value.trim();
  if (!reason) {
    showResponse("error", "Please provide a reason.");
    return;
  }

  const btn = document.getElementById("submit-btn");
  const spinner = document.getElementById("spinner");

  btn.disabled = true;
  spinner.classList.add("active");
  hideResponse();

  try {
    const response = await browser.runtime.sendMessage({
      type: "REQUEST_ACCESS",
      url: blockedUrl,
      reason: reason,
    });

    if (response.approved) {
      showResponse("approved", response.message, [
        `Scope: ${response.scope || "/*"} · Duration: ${response.duration_minutes || "?"} minutes`,
        "Redirecting in 3 seconds...",
      ]);
      // The background script handles the redirect after DNS propagation
    } else {
      showResponse("denied", response.message);
      btn.disabled = false;
    }
  } catch (err) {
    showResponse("error", `Error communicating with Productivity Guard: ${err.message}`);
    btn.disabled = false;
  } finally {
    spinner.classList.remove("active");
  }
}

function showResponse(type, message, scopeLines = []) {
  const el = document.getElementById("response");
  el.className = `response ${type}`;
  el.textContent = message;
  if (scopeLines.length > 0) {
    const infoDiv = document.createElement("div");
    infoDiv.className = "scope-info";
    infoDiv.textContent = scopeLines.join("\n");
    el.appendChild(infoDiv);
  }
}

function hideResponse() {
  const el = document.getElementById("response");
  el.className = "response";
  el.textContent = "";
}
