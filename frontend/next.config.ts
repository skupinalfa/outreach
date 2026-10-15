import type { NextConfig } from "next";

// Proxy `/api/v1/*` to the backend service so browser fetches are same-origin
// with the frontend. This is the fix for cross-site cookies not reaching the
// Next.js SSR layer: with the proxy in place, the session cookie is scoped to
// the frontend origin and `next/headers`' `cookies()` in `app/auth/layout.tsx`
// can see it. Bonus: no more CORS preflights.
//
// Reads INTERNAL_API_URL at Next server startup — override in Railway/env for
// each environment. Falls back to NEXT_PUBLIC_API_URL (still baked-in at build)
// then to localhost for local dev.
const config: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    const backend =
      process.env.INTERNAL_API_URL ??
      process.env.NEXT_PUBLIC_API_URL ??
      "http://localhost:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backend}/api/v1/:path*`,
      },
    ];
  },
};

export default config;
