export type OidcCallback = {
  code: string | null;
  error: string | null;
};

type CallbackGuard = {
  current: boolean;
};

export function claimOidcCallback(
  hash: string,
  guard: CallbackGuard,
): OidcCallback | null {
  if (guard.current) return null;
  const fragment = new URLSearchParams(hash.replace(/^#/, ""));
  const code = fragment.get("oidc_code");
  const error = fragment.get("oidc_error");
  if (!code && !error) return null;
  guard.current = true;
  return { code, error };
}
