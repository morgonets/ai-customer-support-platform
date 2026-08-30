import Link from "next/link";
import { redirect } from "next/navigation";

import { logout } from "@/app/(auth)/actions";
import { getAuthenticatedIdentity } from "@/lib/auth/identity";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export default async function ApplicationLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const supabase = await createServerSupabaseClient();
  const identity = await getAuthenticatedIdentity(supabase);
  if (identity === null) {
    redirect("/login");
  }

  return (
    <div className="application-shell">
      <header className="application-header">
        <Link className="brand-link" href="/app">
          Support Platform
        </Link>
        <div className="account-state">
          <span>{identity.email ?? identity.userId}</span>
          <form action={logout}>
            <button className="secondary-button" type="submit">
              Sign out
            </button>
          </form>
        </div>
      </header>
      {children}
    </div>
  );
}
