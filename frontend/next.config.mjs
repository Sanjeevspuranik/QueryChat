const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Same-origin proxy keeps the auth cookie first-party and avoids CORS in the browser.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  // Compression buffers server-sent events; the chat stream must flush immediately.
  compress: false,
};

export default nextConfig;
