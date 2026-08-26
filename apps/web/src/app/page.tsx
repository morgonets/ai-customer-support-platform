const foundationItems = [
  "Next.js and FastAPI foundations",
  "Strict linting, typing, and tests",
  "Containerized PostgreSQL with pgvector",
  "Independent frontend and backend CI",
] as const;

export default function Home() {
  return (
    <main>
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">Milestone M0 · Foundation</p>
        <h1 id="page-title">AI Customer Support Platform</h1>
        <p className="summary">
          A production-oriented base for grounded, multi-tenant customer support across web chat and
          messaging channels.
        </p>
        <div className="status" role="status">
          Product capabilities are intentionally not implemented yet.
        </div>
      </section>

      <section className="foundation" aria-labelledby="foundation-title">
        <div>
          <p className="eyebrow">Current scope</p>
          <h2 id="foundation-title">A reliable place to build from</h2>
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
