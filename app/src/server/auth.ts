import { Pool } from "@neondatabase/serverless";
import { APIError, createAuthMiddleware } from "better-auth/api";
import { betterAuth } from "better-auth";
import { tanstackStartCookies } from "better-auth/tanstack-start";
import { PostgresDialect, type PostgresPool } from "kysely";
import { sendPasswordResetEmail } from "./resend";
import { verifyTurnstileToken } from "./turnstile";

type AuthDependencies = {
  // Injectable only by trusted server code, never request parameters.
  databaseUrl?: string;
  secret?: string;
  baseURL?: string;
  sendResetEmail?: typeof sendPasswordResetEmail;
  verifySignup?: typeof verifyTurnstileToken;
  loggerDisabled?: boolean;
};

export function createGroundtruthAuth(dependencies: AuthDependencies = {}) {
  const databaseUrl = dependencies.databaseUrl ?? process.env.DATABASE_URL;
  const secret = dependencies.secret ?? process.env.BETTER_AUTH_SECRET;
  const baseURL = dependencies.baseURL ?? process.env.BETTER_AUTH_URL;
  if (!databaseUrl) throw new Error("DATABASE_URL is required for authentication");
  if (!secret || secret.length < 32 || !baseURL)
    throw new Error("Authentication configuration is incomplete");
  const pool = new Pool({ connectionString: databaseUrl });
  const auth = betterAuth({
    appName: "Groundtruth",
    logger: dependencies.loggerDisabled ? { disabled: true } : undefined,
    baseURL,
    secret,
    database: {
      dialect: new PostgresDialect({ pool: pool as unknown as PostgresPool }),
      type: "postgres",
    },
    emailAndPassword: {
      enabled: true,
      minPasswordLength: 10,
      maxPasswordLength: 128,
      revokeSessionsOnPasswordReset: true,
      sendResetPassword: async ({ user, url }) => {
        await (dependencies.sendResetEmail ?? sendPasswordResetEmail)({
          to: user.email,
          name: user.name,
          resetUrl: url,
        });
      },
    },
    rateLimit: {
      enabled: true,
      storage: "database",
      window: 60,
      max: 60,
      customRules: {
        "/sign-up/email": { window: 60, max: 5 },
        "/sign-in/email": { window: 60, max: 10 },
        "/request-password-reset": { window: 300, max: 3 },
      },
    },
    advanced: {
      ipAddress: { ipAddressHeaders: ["cf-connecting-ip"] },
    },
    user: {
      deleteUser: { enabled: true },
    },
    hooks: {
      before: createAuthMiddleware(async (ctx) => {
        if (ctx.path !== "/sign-up/email") return;
        const token = ctx.headers?.get("x-turnstile-token") ?? "";
        const forwarded = ctx.headers?.get("cf-connecting-ip") ?? undefined;
        const hostname = new URL(baseURL).hostname;
        const result = await (dependencies.verifySignup ?? verifyTurnstileToken)(token, {
          expectedAction: "groundtruth_signup",
          expectedHostname: hostname === "localhost" ? undefined : hostname,
          remoteIp: forwarded,
        });
        if (!result.success) {
          throw new APIError("BAD_REQUEST", {
            message: "Human verification failed. Please refresh the challenge and try again.",
          });
        }
      }),
    },
    plugins: [tanstackStartCookies()],
  });

  return { auth, close: () => pool.end() };
}
