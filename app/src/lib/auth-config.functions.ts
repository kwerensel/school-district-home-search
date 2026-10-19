import { createServerFn } from "@tanstack/react-start";

export const getPublicAuthConfig = createServerFn({ method: "GET" }).handler(async () => ({
  turnstileSiteKey: process.env.TURNSTILE_SITE_KEY || "",
}));
