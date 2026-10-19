import type { CreditBand } from "@/lib/finance/purchasing-power";
import { z } from "zod";

export type RegionFilter = "all" | "pa-mainline" | "hudson-valley";
export type WeightKey =
  | "affordability"
  | "green"
  | "walkability"
  | "lowerRisk"
  | "lowerFlood"
  | "darkSkies"
  | "parkAccess";

export const DEFAULT_WEIGHTS: Record<WeightKey, number> = {
  affordability: 5,
  green: 2,
  walkability: 2,
  lowerRisk: 1,
  lowerFlood: 1,
  darkSkies: 1,
  parkAccess: 1,
};

export const CommuteAnchorSchema = z.object({
  label: z.string().trim().min(1).max(160),
  lat: z.number().min(-90).max(90),
  lng: z.number().min(-180).max(180),
  maxMinutes: z.number().positive().max(240),
  mode: z.literal("driving-car"),
});
export type CommuteAnchor = z.infer<typeof CommuteAnchorSchema>;
export const ShortlistSchema = z.array(z.string().min(1).max(120)).max(10);
export const WizardStepSchema = z.enum(["region", "budget", "priorities", "results"]);
export type WizardStep = z.infer<typeof WizardStepSchema>;

export interface DiscoveryProfile {
  monthlyBudget: number;
  downPayment: number;
  creditBand: CreditBand;
  regionGroup: RegionFilter;
  weights: Record<WeightKey, number>;
  grossMonthlyIncome?: number;
  monthlyDebt?: number;
  wizardStep?: WizardStep;
  shortlist?: string[];
  commuteAnchors?: CommuteAnchor[];
}

export const DiscoveryProfileSchema = z.object({
  monthlyBudget: z.number().positive().max(1_000_000),
  downPayment: z.number().min(0).max(100_000_000),
  creditBand: z.enum(["excellent", "good", "fair"]),
  regionGroup: z.enum(["all", "pa-mainline", "hudson-valley"]),
  grossMonthlyIncome: z.number().positive().max(1_000_000).optional(),
  monthlyDebt: z.number().min(0).max(1_000_000).optional(),
  wizardStep: WizardStepSchema.optional(),
  shortlist: ShortlistSchema.optional(),
  commuteAnchors: z.array(CommuteAnchorSchema).max(2).optional(),
  weights: z.object({
    affordability: z.number().min(0).max(10),
    green: z.number().min(0).max(10),
    walkability: z.number().min(0).max(10),
    lowerRisk: z.number().min(0).max(10),
    lowerFlood: z.number().min(0).max(10),
    darkSkies: z.number().min(0).max(10),
    parkAccess: z.number().min(0).max(10),
  }),
});

export const DEFAULT_DISCOVERY_PROFILE: DiscoveryProfile = {
  monthlyBudget: 5500,
  downPayment: 150000,
  creditBand: "good",
  regionGroup: "all",
  weights: DEFAULT_WEIGHTS,
};

export const WEIGHT_KEYS = Object.keys(DEFAULT_WEIGHTS) as WeightKey[];

export function parseDollarAmount(value: string, fallback: number, allowZero = false) {
  const normalized = value.replace(/[$,\s]/g, "");
  if (!normalized) return fallback;
  const parsed = Number(normalized);
  const isValid = Number.isFinite(parsed) && (allowZero ? parsed >= 0 : parsed > 0);
  return isValid ? parsed : fallback;
}

export function parseDiscoveryProfile(params: URLSearchParams): DiscoveryProfile {
  const creditBand = parseCreditBand(params.get("creditBand"));
  const regionGroup = parseRegionFilter(params.get("regionGroup"));
  const weights = { ...DEFAULT_WEIGHTS };

  for (const key of WEIGHT_KEYS) {
    const value = parseBoundedNumber(params.get(key), DEFAULT_WEIGHTS[key], 0, 10);
    weights[key] = value;
  }

  return {
    monthlyBudget: parseDollarAmount(
      params.get("monthlyBudget") ?? "",
      DEFAULT_DISCOVERY_PROFILE.monthlyBudget,
    ),
    downPayment: parseDollarAmount(
      params.get("downPayment") ?? "",
      DEFAULT_DISCOVERY_PROFILE.downPayment,
      true,
    ),
    creditBand,
    regionGroup,
    weights,
    ...optionalProfileFields(params),
  };
}

export function serializeDiscoveryProfile(profile: DiscoveryProfile): URLSearchParams {
  const params = new URLSearchParams();
  params.set("monthlyBudget", String(profile.monthlyBudget));
  params.set("downPayment", String(Math.round(profile.downPayment)));
  params.set("creditBand", profile.creditBand);
  if (profile.regionGroup !== "all") params.set("regionGroup", profile.regionGroup);

  for (const key of WEIGHT_KEYS) {
    if (profile.weights[key] !== DEFAULT_WEIGHTS[key]) {
      params.set(key, String(profile.weights[key]));
    }
  }

  if (profile.grossMonthlyIncome !== undefined)
    params.set("grossMonthlyIncome", String(profile.grossMonthlyIncome));
  if (profile.monthlyDebt !== undefined) params.set("monthlyDebt", String(profile.monthlyDebt));
  if (profile.wizardStep) params.set("step", profile.wizardStep);
  if (profile.shortlist?.length) params.set("shortlist", JSON.stringify(profile.shortlist));
  if (profile.commuteAnchors?.length)
    params.set("commuteAnchors", JSON.stringify(profile.commuteAnchors));
  return params;
}

function optionalProfileFields(params: URLSearchParams): Partial<DiscoveryProfile> {
  const result: Partial<DiscoveryProfile> = {};
  const income = params.get("grossMonthlyIncome");
  const debt = params.get("monthlyDebt");
  if (income?.trim()) {
    const parsed = parseBoundedNumber(income, NaN, 0.01, 1_000_000);
    if (Number.isFinite(parsed)) result.grossMonthlyIncome = parsed;
  }
  if (debt?.trim()) {
    const parsed = parseBoundedNumber(debt, NaN, 0, 1_000_000);
    if (Number.isFinite(parsed)) result.monthlyDebt = parsed;
  }
  const step = WizardStepSchema.safeParse(params.get("step"));
  if (step.success) result.wizardStep = step.data;
  try {
    const shortlist = ShortlistSchema.safeParse(JSON.parse(params.get("shortlist") ?? "null"));
    if (shortlist.success && shortlist.data.length) result.shortlist = [...new Set(shortlist.data)];
  } catch {
    /* Ignore malformed optional URL state. */
  }
  try {
    const anchors = z
      .array(CommuteAnchorSchema)
      .max(2)
      .safeParse(JSON.parse(params.get("commuteAnchors") ?? "null"));
    if (anchors.success && anchors.data.length) result.commuteAnchors = anchors.data;
  } catch {
    /* Ignore malformed optional URL state. */
  }
  return result;
}

function parseCreditBand(value: string | null): CreditBand {
  return value === "excellent" || value === "fair" ? value : "good";
}

function parseRegionFilter(value: string | null): RegionFilter {
  return value === "pa-mainline" || value === "hudson-valley" ? value : "all";
}

function parseBoundedNumber(value: string | null, fallback: number, min: number, max: number) {
  if (value === null || value.trim() === "") return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= min && parsed <= max ? parsed : fallback;
}
