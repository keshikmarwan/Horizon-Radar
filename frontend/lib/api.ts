const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
const FALLBACK_API_URL = 'http://localhost:8000';
const FALLBACK_USER_ID = process.env.NEXT_PUBLIC_DEMO_USER_ID || 'demo-user';

let cachedUserId: string | null = null;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function resolveUserId(): Promise<string> {
  if (cachedUserId) {
    return cachedUserId;
  }

  try {
    const sessionRes = await fetch('/api/auth/session', { cache: 'no-store' });
    if (sessionRes.ok) {
      const session = await sessionRes.json() as { user?: { email?: string } };
      if (session?.user?.email) {
        cachedUserId = session.user.email;
        return cachedUserId;
      }
    }
  } catch {
    // Ignore and use fallback.
  }

  cachedUserId = FALLBACK_USER_ID;
  return cachedUserId;
}

async function withUserHeaders(init?: HeadersInit): Promise<HeadersInit> {
  const userId = await resolveUserId();
  return {
    'X-User-Id': userId,
    ...(init || {}),
  };
}

async function fetchWithRetry(path: string, init: RequestInit, attempts = 8): Promise<Response> {
  const browserHostApi =
    typeof window !== 'undefined' && window.location?.hostname
      ? `${window.location.protocol}//${window.location.hostname}:8000`
      : '';
  const sameHostPortSwap =
    typeof window !== 'undefined' && window.location?.origin
      ? window.location.origin.replace(/:\d+$/, ':8000')
      : '';
  const urls = [API_URL, browserHostApi, FALLBACK_API_URL].filter((v, i, arr) => Boolean(v) && arr.indexOf(v) === i);
  const resolvedUrls = [sameHostPortSwap, ...urls].filter((v, i, arr) => Boolean(v) && arr.indexOf(v) === i);
  let lastError: unknown = null;

  for (let i = 0; i < attempts; i++) {
    for (const base of resolvedUrls) {
      try {
        const res = await fetch(`${base}${path}`, init);
        return res;
      } catch (err) {
        lastError = err;
      }
    }
    await delay(500);
  }

  throw new Error(`API unreachable for ${path}. Last error: ${String(lastError)}`);
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetchWithRetry(path, {
    cache: 'no-store',
    headers: await withUserHeaders(),
  });
  if (!res.ok) {
    throw new Error(`API GET failed (${res.status}) for ${path}`);
  }
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetchWithRetry(path, {
    method: 'POST',
    headers: await withUserHeaders({ 'Content-Type': 'application/json' }),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    throw new Error(`API POST failed (${res.status}) for ${path}`);
  }
  return res.json() as Promise<T>;
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetchWithRetry(path, {
    method: 'PATCH',
    headers: await withUserHeaders({ 'Content-Type': 'application/json' }),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    throw new Error(`API PATCH failed (${res.status}) for ${path}`);
  }
  return res.json() as Promise<T>;
}

export async function apiPostFormData<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetchWithRetry(path, {
    method: 'POST',
    headers: await withUserHeaders(),
    body: formData,
  });
  if (!res.ok) {
    throw new Error(`API POST(form-data) failed (${res.status}) for ${path}`);
  }
  return res.json() as Promise<T>;
}
