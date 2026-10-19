import { describe, it } from "vitest";

// Deliberately skipped in the ordinary suite. Run only after the feature gate is
// closed and the user-authorized account acceptance pass begins (see docs).
const enabled = process.env.GROUNDTRUTH_ACCOUNT_ACCEPTANCE === "1";

describe.runIf(enabled)("opt-in disposable account acceptance", () => {
  it("checks account, save, reopen, favorite, reset, session revocation and deletion cascades", async () => {
    // Dynamic imports prevent database/auth initialization in the normal suite.
    const { createGroundtruthAuth } = await import("./auth");
    const { neon } = await import("@neondatabase/serverless");
    const { createSavedStore } = await import("@/lib/saved/store");
    const { DEFAULT_DISCOVERY_PROFILE, serializeDiscoveryProfile, parseDiscoveryProfile } =
      await import("@/lib/discovery/profile");
    const databaseUrl =
      process.env.GROUNDTRUTH_ACCOUNT_ACCEPTANCE_DATABASE_URL ?? process.env.DATABASE_URL;
    if (!databaseUrl) throw new Error("Account acceptance requires a configured database");
    const sql = neon(databaseUrl);
    const baseURL = "http://localhost:5173";
    const email = `groundtruth-acceptance-${crypto.randomUUID()}@example.invalid`;
    const password = crypto.randomUUID() + crypto.randomUUID();
    const replacementPassword = crypto.randomUUID() + crypto.randomUUID();
    const challenge = crypto.randomUUID();
    const cookies = new Map<string, string>();
    let resetUrl: string | undefined;
    let resetDeliveries = 0;
    let userId: string | undefined;
    let currentPassword = password;
    let stage = "initialization";
    const { auth, close } = createGroundtruthAuth({
      databaseUrl,
      baseURL,
      secret: crypto.randomUUID() + crypto.randomUUID(),
      loggerDisabled: true,
      verifySignup: async (token) => ({ success: token === challenge }),
      sendResetEmail: async (message) => {
        if (message.to !== email) throw new Error("Unexpected test recipient");
        resetUrl = message.resetUrl;
        resetDeliveries += 1;
      },
    });
    function check(condition: unknown) {
      if (!condition) throw new Error("Acceptance assertion failed");
    }
    async function request(
      path: string,
      body?: unknown,
      extraHeaders: Record<string, string> = {},
    ) {
      const response = await auth.handler(
        new Request(`${baseURL}/api/auth${path}`, {
          method: body === undefined ? "GET" : "POST",
          headers: {
            Origin: baseURL,
            "Content-Type": "application/json",
            Cookie: [...cookies].map(([key, value]) => `${key}=${value}`).join("; "),
            ...extraHeaders,
          },
          ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        }),
      );
      for (const value of response.headers.getSetCookie()) {
        const first = value.split(";", 1)[0];
        const separator = first.indexOf("=");
        const name = first.slice(0, separator);
        const content = first.slice(separator + 1);
        if (content) cookies.set(name, content);
        else cookies.delete(name);
      }
      return response;
    }
    async function session() {
      const response = await request("/get-session");
      check(response.ok);
      return (await response.json()) as { user?: { id?: string } } | null;
    }
    async function signIn() {
      const response = await request("/sign-in/email", { email, password: currentPassword });
      check(response.ok);
      const signed = await session();
      check(signed?.user?.id === userId);
    }
    try {
      stage = "migrations and frozen listing fixture";
      const listings = await sql`SELECT id FROM listings ORDER BY id LIMIT 1`;
      check(listings.length === 1);
      const listingId = Number(listings[0].id);

      stage = "signup rejects a missing challenge";
      const rejected = await request("/sign-up/email", {
        email,
        password,
        name: "Disposable acceptance fixture",
      });
      check(!rejected.ok);
      check((await sql`SELECT id FROM "user" WHERE email=${email}`).length === 0);

      stage = "signup and verified session";
      const signup = await request(
        "/sign-up/email",
        { email, password, name: "Disposable acceptance fixture" },
        { "x-turnstile-token": challenge },
      );
      check(signup.ok);
      const created = await sql`SELECT id FROM "user" WHERE email=${email}`;
      userId = typeof created[0]?.id === "string" ? created[0].id : undefined;
      check(userId && (await session())?.user?.id === userId);
      const store = createSavedStore(async (query, params) => sql.query(query, params), userId!);
      const profile = {
        ...DEFAULT_DISCOVERY_PROFILE,
        wizardStep: "results" as const,
        grossMonthlyIncome: 18000,
        monthlyDebt: 500,
        shortlist: ["disposable-fixture"],
        commuteAnchors: [
          {
            label: "Public Center City",
            lat: 39.9526,
            lng: -75.1652,
            maxMinutes: 45,
            mode: "driving-car" as const,
          },
        ],
      };

      stage = "save and favorite";
      const saved = await store.saveProfile({ name: "Disposable acceptance fixture", profile });
      check(saved?.id);
      check((await store.toggleFavorite({ listingId })).favorite);
      const favorites = await store.listFavorites();
      check(
        favorites.length === 1 &&
          favorites[0].listing_id !== undefined &&
          typeof favorites[0].school_district === "string",
      );
      check(!(await store.toggleFavorite({ listingId })).favorite);
      check((await store.listFavorites()).length === 0);
      check((await store.toggleFavorite({ listingId })).favorite);

      stage = "signout and signin";
      check((await request("/sign-out", {})).ok);
      check(!(await session())?.user);
      await signIn();

      stage = "reopen saved profile";
      const restored = await store.listProfiles();
      check(restored.length === 1);
      const serialized = serializeDiscoveryProfile(restored[0].profile as typeof profile);
      check(
        serializeDiscoveryProfile(parseDiscoveryProfile(serialized)).toString() ===
          serializeDiscoveryProfile(profile).toString(),
      );

      stage = "password reset mail capture";
      const oldCookies = new Map(cookies);
      check(
        (
          await request("/request-password-reset", {
            email,
            redirectTo: `${baseURL}/reset-password`,
          })
        ).ok,
      );
      check(resetDeliveries === 1 && resetUrl);
      const delivered = new URL(resetUrl!);
      const token = delivered.pathname.split("/").at(-1);
      check(token && token !== "reset-password");
      check((await request("/reset-password", { token, newPassword: replacementPassword })).ok);
      currentPassword = replacementPassword;
      check(!(await request("/reset-password", { token, newPassword: replacementPassword })).ok);
      cookies.clear();
      for (const [key, value] of oldCookies) cookies.set(key, value);
      check(!(await session())?.user);
      cookies.clear();
      check(!(await request("/sign-in/email", { email, password })).ok);
      await signIn();

      stage = "delete account through authenticated API";
      check((await request("/delete-user", { password: currentPassword })).ok);
      check(!(await session())?.user);
      const counts = await sql`SELECT
        (SELECT count(*)::int FROM "user" WHERE id=${userId!}) AS users,
        (SELECT count(*)::int FROM "session" WHERE "userId"=${userId!}) AS sessions,
        (SELECT count(*)::int FROM "account" WHERE "userId"=${userId!}) AS accounts,
        (SELECT count(*)::int FROM saved_profiles WHERE user_id=${userId!}) AS profiles,
        (SELECT count(*)::int FROM favorites WHERE user_id=${userId!}) AS favorites`;
      check(Object.values(counts[0]).every((value) => Number(value) === 0));
      userId = undefined;
    } catch {
      // Never expose ephemeral passwords, reset URLs, cookies, or profile values
      // through assertion diagnostics, provider errors, or a failing test report.
      throw new Error(`Account acceptance failed during: ${stage}`);
    } finally {
      if (userId) {
        try {
          await signIn();
          check((await request("/delete-user", { password: currentPassword })).ok);
        } catch {
          // Do not bypass the account API with direct deletion. The disposable
          // record can be located by this non-secret ID for reviewed cleanup.
          console.warn("Disposable acceptance cleanup required", { userId });
        }
      }
      cookies.clear();
      resetUrl = undefined;
      await close();
    }
  }, 120_000);
});
