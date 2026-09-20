/**
 * Single-operator identity.
 *
 * There is no login. The backend resolves the owner itself
 * (src/config/owner.py) and the API is published on loopback only, so the
 * browser has nothing to authenticate with and nothing to store.
 *
 * This hook is kept — rather than deleted — because six components consume
 * `{ user, isAuthenticated, isLoading, logout }`. Returning a settled,
 * always-authenticated value lets them all keep working untouched, and means
 * `useRequireAuth()` no longer bounces to a /auth/login page that no longer
 * exists.
 *
 * 單人部署沒有登入流程；此 hook 保留固定回傳值，讓既有六個消費端不需改動，
 * useRequireAuth 也不再導向已刪除的登入頁。
 */

const OWNER = {
  user_id: "owner",
  is_authenticated: true as const,
};

export function useAuth() {
  return {
    user: OWNER,
    isAuthenticated: true,
    isLoading: false,
    error: undefined as unknown,
    logout: async () => {
      /* no session to end in a single-operator deployment */
    },
    mutate: async () => undefined,
  };
}

export function useRequireAuth() {
  return { isAuthenticated: true, isLoading: false };
}
