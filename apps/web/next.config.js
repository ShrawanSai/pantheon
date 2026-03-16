/** @type {import('next').NextConfig} */

// ---------------------------------------------------------------------------
// Fail-fast: refuse to build if critical frontend env vars are missing.
// This catches misconfigured Vercel deployments before they go live.
// ---------------------------------------------------------------------------
const REQUIRED_ENV_VARS = [
  "NEXT_PUBLIC_API_BASE_URL",
  "NEXT_PUBLIC_SUPABASE_URL",
  "NEXT_PUBLIC_SUPABASE_ANON_KEY",
];

// Only enforce during a real build, not during local `next dev` where
// developers may be iterating without all vars set.
if (process.env.NODE_ENV === "production") {
  const missing = REQUIRED_ENV_VARS.filter((key) => !process.env[key]);
  if (missing.length > 0) {
    throw new Error(
      `[Pantheon] Missing required environment variables for production build:\n` +
        missing.map((k) => `  - ${k}`).join("\n") +
        `\n\nSet these in your Vercel project settings under Environment Variables.`
    );
  }
}

const nextConfig = {
  reactStrictMode: true,
};

module.exports = nextConfig;
