import type { CreditBand } from "@/lib/finance/purchasing-power";

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

export interface DiscoveryProfile {
  monthlyBudget: number;
  downPayment: number;
  creditBand: CreditBand;
  regionGroup: RegionFilter;
  weights: Record<WeightKey, number>;
}

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

  return params;
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
