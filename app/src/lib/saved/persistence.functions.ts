import { createServerFn } from "@tanstack/react-start";
import { getRequestHeaders } from "@tanstack/react-start/server";
import { createGroundtruthAuth } from "@/server/auth";
import { sql } from "@/server/db";
import { createSavedStore, SaveProfileSchema, ProfileIdSchema, FavoriteSchema } from "./store";

async function authenticatedUserId() {
  const { auth, close } = createGroundtruthAuth();
  try {
    const session = await auth.api.getSession({ headers: getRequestHeaders() });
    if (!session) throw new Error("AUTH_REQUIRED");
    return session.user.id;
  } finally {
    await close();
  }
}

export function publicPersistenceError(error: unknown) {
  return error instanceof Error && error.message === "AUTH_REQUIRED"
    ? "Please sign in to save this."
    : "Groundtruth could not update your saved items. Please try again.";
}

async function authenticatedStore() {
  const userId = await authenticatedUserId();
  return createSavedStore(async (query, params) => sql.query(query, params), userId);
}

async function withAuthenticatedStore<T>(
  action: (store: ReturnType<typeof createSavedStore>) => Promise<T>,
): Promise<T> {
  try {
    return await action(await authenticatedStore());
  } catch (error) {
    throw new Error(publicPersistenceError(error));
  }
}

export const saveProfile = createServerFn({ method: "POST" })
  .validator(SaveProfileSchema)
  .handler(async ({ data }) => withAuthenticatedStore((store) => store.saveProfile(data)));

export const listProfiles = createServerFn({ method: "GET" }).handler(async () =>
  withAuthenticatedStore((store) => store.listProfiles()),
);

export const deleteProfile = createServerFn({ method: "POST" })
  .validator(ProfileIdSchema)
  .handler(async ({ data }) => withAuthenticatedStore((store) => store.deleteProfile(data)));

export const toggleFavorite = createServerFn({ method: "POST" })
  .validator(FavoriteSchema)
  .handler(async ({ data }) => withAuthenticatedStore((store) => store.toggleFavorite(data)));

export const listFavorites = createServerFn({ method: "GET" }).handler(async () =>
  withAuthenticatedStore((store) => store.listFavorites()),
);
