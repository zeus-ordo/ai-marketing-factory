import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: [
    "fraction-landslide-creole.ngrok-free.dev",
    "*.ngrok-free.dev",
    "localhost",
    "127.0.0.1",
  ],
};

export default nextConfig;
