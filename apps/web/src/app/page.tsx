"use client";

import { useEffect, useState } from "react";

type HealthStatus = "loading" | "healthy" | "unavailable";

type HealthResponse = {
  status: string;
};

export default function Home() {
  const [status, setStatus] = useState<HealthStatus>("loading");
  const [detail, setDetail] = useState("Checking the API...");

  useEffect(() => {
    const controller = new AbortController();
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

    async function checkHealth() {
      try {
        const response = await fetch(`${apiBaseUrl}/health`, {
          headers: { Accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Backend returned HTTP ${response.status}`);
        }

        const health = (await response.json()) as HealthResponse;
        if (health.status !== "ok") {
          throw new Error("Backend returned an unexpected health status");
        }

        setStatus("healthy");
        setDetail("The API is available.");
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }

        setStatus("unavailable");
        setDetail(error instanceof Error ? error.message : "The API could not be reached.");
      }
    }

    void checkHealth();
    return () => controller.abort();
  }, []);

  return (
    <main>
      <h1>Collaborative OSCAL</h1>
      <p>Open-source GRC platform foundation</p>
      <section aria-labelledby="api-heading">
        <h2 id="api-heading">Backend health</h2>
        <p role="status" aria-live="polite">
          <strong>{status === "healthy" ? "Healthy" : status === "loading" ? "Checking" : "Unavailable"}</strong>
          {": "}
          {detail}
        </p>
      </section>
      <p className="notice">
        This foundation does not yet implement GRC or OSCAL management capabilities.
      </p>
    </main>
  );
}
