import type { SupabaseClient } from "@supabase/supabase-js";

export interface AuthenticatedIdentity {
  email: string | null;
  userId: string;
}

export async function getAuthenticatedIdentity(
  client: SupabaseClient,
): Promise<AuthenticatedIdentity | null> {
  const { data, error } = await client.auth.getClaims();
  if (error || data === null) {
    return null;
  }

  const { email, sub } = data.claims;
  if (typeof sub !== "string" || sub === "") {
    return null;
  }
  return {
    userId: sub,
    email: typeof email === "string" ? email : null,
  };
}
