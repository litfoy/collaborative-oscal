"use client";

export default function ErrorBoundary({ reset }: { error: Error; reset: () => void }) {
  return (
    <main id="main" className="page page-narrow">
      <div role="alert" className="alert">
        <p>
          <strong>Something went wrong.</strong>
        </p>
        <p>The page could not be displayed. Please try again.</p>
        <button type="button" onClick={reset}>
          Try again
        </button>
      </div>
    </main>
  );
}
