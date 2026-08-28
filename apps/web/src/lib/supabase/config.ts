export interface SupabasePublicConfig {
  publishableKey: string;
  url: string;
}

function requiredEnvironmentValue(name: string, value: string | undefined): string {
  if (value === undefined || value.trim() === "" || value.startsWith("replace-with-")) {
    throw new Error(`${name} must be configured`);
  }
  return value;
}

export function getSupabasePublicConfig(): SupabasePublicConfig {
  return {
    url: requiredEnvironmentValue("NEXT_PUBLIC_SUPABASE_URL", process.env.NEXT_PUBLIC_SUPABASE_URL),
    publishableKey: requiredEnvironmentValue(
      "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
    ),
  };
}

export function getAppUrl(): string {
  const value = requiredEnvironmentValue("APP_URL", process.env.APP_URL);
  const url = new URL(value);
  if (url.pathname !== "/" || url.search !== "" || url.hash !== "") {
    throw new Error("APP_URL must be an origin without a path, query, or fragment");
  }
  return url.origin;
}
