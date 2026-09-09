# Staging Governance Dashboard

The dashboard uses a same-origin, `HttpOnly`, secure session cookie. It never
returns or renders an OpenAI API key. Authentication is backed by the ALOS
PostgreSQL identity records; local token issuance remains unavailable in staging.

## First director bootstrap

After the new image and migration have been deployed on the VPS, run the command
below from the repository checkout on the VPS. It prompts directly in the VPS
terminal and does not accept a password through command-line arguments or an
environment variable.

```bash
docker compose --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml run --rm --no-deps platform \
  python -m alos.identity.bootstrap_director
```

The command creates or refreshes the configured director account, gives it the
`DIRECTOR` role, and creates the `ALOS_GOVERNANCE` workspace if needed. Its
initial daily budget comes from the existing staging environment values. It
creates an append-only `DIRECTOR_CREDENTIAL_BOOTSTRAPPED` audit event, but never
records the password or its hash in the audit payload.

## Verification

1. Open the staging URL and sign in using the password entered at the VPS prompt.
2. Confirm that the dashboard shows the workspace, daily request/token/USD caps,
   remaining quota, server-side model routing, and the latest safe run metadata.
3. Change a test limit as a Director and confirm that `COST_LIMIT_UPDATED` appears
   in the selected workspace audit trail.
4. Sign out and ensure that the dashboard redirects to `/login`.

## Operational boundary

The dashboard exposes provider and model names because they are runtime policy.
It does not expose provider credentials, raw model gateway headers, agent input,
or agent output bodies. Only `DIRECTOR` and `IT_LEAD` can update a workspace
budget; the API independently enforces this rule.
