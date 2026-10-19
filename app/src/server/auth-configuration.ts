type AuthEnvironment = {
  DATABASE_URL?: string;
  BETTER_AUTH_SECRET?: string;
  BETTER_AUTH_URL?: string;
};

// Presence-only readiness: never return or log secret/configuration values.
export function hasAuthConfiguration(environment: AuthEnvironment = process.env) {
  return Boolean(
    environment.DATABASE_URL &&
    environment.BETTER_AUTH_URL &&
    environment.BETTER_AUTH_SECRET &&
    environment.BETTER_AUTH_SECRET.length >= 32,
  );
}
