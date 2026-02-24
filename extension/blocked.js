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
      showResponse(
        "approved",
        response.message +
          `<div class="scope-info">Scope: ${response.scope || "/*"} · Duration: ${response.duration_minutes || "?"} minutes<br>Redirecting in 3 seconds...</div>`
      );
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

function showResponse(type, message) {
  const el = document.getElementById("response");
  el.className = `response ${type}`;
  el.innerHTML = message;
}

function hideResponse() {
  const el = document.getElementById("response");
  el.className = "response";
  el.innerHTML = "";
}
