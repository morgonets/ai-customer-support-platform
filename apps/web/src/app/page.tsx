import Link from "next/link";

const foundationItems = [
  "Supabase email and password authentication",
  "Protected application routes",
  "FastAPI bearer-token verification",
  "PostgreSQL-backed organization roles",
] as const;

export default function Home() {
  return (
    <main className="landing-main">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">Milestone M1 · Authentication &amp; Organizations</p>
        <h1 id="page-title">AI Customer Support Platform</h1>
        <p className="summary">
          Secure identity and workspace boundaries for a production-oriented customer support
          platform.
        </p>
        <div className="hero-actions">
          <Link className="primary-link" href="/register">
            Create account
          </Link>
          <Link className="secondary-link" href="/login">
            Sign in
          </Link>
        </div>
      </section>

      <section className="foundation" aria-labelledby="foundation-title">
        <div>
          <p className="eyebrow">Current foundation</p>
          <h2 id="foundation-title">Tenant boundaries before product features</h2>
        </div>
        <ul>
          {foundationItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </main>
  );
}
