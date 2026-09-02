import { afterEach, describe, expect, it, vi } from "vitest";

import { COOKIE_SESSION_MARKER, readCsrfToken } from "./session";

describe("browser session", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("menggunakan marker non-rahasia untuk sesi cookie", () => {
    expect(COOKIE_SESSION_MARKER).toBe("__alos_cookie_session__");
  });

  it("membaca CSRF token dari cookie document", () => {
    vi.stubGlobal("document", { cookie: "other=1; alos_csrf=csrf-test-token-123; foo=bar" });
    expect(readCsrfToken()).toBe("csrf-test-token-123");
  });
});
