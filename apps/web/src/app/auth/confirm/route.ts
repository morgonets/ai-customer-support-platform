import type { EmailOtpType } from "@supabase/supabase-js";
import { type NextRequest, NextResponse } from "next/server";

import { createServerSupabaseClient } from "@/lib/supabase/server";

const emailOtpTypes = new Set<EmailOtpType>(["email_change", "recovery", "signup"]);

export async function GET(request: NextRequest): Promise<NextResponse> {
  const tokenHash = request.nextUrl.searchParams.get("token_hash");
  const type = request.nextUrl.searchParams.get("type");
  const requestedNext = request.nextUrl.searchParams.get("next");
  const next = requestedNext === "/reset-password" ? requestedNext : "/app";

  if (tokenHash !== null && type !== null && emailOtpTypes.has(type as EmailOtpType)) {
    const supabase = await createServerSupabaseClient();
    const { error } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type: type as EmailOtpType,
    });
    if (!error) {
      return NextResponse.redirect(new URL(next, request.url));
    }
  }
  return NextResponse.redirect(new URL("/login?error=confirmation_failed", request.url));
}
