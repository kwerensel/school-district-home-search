# Groundtruth deployment

The app is configured for a Cloudflare Worker through Nitro's
`cloudflare-module` preset.

## Required secrets

- `DATABASE_URL`: pooled Neon connection string with PostGIS enabled.
- `ANTHROPIC_API_KEY`: server-only key for guarded archetype labels and
  tradeoff narratives. The signed-out deterministic journey still works when
  this is unavailable.

## Public production configuration

- `MAPBOX_PUBLIC_TOKEN`: public Mapbox token restricted to the production
  origin where possible.
- `ANTHROPIC_MODEL`: optional model override; the checked-in example records
  the tested default.

Phase 12 optional accounts will also require `BETTER_AUTH_SECRET`,
`BETTER_AUTH_URL`, `RESEND_API_KEY`, `TURNSTILE_SITE_KEY`, and
`TURNSTILE_SECRET_KEY`. Do not configure those in production until the Phase
12 routes and database migration are committed. Accounts must remain a save
layer and never gate signed-out Discovery or Explorer use.

Never commit real values. `app/.env.example` contains placeholders only.

## Preflight

From `app/`:

```bash
npm ci
npm test
npm run lint
npm run build
```

From `pipeline/`, with the production `DATABASE_URL` loaded:

```bash
./.venv/bin/pytest -q
./.venv/bin/pytest -k golden -q
```

## Configure and deploy

1. Authenticate Wrangler with the intended Cloudflare account. The read-only
   preflight should report the intended account before any deploy.
2. Run the complete local preflight above.
3. Create the Worker with the first deploy, or verify that an existing Worker
   has exactly the intended name and account.
4. Add server-only values with `wrangler secret put`; never put secret values
   in `wrangler.jsonc`, build logs, or shell history. Public build-time values
   must be restricted to the production origin where the provider supports it.
5. Deploy the verified build and record the resulting `workers.dev` URL. A
   custom domain may be attached afterward without changing application code.
6. Open `/explore` and `/discover/results` on the deployed URL.
7. Verify the signed-out journey: adjust a Discovery budget, select a district,
   open Explorer, and confirm the district focus and max-price filter persist.
8. Open a listing detail and confirm promoted park distance, tree, flood, and
   neighborhood metrics render.
9. After Phase 12 lands, verify signup Turnstile validation, email/password
   login, password reset delivery, logout, and saved profiles separately. Then
   repeat the signed-out smoke journey to prove accounts are still optional.

As of the latest handoff, Wrangler is authenticated to the intended personal
account but `groundtruth-home-search` does not yet exist there. This makes the
next deployment a first release, not an update. Deployment itself remains an
external-state action: it requires the production secret set and an explicit
release checkpoint. A custom domain is optional for the first smoke release.
