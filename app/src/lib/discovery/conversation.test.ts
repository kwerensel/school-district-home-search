import { describe, expect, it, vi } from "vitest";
import {
  runConversation,
  ConversationInputSchema,
  executeDiscoveryTool,
  DiscoveryContextSchema,
} from "./conversation";
import { DEFAULT_DISCOVERY_PROFILE } from "./profile";
import { fetchDistrictPurchasingPower } from "@/lib/finance/server-data";

const input = () => ({
  messages: [{ role: "user" as const, content: "I care more about trees than walkability" }],
  profile: structuredClone(DEFAULT_DISCOVERY_PROFILE),
});
const finish = {
  name: "finish",
  input: {
    interpretation: "I can explore a leafier search while keeping your baseline separate.",
    question: "How important is walking to daily errands?",
  },
};
function provider(calls: Array<{ name: string; input: unknown }>) {
  return vi.fn(
    async (_url: string | URL | Request, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          stop_reason: "tool_use",
          content: [{ type: "tool_use", id: `call-${calls.length}`, ...calls.shift() }],
        }),
        { headers: { "content-type": "application/json" } },
      ),
  );
}
async function districts() {
  return fetchDistrictPurchasingPower(
    { monthlyBudget: 5500, downPaymentAmount: 150000, baseAnnualRate: 0.06 },
    async () => [
      {
        district_region_id: 1,
        district_slug: "leafy",
        district_name: "Leafy Example",
        region_group: "pa-mainline",
        effective_tax_rate: 0.02,
        canopy_height_m: 12,
        tree_canopy_pct: 55,
        median_home_value: 500000,
        walkability_index: 10,
        risk_index: null,
        flood_sfha: null,
        light_pollution_radiance: null,
        park_access: 0.4,
        transit_access: null,
        commute_minutes: null,
        aqi_annual_mean: null,
        noise_mean_dba: null,
        noise_pct_over_55: null,
        noise_siren_density: null,
        noise_nightlife_density: null,
        noise_industrial_land_pct: null,
        noise_freight_rail_density: null,
        metric_provenance: [
          {
            metricKey: "tree_canopy_pct",
            value: 55,
            source: "Approved canopy source",
            vintage: "2025",
            units: "%",
            nativeResolution: "1 m",
          },
          {
            metricKey: "tree_canopy_pct",
            value: 40,
            source: "Earlier canopy source",
            vintage: "2020",
            units: "%",
            nativeResolution: "1 m",
          },
        ],
        archetype_label: null,
        archetype_description: null,
      },
    ],
  );
}

