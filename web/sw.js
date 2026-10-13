// Cache the public shell only. Never cache recordings, private API data or session keys.
const CACHE='cunbo-yunjian-shell-v6';
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(['/','/style.css?v=6','/app.js?v=6','/i18n.js?v=6','/icon.svg','/manifest.webmanifest'])));self.skipWaiting()});
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{if(event.request.method!=='GET'||new URL(event.request.url).origin!==self.location.origin||new URL(event.request.url).pathname.startsWith('/api/'))return;event.respondWith(fetch(event.request).catch(()=>caches.match(event.request)))});
