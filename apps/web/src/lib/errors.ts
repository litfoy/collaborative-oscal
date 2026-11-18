export type ApiErrorKind =
  | "session_expired"
  | "forbidden"
  | "not_found"
  | "invalid"
  | "stale_update"
  | "unavailable";

export class ApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    readonly status: number,
    message: string,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return "session_expired";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 400 || status === 422) return "invalid";
  if (status === 409) return "stale_update";
  return "unavailable";
}

export const ERROR_MESSAGES: Record<ApiErrorKind, string> = {
  session_expired: "Your session has expired. Please sign in again.",
  forbidden: "You do not have access to this workspace.",
  not_found: "The requested item could not be found.",
  invalid: "The request was not valid.",
  stale_update: "The Assessment Plan changed in another session.",
  unavailable: "The service is temporarily unavailable. Please try again.",
};

export const ERROR_TRANSLATION_KEYS = {
  session_expired: "errors.session_expired",
  forbidden: "errors.forbidden",
  not_found: "errors.not_found",
  invalid: "errors.invalid",
  stale_update: "errors.stale_update",
  unavailable: "errors.unavailable",
} as const satisfies Record<ApiErrorKind, string>;