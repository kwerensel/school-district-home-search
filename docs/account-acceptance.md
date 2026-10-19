# Deferred account acceptance

The Phase 12 acceptance pass remains deferred until the preceding product,
GVI research, and private operator feature work is complete. This scaffold has
not been run against the database. Ordinary `npm test` skips the database test.
Production deployment remains outside the current goal.

## Prepared harness

`app/src/server/account-acceptance.integration.test.ts` exercises the installed
Better Auth handler and the same session-owned saved-data store used by the
server functions. It creates one uniquely named `@example.invalid` account
with an ephemeral secret, password, and challenge value, then checks:

- Rejection of signup without the injected challenge and successful signup
  with it.
- Session establishment, signout, signin, and reopening an extended saved
  Discovery profile through the canonical serializer.
- Favorite add/remove/add and the unified school-district display join.
- Reset email capture in memory, password replacement, one-use reset tokens,
  revocation of existing sessions, and rejection of the prior password.
- Authenticated account deletion and cascading removal of sessions, accounts,
  saved profiles, and favorites.

The test uses injected in-memory reset mail and a nonce-checking signup
verifier. It sends no email, submits no CAPTCHA, calls no geocoder or routing
provider, changes no listing data, and never prints credentials, reset tokens,
profile values, or cookies. These injectable dependencies are available only
through trusted server-code arguments; no HTTP request can select them.

Cleanup uses Better Auth's authenticated deletion API. If that fails, the
harness reports only the disposable user's identifier for reviewed cleanup.
It does not bypass the account API by deleting database rows directly.

## Run only when the feature gate has closed

Use a local terminal with the intended database configured. The explicit flag
permits disposable account writes to that database; this is not a read-only
check. The database must already have migrations 008 and 009 and the frozen
listing baseline. The harness does not apply migrations.

```sh
cd app
# Load the intended DATABASE_URL without printing it. Optionally provide a
# dedicated GROUNDTRUTH_ACCOUNT_ACCEPTANCE_DATABASE_URL instead.
GROUNDTRUTH_ACCOUNT_ACCEPTANCE=1 npm test -- src/server/account-acceptance.integration.test.ts
```

Vitest does not automatically import `.env.local` into `process.env` for this
test. Supply the database URL securely in the test process environment. A
failure reports the stage only, preserving the confidentiality of ephemeral
credentials and token-bearing URLs.

## Remaining production/account gate

The harness uses a local test origin and ephemeral signing secret. Passing it
would verify the account engine and persistence flows; it would not establish
production readiness. The production origin, a strong `BETTER_AUTH_SECRET`,
Turnstile site/secret keys with hostname/action checks, Resend sender/account,
and deployed cookie behavior still need their acceptance pass. Missing account
configuration remains fail-closed for protected actions. Optional signed-out
session queries return no session when account configuration is absent.

The later browser pass must verify signup, save/signin return navigation,
favorite reopening, reset delivery and links, and account deletion on the
intended deployment after those settings are configured.
