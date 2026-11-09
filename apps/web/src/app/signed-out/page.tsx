export default function SignedOutPage() {
  return (
    <main id="main" className="page page-narrow">
      <div className="panel">
        <h1>You have been signed out</h1>
        <p className="muted">Your session on this device has ended.</p>
        <a className="button" href="/auth/login">
          Sign in again
        </a>
      </div>
    </main>
  );
}
