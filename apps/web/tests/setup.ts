// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ get: () => undefined })),
}));

afterEach(() => {
  cleanup();
});
