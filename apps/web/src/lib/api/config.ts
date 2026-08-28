function requiredApiUrl(value: string | undefined): URL {
  if (value === undefined || value.trim() === "" || value.startsWith("replace-with-")) {
    throw new Error("API_INTERNAL_URL or NEXT_PUBLIC_API_URL must be configured");
  }
  const url = new URL(value);
  if (url.pathname !== "/" || url.search !== "" || url.hash !== "") {
    throw new Error("The API URL must be an origin without path state");
  }
  return url;
}

export function getApiBaseUrl(): string {
  const internalUrl = process.env.API_INTERNAL_URL;
  const configuredUrl =
    internalUrl !== undefined && internalUrl.trim() !== ""
      ? internalUrl
      : process.env.NEXT_PUBLIC_API_URL;
  return requiredApiUrl(configuredUrl).origin;
}
