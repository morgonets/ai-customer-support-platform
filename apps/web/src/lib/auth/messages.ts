const authMessages = {
  confirmation_failed: "The confirmation link is invalid or expired.",
  invalid_credentials: "The email or password is incorrect.",
  invalid_input: "Check the form fields and try again.",
  password_update_failed: "The password could not be updated. Request a new recovery link.",
  registration_failed: "Registration could not be completed. Try again shortly.",
} as const;

export function authErrorMessage(code: string | undefined): string | null {
  return code !== undefined && code in authMessages
    ? authMessages[code as keyof typeof authMessages]
    : null;
}
