import { z } from "zod";
import { PlaceSearchSchema, searchVerifiedPlaces, loadVerifiedPlace } from "./places";
import type { PlaceAccess } from "./places";
import { createServerFn } from "@tanstack/react-start";
import { setResponseHeader } from "@tanstack/react-start/server";
import {
  ConversationInputSchema,
  DiscoveryContextSchema,
  runConversation,
  executeDiscoveryTool,
} from "./conversation";
import type { ConversationResult, ConversationProfile, Evidence } from "./conversation";

async function getDistricts(profile: ConversationProfile) {
  const { getDistrictPurchasingPower } = await import("@/lib/finance/purchasing-power.functions");
  return getDistrictPurchasingPower({
    data: {
      monthlyBudget: profile.monthlyBudget,
      downPaymentAmount: profile.downPayment,
      creditBand: profile.creditBand,
      environmentWeights: profile.weights,
      ...(profile.regionGroup === "all" ? {} : { regionGroup: profile.regionGroup }),
    },
  });
}

async function executePlaceQuery(text: string, params: unknown[]) {
  const { sql } = await import("@/server/db");
  return sql.query(text, params);
}
const places: PlaceAccess = {
  search: (query, regionGroup) =>
    searchVerifiedPlaces(PlaceSearchSchema.parse({ query, regionGroup }), executePlaceQuery),
  context: (slug, regionGroup) => loadVerifiedPlace(slug, regionGroup, executePlaceQuery),
};
export const searchDiscoveryPlaces = createServerFn({ method: "POST" })
  .validator(PlaceSearchSchema)
  .handler(async ({ data }) => {
    setResponseHeader("Cache-Control", "no-store");
    try {
      return { status: "ok" as const, places: await searchVerifiedPlaces(data, executePlaceQuery) };
    } catch {
      return {
        status: "error" as const,
        message: "Verified place search could not load. Please try again.",
      };
    }
  });

type Reply =
  | { status: "ok"; result: ConversationResult }
  | { status: "unavailable" | "error"; message: string };

export const getConversationAvailability = createServerFn({ method: "GET" }).handler(() => {
  setResponseHeader("Cache-Control", "no-store");
  return { configured: Boolean(process.env.ANTHROPIC_API_KEY), researchEnabled: false as const };
});

export const converseWithDiscovery = createServerFn({ method: "POST" })
  .validator(ConversationInputSchema)
  .handler(async ({ data }): Promise<Reply> => {
    setResponseHeader("Cache-Control", "no-store");
    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey)
      return {
        status: "unavailable",
        message:
          "Conversation is not configured yet. You can still compare verified data and run scenarios below.",
      };
    try {
      const result = await runConversation(data, {
        apiKey,
        model: process.env.ANTHROPIC_MODEL,
        getDistricts,
        places,
      });
      return { status: "ok", result };
    } catch {
      // Never log conversation, financial inputs, provider bodies, or credentials.
      return {
        status: "error",
        message:
          "The assistant could not complete a grounded response. Your search has not changed. Please try again.",
      };
    } finally {
      setResponseHeader("Cache-Control", "no-store");
    }
  });

const AnalysisRequestSchema = DiscoveryContextSchema.extend({
  tool: z.enum([
    "compare_places",
    "compare_regions",
    "compare_housing_costs",
    "opportunity_cost",
    "rental_feasibility",
  ]),
}).strict();

export const runDiscoveryAnalysis = createServerFn({ method: "POST" })
  .validator(AnalysisRequestSchema)
  .handler(
    async ({
      data,
    }): Promise<{ status: "ok"; evidence: Evidence[] } | { status: "error"; message: string }> => {
      try {
        const analysis = await executeDiscoveryTool(data.tool, {}, data, getDistricts, places);
        if (!analysis.evidence.length)
          return {
            status: "error",
            message: "Complete the assumptions for this scenario before running it.",
          };
        return { status: "ok", evidence: analysis.evidence };
      } catch {
        return {
          status: "error",
          message:
            "Comparison could not load. Check your selected districts and scenario inputs, then try again.",
        };
      } finally {
        setResponseHeader("Cache-Control", "no-store");
      }
    },
  );
