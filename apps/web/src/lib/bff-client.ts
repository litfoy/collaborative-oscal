import { ApiError, ERROR_MESSAGES, kindForStatus } from "./errors";

/** Browser-side client for the same-origin BFF. It never sees any token. */
export async function bffGet<T>(
  path: string,
  query?: Record<string, string | number | undefined>,
  signal?: AbortSignal,
): Promise<T> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const suffix = search.size > 0 ? `?${search.toString()}` : "";
  let response: Response;
  try {
    response = await fetch(`/bff/${path}${suffix}`, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("unavailable", 0, ERROR_MESSAGES.unavailable);
  }
  if (!response.ok) {
    const parsed = await parseErrorResponse(response);
    const kind = classifyError(response.status, parsed.detail);
    throw new ApiError(
      kind,
      response.status,
      parsed.message || ERROR_MESSAGES[kind],
      parsed.detail,
    );
  }
  return (await response.json()) as T;
}

export function bffWrite<T>(method: "POST" | "PUT", path: string, body: unknown): Promise<T>;
export function bffWrite(method: "DELETE", path: string, body: unknown): Promise<void>;
export async function bffWrite<T>(
  method: "POST" | "PUT" | "DELETE",
  path: string,
  body: unknown,
): Promise<T | void> {
  let response: Response;
  try {
    response = await fetch(`/bff/${path}`, {
      method,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("unavailable", 0, ERROR_MESSAGES.unavailable);
  }
  if (!response.ok) {
    const parsed = await parseErrorResponse(response);
    const kind = classifyError(response.status, parsed.detail);
    throw new ApiError(
      kind,
      response.status,
      parsed.message || ERROR_MESSAGES[kind],
      parsed.detail,
    );
  }
  if (response.status === 204) return;
  return (await response.json()) as T;
}

async function parseErrorResponse(
  response: Response,
): Promise<{ message: string; detail?: unknown }> {
  try {
    const problem = (await response.json()) as { detail?: unknown };
    if (typeof problem.detail === "string") return { message: problem.detail };
    if (problem.detail !== undefined) {
      return { message: "", detail: problem.detail };
    }
  } catch {
    // Keep the standard status message when the proxy did not return JSON.
  }
  return { message: "" };
}

function classifyError(status: number, detail?: unknown): ApiError["kind"] {
  if (status !== 409) return kindForStatus(status);
  if (
    detail &&
    typeof detail === "object" &&
    "code" in detail &&
    (detail as { code?: unknown }).code === "stale_update"
  ) {
    return "stale_update";
  }
  return "conflict";
}
