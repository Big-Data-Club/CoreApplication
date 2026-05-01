/**
 * Shared Bearer-token cache for API clients.
 *
 * Reads the NextAuth session once, then serves the access token from memory
 * for TOKEN_CACHE_MS.  The cache is automatically cleared on 401 so the next
 * outgoing request refetches.
 */

let _cachedToken: string | null = null;
let _tokenFetchedAt = 0;
const TOKEN_CACHE_MS = 5 * 60 * 1000; // 5 minutes

export async function getAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;

  const now = Date.now();
  if (_cachedToken && now - _tokenFetchedAt < TOKEN_CACHE_MS) {
    return _cachedToken;
  }

  try {
    const { getSession } = await import("next-auth/react");
    const session = await getSession();
    _cachedToken = (session as any)?.accessToken ?? null;
    _tokenFetchedAt = now;
  } catch {
    // keep stale token on transient network errors
  }

  return _cachedToken;
}

export function clearAccessTokenCache() {
  _cachedToken = null;
  _tokenFetchedAt = 0;
}
