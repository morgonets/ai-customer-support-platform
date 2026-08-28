export interface Credentials {
  email: string;
  password: string;
}

function formString(formData: FormData, name: string): string | null {
  const value = formData.get(name);
  return typeof value === "string" ? value : null;
}

export function parseCredentials(formData: FormData): Credentials | null {
  const email = formString(formData, "email")?.trim().toLowerCase();
  const password = formString(formData, "password");
  if (email === undefined || password === null || !email.includes("@") || password.length < 8) {
    return null;
  }
  return { email, password };
}

export function parseEmail(formData: FormData): string | null {
  const email = formString(formData, "email")?.trim().toLowerCase();
  return email !== undefined && email.includes("@") ? email : null;
}

export function parseNewPassword(formData: FormData): string | null {
  const password = formString(formData, "password");
  return password !== null &&
    /[A-Za-z]/.test(password) &&
    /\d/.test(password) &&
    password.length >= 8
    ? password
    : null;
}
