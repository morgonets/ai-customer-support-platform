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
        "src/app/app/create-organization-form.tsx",
        "src/app/app/[organizationId]/knowledge/knowledge-components.tsx",
        "src/app/app/organization-switcher.tsx",
        "src/lib/api/client.ts",
        "src/lib/api/config.ts",
        "src/lib/api/knowledge.ts",
        "src/lib/api/organizations.ts",
        "src/lib/auth/credentials.ts",
        "src/lib/auth/identity.ts",
        "src/lib/auth/messages.ts",
        "src/lib/knowledge/forms.ts",
        "src/lib/knowledge/messages.ts",
        "src/lib/organizations/active.ts",
        "src/lib/organizations/forms.ts",
        "src/lib/organizations/messages.ts",
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
