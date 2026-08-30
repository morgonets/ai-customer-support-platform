import { redirect } from "next/navigation";

import { getAuthenticatedIdentity } from "@/lib/auth/identity";
import { authErrorMessage } from "@/lib/auth/messages";
import { createServerSupabaseClient } from "@/lib/supabase/server";

import { updatePassword } from "../actions";

interface ResetPasswordPageProps {
  searchParams: Promise<{ error?: string }>;
}

export default async function ResetPasswordPage({ searchParams }: ResetPasswordPageProps) {
  const supabase = await createServerSupabaseClient();
  if ((await getAuthenticatedIdentity(supabase)) === null) {
    redirect("/forgot-password");
  }
  const { error } = await searchParams;
  const message = authErrorMessage(error);
  return (
    <main className="auth-layout">
      <section className="auth-card" aria-labelledby="new-password-title">
        <h1 id="new-password-title">Choose a new password</h1>
        {message === null ? null : (
          <p className="form-error" role="alert">
            {message}
          </p>
        )}
        <form action={updatePassword} className="stack-form">
          <label htmlFor="password">New password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            pattern="(?=.*[A-Za-z])(?=.*\d).{8,}"
            required
          />
          <p className="field-hint">Use at least 8 characters with a letter and a number.</p>
          <button type="submit">Update password</button>
        </form>
      </section>
    </main>
  );
}
