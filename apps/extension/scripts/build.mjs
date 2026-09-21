// Build the extension into dist/: panel + options pages (React, Tailwind), content script (IIFE),
// background service worker (ESM), then the manifest with the API origins baked in.
//
//   npm run build
//   API_ORIGINS="https://kb.msb.com.vn/*" VITE_DEFAULT_API_BASE="https://kb.msb.com.vn" npm run build
import { build } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root, process.env.OUT_DIR || "dist");   // OUT_DIR: build a variant elsewhere (e.g. for a server)
const webSrc = resolve(root, "../web/src");

const DEFAULT_API_BASE = process.env.VITE_DEFAULT_API_BASE || "http://localhost:8000";
const API_ORIGINS = (process.env.API_ORIGINS || "http://localhost:8000/*,https://59-153-246-116.sslip.io/*")
  .split(",").map((s) => s.trim()).filter(Boolean);

const define = {
  "import.meta.env.VITE_DEFAULT_API_BASE": JSON.stringify(DEFAULT_API_BASE),
  // transport.ts guards `process`, but be explicit so nothing in the web code reaches for it
  "process.env.NEXT_PUBLIC_API_URL": "undefined",
};

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

// 1. extension pages
await build({
  configFile: false, root: resolve(root, "src"), base: "./", logLevel: "warn", define,
  plugins: [react(), tailwindcss()],
  // the shared chat component lives under apps/web and would otherwise pull apps/web's React copy
  // next to ours — two Reacts means hooks resolve to null at runtime
  resolve: { alias: { "@": webSrc }, dedupe: ["react", "react-dom", "react/jsx-runtime", "react-dom/client"] },
  build: {
    outDir: dist, emptyOutDir: false, target: "es2022", sourcemap: false,
    rollupOptions: { input: { panel: resolve(root, "src/panel.html"), options: resolve(root, "src/options.html") } },
  },
});

// 2. content script — one self-contained IIFE, no module loading in the page
await build({
  configFile: false, root, logLevel: "warn", define,
  build: {
    outDir: dist, emptyOutDir: false, target: "es2022", sourcemap: false, minify: true,
    lib: { entry: resolve(root, "src/content/content.ts"), name: "msbkaContent", formats: ["iife"], fileName: () => "content.js" },
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
});

// 3. background service worker
await build({
  configFile: false, root, logLevel: "warn", define,
  build: {
    outDir: dist, emptyOutDir: false, target: "es2022", sourcemap: false,
    lib: { entry: resolve(root, "src/background.ts"), formats: ["es"], fileName: () => "background.js" },
  },
});

// 4. manifest + static files
const manifest = JSON.parse(readFileSync(resolve(root, "manifest.json"), "utf8"));
manifest.host_permissions = API_ORIGINS;
writeFileSync(resolve(dist, "manifest.json"), JSON.stringify(manifest, null, 2));
cpSync(resolve(root, "icons"), resolve(dist, "icons"), { recursive: true });
cpSync(resolve(root, "managed_schema.json"), resolve(dist, "managed_schema.json"));
console.log(`built → ${dist}\n  API mặc định: ${DEFAULT_API_BASE}\n  host_permissions: ${API_ORIGINS.join(", ")}`);
