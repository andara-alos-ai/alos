import { describe, expect, it } from "vitest";

import { claimOidcCallback } from "./oidc-callback";

describe("claimOidcCallback", () => {
  it("tidak mengklaim URL tanpa callback OIDC", () => {
    const guard = { current: false };

    expect(claimOidcCallback("", guard)).toBeNull();
    expect(guard.current).toBe(false);
  });

  it("hanya memproses satu callback saat effect dijalankan ulang oleh Strict Mode", () => {
    const guard = { current: false };

    expect(claimOidcCallback("#oidc_code=one-time-code", guard)).toEqual({
      code: "one-time-code",
      error: null,
    });
    expect(claimOidcCallback("#oidc_code=one-time-code", guard)).toBeNull();
    expect(guard.current).toBe(true);
  });

  it("mengenali callback kegagalan provider", () => {
    const guard = { current: false };

    expect(claimOidcCallback("#oidc_error=access_denied", guard)).toEqual({
      code: null,
      error: "access_denied",
    });
  });
});
