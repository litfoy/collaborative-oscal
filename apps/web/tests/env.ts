import { resetConfigForTests } from "@/lib/config";
import { vi } from "vitest";

export const TEST_SECRET = "test-session-secret-0123456789abcdef-xyz";

export function stubWebEnv(overrides: Record<string, string> = {}): void {
  const values: Record<string, string> = {
    APP_PUBLIC_URL: "http://localhost:3000",
    OIDC_ISSUER_URL: "http://localhost:8080/realms/test",
    WEB_OIDC_CLIENT_ID: "web-client",
    SESSION_SECRET: TEST_SECRET,
    API_BASE_URL: "http://api.test",
    ...overrides,
  };
  for (const [key, value] of Object.entries(values)) vi.stubEnv(key, value);
  resetConfigForTests();
}