describe("conversational Discovery", () => {
  it("previews preferences through trusted data without mutating the baseline", async () => {
    const request = input();
    const getDistricts = vi.fn(districts);
    const fetcher = provider([
      { name: "preview_preferences", input: { weights: { green: 9, walkability: 1 } } },
      finish,
    ]);
    const result = await runConversation(request, { apiKey: "test", fetcher, getDistricts });
    expect(request.profile.weights.green).toBe(DEFAULT_DISCOVERY_PROFILE.weights.green);
    expect(result.proposal?.weights.green).toBe(9);
    expect(getDistricts).toHaveBeenCalledWith(
      expect.objectContaining({ weights: expect.objectContaining({ green: 9 }) }),
    );
    expect(result.evidence[0].title).toContain("Leafy Example");
    expect(result.evidence[0].details).toContain("55.0%");
    expect(result.research).toBe("not-performed");
    const secondRequest = JSON.parse(String(fetcher.mock.calls[1][1]?.body));
    expect(secondRequest.messages.at(-1).content[0].type).toBe("tool_result");
    expect(secondRequest.model).toBe("claude-sonnet-4-6");
  });
  it("uses the applied profile as the next turn baseline while preserving history", async () => {
    const first = await runConversation(input(), {
      apiKey: "test",
      getDistricts: districts,
      fetcher: provider([
        { name: "preview_preferences", input: { weights: { green: 9 } } },
        finish,
      ]),
    });
    const applied = first.proposal!;
    const secondFetcher = provider([
      { name: "preview_preferences", input: { weights: { walkability: 1 } } },
      finish,
    ]);
    const result = await runConversation(
      {
        profile: applied,
        messages: [
          ...input().messages,
          { role: "assistant", content: first.interpretation },
          { role: "user", content: "Keep that change, but make walkability less important too" },
        ],
      },
      { apiKey: "test", getDistricts: districts, fetcher: secondFetcher },
    );
    expect(result.baseline.weights.green).toBe(9);
    expect(result.proposal?.weights.green).toBe(9);
    expect(result.proposal?.weights.walkability).toBe(1);
    expect(applied.weights.walkability).toBe(DEFAULT_DISCOVERY_PROFILE.weights.walkability);
    expect(JSON.parse(String(secondFetcher.mock.calls[0][1]?.body)).messages[2].content).toContain(
      "Keep that change",
    );
  });
  it("runs housing cash-flow comparisons from user inputs and trusted tax data", async () => {
    const result = await runConversation(
      { ...input(), housing: { purchasePrice: 500000, additionalMonthlyCosts: 250 } },
      {
        apiKey: "test",
        getDistricts: districts,
        fetcher: provider([{ name: "compare_housing_costs", input: {} }, finish]),
      },
    );
    expect(result.evidence[0].kind).toBe("calculation");
    expect(result.evidence[0].details).toContain("taxes: $833.33");
    expect(result.evidence[0].details).toContain("Includes taxes once");
    expect(result.evidence[0].details).toContain("$500000");
  });
  it("leaves rental permission unknown and never claims research", async () => {
    const getDistricts = vi.fn(districts);
    const result = await runConversation(input(), {
      apiKey: "test",
      fetcher: provider([{ name: "rental_feasibility", input: {} }, finish]),
      getDistricts,
    });
    expect(result.evidence[0].kind).toBe("unknown");
    expect(result.evidence[0].details).toContain("No outside research");
    expect(getDistricts).not.toHaveBeenCalled();
  });
  it("does not let model-supplied financial arguments replace user assumptions", async () => {
    const result = await runConversation(
      {
        ...input(),
        opportunity: { monthlyContribution: 500, upfrontCapital: 0, years: 10, annualReturn: 0 },
      },
      {
        apiKey: "test",
        getDistricts: districts,
        fetcher: provider([{ name: "opportunity_cost", input: { annualReturn: 0.2 } }, finish]),
      },
    );
    expect(result.evidence).toHaveLength(0);
  });
  it("calculates only from supplied financial assumptions", async () => {
    const result = await runConversation(
      {
        ...input(),
        opportunity: { monthlyContribution: 500, upfrontCapital: 0, years: 10, annualReturn: 0 },
      },
      {
        apiKey: "test",
        getDistricts: districts,
        fetcher: provider([{ name: "opportunity_cost", input: {} }, finish]),
      },
    );
    expect(result.evidence[0].details).toContain("$60000.00");
    expect(result.evidence[0].kind).toBe("calculation");
  });
  it("asks for missing financial inputs without producing a forecast", async () => {
    const result = await runConversation(input(), {
      apiKey: "test",
      getDistricts: districts,
      fetcher: provider([{ name: "opportunity_cost", input: {} }, finish]),
    });
    expect(result.evidence).toHaveLength(0);
  });
  it("rejects invented numerical claims and overlong or invalid requests", async () => {
    await expect(
      runConversation(input(), {
        apiKey: "test",
        getDistricts: districts,
        fetcher: provider([
          { name: "finish", input: { interpretation: "You will earn 999 dollars", question: "" } },
        ]),
      }),
    ).rejects.toThrow("unverified numbers");
    expect(
      ConversationInputSchema.safeParse({
        ...input(),
        profile: {
          ...DEFAULT_DISCOVERY_PROFILE,
          weights: { ...DEFAULT_DISCOVERY_PROFILE.weights, green: 11 },
        },
      }).success,
    ).toBe(false);
    expect(
      ConversationInputSchema.safeParse({
        ...input(),
        messages: [{ role: "assistant", content: "hi" }],
      }).success,
    ).toBe(false);
  });
  it("caps tool loops and hides provider error bodies", async () => {
    await expect(
      runConversation(input(), {
        apiKey: "test",
        getDistricts: districts,
        fetcher: provider(
          Array.from({ length: 5 }, () => ({ name: "rental_feasibility", input: {} })),
        ),
      }),
    ).rejects.toThrow("analysis limit");
    await expect(
      runConversation(input(), {
        apiKey: "test",
        getDistricts: districts,
        fetcher: vi.fn(async () => new Response("sensitive provider details", { status: 500 })),
      }),
    ).rejects.toThrow("provider is unavailable");
  });
});

