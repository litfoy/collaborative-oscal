import Link from "next/link";
import { ApiError, ERROR_MESSAGES } from "@/lib/errors";

export function ApiProblem({ error }: { error: unknown }) {
  const kind = error instanceof ApiError ? error.kind : "unavailable";
  return (
    <div role="alert" className="alert">
      <p>
        <strong>
          {kind === "forbidden"
            ? "Access denied"
            : kind === "session_expired"
              ? "Session expired"
              : kind === "not_found"
                ? "Not found"
                : "Something went wrong"}
        </strong>
      </p>
      <p>{ERROR_MESSAGES[kind]}</p>
      {kind === "session_expired" ? (
        <p>
          <a className="button" href="/auth/login">
            Sign in again
          </a>
        </p>
      ) : (
        <p>
          <Link href="/">Back to workspaces</Link>
        </p>
      )}
    </div>
  );
}
