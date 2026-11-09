import Link from "next/link";
export default function NotFound() {
  return (
    <main id="main" className="page page-narrow">
      <div className="panel">
        <h1>Page not found</h1>
        <Link href="/">Back to workspaces</Link>
      </div>
    </main>
  );
}
