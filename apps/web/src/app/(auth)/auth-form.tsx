import type { Route } from "next";
import Link from "next/link";

interface AuthFormProps {
  action: (formData: FormData) => Promise<never>;
  alternateHref: Route;
  alternateLabel: string;
  error: string | null;
  submitLabel: string;
  title: string;
}

export function AuthForm({
  action,
  alternateHref,
  alternateLabel,
  error,
  submitLabel,
  title,
}: AuthFormProps) {
  return (
    <main className="auth-layout">
      <section className="auth-card" aria-labelledby="auth-title">
        <Link className="brand-link" href="/">
          Support Platform
        </Link>
        <h1 id="auth-title">{title}</h1>
        {error === null ? null : (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <form action={action} className="stack-form">
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" autoComplete="email" required />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete={submitLabel === "Create account" ? "new-password" : "current-password"}
            minLength={8}
            required
          />
          <button type="submit">{submitLabel}</button>
        </form>
        <div className="auth-links">
          <Link href={alternateHref}>{alternateLabel}</Link>
          {submitLabel === "Sign in" ? <Link href="/forgot-password">Forgot password?</Link> : null}
        </div>
      </section>
    </main>
  );
}
