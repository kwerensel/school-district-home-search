import type { DistrictPurchasingPower, PurchasingPowerQuery } from "./server-data";

export function addMatchScores(
  districts: DistrictPurchasingPower[],
  weights: PurchasingPowerQuery["environmentWeights"],
) {
  const normalizedWeights = {
    affordability: weights?.affordability ?? 5,
    green: weights?.green ?? 2,
    walkability: weights?.walkability ?? 2,
    lowerRisk: weights?.lowerRisk ?? 1,
    lowerFlood: weights?.lowerFlood ?? 1,
    darkSkies: weights?.darkSkies ?? 1,
    parkAccess: weights?.parkAccess ?? 1,
  } satisfies Required<NonNullable<PurchasingPowerQuery["environmentWeights"]>>;

  const scoreInputs = {
    affordability: districtScores(
      districts,
      (district) => district.affordabilityRatio ?? district.maxPurchasePrice,
      "higher",
    ),
    green: averagedScores([
      districtScores(districts, (district) => district.environmentMetrics.canopyHeightM, "higher"),
      districtScores(districts, (district) => district.environmentMetrics.treeCanopyPct, "higher"),
    ]),
    walkability: districtScores(
      districts,
      (district) => district.environmentMetrics.walkabilityIndex,
      "higher",
    ),
    lowerRisk: districtScores(
      districts,
      (district) => district.environmentMetrics.riskIndex,
      "lower",
    ),
    lowerFlood: districtScores(
      districts,
      (district) => district.environmentMetrics.floodSfha,
      "lower",
    ),
    darkSkies: districtScores(
      districts,
      (district) => district.environmentMetrics.lightPollutionRadiance,
      "lower",
    ),
    parkAccess: districtScores(
      districts,
      (district) => district.environmentMetrics.parkAccess,
      "higher",
    ),
  };

  return districts.map((district) => {
    let weightedTotal = 0;
    let weightTotal = 0;
    for (const key of Object.keys(normalizedWeights) as Array<keyof typeof normalizedWeights>) {
      const weight = normalizedWeights[key];
      const score = scoreInputs[key].get(district.districtSlug);
      if (score === undefined || weight <= 0) continue;
      weightedTotal += score * weight;
      weightTotal += weight;
    }
    return {
      ...district,
      matchComponents: {
        affordability: scoreInputs.affordability.get(district.districtSlug) ?? null,
        green: scoreInputs.green.get(district.districtSlug) ?? null,
        walkability: scoreInputs.walkability.get(district.districtSlug) ?? null,
        lowerRisk: scoreInputs.lowerRisk.get(district.districtSlug) ?? null,
        lowerFlood: scoreInputs.lowerFlood.get(district.districtSlug) ?? null,
        darkSkies: scoreInputs.darkSkies.get(district.districtSlug) ?? null,
        parkAccess: scoreInputs.parkAccess.get(district.districtSlug) ?? null,
      },
      matchScore: weightTotal > 0 ? weightedTotal / weightTotal : 0,
    };
  });
}

function districtScores(
  districts: DistrictPurchasingPower[],
  getValue: (district: DistrictPurchasingPower) => number | null,
  direction: "higher" | "lower",
) {
  const values = districts
    .map((district) => getValue(district))
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const scores = new Map<string, number>();
  for (const district of districts) {
    const value = getValue(district);
    if (value === null || !Number.isFinite(value)) continue;
    const rank = max === min ? 0.5 : (value - min) / (max - min);
    scores.set(district.districtSlug, (direction === "higher" ? rank : 1 - rank) * 100);
  }
  return scores;
}

function averagedScores(scoreMaps: Array<Map<string, number>>) {
  const scores = new Map<string, number>();
  const slugs = new Set(scoreMaps.flatMap((scoreMap) => [...scoreMap.keys()]));
  for (const slug of slugs) {
    const values = scoreMaps
      .map((scoreMap) => scoreMap.get(slug))
      .filter((value): value is number => value !== undefined);
    if (values.length)
      scores.set(slug, values.reduce((sum, value) => sum + value, 0) / values.length);
  }
  return scores;
}
