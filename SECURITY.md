# Security Policy

## Reporting a vulnerability

Do not disclose suspected vulnerabilities in a public issue. Use GitHub's private vulnerability reporting for this repository when available, or contact the repository owner privately through their GitHub profile.

Include a clear description, reproduction steps, affected versions or commits, and potential impact. Do not include real customer data or active credentials.

## Supported versions

The project is pre-release. Security fixes are applied to the latest `main` branch until versioned releases begin.

## Baseline practices

- Secrets belong in environment variables or a managed secret store, never in Git.
- Tenant isolation, authorization, uploads, prompt injection, and model output are treated as security boundaries.
- Dependencies and container images should be updated deliberately and validated in CI.
- Logs and analytics must avoid credentials, unnecessary personal data, and raw customer content.
- FastAPI authorization and PostgreSQL row-level security independently enforce organization access;
  organization memberships and roles are live database state rather than JWT claims.
