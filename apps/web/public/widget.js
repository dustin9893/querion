/*!
 * MSB Knowledge Assistant — embeddable chat bubble (loader).
 *
 *   <script src="https://<web-app>/widget.js" data-app="<assistant id>" data-key="<publishable key>" async></script>
 *
 * Optional attributes: data-position="right|left", data-origin="https://<web-app>" (defaults to the
 * script's own origin), data-zindex="2147483000".
 *
 * Security model
 * - The chat UI runs in an <iframe> on OUR origin; this loader only draws the bubble and
 *   relays open/close. The host page never talks to the API directly.
 * - The browser enforces which sites may embed via CSP frame-ancestors on the iframe page;
 *   the iframe additionally verifies the parent origin against the assistant's allowlist.
 * - postMessage is exchanged only with the iframe's exact origin (never "*"), protocol "msbka/1".
 * - The key is publishable: it can only reach public assistant endpoints and can be revoked
 *   from the admin console ("Tạo lại key").
 */
(function () {
  "use strict";
  var script = document.currentScript;
  if (!script) return;
  var appId = script.getAttribute("data-app");
  var key = script.getAttribute("data-key");
  if (!appId || !key) { console.warn("[msbka] widget.js needs data-app and data-key"); return; }
  if (window.__msbkaLoaded) return; window.__msbkaLoaded = true;

  var widgetOrigin = script.getAttribute("data-origin") || new URL(script.src, location.href).origin;
  var position = script.getAttribute("data-position") === "left" ? "left" : "right";
  var zIndex = script.getAttribute("data-zindex") || "2147483000";
  var PROTOCOL = "msbka/1";
  var hostOrigin = location.origin;
  var isOpen = false, ready = false, unread = 0, teaserShown = false;
  var cfg = { primary_color: "#ee6d1f", launcher_text: "Hỗ trợ trực tuyến", greeting: "", position: position, title: "Trợ lý" };

  /* ---------- styles ---------- */
  var css = "" +
    ".msbka-root{position:fixed;bottom:20px;" + position + ":20px;z-index:" + zIndex + ";font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;}" +
    ".msbka-btn{width:56px;height:56px;border-radius:50%;border:0;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.18);display:flex;align-items:center;justify-content:center;color:#fff;position:relative;transition:transform .15s ease;}" +
    ".msbka-btn:hover{transform:scale(1.05);}" +
    ".msbka-btn img{width:40px;height:40px;border-radius:50%;object-fit:cover;display:block;background:#fff;}" +
    ".msbka-btn:focus-visible{outline:3px solid rgba(255,255,255,.9);outline-offset:2px;}" +
    ".msbka-badge{position:absolute;top:-4px;right:-4px;min-width:20px;height:20px;border-radius:10px;background:#ef4444;color:#fff;font-size:11px;font-weight:700;display:none;align-items:center;justify-content:center;padding:0 5px;border:2px solid #fff;}" +
    ".msbka-teaser{position:absolute;bottom:68px;" + position + ":0;max-width:260px;background:#fff;color:#0f172a;border-radius:14px;padding:10px 12px 10px 12px;box-shadow:0 8px 24px rgba(0,0,0,.14);font-size:13px;line-height:1.35;display:none;}" +
    ".msbka-teaser button{position:absolute;top:4px;right:6px;border:0;background:transparent;color:#94a3b8;cursor:pointer;font-size:14px;}" +
    ".msbka-label{position:absolute;bottom:14px;" + (position === "right" ? "right:66px" : "left:66px") + ";background:#0f172a;color:#fff;font-size:12px;padding:6px 10px;border-radius:8px;white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .15s;}" +
    ".msbka-btn:hover + .msbka-label{opacity:1;}" +
    ".msbka-panel{position:fixed;bottom:88px;" + position + ":20px;width:380px;height:min(600px,calc(100vh - 110px));border-radius:16px;overflow:hidden;box-shadow:0 16px 48px rgba(0,0,0,.22);background:#f7f7f9;display:none;transform:translateY(12px);opacity:0;transition:transform .2s ease,opacity .2s ease;}" +
    ".msbka-panel.msbka-open{display:block;transform:translateY(0);opacity:1;}" +
    ".msbka-panel iframe{width:100%;height:100%;border:0;display:block;}" +
    "@media (max-width:640px){.msbka-panel{bottom:0;" + position + ":0;left:0;right:0;width:100%;height:100%;border-radius:0;padding-bottom:env(safe-area-inset-bottom);}.msbka-root.msbka-panel-open .msbka-btn,.msbka-root.msbka-panel-open .msbka-teaser,.msbka-root.msbka-panel-open .msbka-label{display:none;}}" +
    "@media (prefers-reduced-motion:reduce){.msbka-panel,.msbka-btn{transition:none;}}";
  var style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);

  /* ---------- DOM ---------- */
  var root = document.createElement("div"); root.className = "msbka-root";
  var btn = document.createElement("button"); btn.className = "msbka-btn"; btn.type = "button";
  btn.setAttribute("aria-label", cfg.launcher_text); btn.setAttribute("aria-expanded", "false"); btn.setAttribute("aria-haspopup", "dialog");
  btn.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.2 3.4c-.5.4-1.3 0-1.3-.6V16A2.5 2.5 0 0 1 4 13.5v-8Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M8 8.5h8M8 11.5h5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>' +
    '<span class="msbka-badge" aria-live="polite"></span>';
  var label = document.createElement("span"); label.className = "msbka-label"; label.textContent = cfg.launcher_text;
  var teaser = document.createElement("div"); teaser.className = "msbka-teaser"; teaser.setAttribute("role", "status");
  var panel = document.createElement("div"); panel.className = "msbka-panel"; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "Khung chat trợ lý"); panel.setAttribute("aria-modal", "false");
  var frame = document.createElement("iframe");
  frame.title = "Trợ lý";
  frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms allow-popups");
  frame.setAttribute("allow", "clipboard-write");
  frame.setAttribute("referrerpolicy", "strict-origin");
  frame.setAttribute("loading", "eager");
  // key + host origin travel in the fragment (never in server logs)
  frame.src = widgetOrigin + "/embed/" + encodeURIComponent(appId) + "#k=" + encodeURIComponent(key) + "&o=" + encodeURIComponent(hostOrigin);
  panel.appendChild(frame);
  root.appendChild(btn); root.appendChild(label); root.appendChild(teaser); root.appendChild(panel);
  var badge = btn.querySelector(".msbka-badge");
  var icon = btn.querySelector("svg");

  function mount() { (document.body || document.documentElement).appendChild(root); applyColor(); }
  function applyColor() { btn.style.background = cfg.primary_color; }
  function setLogo(url) {
    if (btn.querySelector("img")) return;
    var img = document.createElement("img"); img.alt = ""; img.setAttribute("aria-hidden", "true");
    img.decoding = "async"; img.referrerPolicy = "no-referrer";
    img.onerror = function () { if (img.parentNode) img.parentNode.removeChild(img); if (icon) icon.style.display = ""; };
    img.src = url; if (icon) icon.style.display = "none"; btn.insertBefore(img, badge);
  }
  function setBadge(n) { unread = n; if (!badge) return; badge.textContent = n > 9 ? "9+" : String(n); badge.style.display = n > 0 ? "flex" : "none"; }
  function post(msg) { if (!frame.contentWindow) return; frame.contentWindow.postMessage(Object.assign({ protocol: PROTOCOL }, msg), widgetOrigin); }

  function open() {
    if (isOpen) return; isOpen = true;
    panel.style.display = "block";
    requestAnimationFrame(function () { panel.classList.add("msbka-open"); });
    root.classList.add("msbka-panel-open");
    btn.setAttribute("aria-expanded", "true");
    hideTeaser(); setBadge(0);
    post({ type: "visibility", visible: true });
    try { frame.contentWindow && frame.contentWindow.focus(); } catch (e) { /* ignore */ }
  }
  function close() {
    if (!isOpen) return; isOpen = false;
    panel.classList.remove("msbka-open");
    root.classList.remove("msbka-panel-open");
    btn.setAttribute("aria-expanded", "false");
    post({ type: "visibility", visible: false });
    setTimeout(function () { if (!isOpen) panel.style.display = "none"; }, 220);
    btn.focus();
  }
  function toggle() { isOpen ? close() : open(); }
  function showTeaser() {
    if (teaserShown || isOpen || !cfg.greeting) return;
    try { if (sessionStorage.getItem("msbka-teaser-" + appId)) return; } catch (e) { /* ignore */ }
    teaserShown = true;
    teaser.innerHTML = ""; var t = document.createElement("span"); t.textContent = cfg.greeting; teaser.appendChild(t);
    var x = document.createElement("button"); x.type = "button"; x.setAttribute("aria-label", "Đóng"); x.textContent = "×";
    x.addEventListener("click", function (e) { e.stopPropagation(); hideTeaser(); });
    teaser.appendChild(x); teaser.style.display = "block"; teaser.style.cursor = "pointer";
    teaser.addEventListener("click", open);
  }
  function hideTeaser() { teaser.style.display = "none"; try { sessionStorage.setItem("msbka-teaser-" + appId, "1"); } catch (e) { /* ignore */ } }

  btn.addEventListener("click", toggle);
  window.addEventListener("keydown", function (e) { if (e.key === "Escape" && isOpen) close(); });

  // Only accept messages from the widget iframe (exact origin + protocol + schema)
  window.addEventListener("message", function (e) {
    if (e.origin !== widgetOrigin || e.source !== frame.contentWindow) return;
    var d = e.data;
    if (!d || d.protocol !== PROTOCOL || typeof d.type !== "string") return;
    if (d.type === "ready") {
      ready = true;
      var w = d.widget || {};
      if (typeof w.primary_color === "string" && /^#[0-9a-fA-F]{6}$/.test(w.primary_color)) cfg.primary_color = w.primary_color;
      if (typeof w.launcher_text === "string" && w.launcher_text) { cfg.launcher_text = w.launcher_text.slice(0, 40); label.textContent = cfg.launcher_text; btn.setAttribute("aria-label", cfg.launcher_text); }
      if (typeof w.greeting === "string") cfg.greeting = w.greeting.slice(0, 300);
      if (typeof w.title === "string") { cfg.title = w.title.slice(0, 80); frame.title = cfg.title; panel.setAttribute("aria-label", cfg.title); }
      if (typeof w.logo_url === "string" && w.logo_url.length < 600 && /^https?:\/\//.test(w.logo_url)) setLogo(w.logo_url);
      applyColor();
      setTimeout(showTeaser, 3000);
    } else if (d.type === "close") {
      close();
    } else if (d.type === "unread") {
      if (!isOpen) setBadge(unread + (typeof d.count === "number" ? d.count : 1));
    }
  });

  // Public API for the host page
  window.MSBAssistant = { open: open, close: close, toggle: toggle, isOpen: function () { return isOpen; } };

  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);
})();
