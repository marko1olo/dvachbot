const CACHE_VERSION = 'tgach-v3';
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `dynamic-${CACHE_VERSION}`;
const IMAGE_CACHE = `images-${CACHE_VERSION}`;

// Лимит кэша картинок (чтобы телефон не лопнул)
const MAX_IMAGES = 50;

const STATIC_ASSETS = [
    '/',
    '/static/offline.html',
    '/static/css/style.css',
    '/static/js/main.js',
    '/static/favicon.ico',
    '/static/logo.png',
    '/static/sounds/not.mp3',
    '/static/fonts/Roboto.woff2',
    '/static/fonts/RobotoSlab.woff2'
];

// --- INSTALL (Безопасная версия с логами) ---
self.addEventListener('install', (event) => {
    self.skipWaiting(); 
    event.waitUntil(
        caches.open(STATIC_CACHE).then(async (cache) => {
            // Пытаемся добавить всё разом
            try {
                return await cache.addAll(STATIC_ASSETS);
            } catch (e) {
                console.error('SW: Ошибка при кэшировании статики. Ищу битый файл...');
                // Если ошибка - перебираем по одному, чтобы найти виновника
                for (const url of STATIC_ASSETS) {
                    try {
                        const res = await fetch(url);
                        if (!res.ok) throw new Error(res.statusText);
                        await cache.put(url, res);
                    } catch (err) {
                        console.error(`❌ SW: Не найден файл: ${url} (${err})`);
                    }
                }
            }
        })
    );
});

// --- ACTIVATE (Cleanup) ---
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== STATIC_CACHE && key !== DYNAMIC_CACHE && key !== IMAGE_CACHE) {
                        return caches.delete(key);
                    }
                })
            );
        })
    );
    return self.clients.claim();
});

// --- FETCH STRATEGIES ---
self.addEventListener('fetch', (event) => {
    const req = event.request;
    const url = new URL(req.url);

    // 1. Игнорируем API, WS и Админку (всегда сеть)
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/') || url.pathname.startsWith('/admin')) {
        return;
    }

    // 2. СТАТИКА (Fonts, CSS, JS) -> Cache First (Скорость!)
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(req).then((cached) => {
                return cached || fetch(req).then((networkResp) => {
                    return caches.open(STATIC_CACHE).then((cache) => {
                        cache.put(req, networkResp.clone());
                        return networkResp;
                    });
                });
            })
        );
        return;
    }

    // 3. КАРТИНКИ/ФАЙЛЫ (/files/...) -> Cache First + Limit
    if (url.pathname.startsWith('/files/')) {
        event.respondWith(
            caches.match(req).then((cached) => {
                if (cached) return cached;

                return fetch(req).then((networkResp) => {
                    return caches.open(IMAGE_CACHE).then((cache) => {
                        cache.put(req, networkResp.clone());
                        trimCache(IMAGE_CACHE, MAX_IMAGES); // Чистим старое
                        return networkResp;
                    });
                });
            })
        );
        return;
    }

    // 4. СТРАНИЦЫ (HTML) -> Network First -> Cache -> Offline Page
    if (req.headers.get('accept').includes('text/html')) {
        event.respondWith(
            fetch(req)
                .then((networkResp) => {
                    return caches.open(DYNAMIC_CACHE).then((cache) => {
                        // Кэшируем копию страницы, чтобы она была доступна офлайн
                        cache.put(req, networkResp.clone());
                        return networkResp;
                    });
                })
                .catch(() => {
                    // Если нет сети, ищем в кэше
                    return caches.match(req).then((cached) => {
                        if (cached) return cached;
                        // Если нет в кэше, отдаем страницу заглушку
                        return caches.match('/static/offline.html');
                    });
                })
        );
    }
});

// Хелпер: Удаление старых записей из кэша
function trimCache(cacheName, maxItems) {
    caches.open(cacheName).then((cache) => {
        cache.keys().then((keys) => {
            if (keys.length > maxItems) {
                // Удаляем самый старый (первый) и рекурсивно вызываем снова
                cache.delete(keys[0]).then(() => trimCache(cacheName, maxItems));
            }
        });
    });
}