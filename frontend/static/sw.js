/**
 * Caledonia Taxi — Service Worker
 * Handles Web Push notifications for drivers (works even when app is closed).
 */

const CACHE_NAME = 'ct-driver-v1';

// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

// ── Push Event ────────────────────────────────────────────────────────────────
self.addEventListener('push', event => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: 'Caledonia Taxi', body: event.data ? event.data.text() : 'New ride request!' };
  }

  const title   = data.title   || '🚕 New Ride Request!';
  const options = {
    body:    data.body    || 'You have a new fare waiting. Open the app to accept.',
    icon:    '/static/images/taxi-icon.png',
    badge:   '/static/images/taxi-icon.png',
    tag:     'new-ride-' + (data.booking_id || Date.now()),
    renotify: true,
    requireInteraction: true,   // stays until dismissed
    vibrate: [300, 100, 300, 100, 300],
    data: {
      url:        '/driver',
      booking_id: data.booking_id || null,
    },
    actions: [
      { action: 'open', title: '📲 Open App' },
      { action: 'dismiss', title: 'Dismiss' },
    ],
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// ── Notification Click ────────────────────────────────────────────────────────
self.addEventListener('notificationclick', event => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  const targetUrl = (event.notification.data && event.notification.data.url) || '/driver';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      // If driver app is already open — focus it
      for (const client of clientList) {
        if (client.url.includes('/driver') && 'focus' in client) {
          return client.focus();
        }
      }
      // Otherwise open a new window
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});

// ── Message from page ─────────────────────────────────────────────────────────
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
