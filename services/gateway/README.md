## Policies

Rules live in the repo-root `policies/` folder, not in code:

- `defaults.yaml`: approval threshold, risk hold score, bank-change hold, fail mode, assistant limits
- `role_tools.yaml`: which tools each role may call (deny by default)

The gateway loads and validates both at start-up. A missing or unsafe file (for example
`creator_can_approve: true`, `fail_mode: allow`) stops the service instead of weakening the rules.
Set `POLICY_DIR` to point at a different folder (needed if the Docker image does not contain `policies/`).