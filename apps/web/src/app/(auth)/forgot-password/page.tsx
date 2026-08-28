import Link from "next/link";

import { requestPasswordReset } from "../actions";

interface ForgotPasswordPageProps {
  searchParams: Promise<{ sent?: string }>;
}

export default async function ForgotPasswordPage({ searchParams }: ForgotPasswordPageProps) {
  const { sent } = await searchParams;
  return (
    <main className="auth-layout">
      <section className="auth-card" aria-labelledby="recovery-title">
        <Link className="brand-link" href="/">
          Support Platform
        </Link>
        <h1 id="recovery-title">Reset your password</h1>
        {sent === "true" ? (
          <p role="status">If an account exists for that email, a recovery link has been sent.</p>
        ) : (
          <form action={requestPasswordReset} className="stack-form">
            <label htmlFor="email">Email</label>
            <input id="email" name="email" type="email" autoComplete="email" required />
            <button type="submit">Send recovery link</button>
          </form>
        )}
        <Link href="/login">Back to sign in</Link>
      </section>
    </main>
  );
}
