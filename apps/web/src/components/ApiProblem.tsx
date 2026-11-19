// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiError } from "@/lib/errors";
import { ApiProblemDetails } from "./ApiProblemDetails";

export function ApiProblem({ error }: { error: unknown }) {
  const kind = error instanceof ApiError ? error.kind : "unavailable";
  return <ApiProblemDetails kind={kind} />;
}
