import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: "/dashboard/jobs",
        destination: "/jobs",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
