/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  // No env vars needed - API URL is auto-detected at runtime in the browser
}

module.exports = nextConfig