// SPA mode: adapter-static + fallback HTML produces a single index.html that
// hydrates client-side. Mapbox GL JS touches `window` on import, so SSR is off.
export const ssr = false;
export const prerender = true;
export const trailingSlash = 'never';
