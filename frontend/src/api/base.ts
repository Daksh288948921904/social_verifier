// In local dev this is empty and every /api call goes through the Vite proxy
// (see vite.config.ts) to localhost:8787. In production, if the frontend is
// deployed separately from the backend (e.g. Vercel + Render), set
// VITE_API_BASE at build time to the backend's full origin, e.g.
// "https://live-cutter-backend.onrender.com". If both are deployed on the
// same Render service/domain, leave it unset.
export const API_BASE = import.meta.env.VITE_API_BASE ?? ''

// For plain <img src>/<video src>/<a href> URLs, which bypass client.ts
// entirely and can't go through fetch()'s credentials/headers handling.
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

export function wsBase(): string {
  if (API_BASE) return API_BASE.replace(/^http/, 'ws')
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}`
}
