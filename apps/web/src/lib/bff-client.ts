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
    const kind = kindForStatus(response.status);
    throw new ApiError(kind, response.status, await responseMessage(response, kind));
  }
  return (await response.json()) as T;
}

export async function bffWrite<T>(
  method: "POST" | "PUT",
  path: string,
  body: unknown,
): Promise<T> {
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
    const kind = kindForStatus(response.status);
    throw new ApiError(kind, response.status, await responseMessage(response, kind));
  }
  return (await response.json()) as T;
}

async function responseMessage(response: Response, kind: ApiError["kind"]): Promise<string> {
  try {
    const problem = (await response.json()) as { detail?: unknown };
    if (typeof problem.detail === "string") return problem.detail;
  } catch {
    // Keep the standard status message when the proxy did not return JSON.
  }
  return ERROR_MESSAGES[kind];
}
