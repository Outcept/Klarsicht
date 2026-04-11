/**
 * OIDC auth for the Klarsicht dashboard.
 *
 * Two modes, picked at runtime via /api/auth/config:
 *  - BFF mode (bff_mode=true): backend handles the OAuth flow, sets a
 *    session cookie. React just calls /api/auth/login and /api/auth/me.
 *  - PKCE mode (bff_mode=false): React handles the flow itself with
 *    oidc-client-ts. Used when no client secret is configured.
 */

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";

interface AuthConfig {
  enabled: boolean;
  issuer_url: string;
  client_id: string;
  scopes: string;
  bff_mode: boolean;
}

interface SimpleUser {
  sub?: string;
  email?: string;
  name?: string;
}

interface AuthContextValue {
  enabled: boolean;
  user: User | SimpleUser | null;
  loading: boolean;
  error: string | null;
  login: () => void;
  logout: () => void;
  token: string | null;
}

const AuthContext = createContext<AuthContextValue>({
  enabled: false,
  user: null,
  loading: true,
  error: null,
  login: () => {},
  logout: () => {},
  token: null,
});

let userManager: UserManager | null = null;
let bffMode = false;
let appBasename = "/";

function buildUserManager(config: AuthConfig, basename: string): UserManager {
  const cleanBase = basename === "/" ? "" : basename;
  return new UserManager({
    authority: config.issuer_url,
    client_id: config.client_id,
    redirect_uri: `${window.location.origin}${cleanBase}/oauth2/callback`,
    post_logout_redirect_uri: `${window.location.origin}${cleanBase}/`,
    response_type: "code",
    scope: config.scopes || "openid profile email",
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    automaticSilentRenew: true,
    loadUserInfo: true,
  });
}

export function AuthProvider({ children, basename = "/" }: { children: ReactNode; basename?: string }) {
  appBasename = basename;
  const [user, setUser] = useState<User | SimpleUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const resp = await fetch("/api/auth/config");
        const config: AuthConfig = await resp.json();

        if (!config.enabled) {
          setEnabled(false);
          setLoading(false);
          return;
        }

        setEnabled(true);
        bffMode = config.bff_mode;

        if (bffMode) {
          // Backend handles OAuth — just check if we have a session
          const meResp = await fetch("/api/auth/me");
          if (meResp.ok) {
            const me = await meResp.json();
            if (me.authenticated) {
              setUser({ sub: me.sub, email: me.email, name: me.name });
            }
          }
        } else {
          // SPA PKCE flow
          userManager = buildUserManager(config, appBasename);
          const cleanBase = appBasename === "/" ? "" : appBasename;
          const callbackPath = `${cleanBase}/oauth2/callback`;
          const homePath = `${cleanBase}/`;

          if (window.location.pathname === callbackPath) {
            try {
              await userManager.signinRedirectCallback();
              window.location.replace(homePath);
              return;
            } catch (e) {
              console.error("OIDC callback failed", e);
              setError(e instanceof Error ? e.message : String(e));
            }
          } else {
            const u = await userManager.getUser();
            setUser(u && !u.expired ? u : null);
          }

          userManager.events.addUserLoaded((u) => setUser(u));
          userManager.events.addUserUnloaded(() => setUser(null));
          userManager.events.addAccessTokenExpired(() => setUser(null));
        }
      } catch (e) {
        console.error("Auth init failed", e);
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = () => {
    if (bffMode) {
      window.location.href = "/api/auth/login";
    } else if (userManager) {
      userManager.signinRedirect();
    }
  };

  const logout = () => {
    if (bffMode) {
      fetch("/api/auth/logout", { method: "POST" }).then(() => {
        setUser(null);
        window.location.href = "/";
      });
    } else if (userManager) {
      userManager.signoutRedirect();
    }
  };

  const token = bffMode ? null : (user as User | null)?.access_token ?? null;

  return (
    <AuthContext.Provider
      value={{ enabled, user, loading, error, login, logout, token }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

/**
 * Drop-in fetch replacement.
 * - BFF mode: include cookies (credentials: 'include').
 * - PKCE mode: add Bearer token from oidc-client-ts.
 */
export async function authFetch(input: RequestInfo, init: RequestInit = {}): Promise<Response> {
  if (bffMode) {
    return fetch(input, { ...init, credentials: "include" });
  }
  if (userManager) {
    const u = await userManager.getUser();
    if (u && !u.expired) {
      init.headers = {
        ...(init.headers || {}),
        Authorization: `Bearer ${u.access_token}`,
      };
    }
  }
  return fetch(input, init);
}
