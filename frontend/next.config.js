/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
  async rewrites() {
    const target = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${target}/api/:path*` }];
  },
};
module.exports = nextConfig;
