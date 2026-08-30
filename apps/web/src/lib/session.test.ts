import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSessionToken, readSessionToken, storeSessionToken } from "./session";

describe("session token", () => {
  const values = new Map<string, string>();

  beforeEach(() => {
    values.clear();
    const sessionStorage = {
      getItem: vi.fn((key: string) => values.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => values.set(key, value)),
      removeItem: vi.fn((key: string) => values.delete(key)),
    } as unknown as Storage;
    vi.stubGlobal("window", { sessionStorage });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("menghapus token lokal saat pengguna logout", () => {
    storeSessionToken("synthetic-session-token");
    expect(readSessionToken()).toBe("synthetic-session-token");

    clearSessionToken();

    expect(readSessionToken()).toBeNull();
  });
});
