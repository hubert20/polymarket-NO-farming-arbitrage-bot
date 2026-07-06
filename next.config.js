/** @type {import('next').NextConfig} */

require('./src/lib/log.cjs');

const nextConfig = {
  reactStrictMode: true,
  images: { unoptimized: true },
  turbopack: {
    root: __dirname,
  },
};

module.exports = nextConfig;
