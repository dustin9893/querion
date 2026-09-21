import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image (apps/web/Dockerfile runs server.js)
  output: "standalone",
  async headers() {
    return [
      {
        // Everything except the embeddable widget page must never be framed.
        // /embed/* gets a per-assistant CSP frame-ancestors header from src/proxy.ts instead.
        source: "/((?!embed/).*)",
        headers: [{ key: "X-Frame-Options", value: "DENY" }],
      },
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
      {
        // First-party loader for the chat bubble; short cache so fixes roll out quickly.
        source: "/widget.js",
        headers: [
          { key: "Cache-Control", value: "public, max-age=300" },
          { key: "Access-Control-Allow-Origin", value: "*" },
        ],
      },
    ];
  },
};

export default nextConfig;
