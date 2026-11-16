import { ApiError } from "@/lib/errors";
import { ApiProblemDetails } from "./ApiProblemDetails";

export function ApiProblem({ error }: { error: unknown }) {
  const kind = error instanceof ApiError ? error.kind : "unavailable";
  return <ApiProblemDetails kind={kind} />;
}
