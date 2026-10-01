// Fetch fresh assets. Never cache API responses or credentials.
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('beldin-mobile-')).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
