/**
 * Content script: draws the floating bubble on the page and frames the extension's panel.
 *
 * The page never sees the chat: the panel is a chrome-extension:// page inside an iframe, so the
 * host page's CSP does not apply to it, its storage is the extension's own, and the staff token
 * never touches the page. This script only draws the launcher, relays open/close/unread, and tells
 * the panel which page it is on (host for the default assistant, selection for "ask about this").
 */
import { MAX_SELECTION, PROTOCOL, extensionOrigin, type PageContext, type ToPage, type ToPanel } from "../lib/bridge";
import { anyHostMatches } from "../lib/hosts";
import { getPos, loadConfig, setPos } from "../lib/storage";

(async function main() {
  if (window.top !== window.self) return;                        // main document only
  if (document.getElementById("msbka-ext-host")) return;
  const cfg = await loadConfig();
  const here = location.origin;
  // Tell the toolbar icon why there is no bubble here, so a silent page is not a mystery.
  const suppressed = (reason: string) => { chrome.runtime.sendMessage({ type: "suppressed", reason }).catch(() => {}); };
  // stay out of the web app itself and of hosts IT excluded (e.g. customer e-banking pages)
  if (here === cfg.apiBase || here === cfg.webBase) return suppressed("Đây là chính web app MSB Knowledge Assistant — dùng cổng cán bộ tại đây");
  if (anyHostMatches(cfg.disabledHosts, location.host)) return suppressed("Trang này nằm trong danh sách IT loại trừ");
  // a site that already embeds the assistant with widget.js keeps its own bubble
  if (document.querySelector(".msbka-root")) return suppressed("Trang này đã nhúng sẵn bong bóng trợ lý (widget.js)");
  chrome.runtime.sendMessage({ type: "active" }).catch(() => {});

  const extOrigin = extensionOrigin();
  let isOpen = false, unread = 0, panelReady = false;

  /* ---------- Shadow DOM so the page's CSS and ours never meet ---------- */
  const host = document.createElement("div");
  host.id = "msbka-ext-host";
  host.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:2147483000;";
  const shadow = host.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = `
    :host{all:initial}
    .root{position:absolute;pointer-events:auto;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;touch-action:none}
    .btn{width:56px;height:56px;border-radius:50%;border:0;cursor:grab;box-shadow:0 8px 24px rgba(0,0,0,.22);display:flex;align-items:center;justify-content:center;color:#fff;position:relative;background:#ee6d1f;transition:transform .15s ease;user-select:none;padding:0}
    .btn:hover{transform:scale(1.05)}.btn.dragging{cursor:grabbing;transform:scale(1.08)}
    .btn:focus-visible{outline:3px solid rgba(255,255,255,.9);outline-offset:2px}
    .badge{position:absolute;top:-4px;right:-4px;min-width:20px;height:20px;border-radius:10px;background:#ef4444;color:#fff;font-size:11px;font-weight:700;display:none;align-items:center;justify-content:center;padding:0 5px;border:2px solid #fff}
    .label{position:absolute;top:50%;transform:translateY(-50%);background:#0f172a;color:#fff;font-size:12px;padding:6px 10px;border-radius:8px;white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .15s}
    .btn:hover+.label{opacity:1}
    .panel{position:absolute;width:390px;height:600px;border-radius:16px;overflow:hidden;box-shadow:0 16px 48px rgba(0,0,0,.26);background:#f7f7f9;display:none;transform:translateY(12px);opacity:0;transition:transform .2s ease,opacity .2s ease}
    .panel.open{display:block;transform:translateY(0);opacity:1}
    .panel iframe{width:100%;height:100%;border:0;display:block;background:#f7f7f9}
    @media (prefers-reduced-motion:reduce){.panel,.btn{transition:none}}
  `;
  shadow.appendChild(style);

  const root = document.createElement("div"); root.className = "root";
  const btn = document.createElement("button"); btn.className = "btn"; btn.type = "button";
  btn.setAttribute("aria-label", "Trợ lý cán bộ"); btn.setAttribute("aria-expanded", "false"); btn.setAttribute("aria-haspopup", "dialog");
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("width", "26"); icon.setAttribute("height", "26"); icon.setAttribute("viewBox", "0 0 24 24"); icon.setAttribute("fill", "none"); icon.setAttribute("aria-hidden", "true");
  const p1 = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p1.setAttribute("d", "M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.2 3.4c-.5.4-1.3 0-1.3-.6V16A2.5 2.5 0 0 1 4 13.5v-8Z");
  p1.setAttribute("stroke", "currentColor"); p1.setAttribute("stroke-width", "1.7"); p1.setAttribute("stroke-linejoin", "round");
  const p2 = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p2.setAttribute("d", "M8 8.5h8M8 11.5h5"); p2.setAttribute("stroke", "currentColor"); p2.setAttribute("stroke-width", "1.7"); p2.setAttribute("stroke-linecap", "round");
  icon.appendChild(p1); icon.appendChild(p2); btn.appendChild(icon);
  const badge = document.createElement("span"); badge.className = "badge"; badge.setAttribute("aria-live", "polite"); btn.appendChild(badge);
  const label = document.createElement("span"); label.className = "label"; label.textContent = "Trợ lý cán bộ";
  const panel = document.createElement("div"); panel.className = "panel"; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "Trợ lý cán bộ");
  root.appendChild(btn); root.appendChild(label); root.appendChild(panel);
  shadow.appendChild(root);

  let frame: HTMLIFrameElement | null = null;
  function ensureFrame() {
    if (frame) return frame;
    frame = document.createElement("iframe");
    frame.title = "Trợ lý cán bộ";
    frame.setAttribute("allow", "clipboard-write");
    // the panel learns the page origin from ancestorOrigins; the fragment is only a hint for tests
    frame.src = chrome.runtime.getURL("panel.html") + "#o=" + encodeURIComponent(here);
    panel.appendChild(frame);
    return frame;
  }

  /* ---------- position: remembered per site, clamped to the viewport ---------- */
  let pos = { x: window.innerWidth - 76, y: window.innerHeight - 76 };
  const saved = await getPos(here);
  if (saved) pos = saved;
  function place() {
    pos.x = Math.max(8, Math.min(window.innerWidth - 64, pos.x));
    pos.y = Math.max(8, Math.min(window.innerHeight - 64, pos.y));
    root.style.left = `${pos.x}px`; root.style.top = `${pos.y}px`;
    const onLeft = pos.x < window.innerWidth / 2;
    const below = pos.y < window.innerHeight / 2;           // open the panel towards the free side
    label.style.left = onLeft ? "66px" : ""; label.style.right = onLeft ? "" : "66px";
    panel.style.left = onLeft ? "0" : ""; panel.style.right = onLeft ? "" : "0";
    const h = Math.min(600, window.innerHeight - 24);
    panel.style.height = `${h}px`;
    let top = below ? 66 : -h - 10;
    top = Math.max(8 - pos.y, Math.min(window.innerHeight - 8 - h - pos.y, top));
    panel.style.top = `${top}px`;
  }
  place();
  window.addEventListener("resize", place);

  /* ---------- drag: > 6px is a drag, less is a click ---------- */
  let drag: { sx: number; sy: number; ox: number; oy: number; moved: boolean } | null = null;
  btn.addEventListener("pointerdown", (e) => {
    drag = { sx: e.clientX, sy: e.clientY, ox: pos.x, oy: pos.y, moved: false };
    btn.setPointerCapture(e.pointerId);
  });
  btn.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
    if (!drag.moved && Math.hypot(dx, dy) < 6) return;
    drag.moved = true; btn.classList.add("dragging");
    pos = { x: drag.ox + dx, y: drag.oy + dy }; place();
  });
  btn.addEventListener("pointerup", () => {
    if (!drag) return;
    const wasDrag = drag.moved; drag = null; btn.classList.remove("dragging");
    if (wasDrag) void setPos(here, pos); else toggle();
  });
  btn.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });

  /* ---------- talking to the panel ---------- */
  function post(msg: ToPanel) {
    frame?.contentWindow?.postMessage({ protocol: PROTOCOL, ...msg }, extOrigin);
  }
  function context(): PageContext {
    const sel = (window.getSelection()?.toString() || "").replace(/\s+/g, " ").trim().slice(0, MAX_SELECTION);
    return { origin: here, host: location.host, href: location.href, title: document.title, selection: sel };
  }
  function setBadge(n: number) { unread = n; badge.textContent = n > 9 ? "9+" : String(n); badge.style.display = n > 0 ? "flex" : "none"; }
  function open() {
    if (isOpen) return; isOpen = true;
    ensureFrame(); place();
    panel.style.display = "block";
    requestAnimationFrame(() => panel.classList.add("open"));
    btn.setAttribute("aria-expanded", "true"); setBadge(0);
    if (panelReady) { post({ type: "context", context: context() }); post({ type: "visibility", visible: true }); }
  }
  function close() {
    if (!isOpen) return; isOpen = false;
    panel.classList.remove("open"); btn.setAttribute("aria-expanded", "false");
    post({ type: "visibility", visible: false });
    setTimeout(() => { if (!isOpen) panel.style.display = "none"; }, 220);
    btn.focus();
  }
  function toggle() { isOpen ? close() : open(); }
  window.addEventListener("keydown", (e) => { if (e.key === "Escape" && isOpen) close(); });

  // selection on the page → the panel offers "hỏi về đoạn này"
  let selTimer: number | undefined, pushTimer: number | undefined;
  document.addEventListener("selectionchange", () => {
    if (!isOpen || !panelReady) return;
    window.clearTimeout(selTimer);
    selTimer = window.setTimeout(() => post({ type: "context", context: context() }), 250);
  });

  // only the panel we created may talk to us
  window.addEventListener("message", (e: MessageEvent) => {
    if (!frame || e.source !== frame.contentWindow || e.origin !== extOrigin) return;
    const d = e.data as (ToPage & { protocol?: string }) | undefined;
    if (!d || d.protocol !== PROTOCOL || typeof d.type !== "string") return;
    if (d.type === "ready") {
      panelReady = true;
      if (/^#[0-9a-fA-F]{6}$/.test(d.color)) btn.style.background = d.color;
      if (d.title) { label.textContent = d.title.slice(0, 40); btn.setAttribute("aria-label", label.textContent); }
      if (isOpen) { post({ type: "context", context: context() }); post({ type: "visibility", visible: true }); }
    } else if (d.type === "close") close();
    else if (d.type === "unread") { if (!isOpen) setBadge(unread + (typeof d.count === "number" ? d.count : 1)); }
  });

  // the side panel asks the active tab what it is looking at; also lets a toolbar toggle through
  chrome.runtime.onMessage.addListener((msg: { type?: string }, _sender, sendResponse) => {
    if (msg?.type === "toggle") toggle();
    if (msg?.type === "get-context") { sendResponse(context()); return true; }
    return undefined;
  });
  // push selection changes to the side panel (debounced, only when the text actually changed)
  let lastPushed = "";
  document.addEventListener("selectionchange", () => {
    window.clearTimeout(pushTimer);
    pushTimer = window.setTimeout(() => {
      const ctx = context();
      if (ctx.selection === lastPushed) return;
      lastPushed = ctx.selection;
      chrome.runtime.sendMessage({ type: "selection", context: ctx }).catch(() => {});
    }, 400);
  });

  // one assistant, two places: while the Side Panel is open the bubble steps aside
  const applySidePanel = (open: boolean) => {
    if (open && isOpen) close();
    host.style.display = open ? "none" : "";
  };
  try {
    chrome.storage.session.get("sidePanelOpen").then((r) => applySidePanel(!!r.sidePanelOpen)).catch(() => {});
    chrome.storage.session.onChanged.addListener((changes) => {
      if ("sidePanelOpen" in changes) applySidePanel(!!changes.sidePanelOpen.newValue);
    });
  } catch { /* storage.session not reachable from this context → bubble stays */ }

  (document.body || document.documentElement).appendChild(host);
})();
