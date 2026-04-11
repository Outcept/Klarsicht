/**
 * OIDC PKCE auth for the Klarsicht dashboard.
 *
 * Reads runtime config from /api/auth/config (so the same build can be
 * deployed against any OIDC provider). Stores tokens in sessionStorage,
 * adds Authorization: Bearer header to fetch via authFetch().
 */

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";

interface AuthConfig {
  enabled: boolean;
  issuer_url: string;
  client_id: string;
  scopes: string;
}

interface AuthContextValue {
  enabled: boolean;
  user: User | null;
  loading: boolean;
  login: () => void;
  logout: () => void;
  token: string | null;
}

const AuthContext = createContext<AuthContextValue>({
  enabled: false,
  user: null,
  loading: true,
  login: () => {},
  logout: () => {},
  token: null,
});

let userManager: UserManager | null = null;
let appBasename = "/";

function buildUserManager(config: AuthConfig, basename: string): UserManager {
  const cleanBase = basename === "/" ? "" : basename;
  return new UserManager({
    authority: config.issuer_url,
    client_id: config.client_id,
    redirect_uri: `${window.location.origin}${cleanBase}/callback`,
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
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);

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
        userManager = buildUserManager(config, appBasename);

        const cleanBase = appBasename === "/" ? "" : appBasename;
        const callbackPath = `${cleanBase}/callback`;
        const homePath = `${cleanBase}/`;

        // Handle the OIDC redirect callback
        if (window.location.pathname === callbackPath) {
          try {
            const u = await userManager.signinRedirectCallback();
            setUser(u);
            window.history.replaceState({}, document.title, homePath);
          } catch (e) {
            console.error("OIDC callback failed", e);
          }
        } else {
          const u = await userManager.getUser();
          setUser(u && !u.expired ? u : null);
        }

        // React to silent renew
        userManager.events.addUserLoaded((u) => setUser(u));
        userManager.events.addUserUnloaded(() => setUser(null));
        userManager.events.addAccessTokenExpired(() => setUser(null));
      } catch (e) {
        console.error("Auth init failed", e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = () => {
    if (userManager) userManager.signinRedirect();
  };

  const logout = () => {
    if (userManager) userManager.signoutRedirect();
  };

  return (
    <AuthContext.Provider
      value={{
        enabled,
        user,
        loading,
        login,
        logout,
        token: user?.access_token ?? null,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

/**
 * Drop-in fetch replacement that adds the Bearer token when OIDC is enabled.
 * Falls back to plain fetch when auth is disabled.
 */
export async function authFetch(input: RequestInfo, init: RequestInit = {}): Promise<Response> {
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
