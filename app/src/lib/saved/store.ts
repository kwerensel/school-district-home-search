import { z } from "zod";
import { DiscoveryProfileSchema } from "@/lib/discovery/profile";

export const SaveProfileSchema = z.object({
  name: z.string().trim().min(1).max(120),
  profile: DiscoveryProfileSchema,
});
export const ProfileIdSchema = z.object({ id: z.number().int().positive() });
export const FavoriteSchema = z.object({ listingId: z.number().int().positive() });
export type SavedProfileRow = {
  id: number;
  name: string;
  profile: z.infer<typeof DiscoveryProfileSchema>;
  created_at: string;
  updated_at: string;
};
export type FavoriteRow = {
  listing_id: number;
  created_at: string;
  address: string;
  city: string;
  price: number;
  beds: number;
  baths: number;
  school_district: string;
};
function profileRow(row: Record<string, unknown>): SavedProfileRow {
  return {
    id: Number(row.id),
    name: String(row.name),
    profile: DiscoveryProfileSchema.parse(row.profile),
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
}
export type SavedQuery = (query: string, params?: unknown[]) => Promise<Record<string, unknown>[]>;

// Ownership comes from a verified server session. Inputs never accept a user ID.
export function createSavedStore(execute: SavedQuery, verifiedUserId: string) {
  if (!verifiedUserId) throw new Error("AUTH_REQUIRED");
  return {
    async saveProfile(input: z.infer<typeof SaveProfileSchema>) {
      const data = SaveProfileSchema.parse(input);
      const rows = await execute(
        `INSERT INTO saved_profiles (user_id, name, profile)
        VALUES ($1, $2, $3::jsonb) RETURNING id, name, profile, created_at, updated_at`,
        [verifiedUserId, data.name, JSON.stringify(data.profile)],
      );
      if (!rows[0]) throw new Error("Saved profile was not returned");
      return profileRow(rows[0]);
    },
    async listProfiles() {
      const rows = await execute(
        `SELECT id, name, profile, created_at, updated_at FROM saved_profiles
        WHERE user_id = $1 ORDER BY updated_at DESC, id DESC`,
        [verifiedUserId],
      );
      return rows.map(profileRow);
    },
    async deleteProfile(input: z.infer<typeof ProfileIdSchema>) {
      const { id } = ProfileIdSchema.parse(input);
      await execute("DELETE FROM saved_profiles WHERE id = $1 AND user_id = $2", [
        id,
        verifiedUserId,
      ]);
      return { deleted: true };
    },
    async toggleFavorite(input: z.infer<typeof FavoriteSchema>) {
      const { listingId } = FavoriteSchema.parse(input);
      const removed = await execute(
        "DELETE FROM favorites WHERE user_id = $1 AND listing_id = $2 RETURNING listing_id",
        [verifiedUserId, listingId],
      );
      if (removed.length) return { favorite: false };
      await execute(
        "INSERT INTO favorites (user_id, listing_id) VALUES ($1, $2) ON CONFLICT (user_id, listing_id) DO NOTHING",
        [verifiedUserId, listingId],
      );
      return { favorite: true };
    },
    async listFavorites(): Promise<FavoriteRow[]> {
      const rows = await execute(
        `SELECT f.listing_id, f.created_at, l.address, l.city, l.price, l.beds, l.baths,
          d.name_display AS school_district
        FROM favorites f JOIN listings l ON l.id = f.listing_id
        JOIN school_districts d ON d.id = l.district_id
        WHERE f.user_id = $1 ORDER BY f.created_at DESC, f.listing_id DESC`,
        [verifiedUserId],
      );
      return rows.map((row) => ({
        listing_id: Number(row.listing_id),
        created_at: String(row.created_at),
        address: String(row.address),
        city: String(row.city),
        price: Number(row.price),
        beds: Number(row.beds),
        baths: Number(row.baths),
        school_district: String(row.school_district),
      }));
    },
  };
}
