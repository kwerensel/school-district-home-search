import { createServerFn } from "@tanstack/react-start";
import { setResponseHeader } from "@tanstack/react-start/server";
import { z } from "zod";
import { requireOperator } from "@/server/operator";
import { sql } from "@/server/db";

export const getOperatorOverview = createServerFn({ method: "GET" }).handler(async () => {
  setResponseHeader("Cache-Control", "private, no-store");
  await requireOperator();
  const jobs =
    await sql`SELECT id,kind,target,phase,created_at,updated_at FROM operator_jobs ORDER BY created_at DESC LIMIT 50`;
  const versions =
    await sql`SELECT version,dataset_kind,status,provider,provider_vintage,expected_record_count FROM listing_dataset_versions ORDER BY created_at DESC LIMIT 20`;
  const outreach =
    await sql`SELECT id,status,district_id FROM district_outreach_queue ORDER BY id DESC LIMIT 50`;
  return { jobs, versions, outreach, providerCallsEnabled: false, outreachEnabled: false };
});

const JobInputSchema = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("listing_refresh"),
    region: z.enum(["pa-mainline", "hudson-valley"]),
  }),
  z.object({
    kind: z.literal("region_expansion"),
    slug: z
      .string()
      .regex(/^[a-z0-9][a-z0-9-]*$/)
      .max(80),
    name: z.string().trim().min(1).max(160),
    counties: z
      .array(z.string().regex(/^\d{5}$/))
      .min(1)
      .max(20),
  }),
]);
export const createOperatorDraft = createServerFn({ method: "POST" })
  .validator(JobInputSchema)
  .handler(async ({ data }) => {
    setResponseHeader("Cache-Control", "private, no-store");
    const userId = await requireOperator();
    const manifest =
      data.kind === "region_expansion"
        ? {
            slug: data.slug,
            name: data.name,
            counties: [...new Set(data.counties)].sort(),
            state_fips: [...new Set(data.counties.map((county) => county.slice(0, 2)))].sort(),
            layers: [],
            anchors: [],
            status: "draft_official_county_codes_require_review",
          }
        : {
            region: data.region,
            provider: null,
            estimated_records: null,
            estimated_credits: null,
            blocked_reason:
              "Provider, terms, credit budget and versioning approval required. Frozen baseline unchanged.",
          };
    const rows = await sql`
    INSERT INTO operator_jobs (kind,target,requested_by,input_manifest)
    VALUES (${data.kind},${data.kind === "region_expansion" ? data.slug : data.region},${userId},${JSON.stringify(manifest)}::jsonb)
    RETURNING id,kind,target,phase
  `;
    return { job: rows[0], manifest };
  });
