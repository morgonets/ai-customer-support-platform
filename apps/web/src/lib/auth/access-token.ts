import "server-only";

import { getAuthenticatedIdentity } from "./identity";
import { createServerSupabaseClient } from "../supabase/server";

export async function getVerifiedAccessToken(): Promise<string | null> {
  const supabase = await createServerSupabaseClient();
  if ((await getAuthenticatedIdentity(supabase)) === null) {
    return null;
  }
  // The session is used only as the source of the raw bearer token after getClaims verified it.
  const { data, error } = await supabase.auth.getSession();
  if (error || data.session === null || data.session.access_token === "") {
    return null;
  }
  return data.session.access_token;
}
