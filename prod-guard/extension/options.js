/**
 * Options page logic — configure backend API URL.
 */

const apiUrlInput = document.getElementById("api-url");
const saveBtn = document.getElementById("save-btn");
const savedMsg = document.getElementById("saved-msg");

// Load current settings
browser.storage.local.get(["apiUrl"]).then((result) => {
  apiUrlInput.value = result.apiUrl || "http://192.168.22.1:8800";
});

saveBtn.addEventListener("click", async () => {
  const apiUrl = apiUrlInput.value.trim().replace(/\/+$/, ""); // Remove trailing slashes

  // Update background script
  await browser.runtime.sendMessage({
    type: "UPDATE_SETTINGS",
    apiUrl: apiUrl,
  });

  // Show saved confirmation
  savedMsg.style.display = "inline";
  setTimeout(() => {
    savedMsg.style.display = "none";
  }, 2000);
});
