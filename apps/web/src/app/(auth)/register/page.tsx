import { authErrorMessage } from "@/lib/auth/messages";

import { register } from "../actions";
import { AuthForm } from "../auth-form";

interface RegisterPageProps {
  searchParams: Promise<{ error?: string }>;
}

export default async function RegisterPage({ searchParams }: RegisterPageProps) {
  const { error } = await searchParams;
  return (
    <AuthForm
      action={register}
      alternateHref="/login"
      alternateLabel="Sign in instead"
      error={authErrorMessage(error)}
      submitLabel="Create account"
      title="Create your account"
    />
  );
}
