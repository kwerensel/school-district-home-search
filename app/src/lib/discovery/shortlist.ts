import { z } from "zod";
import { serializeDiscoveryProfile } from "./profile";
import type { DiscoveryProfile } from "./profile";
import type { DistrictPurchasingPower } from "@/lib/finance/server-data";

export const DistrictPriceCapSchema = z.object({
  slug: z.string().min(1).max(120),
  name: z.string().min(1).max(160),
  maxPrice: z.number().min(0).max(1_000_000_000_000),
});
export const DistrictPriceCapsSchema = z.array(DistrictPriceCapSchema).max(10);
export type DistrictPriceCap = z.infer<typeof DistrictPriceCapSchema>;

export function parseDistrictPriceCaps(params: URLSearchParams): DistrictPriceCap[] {
  try {
    const parsed = DistrictPriceCapsSchema.safeParse(
      JSON.parse(params.get("districtCaps") ?? "null"),
    );
    if (!parsed.success) return [];
    return parsed.data.filter(
      (cap, index, caps) => caps.findIndex((item) => item.slug === cap.slug) === index,
    );
  } catch {
    return [];
  }
}

export function shortlistExplorerHref(
  profile: DiscoveryProfile,
  districts: DistrictPurchasingPower[],
) {
  const selected = (profile.shortlist ?? []).flatMap((slug) => {
    const district = districts.find((item) => item.districtSlug === slug);
    return district
      ? [{ slug, name: district.districtName, maxPrice: Math.floor(district.maxPurchasePrice) }]
      : [];
  });
  const params = serializeDiscoveryProfile(profile);
  params.set("districtCaps", JSON.stringify(selected));
  return `/explore?${params}`;
}
