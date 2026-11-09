import { hkdfSync } from "node:crypto";

import { EncryptJWT, jwtDecrypt } from "jose";

export interface SessionData {
  sub: string;
  name?: string;
  email?: string;
  accessToken: string;
  /** Epoch seconds. */
  accessTokenExpiresAt: number;
  refreshToken?: string;
  /** Kept server-side only, to send as id_token_hint on logout. */
  idToken?: string;
  /** Epoch seconds; absolute lifetime of the application session. */
  expiresAt: number;
}

export type SealPurpose = "session" | "flow";

const AUDIENCE: Record<SealPurpose, string> = {
  session: "collaborative-oscal:web-session",
  flow: "collaborative-oscal:web-login-flow",
};

function deriveKey(secret: string, purpose: SealPurpose): Uint8Array {
  const key = hkdfSync(
    "sha256",
    Buffer.from(secret, "utf8"),
    Buffer.from("collaborative-oscal-web", "utf8"),
    Buffer.from(`cookie:${purpose}`, "utf8"),
    32,
  );
  return new Uint8Array(key);
}

/** Encrypts and authenticates a payload as a compact JWE (dir + A256GCM). */
export async function seal(
  payload: object,
  secret: string,
  purpose: SealPurpose,
  lifetimeSeconds: number,
): Promise<string> {
  return new EncryptJWT({ ...payload })
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setAudience(AUDIENCE[purpose])
    .setIssuedAt()
    .setExpirationTime(Math.floor(Date.now() / 1000) + lifetimeSeconds)
    .encrypt(deriveKey(secret, purpose));
}

export async function unseal<T extends object>(
  token: string,
  secret: string,
  purpose: SealPurpose,
): Promise<T | null> {
  try {
    const { payload } = await jwtDecrypt(token, deriveKey(secret, purpose), {
      audience: AUDIENCE[purpose],
      keyManagementAlgorithms: ["dir"],
      contentEncryptionAlgorithms: ["A256GCM"],
    });
    return payload as unknown as T;
  } catch {
    return null;
  }
}

export function isSessionData(value: unknown): value is SessionData {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.sub === "string" &&
    typeof record.accessToken === "string" &&
    typeof record.accessTokenExpiresAt === "number" &&
    typeof record.expiresAt === "number"
  );
}

// Browsers accept ~4096 bytes per cookie; stay well below that per chunk.
export const COOKIE_CHUNK_SIZE = 3600;

export function chunk(value: string, size = COOKIE_CHUNK_SIZE): string[] {
  const chunks: string[] = [];
  for (let index = 0; index < value.length; index += size) {
    chunks.push(value.slice(index, index + size));
  }
  return chunks.length > 0 ? chunks : [""];
}
