import { ApiError, ERROR_MESSAGES, kindForStatus } from "./errors";

/** Browser-side read-only client for the same-origin BFF. It never sees any token. */
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
    throw new ApiError(kind, response.status, ERROR_MESSAGES[kind]);
  }
  return (await response.json()) as T;
}
