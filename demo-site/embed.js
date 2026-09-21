// Injects the chat bubble for the assistant named in data-assistant ("customer" | "staff") using demo-site/config.js.
(function () {
  var me = document.currentScript;
  var which = (me && me.getAttribute("data-assistant")) || "customer";
  var c = window.MSB_DEMO && window.MSB_DEMO[which];
  if (!c || !c.app) { console.warn("[demo-site] thiếu config.js — chạy seed_demo"); return; }
  var s = document.createElement("script");
  s.src = window.MSB_DEMO.web + "/widget.js";
  s.async = true;
  s.setAttribute("data-app", c.app);
  s.setAttribute("data-key", c.key);
  document.body.appendChild(s);
})();
