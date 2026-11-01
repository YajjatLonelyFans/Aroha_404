import { readFileSync } from "node:fs";
import path from "node:path";
import type { NextConfig } from "next";

// The repo keeps one .env at its root, shared with the backend. Forward only its
// NEXT_PUBLIC_* values so backend secrets never reach the frontend build. Values in
// frontend/.env.local (already loaded by Next) win; "<...>" placeholders are skipped.
function publicEnvFromRoot(): Record<string, string> {
  let text: string;
  try {
    text = readFileSync(path.resolve(process.cwd(), "..", ".env"), "utf8");
  } catch {
    return {};
  }
  const env: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^\s*(NEXT_PUBLIC_[A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (!m || process.env[m[1]] !== undefined) continue;
    const value = m[2].replace(/^["']|["']$/g, "");
    if (value && !value.startsWith("<")) env[m[1]] = value;
  }
  return env;
}

const nextConfig: NextConfig = {
  env: publicEnvFromRoot(),
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
