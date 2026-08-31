// Dev-only login curtain. This is NOT authentication.
//
// There is no server middleware behind it. The Go API on :8300 is
// unauthenticated, so anything that talks to it directly — curl, a second
// browser tab, a script — bypasses this gate entirely. It exists only so the
// demo UI has a front door.

export const DEV_USER = "dev"; // dev-only, not a secret
export const DEV_PASS = "dev"; // dev-only, not a secret
export const AUTH_KEY = "stacks.auth";
export const AUTH_EVENT = "stacks-auth-changed";

export function isAuthenticated(): boolean {
  try {
    return window.sessionStorage.getItem(AUTH_KEY) === "1";
  } catch {
    return false;
  }
}

export function login(user: string, pass: string): boolean {
  if (user !== DEV_USER || pass !== DEV_PASS) {
    return false;
  }
  window.sessionStorage.setItem(AUTH_KEY, "1");
  window.dispatchEvent(new CustomEvent(AUTH_EVENT, { detail: { signedIn: true } }));
  return true;
}

export function logout(): void {
  window.sessionStorage.removeItem(AUTH_KEY);
  window.dispatchEvent(new CustomEvent(AUTH_EVENT, { detail: { signedIn: false } }));
}
