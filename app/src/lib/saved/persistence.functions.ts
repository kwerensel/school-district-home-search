import { createServerFn } from "@tanstack/react-start";
import { getRequestHeaders } from "@tanstack/react-start/server";
import { z } from "zod";
import { DiscoveryProfileSchema } from "@/lib/discovery/profile";
import { createGroundtruthAuth } from "@/server/auth";
import { sql } from "@/server/db";

const SaveProfileSchema = z.object({
  name: z.string().trim().min(1).max(120),
  profile: DiscoveryProfileSchema,
});
const ProfileIdSchema = z.object({ id: z.number().int().positive() });
const FavoriteSchema = z.object({ listingId: z.number().int().positive() });

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

export const saveProfile = createServerFn({ method: "POST" })
  .validator(SaveProfileSchema)
  .handler(async ({ data }) => {
    const userId = await authenticatedUserId();
    const rows = await sql`
      INSERT INTO saved_profiles (user_id, name, profile)
      VALUES (${userId}, ${data.name}, ${JSON.stringify(data.profile)}::jsonb)
      RETURNING id, name, profile, created_at, updated_at
    `;
    return rows[0];
  });

export const listProfiles = createServerFn({ method: "GET" }).handler(async () => {
  const userId = await authenticatedUserId();
  return sql`
    SELECT id, name, profile, created_at, updated_at
    FROM saved_profiles
    WHERE user_id = ${userId}
    ORDER BY updated_at DESC, id DESC
  `;
});

export const deleteProfile = createServerFn({ method: "POST" })
  .validator(ProfileIdSchema)
  .handler(async ({ data }) => {
    const userId = await authenticatedUserId();
    await sql`DELETE FROM saved_profiles WHERE id = ${data.id} AND user_id = ${userId}`;
    return { deleted: true };
  });

export const toggleFavorite = createServerFn({ method: "POST" })
  .validator(FavoriteSchema)
  .handler(async ({ data }) => {
    const userId = await authenticatedUserId();
    const removed = await sql`
      DELETE FROM favorites
      WHERE user_id = ${userId} AND listing_id = ${data.listingId}
      RETURNING listing_id
    `;
    if (removed.length) return { favorite: false };
    await sql`
      INSERT INTO favorites (user_id, listing_id)
      VALUES (${userId}, ${data.listingId})
      ON CONFLICT (user_id, listing_id) DO NOTHING
    `;
    return { favorite: true };
  });

export const listFavorites = createServerFn({ method: "GET" }).handler(async () => {
  const userId = await authenticatedUserId();
  return sql`
    SELECT
      f.listing_id,
      f.created_at,
      l.address,
      l.city,
      l.price,
      l.beds,
      l.baths,
      l.school_district
    FROM favorites f
    JOIN listings l ON l.id = f.listing_id
    WHERE f.user_id = ${userId}
    ORDER BY f.created_at DESC, f.listing_id DESC
  `;
});