describe("key-free Discovery tools", () => {
  it("attaches only provenance matching the displayed metric value", async () => {
    const result = await executeDiscoveryTool(
      "compare_regions",
      {},
      DiscoveryContextSchema.parse({ profile: input().profile }),
      districts,
    );
    expect(result.evidence[0].provenance).toHaveLength(1);
    expect(result.evidence[0].provenance?.[0].vintage).toBe("2025");
    expect(result.evidence[0].provenance?.[0].source).toBe("Approved canopy source");
  });
  it("rejects selected districts outside the active profile rather than substituting a ranking", async () => {
    await expect(
      executeDiscoveryTool(
        "compare_regions",
        {},
        DiscoveryContextSchema.parse({
          profile: input().profile,
          comparisonSlugs: ["not-in-current-region"],
        }),
        districts,
      ),
    ).rejects.toThrow("outside");
  });
  it("compares exactly the selected districts and models investing their cost difference", async () => {
    const getDistricts = async () => {
      const result = await districts();
      return {
        ...result,
        districts: [
          result.districts[0],
          {
            ...result.districts[0],
            districtSlug: "higher-tax",
            districtName: "Higher Tax Example",
            effectiveTaxRate: 0.03,
          },
        ],
      };
    };
    const result = await executeDiscoveryTool(
      "compare_housing_costs",
      {},
      DiscoveryContextSchema.parse({
        profile: input().profile,
        comparisonSlugs: ["leafy", "higher-tax"],
        housing: { purchasePrice: 500000, additionalMonthlyCosts: 0 },
        opportunity: {
          monthlyContribution: 9999,
          upfrontCapital: 100000,
          years: 10,
          annualReturn: 0,
        },
      }),
      getDistricts,
    );
    const delta = result.evidence.find((card) => card.id === "housing-opportunity");
    expect(delta?.details).toContain("$416.67");
    expect(delta?.details).toContain("$50000.00");
    expect(delta?.details).not.toContain("9999");
    expect(delta?.details).not.toContain("100000");
    expect(delta?.details).toContain("not a total-wealth comparison");
  });
  it("keeps the distinct housing and investment scenarios separate when no pair is selected", async () => {
    const result = await executeDiscoveryTool(
      "compare_housing_costs",
      {},
      DiscoveryContextSchema.parse({
        profile: input().profile,
        housing: { purchasePrice: 500000, additionalMonthlyCosts: 0 },
        opportunity: { monthlyContribution: 500, upfrontCapital: 0, years: 10, annualReturn: 0 },
      }),
      districts,
    );
    expect(result.evidence.some((card) => card.id === "housing-opportunity")).toBe(false);
  });
  it("validates model parameters independently of a key or provider request", async () => {
    await expect(
      executeDiscoveryTool(
        "opportunity_cost",
        { annualReturn: 1 },
        DiscoveryContextSchema.parse({ profile: input().profile }),
        districts,
      ),
    ).rejects.toThrow();
  });
});
