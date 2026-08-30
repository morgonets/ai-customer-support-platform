const organizationMessages = {
  create_failed: "The organization could not be created. Try again.",
  invalid_name: "Enter an organization name between 1 and 100 characters.",
} as const;

export function organizationErrorMessage(code: string | undefined): string | null {
  return code !== undefined && code in organizationMessages
    ? organizationMessages[code as keyof typeof organizationMessages]
    : null;
}
