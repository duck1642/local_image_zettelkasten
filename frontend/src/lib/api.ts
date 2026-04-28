const API_BASE = 'http://localhost:8000';

let apiKeyPromise: Promise<string> | null = null;

export function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

async function getApiKey() {
  if (!apiKeyPromise) {
    apiKeyPromise = fetch(apiUrl('/api/session-key'))
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load API session key');
        return res.json();
      })
      .then((data) => data.key || '');
  }
  return apiKeyPromise;
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const method = (init.method || 'GET').toUpperCase();
  const headers = new Headers(init.headers || {});
  if (['POST', 'PATCH', 'DELETE'].includes(method)) {
    headers.set('X-LIZ-API-KEY', await getApiKey());
  }
  return fetch(apiUrl(path), { ...init, headers });
}
