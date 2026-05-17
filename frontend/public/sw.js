// Service Worker for Kahani - Minimal caching for essential assets only
// API responses are NOT cached to prevent stale data issues
const CACHE_NAME = 'kahani-v2';

// Only cache truly static assets
const STATIC_CACHE_URLS = [
  // Note: Next.js pages are dynamically generated, so we don't cache them
  // Only cache assets that are truly static
];

// Install event - cache essential static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_CACHE_URLS);
    }).catch((error) => {
      console.warn('[SW] Failed to cache static assets:', error);
    })
  );
  // Skip waiting to activate immediately
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => {
            console.log('[SW] Deleting old cache:', name);
            return caches.delete(name);
          })
      );
    })
  );
  // Take control of all clients immediately
  self.clients.claim();
});

// Fetch event - network-first for everything, minimal caching
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests (POST, PUT, DELETE, etc.) - let them pass through
  if (request.method !== 'GET') {
    return;
  }

  // Skip external URLs entirely
  if (url.origin !== location.origin) {
    return;
  }

  // Skip API requests entirely - do NOT intercept or cache them
  // This prevents the service worker from interfering with API calls
  // which was causing issues when the backend became unresponsive
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // Skip WebSocket upgrade requests
  if (url.pathname.startsWith('/ws/')) {
    return;
  }

  // Skip streaming endpoints
  if (url.pathname.includes('/stream') || url.pathname.includes('/streaming')) {
    return;
  }

  // Skip source maps
  if (url.pathname.endsWith('.map')) {
    return;
  }

  // For static assets (JS, CSS, images), use network-first with cache fallback
  // This ensures users always get the latest version when online
  if (isStaticAsset(url.pathname)) {
    event.respondWith(
      fetch(request)
        .then((networkResponse) => {
          // Only cache successful responses
          if (networkResponse.ok) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseToCache);
            });
          }
          return networkResponse;
        })
        .catch(() => {
          // Network failed, try cache
          return caches.match(request).then((cachedResponse) => {
            if (cachedResponse) {
              return cachedResponse;
            }
            // No cache, return a simple offline response
            return new Response('Offline', { status: 503, statusText: 'Offline' });
          });
        })
    );
    return;
  }

  // For HTML pages (Next.js routes), always go to network
  // Don't cache dynamic pages to prevent stale UI
  // Let the request pass through without interception
});

/**
 * Check if a path is a static asset that can be safely cached
 */
function isStaticAsset(pathname) {
  const staticExtensions = [
    '.js',
    '.css',
    '.png',
    '.jpg',
    '.jpeg',
    '.gif',
    '.webp',
    '.svg',
    '.ico',
    '.woff',
    '.woff2',
    '.ttf',
    '.eot'
  ];
  
  // Check if it's a Next.js static asset
  if (pathname.startsWith('/_next/static/')) {
    return true;
  }
  
  // Check file extensions
  return staticExtensions.some(ext => pathname.endsWith(ext));
}
