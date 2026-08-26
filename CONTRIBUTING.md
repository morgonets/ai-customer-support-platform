# Contributing

Thank you for helping improve the AI Customer Support Platform.

## Workflow

1. Start from an up-to-date `main` branch and create a focused feature branch.
2. Read `AGENTS.md` and the documentation relevant to the change.
3. Keep implementation, tests, and documentation in the same pull request.
4. Run `pnpm check` and `pnpm build` before requesting review.
5. Complete the pull request template, including validation evidence and operational impact.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat(web): add conversation list
fix(api): enforce tenant scope on message lookup
docs: explain vector index selection
chore(ci): cache Python dependencies
```

Keep commits cohesive and reviewable. Do not create filler commits, mix unrelated changes, or commit code that does not pass its relevant checks.

## Quality expectations

- Preserve strict TypeScript and mypy settings.
- Add tests for business rules, regressions, and tenant boundaries.
- Do not weaken checks to make a change pass.
- Never commit secrets or real customer data.
- Update architecture, API, database, deployment, and environment documentation when those contracts change.

## Pull requests

Explain why the change exists, not only what files changed. Highlight migrations, new configuration, security implications, compatibility concerns, and follow-up work. Screenshots are expected for meaningful UI changes.
