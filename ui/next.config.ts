import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: { root: __dirname },
  devIndicators: false,
  /* config options here */
};

export default nextConfig;
