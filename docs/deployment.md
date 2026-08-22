# Groundtruth deployment

The app is configured for a Cloudflare Worker through Nitro's
`cloudflare-module` preset.

## Required secrets

- `DATABASE_URL`: pooled Neon connection string with PostGIS enabled.
- `MAPBOX_PUBLIC_TOKEN`: public Mapbox token restricted to the production
  domain where possible.

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

1. Authenticate Wrangler with the intended Cloudflare account.
2. Add `DATABASE_URL` and `MAPBOX_PUBLIC_TOKEN` as Worker secrets; do not put
   them in `wrangler.jsonc`.
3. From `app/`, run `npm run deploy`.
4. Open `/explore` and `/discover/results` on the deployed URL.
5. Verify the signed-out journey: adjust a Discovery budget, select a district,
   open Explorer, and confirm the district focus and max-price filter persist.
6. Open a listing detail and confirm promoted park distance, tree, flood, and
   neighborhood metrics render.

Deployment itself remains an external-state action: it requires the Cloudflare
account, production secrets, and desired domain to be configured.
