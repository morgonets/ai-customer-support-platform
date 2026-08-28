import Link from "next/link";

export default function CheckEmailPage() {
  return (
    <main className="auth-layout">
      <section className="auth-card" aria-labelledby="check-email-title">
        <p className="eyebrow">One more step</p>
        <h1 id="check-email-title">Check your email</h1>
        <p>Use the confirmation link to activate your account. Local messages appear in Mailpit.</p>
        <Link href="/login">Return to sign in</Link>
      </section>
    </main>
  );
}
