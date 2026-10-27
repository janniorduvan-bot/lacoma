(function () {
  'use strict';

  const path = window.location.pathname;
  let page = '';
  if (path === '/') page = 'home';
  else if (path === '/elpunto') page = 'elpunto';
  else if (path === '/contacto' || path === '/resenas') page = 'contact';
  else if (path === '/juegos') page = 'games';
  else if (path === '/foros') page = 'forums';
  else if (path.startsWith('/foros/')) page = 'game_forum';
  else if (path === '/terminos') page = 'terms';
  else if (path === '/privacidad') page = 'privacy';
  if (!page) return;

  const endpoint = '/api/metrics/performance';
  const metrics = {};
  const supportedEntries = window.PerformanceObserver &&
    Array.isArray(PerformanceObserver.supportedEntryTypes)
    ? PerformanceObserver.supportedEntryTypes
    : [];
  let clsWindowValue = 0;
  let clsWindowStart = 0;
  let clsWindowLast = 0;
  let clsValue = 0;
  const interactionDurations = new Map();
  let sentVitals = false;

  function send(data) {
    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page: page, metrics: data }),
      keepalive: true,
      credentials: 'omit'
    }).catch(function () {});
  }

  send({ page_view: 1 });

  const navigation = performance.getEntriesByType('navigation')[0];
  if (navigation && navigation.responseStart > 0) {
    metrics.ttfb = Math.round(navigation.responseStart - navigation.requestStart);
  }
  const firstPaint = performance.getEntriesByName('first-contentful-paint')[0];
  if (firstPaint) metrics.fcp = Math.round(firstPaint.startTime);

  if (supportedEntries.includes('largest-contentful-paint')) {
    new PerformanceObserver(function (list) {
      const entries = list.getEntries();
      if (entries.length) metrics.lcp = Math.round(entries[entries.length - 1].startTime);
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  }

  if (supportedEntries.includes('layout-shift')) {
    new PerformanceObserver(function (list) {
      list.getEntries().forEach(function (entry) {
        if (entry.hadRecentInput) return;
        const time = entry.startTime;
        if (!clsWindowLast || time - clsWindowLast > 1000 || time - clsWindowStart > 5000) {
          clsWindowValue = 0;
          clsWindowStart = time;
        }
        if (time - clsWindowStart <= 5000) {
          clsWindowValue += entry.value;
          clsValue = Math.max(clsValue, clsWindowValue);
        }
        clsWindowLast = time;
      });
    }).observe({ type: 'layout-shift', buffered: true });
  }

  if (supportedEntries.includes('event')) {
    new PerformanceObserver(function (list) {
      list.getEntries().forEach(function (entry) {
        if (!entry.interactionId) return;
        const duration = interactionDurations.get(entry.interactionId) || 0;
        interactionDurations.set(entry.interactionId, Math.max(duration, entry.duration));
      });
    }).observe({ type: 'event', buffered: true, durationThreshold: 16 });
  }

  function sendVitals() {
    if (sentVitals) return;
    sentVitals = true;
    if (clsValue > 0) metrics.cls = Number(clsValue.toFixed(4));
    if (interactionDurations.size) {
      const interactionValues = Array.from(interactionDurations.values()).sort(function (a, b) {
        return b - a;
      });
      metrics.inp = Math.round(interactionValues[Math.floor(interactionValues.length * 0.02)]);
    }
    if (Object.keys(metrics).length) send(metrics);
  }

  window.addEventListener('pagehide', sendVitals, { once: true });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') sendVitals();
  }, { once: true });
})();
