/** @type {import('next').NextConfig} */

const withBundleAnalyzer = require('@next/bundle-analyzer')({
  enabled: process.env.ANALYZE === 'true',
});

const nextConfig = {
  reactStrictMode: true,
  // swcMinify is enabled by default in Next.js 16, no need to specify
  // Remove console logs in production for better mobile performance
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production' ? {
      exclude: ['error', 'warn']
    } : false
  },
  // Disable Next.js development indicators (the "N" button)
  devIndicators: {
    buildActivity: false,
    buildActivityPosition: 'bottom-right',
  },
  // Optimize images
  images: {
    formats: ['image/avif', 'image/webp'],
    deviceSizes: [640, 750, 828, 1080, 1200],
    imageSizes: [16, 32, 48, 64, 96],
  },
  // No env vars needed - API URL is auto-detected at runtime in the browser

  // CRITICAL (mobile/Capacitor deploy bug): Next prerenders pages with
  // `Cache-Control: s-maxage=31536000`. WKWebView/mobile browsers then cache
  // the HTML document for a year; it hard-references the OLD content-hashed
  // /_next/static chunks, so container rebuilds never reach the device — the
  // UI stays frozen at the build that was cached. Force the HTML document to
  // always revalidate (cheap: ETag → 304 when unchanged, fresh chunk refs on
  // deploy). /_next/static is content-hashed and excluded so it stays
  // immutable (Next sets that itself; we must NOT clobber it).
  async headers() {
    return [
      {
        source: '/:path((?!_next/static/).*)',
        headers: [
          { key: 'Cache-Control', value: 'no-cache, must-revalidate' },
        ],
      },
    ]
  },
}

module.exports = withBundleAnalyzer(nextConfig)