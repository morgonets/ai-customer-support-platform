"use server";

import { redirect } from "next/navigation";

import { parseCredentials, parseEmail, parseNewPassword } from "@/lib/auth/credentials";
import { getAppUrl } from "@/lib/supabase/config";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export async function login(formData: FormData): Promise<never> {
  const credentials = parseCredentials(formData);
  if (credentials === null) {
    redirect("/login?error=invalid_input");
  }
  const supabase = await createServerSupabaseClient();
  const { error } = await supabase.auth.signInWithPassword(credentials);
  if (error) {
    redirect("/login?error=invalid_credentials");
  }
  redirect("/app");
}

export async function register(formData: FormData): Promise<never> {
  const credentials = parseCredentials(formData);
  const password = parseNewPassword(formData);
  if (credentials === null || password === null) {
    redirect("/register?error=invalid_input");
  }
  const supabase = await createServerSupabaseClient();
  const { error } = await supabase.auth.signUp({
    email: credentials.email,
    password,
    options: { emailRedirectTo: `${getAppUrl()}/auth/confirm` },
  });
  if (error) {
    redirect("/register?error=registration_failed");
  }
  redirect("/check-email");
}

export async function requestPasswordReset(formData: FormData): Promise<never> {
  const email = parseEmail(formData);
  if (email !== null) {
    const supabase = await createServerSupabaseClient();
    await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${getAppUrl()}/auth/confirm?next=/reset-password`,
    });
  }
  redirect("/forgot-password?sent=true");
}

export async function updatePassword(formData: FormData): Promise<never> {
  const password = parseNewPassword(formData);
  if (password === null) {
    redirect("/reset-password?error=invalid_input");
  }
  const supabase = await createServerSupabaseClient();
  const { error } = await supabase.auth.updateUser({ password });
  if (error) {
    redirect("/reset-password?error=password_update_failed");
  }
  redirect("/app");
}

export async function logout(): Promise<never> {
  const supabase = await createServerSupabaseClient();
  await supabase.auth.signOut();
  redirect("/login");
}
