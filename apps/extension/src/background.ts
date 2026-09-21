// MV3 service worker.
//  - Toolbar icon → the Side Panel (browser-level: works on every tab, New Tab and chrome:// included,
//    stays open while switching tabs). The floating bubble on web pages is drawn by the content script.
//  - Badge/title on a tab say why that page has no bubble.
const TITLE = "Trợ lý cán bộ MSB — mở panel bên";

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
});
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

// Side Panel and bubble are one assistant in two places: while the panel is open the bubbles hide.
// The panel page holds a port for as long as it lives; the state goes to session storage so content
// scripts (present and future tabs) can read it and react to changes without asking anyone.
const SIDE_PANEL_PORT = "msbka-sidepanel";
let openPanels = 0;
chrome.storage.session.setAccessLevel({ accessLevel: "TRUSTED_AND_UNTRUSTED_CONTEXTS" }).catch(() => {});
chrome.storage.session.set({ sidePanelOpen: false }).catch(() => {});   // fresh worker → no panel yet
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== SIDE_PANEL_PORT) return;
  openPanels += 1;
  chrome.storage.session.set({ sidePanelOpen: true }).catch(() => {});
  port.onDisconnect.addListener(() => {
    openPanels = Math.max(0, openPanels - 1);
    if (openPanels === 0) chrome.storage.session.set({ sidePanelOpen: false }).catch(() => {});
  });
});

chrome.runtime.onMessage.addListener((msg: { type?: string; reason?: string }, sender) => {
  const tabId = sender.tab?.id;
  if (tabId === undefined) return;
  if (msg?.type === "suppressed") {
    chrome.action.setBadgeText({ tabId, text: "–" });
    chrome.action.setBadgeBackgroundColor({ tabId, color: "#64748b" });
    chrome.action.setTitle({ tabId, title: `Không có bong bóng trên trang này: ${msg.reason || "trang bị bỏ qua"}. Bấm icon để mở panel bên.` });
  } else if (msg?.type === "active") {
    chrome.action.setBadgeText({ tabId, text: "" });
    chrome.action.setTitle({ tabId, title: TITLE });
  }
});
