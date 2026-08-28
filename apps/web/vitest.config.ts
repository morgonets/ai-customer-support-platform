import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": new URL("./src", import.meta.url).pathname,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      include: [
        "src/app/page.tsx",
        "src/app/(auth)/auth-form.tsx",
        "src/lib/auth/credentials.ts",
        "src/lib/auth/identity.ts",
        "src/lib/auth/messages.ts",
        "src/lib/supabase/config.ts",
      ],
      reporter: ["text", "json-summary"],
      thresholds: {
        branches: 100,
        functions: 100,
        lines: 100,
        statements: 100,
      },
    },
  },
});
