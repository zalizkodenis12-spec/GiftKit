const CACHE_NAME = 'giftkit-static-v2';
const PRECACHE_URLS = [
  '/',
  '/manifest.webmanifest',
  '/giftkit-logo.png',
  '/icon-192.png',
  '/icon-512.png',
  '/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS).catch(() => undefined))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== CACHE_NAME)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Network-first for API and WebSocket paths — never cache stale API errors
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) {
    event.respondWith(fetch(request));
    return;
  }

  // Navigation requests: network-first with cached shell fallback
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put('/', copy)).catch(() => undefined);
          }
          return response;
        })
        .catch(() => caches.match('/')),
    );
    return;
  }

  // Static assets & icons: stale-while-revalidate
  const isStaticAsset =
    url.pathname.startsWith('/assets/') ||
    /\.(?:png|jpg|jpeg|webp|svg|ico|css|js|woff2|webmanifest)$/i.test(url.pathname);

  if (isStaticAsset) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) =>
        cache.match(request).then((cached) => {
          const networkPromise = fetch(request)
            .then((response) => {
              if (response && response.ok) {
                cache.put(request, response.clone()).catch(() => undefined);
              }
              return response;
            })
            .catch(() => cached);

          return cached || networkPromise;
        }),
      ),
    );
  }
});
