import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // OAuth authorization codes must not appear in development access logs.
  logging: { incomingRequests: { ignore: [/^\/auth\/callback(?:\?|$)/] } },
};

export default nextConfig;
