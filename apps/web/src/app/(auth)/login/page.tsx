import { authErrorMessage } from "@/lib/auth/messages";

import { login } from "../actions";
import { AuthForm } from "../auth-form";

interface LoginPageProps {
  searchParams: Promise<{ error?: string }>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const { error } = await searchParams;
  return (
    <AuthForm
      action={login}
      alternateHref="/register"
      alternateLabel="Create an account"
      error={authErrorMessage(error)}
      submitLabel="Sign in"
      title="Welcome back"
    />
  );
}
